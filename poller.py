"""Background worker for feed fetching, jitter calculation, and article ingestion."""

import asyncio
from datetime import datetime, timezone
import random
import re
import time
from typing import Any, List

import feedparser
import httpx

from config import (
    DEFAULT_LOGO,
    HTTP_HEADERS,
    POLL_INTERVAL,
    SOURCES,
    SourceConfig,
    classify_article,
)
import db
from extractor import async_scrape_and_clean_article


def extract_image(entry: Any, fallback_logo: str = DEFAULT_LOGO) -> str:
    """Extract lead article image from media tags, enclosures, <img>, or fallback logo."""
    url = (entry.get("media_content") or [{}])[0].get("url")
    if url:
        return url

    url = (entry.get("enclosures") or [{}])[0].get("href")
    if url:
        return url

    raw_html = entry.get("summary", "") or ""
    if "content" in entry:
        raw_html += "".join([c.get("value", "") for c in entry.content])

    img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', raw_html, re.IGNORECASE)
    if img_match:
        return img_match.group(1)

    return fallback_logo


def clean_summary(summary_html: str) -> str:
    """Strip HTML tags and normalize whitespace in article summary."""
    clean = re.sub(r"<[^>]+>", " ", summary_html or "")
    clean = re.sub(r"\s+", " ", clean)
    return clean.strip()


def parse_entry_date(entry: Any) -> str:
    """Extract and parse published date into a normalized ISO 8601 string."""
    t = entry.get("published_parsed") or entry.get("updated_parsed")
    return (datetime(*t[:6], tzinfo=timezone.utc) if t else datetime.now(timezone.utc)).isoformat()


def parse_feed(resp: httpx.Response):
    """Parse feed from HTTP response with XML control-character cleanup and unescaped entity repair."""
    content_type = resp.headers.get("content-type", "").lower()
    stripped = resp.text.lstrip()
    if ("text/html" in content_type and "xml" not in content_type) or stripped.startswith("<!DOCTYPE html") or stripped.startswith("<html"):
        raise ValueError(f"Endpoint returned HTML webpage instead of XML feed (content-type: {content_type})")

    parsed = feedparser.parse(resp.content)
    if getattr(parsed, "bozo", 0) and not parsed.entries:
        # Clean control characters and repair raw unescaped ampersands (e.g. 'L&T' -> 'L&amp;T')
        cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", resp.text)
        cleaned = re.sub(r"&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)", "&amp;", cleaned)
        parsed = feedparser.parse(cleaned.encode("utf-8", errors="ignore"))
    if getattr(parsed, "bozo", 0) and not parsed.entries:
        raise ValueError(str(getattr(parsed, "bozo_exception", "Malformed feed")))
    return parsed


class NewsPoller:
    """Core news feed poller and background ingestion worker."""

    def __init__(self, interval_seconds: int = POLL_INTERVAL, max_concurrency: int = 3):
        self.interval_seconds = interval_seconds
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.is_running = False

    async def poll_single_source(
        self,
        client: httpx.AsyncClient,
        source: SourceConfig,
    ) -> List[dict]:
        """Poll a single source with concurrency limiter and jitter."""
        async with self.semaphore:
            parsed_articles: List[dict] = []
            start_time = time.monotonic()

            # Add jitter between 1.0 and 3.0 seconds to avoid burst traffic
            await asyncio.sleep(random.uniform(1.0, 3.0))

            try:
                resp = await client.get(source.feed_url)
                resp.raise_for_status()
                feed = parse_feed(resp)

                for entry in feed.entries:
                    link = getattr(entry, "link", None)
                    title = getattr(entry, "title", None)
                    if not link or not title:
                        continue

                    link_clean = link.strip()
                    title_clean = title.strip()
                    summary_clean = clean_summary(getattr(entry, "summary", ""))
                    item_category = classify_article(title_clean, summary_clean, source.category)

                    item = {
                        "id": db.generate_article_id(link_clean),
                        "title": title_clean,
                        "summary": summary_clean,
                        "image_url": extract_image(entry, source.logo_url),
                        "source_url": link_clean,
                        "source": source.name,
                        "category": item_category,
                        "pub_date": parse_entry_date(entry),
                    }
                    parsed_articles.append(item)

                inserted = db.insert_articles(parsed_articles)
                duration_ms = int((time.monotonic() - start_time) * 1000)
                print(f"[INGEST] {source.name} ({source.category}): {len(parsed_articles)} fetched, {inserted} fresh in {duration_ms}ms.")

                db.record_poll_log(
                    source=source.name,
                    status="success",
                    articles_found=len(parsed_articles),
                    articles_new=inserted,
                    duration_ms=duration_ms,
                )

                for art in parsed_articles[:inserted]:
                    try:
                        ext = await async_scrape_and_clean_article(art["source_url"], selectors=source.selectors)
                        if ext.content:
                            db.update_article_extraction(
                                article_id=art["id"],
                                content=ext.content,
                                image_url=ext.image_url,
                            )
                    except Exception:
                        pass

            except Exception as e:
                duration_ms = int((time.monotonic() - start_time) * 1000)
                print(f"[POLL FAILED] {source.name}: {e}")
                db.record_poll_log(
                    source=source.name,
                    status="error",
                    articles_found=0,
                    articles_new=0,
                    duration_ms=duration_ms,
                    error_message=str(e),
                )

            return parsed_articles

    async def run_cycle(self) -> None:
        """Polls all registered publishers."""
        limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
        async with httpx.AsyncClient(
            headers=HTTP_HEADERS, timeout=12.0, limits=limits, follow_redirects=True
        ) as client:
            await asyncio.gather(*(self.poll_single_source(client, s) for s in SOURCES), return_exceptions=True)

    async def start(self) -> None:
        """Start the continuous polling worker loop."""
        self.is_running = True
        print(f"[WORKER] Polling daemon started. Interval: {self.interval_seconds}s")
        while self.is_running:
            await self.run_cycle()
            try:
                await asyncio.sleep(self.interval_seconds)
            except asyncio.CancelledError:
                break

    def stop(self) -> None:
        """Stop the background polling worker."""
        self.is_running = False


if __name__ == "__main__":
    db.init_db()
    try:
        asyncio.run(NewsPoller().start())
    except KeyboardInterrupt:
        pass
