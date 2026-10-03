"""Full-article text scraper and content cleaner with publisher-specific DOM selectors."""

from dataclasses import dataclass
import re
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup
import httpx

from config import DEFAULT_SELECTORS, HTTP_HEADERS, HTTP_TIMEOUT

# Common paywall, subscription, and comment widget boilerplate patterns
BOILERPLATE_RE = re.compile(
    r"(active subscription|subscribed with another email|unlock these with subscription|"
    r"institutional subscriber|community guidelines|comments have to be in english|"
    r"vuukle|migrated to a new commenting platform|terms & conditions\||"
    r"read also:|also read:|download.*app|all rights reserved)",
    re.IGNORECASE,
)

BOILERPLATE_SELECTORS = [
    ".paywall", ".paywall-content", ".subscription", ".sub-block", ".subscribe-banner",
    ".comments", "#comments", ".comment-box", ".vuukle", "#vuukle-comments", ".vuukle-powerbar",
    ".social-share", ".newsletter-signup", ".author-bio", ".related-articles",
    ".recommended-stories", ".also-read", ".tag-list", ".ad-container", ".advertisement",
]


@dataclass
class ExtractedArticle:
    """Structured result from article extraction."""
    url: str
    content: Optional[str] = None
    image_url: Optional[str] = None
    error: Optional[str] = None


def clean_html_text(text: str) -> str:
    """Clean redundant boilerplate, ads, and publisher credits from text."""
    text = re.sub(r"\s+", " ", text)
    text = re.sub(
        r"\b(Advertisement|Follow us|Share this|Subscribe|Newsletter)\b.*?[.!?]",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"(Written by|Updated:|Published:|Last Updated:).*?[.!?]", "", text)
    text = re.sub(r"\(\s*PTI\s*\)|\(\s*ANI\s*\)", "", text)
    return text.strip()


def generate_extractive_summary(text: str, max_sentences: int = 4) -> str:
    """Generate leading contextual summary from full article text."""
    if not text:
        return "Summary unavailable."
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return " ".join(sentences[:max_sentences])


def extract_lead_image(soup: BeautifulSoup, base_url: str) -> Optional[str]:
    """Find lead article image from OpenGraph, Twitter card, or DOM tags."""
    og_img = soup.find("meta", property="og:image") or soup.find("meta", attrs={"name": "twitter:image"})
    if og_img and og_img.get("content"):
        return urljoin(base_url, og_img["content"].strip())

    img = soup.find("img")
    if img and img.get("src"):
        src = img["src"].strip()
        if not src.startswith("data:"):
            return urljoin(base_url, src)

    return None


def parse_article_html(html: str, final_url: str, selectors: Optional[list[str]] = None) -> ExtractedArticle:
    """Pure parsing function: extract lead image and cleaned text from HTML."""
    soup = BeautifulSoup(html, "html.parser")
    lead_image = extract_lead_image(soup, final_url)

    for element in soup(["script", "style", "noscript", "iframe", "form", "nav", "header", "footer", "aside"]):
        element.decompose()

    for sel in BOILERPLATE_SELECTORS:
        for el in soup.select(sel):
            el.decompose()

    active_selectors = selectors or DEFAULT_SELECTORS
    target_container = (
        next((c for s in active_selectors if (c := soup.select_one(s))), None)
        or soup.find("article")
        or soup.find("main")
        or soup.body
    )

    if not target_container:
        return ExtractedArticle(url=final_url, error="No content container found")

    paragraphs = [
        t for p in target_container.find_all(["p", "h2", "h3"])
        if len(t := p.get_text(strip=True)) > 25 and not BOILERPLATE_RE.search(t)
    ]
    clean_text = clean_html_text(" ".join(paragraphs))

    return ExtractedArticle(
        url=final_url,
        content=clean_text or None,
        image_url=lead_image,
        error=None if clean_text else "Empty content extracted",
    )


async def async_scrape_and_clean_article(
    url: str,
    selectors: Optional[list[str]] = None,
    timeout: Optional[float] = None,
) -> ExtractedArticle:
    """Asynchronously fetch HTML and parse article content."""
    try:
        async with httpx.AsyncClient(timeout=timeout or HTTP_TIMEOUT, headers=HTTP_HEADERS, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return parse_article_html(resp.text, str(resp.url), selectors)
    except Exception as e:
        return ExtractedArticle(url=url, error=str(e))
