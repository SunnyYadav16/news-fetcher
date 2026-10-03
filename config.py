"""Configuration file containing news sources, categories, and branding assets."""

from dataclasses import dataclass
import os
import re
from typing import Dict, List, Optional
from urllib.parse import urlparse

# Standard HTTP headers for scraping and feed requests
HTTP_HEADERS: Dict[str, str] = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/rss+xml, application/xml, text/xml, */*;q=0.9",
    "Accept-Language": "en-US,en;q=0.9",
}


@dataclass
class SourceConfig:
    """Configuration for an individual news feed source."""
    id: str
    name: str
    category: str
    feed_url: str
    homepage_url: str
    logo_url: str
    selectors: List[str]
    tier: int = 1


POLL_INTERVAL: int = 300
HTTP_TIMEOUT: float = 15.0
API_PORT: int = int(os.getenv("API_PORT", "8000"))


def _derive_homepage(feed_url: str) -> str:
    parsed = urlparse(feed_url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _generate_slug(text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower())
    return cleaned.strip("-")


# Unified definition for all news sources (combines feeds, logos, homepages, and selectors)
_SOURCE_DEFS = [
    # Top News
    {
        "name": "The Hindu",
        "category": "top",
        "feed_url": "https://www.thehindu.com/news/national/feeder/default.rss",
        "logo_url": "https://www.thehindu.com/theme/images/th-online/logo.png",
        "selectors": [".article-body-content-container", ".article__content", ".article-text"],
        "tier": 1,
    },
    {
        "name": "Indian Express",
        "category": "top",
        "feed_url": "https://indianexpress.com/section/india/feed/",
        "logo_url": "https://indianexpress.com/wp-content/themes/indianexpress/images/indian-express-logo-n.svg",
        "selectors": [".story-details", ".m-story-content__body", "#story-body"],
        "tier": 1,
    },
    {
        "name": "Indian Express World",
        "category": "world",
        "feed_url": "https://indianexpress.com/section/world/feed/",
        "logo_url": "https://indianexpress.com/wp-content/themes/indianexpress/images/indian-express-logo-n.svg",
        "selectors": [".story-details", ".m-story-content__body", "#story-body"],
        "tier": 1,
    },
    {
        "name": "The Hindu World",
        "category": "world",
        "feed_url": "https://www.thehindu.com/news/international/feeder/default.rss",
        "logo_url": "https://www.thehindu.com/theme/images/th-online/logo.png",
        "selectors": [".article-body-content-container", ".article__content", ".article-text"],
        "tier": 1,
    },
    {
        "name": "Free Press Journal",
        "category": "top",
        "feed_url": "https://www.freepressjournal.in/stories.rss",
        "logo_url": "https://fea.assettype.com/freepressjournal/assets/logo-600x60.png",
        "selectors": [".story-element-text", ".story-content", ".content", "article"],
        "tier": 1,
    },
    {
        "name": "Hindustan Times",
        "category": "top",
        "feed_url": "https://www.hindustantimes.com/feeds/rss/india-news/rssfeed.xml",
        "logo_url": "https://www.hindustantimes.com/images/app-images/ht-logo.png",
        "selectors": [".detail", ".storyParagraph", ".storyDetails"],
        "tier": 1,
    },
    {
        "name": "Times of India",
        "category": "top",
        "feed_url": "https://timesofindia.indiatimes.com/rssfeedstopstories.cms",
        "logo_url": "https://static.toiimg.com/photo/msid-58124960/TOI-logo.jpg",
        "selectors": ["._s30J", ".main-content", ".article-content"],
        "tier": 1,
    },
    {
        "name": "NDTV",
        "category": "top",
        "feed_url": "https://feeds.feedburner.com/ndtvnews-india-news",
        "homepage_url": "https://www.ndtv.com",
        "logo_url": "https://drop.ndtv.com/homepage/ndtv_news_logo.png",
        "selectors": ["#ins_storybody", ".sp-cn", ".story__content"],
        "tier": 1,
    },
    # Business
    {
        "name": "Mint Business",
        "category": "business",
        "feed_url": "https://www.livemint.com/rss/markets",
        "logo_url": "https://images.livemint.com/img/static/livemint-logo.svg",
        "selectors": [".contentSec", ".mainArea", ".storyPage"],
        "tier": 2,
    },
    {
        "name": "Business Standard",
        "category": "business",
        "feed_url": "https://www.business-standard.com/rss/markets-106.rss",
        "logo_url": "https://bsmedia.business-standard.com/include/_mod/site/html5/images/business-standard-logo.png",
        "selectors": [".story-content", ".article-content"],
        "tier": 2,
    },
    {
        "name": "Economic Times",
        "category": "business",
        "feed_url": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
        "logo_url": "https://economictimes.indiatimes.com/photo/47529900.cms",
        "selectors": [".artText", ".normal", ".article-body"],
        "tier": 2,
    },
    {
        "name": "Business Today",
        "category": "business",
        "feed_url": "https://www.businesstoday.in/rss/latestnews.xml",
        "logo_url": "https://akm-img-a-in.tosshub.com/businesstoday/resource/img/logo.png",
        "selectors": [".story-with-main-sec", ".story-content", ".text-desc"],
        "tier": 2,
    },
    {
        "name": "NDTV Profit",
        "category": "business",
        "feed_url": "https://feeds.feedburner.com/ndtvprofit-latest",
        "homepage_url": "https://www.ndtvprofit.com",
        "logo_url": "https://drop.ndtv.com/homepage/ndtv_news_logo.png",
        "selectors": [".story__content", ".sp-cn"],
        "tier": 2,
    },
    {
        "name": "The Hindu BusinessLine",
        "category": "business",
        "feed_url": "https://www.thehindubusinessline.com/markets/feeder/default.rss",
        "logo_url": "https://www.thehindubusinessline.com/theme/images/bl-online/logo.png",
        "selectors": [".contentbody", "#ControlPara", ".article-main"],
        "tier": 2,
    },
    {
        "name": "Money Control",
        "category": "business",
        "feed_url": "https://www.moneycontrol.com/rss/latestnews.xml",
        "logo_url": "https://images.moneycontrol.com/static-mcnews/2020/04/moneycontrol-logo-620x435.jpg",
        "selectors": ["#content_wrapper", ".article_desc", ".content"],
        "tier": 2,
    },
    # Legal
    {
        "name": "ET LegalWorld",
        "category": "legal",
        "feed_url": "https://legal.economictimes.indiatimes.com/rss/recentstories",
        "logo_url": "https://economictimes.indiatimes.com/photo/47529900.cms",
        "selectors": [".artText", ".article-body", ".content"],
        "tier": 3,
    },
    {
        "name": "ET Legal Litigation",
        "category": "legal",
        "feed_url": "https://legal.economictimes.indiatimes.com/rss/litigation",
        "logo_url": "https://economictimes.indiatimes.com/photo/47529900.cms",
        "selectors": [".artText", ".article-body", ".content"],
        "tier": 3,
    },
    {
        "name": "Verdictum",
        "category": "legal",
        "feed_url": "https://www.verdictum.in/feed",
        "logo_url": "https://www.verdictum.in/assets/images/logo.png",
        "selectors": [".article-content", ".content-inner"],
        "tier": 3,
    },
    # Governance
    {
        "name": "PIB India",
        "category": "governance",
        "feed_url": "https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3",
        "logo_url": "https://pib.gov.in/WriteReadData/userfiles/image/pib_logo.png",
        "selectors": ["#form1 table", ".content-area", "#MainContent"],
        "tier": 3,
    },
    {
        "name": "Scroll.in",
        "category": "governance",
        "feed_url": "http://feeds.feedburner.com/ScrollinArticles.rss",
        "homepage_url": "https://scroll.in",
        "logo_url": "https://scroll.in/static/images/brand/scroll-logo-black.svg",
        "selectors": [".article-content", "#article-contents", ".story-detail"],
        "tier": 3,
    },
    # Technology
    {
        "name": "NDTV Gadgets",
        "category": "technology",
        "feed_url": "https://feeds.feedburner.com/gadgets360-latest",
        "homepage_url": "https://gadgets360.com",
        "logo_url": "https://drop.ndtv.com/homepage/ndtv_news_logo.png",
        "selectors": [".content_wrapper", ".story__content", ".fullstory"],
        "tier": 2,
    },
    {
        "name": "Indian Express Tech",
        "category": "technology",
        "feed_url": "https://indianexpress.com/section/technology/feed/",
        "homepage_url": "https://indianexpress.com/section/technology/",
        "logo_url": "https://indianexpress.com/wp-content/themes/indianexpress/images/indian-express-logo-n.svg",
        "selectors": [".story-details", ".m-story-content__body", "#story-body"],
        "tier": 2,
    },
    {
        "name": "Digit",
        "category": "technology",
        "feed_url": "https://www.digit.in/feed/",
        "logo_url": "https://www.digit.in/images/digit_logo.png",
        "selectors": [".article-text", ".body-content"],
        "tier": 2,
    },
    {
        "name": "India Today Tech",
        "category": "technology",
        "feed_url": "https://www.indiatoday.in/rss/1206578",
        "homepage_url": "https://www.indiatoday.in/technology",
        "logo_url": "https://akm-img-a-in.tosshub.com/indiatoday/images/misc/indiatoday-logo_170x85.png",
        "selectors": [".story-with-main-sec", ".description", ".it-article-content"],
        "tier": 2,
    },
    {
        "name": "FoneArena",
        "category": "technology",
        "feed_url": "https://www.fonearena.com/blog/feed/",
        "homepage_url": "https://www.fonearena.com",
        "logo_url": "https://www.fonearena.com/blog/wp-content/uploads/2017/04/fonearena-logo-300.png",
        "selectors": [".post-content", ".entry-content"],
        "tier": 2,
    },
]


def _build_source(d: dict) -> SourceConfig:
    feed_url = d["feed_url"]
    name = d["name"]
    return SourceConfig(
        id=_generate_slug(name),
        name=name,
        category=d["category"],
        feed_url=feed_url,
        homepage_url=d.get("homepage_url") or _derive_homepage(feed_url),
        logo_url=d["logo_url"],
        selectors=d["selectors"],
        tier=d.get("tier", 1),
    )


SOURCES: List[SourceConfig] = [_build_source(d) for d in _SOURCE_DEFS]
CATEGORIES: List[str] = [
    "top",
    "world",
    "business",
    "finance",
    "legal",
    "criminal",
    "civil",
    "governance",
    "technology",
]

DEFAULT_LOGO = "https://images.news18.com/static_news18/pix/ibnhome/news18/news18-logo-sharing.png"
DEFAULT_SELECTORS = [".article-content", ".story-content", ".post-content"]


def classify_article(title: str, summary: str, default_category: str) -> str:
    """Classify article into refined categories: criminal, civil, finance, world, or keep default."""
    text = f"{title} {summary}".lower()

    # World / International news
    if default_category in ("top", "world") and any(k in text for k in [
        "israel", "gaza", "palestine", "ukraine", "russia", "putin", "biden", "trump",
        "white house", "beijing", "china", "xi jinping", "taiwan", "united nations",
        "pentagon", "iran", "middle east", "pakistan", "bangladesh", "sri lanka",
        "london", "uk parliament", "foreign policy", "global economy", "syria", "yemen"
    ]):
        return "world"

    # Criminal legal news
    if default_category in ("legal", "criminal", "civil") and any(k in text for k in [
        "bail", "fir", "police", "arrest", "custody", "murder", "rape", "assault",
        "narcotics", "ndps", "cbi", "ed custody", "money laundering", "chargesheet",
        "accused", "remand", "jail", "prison", "convict", "criminal", "homicide",
        "penal code", "ipc", "bns", "uapa", "pmla", "extortion", "cybercrime"
    ]):
        return "criminal"

    # Civil / Commercial legal news
    if default_category in ("legal", "civil") and any(k in text for k in [
        "arbitration", "contract", "property", "trademark", "patent", "copyright",
        "defamation", "insolvency", "ibbi", "nclt", "nclat", "consumer forum",
        "damages", "injunction", "civil suit", "commercial dispute", "tenancy", "writ petition"
    ]):
        return "civil"

    # Finance news (sub-class of business)
    if default_category in ("business", "finance") and any(k in text for k in [
        "sensex", "nifty", "stock market", "shares", "equity", "bse", "nse", "ipo",
        "mutual fund", "rbi", "repo rate", "inflation", "sebi", "forex", "rupee",
        "quarterly profit", "dividend", "yield", "bullish", "bearish", "monetary policy"
    ]):
        return "finance"

    return default_category


def get_source(query: str) -> Optional[SourceConfig]:
    """Retrieve a single source configuration by ID or source name."""
    q = (query or "").strip().lower()
    return next((s for s in SOURCES if q in (s.id, s.name.lower())), None)
