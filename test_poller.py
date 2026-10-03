#!/usr/bin/env python3
"""
Standalone CLI test script to verify RSS/Atom feeds, deduplication, and extraction.

Usage examples:
    # Test all enabled sources (dry-run by default, no DB modification)
    python test_poller.py

    # Test a specific source with full-text article extraction
    python test_poller.py --source techcrunch --extract

    # Test direct full-article extraction on an arbitrary URL
    python test_poller.py --url "https://techcrunch.com/..."

    # List all configured sources
    python test_poller.py --list
"""

import argparse
import asyncio
import sys
import time
from typing import List, Optional

import httpx

from config import HTTP_HEADERS, HTTP_TIMEOUT, SOURCES, SourceConfig, get_source
import db
from extractor import async_scrape_and_clean_article
from poller import (
    NewsPoller,
    clean_summary,
    extract_image,
    parse_entry_date,
    parse_feed,
)

# Terminal styling helpers
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def poll_source_sync(source: SourceConfig) -> List[dict]:
    """Execute poll_single_source via a temporary async client for CLI testing."""
    async def _poll():
        async with httpx.AsyncClient(headers=HTTP_HEADERS, timeout=12.0, follow_redirects=True) as client:
            poller = NewsPoller()
            return await poller.poll_single_source(client, source)
    return asyncio.run(_poll())


def print_banner(text: str) -> None:
    print(f"\n{BOLD}{CYAN}{'=' * 70}{RESET}")
    print(f"{BOLD}{CYAN}  {text}{RESET}")
    print(f"{BOLD}{CYAN}{'=' * 70}{RESET}\n")


def list_sources() -> None:
    """Print all configured sources in a clean table."""
    print_banner("CONFIGURED NEWS SOURCES")
    print(f"{BOLD}{'ID':<20} {'Category':<14} {'Tier':<6} {'Name':<20} {'Feed URL'}{RESET}")
    print("-" * 80)
    for s in SOURCES:
        tier_str = f"T{s.tier}"
        print(f"{s.id:<20} {s.category:<14} {tier_str:<6} {s.name:<20} {s.feed_url}")
    print(f"\nTotal sources: {len(SOURCES)}\n")


def test_article_url(url: str) -> None:
    """Test full-text extraction directly on a specific article URL."""
    print_banner(f"TESTING ARTICLE EXTRACTION: {url}")
    print(f"Fetching and extracting: {CYAN}{url}{RESET} ...")

    start_time = time.monotonic()
    result = asyncio.run(async_scrape_and_clean_article(url))
    duration = time.monotonic() - start_time

    if result.content:
        print(f"\n[{GREEN}SUCCESS{RESET}] Extracted in {duration:.2f}s")
        print(f"  {BOLD}Image:{RESET} {result.image_url or 'N/A'}")
        print(f"  {BOLD}Content Length:{RESET} {len(result.content or '')} chars")
        print(f"  {BOLD}URL:{RESET} {result.url}")
        print(f"\n{BOLD}Content Preview (First 400 chars):{RESET}")
        print("-" * 60)
        snippet = (result.content[:400] + "...") if len(result.content or "") > 400 else result.content
        print(snippet)
        print("-" * 60)
    else:
        print(f"\n[{RED}FAILED{RESET}] Extraction error: {result.error} ({duration:.2f}s)")


def test_feed_source(
    source: SourceConfig,
    dry_run: bool = True,
    sample_limit: int = 3,
    test_extract: bool = False,
) -> bool:
    """
    Test fetching, parsing, deduplication check, and optional extraction for a source.
    """
    print(f"{BOLD}[SOURCE]{RESET} {source.name} ({source.id}) - Category: {source.category}")
    print(f"         Feed: {source.feed_url}")

    start_time = time.monotonic()
    parsed_feed, error = None, None
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT, headers=HTTP_HEADERS, follow_redirects=True) as client:
            resp = client.get(source.feed_url)
            resp.raise_for_status()
            parsed_feed = parse_feed(resp)
    except Exception as e:
        error = str(e)
    duration = time.monotonic() - start_time

    if error or not parsed_feed:
        print(f"  {RED}[ERROR]{RESET} Failed to fetch/parse feed: {error} ({duration:.2f}s)\n")
        return False

    entries = parsed_feed.entries or []
    feed_title = parsed_feed.feed.get("title", source.name)
    print(f"  {GREEN}[OK]{RESET} Feed responded in {duration:.2f}s | Title: '{feed_title}'")
    print(f"  Found {BOLD}{len(entries)}{RESET} entries in feed.")

    if not entries:
        print(f"  {YELLOW}[WARN]{RESET} Feed contains 0 entries.\n")
        return True

    # Inspect sample entries
    print(f"\n  {BOLD}Sample Entries (up to {sample_limit}):{RESET}")
    first_entry_url: Optional[str] = None

    for i, entry in enumerate(entries[:sample_limit], 1):
        raw_url = getattr(entry, "link", None)
        title = getattr(entry, "title", "No Title").strip()
        pub_date = parse_entry_date(entry)
        image = extract_image(entry, source.logo_url)
        summary = clean_summary(getattr(entry, "summary", "") or getattr(entry, "description", ""))

        if i == 1 and raw_url:
            first_entry_url = raw_url

        norm_url = db.normalize_url(raw_url) if raw_url else ""
        print(f"    {BOLD}{i}. {title}{RESET}")
        print(f"       Link: {raw_url}")
        print(f"       Normalized: {norm_url}")
        print(f"       Published: {pub_date}")
        if image:
            print(f"       Lead Image: {image}")
        if summary:
            short_summary = (summary[:120] + "...") if len(summary) > 120 else summary
            print(f"       Summary: {short_summary}")
        print()

    # If write mode requested (not dry-run), run the poll insertion
    if not dry_run:
        print(f"  {CYAN}Executing actual DB insertion (dry_run=False)...{RESET}")
        start_poll = time.monotonic()
        articles = poll_source_sync(source)
        poll_dur = int((time.monotonic() - start_poll) * 1000)
        print(
            f"  {GREEN}[DB Ingested]{RESET} Total Articles Processed: {len(articles)}, Time: {poll_dur}ms"
        )
    else:
        print(f"  {YELLOW}[Dry Run Mode]{RESET} Skipped database insertion.")

    # Optional extraction test on newest entry
    if test_extract and first_entry_url:
        print(f"\n  {CYAN}Testing article extraction on newest entry:{RESET}")
        ext_res = asyncio.run(async_scrape_and_clean_article(first_entry_url, selectors=source.selectors))
        if ext_res.content:
            print(f"  {GREEN}[Extraction OK]{RESET} Content Length: {len(ext_res.content or '')} chars")
            snippet = (ext_res.content[:200] + "...") if len(ext_res.content or "") > 200 else ext_res.content
            print(f"  Snippet: {snippet}")
        else:
            print(f"  {RED}[Extraction Failed]{RESET} Reason: {ext_res.error}")

    print("-" * 70 + "\n")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify and test news RSS feeds, deduplication, and extraction."
    )
    parser.add_argument(
        "-s", "--source",
        help="Test a specific source ID (e.g. 'the-hindu', 'indian-express', 'mint-business')",
    )
    parser.add_argument(
        "-l", "--list",
        action="store_true",
        help="List all configured news sources",
    )
    parser.add_argument(
        "-u", "--url",
        help="Test full-text extraction on a direct article URL",
    )
    parser.add_argument(
        "-e", "--extract",
        action="store_true",
        help="Test article text scraper on the newest article from each feed",
    )
    parser.add_argument(
        "--live-insert",
        action="store_true",
        help="Perform real database insertion during test run",
    )
    parser.add_argument(
        "-n", "--limit",
        type=int,
        default=3,
        help="Number of sample entries to display per feed (default: 3)",
    )

    args = parser.parse_args()

    # Always ensure DB tables exist before running checks
    db.init_db()

    if args.list:
        list_sources()
        return

    if args.url:
        test_article_url(args.url)
        return

    dry_run = not args.live_insert

    print_banner(f"FEED VERIFICATION TEST (Dry Run: {dry_run})")

    sources_to_test: List[SourceConfig] = []
    if args.source:
        src = get_source(args.source)
        if not src:
            print(f"{RED}Error: Source '{args.source}' not found.{RESET}")
            list_sources()
            sys.exit(1)
        sources_to_test = [src]
    else:
        sources_to_test = SOURCES

    passed = 0
    failed = 0

    for source in sources_to_test:
        success = test_feed_source(
            source=source,
            dry_run=dry_run,
            sample_limit=args.limit,
            test_extract=args.extract,
        )
        if success:
            passed += 1
        else:
            failed += 1

    print_banner("TEST SUMMARY")
    print(f"Total Feeds Tested: {len(sources_to_test)}")
    print(f"Passed: {GREEN}{passed}{RESET}")
    print(f"Failed: {RED}{failed}{RESET}\n")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
