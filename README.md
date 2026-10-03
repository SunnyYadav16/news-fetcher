# News Ingestion and Article Extraction Service

An automated pipeline for ingesting, categorizing, deduplicating, and scraping full articles from leading Indian and international news publishers.

The system continuously polls news feeds, normalizes publication timestamps and URLs, classifies articles into domain-specific categories, stores records in an optimized SQLite database with write-ahead logging, and provides on-demand full-text web scraping and a FastAPI service.

---

## Architecture Overview

The system consists of five distinct components:

1. Polling Engine (`poller.py`): An asynchronous background worker that queries feeds periodically, handles network rate limiting and jitter, sanitizes XML inputs, extracts preview metadata, and records execution audit logs.
2. Content Extractor (`extractor.py`): A targeted DOM scraper that retrieves full article bodies, strips paywall banners, removes comment widgets, extracts high-resolution lead images, and normalizes article text.
3. Database Layer (`db.py`): SQLite storage engine configured with Write-Ahead Logging (WAL) and busy timeout handlers to enable concurrent reads and writes without file locks. Handles URL tracking cleanup and deterministic 16-character SHA-256 hash generation for deduplication.
4. Feed and Source Configuration (`config.py`): Central repository defining 25 curated sources, CSS selector rules, logos, polling tiers, and automated rule-based article categorization.
5. REST API (`main.py`): FastAPI server exposing query interfaces, category filtering, search capabilities, database metrics, and extraction triggers.

---

## News Sources and Tracked Feeds

The system tracks 25 news providers grouped across major domains:

### General and National News
| Source Name | Category | Feed Endpoint |
| :--- | :--- | :--- |
| The Hindu | top | https://www.thehindu.com/news/national/feeder/default.rss |
| Indian Express | top | https://indianexpress.com/section/india/feed/ |
| Free Press Journal | top | https://www.freepressjournal.in/stories.rss |
| Hindustan Times | top | https://www.hindustantimes.com/feeds/rss/india-news/rssfeed.xml |
| Times of India | top | https://timesofindia.indiatimes.com/rssfeedstopstories.cms |
| NDTV News | top | https://feeds.feedburner.com/ndtvnews-india-news |

### World and International Affairs
| Source Name | Category | Feed Endpoint |
| :--- | :--- | :--- |
| Indian Express World | world | https://indianexpress.com/section/world/feed/ |
| The Hindu World | world | https://www.thehindu.com/news/international/feeder/default.rss |

### Business, Markets, and Finance
| Source Name | Category | Feed Endpoint |
| :--- | :--- | :--- |
| Mint Business | business | https://www.livemint.com/rss/markets |
| Business Standard | business | https://www.business-standard.com/rss/markets-106.rss |
| Economic Times | business | https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms |
| Business Today | business | https://www.businesstoday.in/rss/latestnews.xml |
| NDTV Profit | business | https://feeds.feedburner.com/ndtvprofit-latest |
| The Hindu BusinessLine | business | https://www.thehindubusinessline.com/markets/feeder/default.rss |
| Moneycontrol | business | https://www.moneycontrol.com/rss/latestnews.xml |

### Legal, Judiciary, and Law
| Source Name | Category | Feed Endpoint |
| :--- | :--- | :--- |
| ET LegalWorld | legal | https://legal.economictimes.indiatimes.com/rss/recentstories |
| ET Legal Litigation | legal | https://legal.economictimes.indiatimes.com/rss/litigation |
| Verdictum | legal | https://www.verdictum.in/feed |

### Public Policy and Governance
| Source Name | Category | Feed Endpoint |
| :--- | :--- | :--- |
| PIB India | governance | https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3 |
| Scroll.in | governance | http://feeds.feedburner.com/ScrollinArticles.rss |

### Technology and Gadgets
| Source Name | Category | Feed Endpoint |
| :--- | :--- | :--- |
| NDTV Gadgets 360 | technology | https://feeds.feedburner.com/gadgets360-latest |
| Indian Express Tech | technology | https://indianexpress.com/section/technology/feed/ |
| Digit | technology | https://www.digit.in/feed/ |
| India Today Tech | technology | https://www.indiatoday.in/rss/1206578 |
| FoneArena | technology | https://www.fonearena.com/blog/feed/ |

---

## Collected Data Fields

When an article entry is ingested from a feed, the poller extracts and stores the following fields:

1. `id`: Deterministic 16-character hexadecimal hash derived from the sanitized article URL.
2. `title`: Headline of the news story with HTML tags stripped.
3. `summary`: Text summary or description provided in the feed payload.
4. `source_url`: Normalized canonical URL with marketing query parameters (`utm_*`, `fbclid`, `gclid`, `ref`, etc.) removed.
5. `source`: Publisher identity (for example, "The Hindu" or "Business Standard").
6. `category`: Classified topical category assigned to the article.
7. `image_url`: Lead visual extracted by priority:
   - Media tags (`media:content`, `media:thumbnail`)
   - RSS enclosure attributes
   - Embedded `<img>` tags inside feed description HTML
   - Verified publisher logo fallback
8. `pub_date`: Normalized ISO 8601 UTC timestamp (`YYYY-MM-DDTHH:MM:SS+00:00`).
9. `created_at`: SQLite timestamp marking database ingestion.
10. `full_text`: Extracted article paragraphs (populated during full article scraping).

---

## Categorization Engine

Articles are initially tagged with their parent source category, then evaluated by the classifier in `config.py` against headline and summary text:

1. `criminal`: Triggered when legal stories mention arrests, police custody, FIRs, bail, CBI, ED, chargesheets, homicide, Narcotics/NDPS, or penal codes (IPC/BNS/UAPA/PMLA).
2. `civil`: Triggered when legal stories reference arbitration, contracts, trademark/patent disputes, insolvency (NCLT/IBBI), consumer forums, or property litigation.
3. `finance`: Triggered when business articles cover Sensex, Nifty, equities, IPOs, mutual funds, monetary policy, SEBI, or RBI rate decisions.
4. `world`: Triggered when national feeds cover foreign affairs, diplomacy, conflicts, or international heads of state.

---

## Full-Text Scraper and Boilerplate Filter

When scraping an article's full text, `extractor.py` performs the following processing:

1. DOM Targeting: Resolves the publisher's main container using site-specific CSS selectors defined in `config.py`.
2. Paywall and Promotion Removal: Eliminates elements matching `.paywall`, `.subscription`, `.newsletter-signup`, `.social-share`, and related selectors.
3. Noise Filtering: Detects and discards subscription reminders ("You do not have an active subscription", "Unlock these with subscription"), author bios, app installation pitches, and commenting widgets such as Vuukle.
4. Paragraph Assembly: Collects textual paragraphs exceeding minimum length thresholds, filters duplicate statements, and aggregates clean narrative text.

---

## Database Architecture

The application persists data in SQLite (`news.db`).

### Table: `articles`
Stores all discovered articles. Duplicates are rejected at the database level using `source_url TEXT UNIQUE` and `INSERT OR IGNORE`.

```sql
CREATE TABLE articles (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    summary TEXT,
    full_text TEXT,
    image_url TEXT,
    source_url TEXT UNIQUE,
    source TEXT NOT NULL,
    category TEXT NOT NULL,
    pub_date TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_category ON articles(category);
CREATE INDEX idx_created_at ON articles(created_at DESC);
CREATE INDEX idx_source ON articles(source);
```

### Table: `poll_logs`
Records polling telemetry for health monitoring and diagnostics.

```sql
CREATE TABLE poll_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL,
    polled_at TEXT NOT NULL,
    status TEXT NOT NULL,
    articles_found INTEGER DEFAULT 0,
    articles_new INTEGER DEFAULT 0,
    duration_ms INTEGER DEFAULT 0,
    error_message TEXT
);
```

---

## REST API Reference

The service includes a FastAPI application runnable via `uvicorn main:app`.

### Endpoints

1. `GET /health`
   Returns system status and database connectivity check.

2. `GET /api/sources`
   Returns all 25 configured publishers, homepage links, branding logos, categories, and total article counts stored per source.

3. `GET /api/articles`
   Retrieves paginated articles with optional filters:
   - `category`: Filter by category name (e.g. `finance`, `criminal`, `top`)
   - `source`: Filter by source name
   - `has_content`: Boolean flag (`true` for articles with scraped `full_text`, `false` for unextracted)
   - `search`: Keyword search across titles and summaries
   - `limit`: Number of records (default 20, max 100)
   - `offset`: Pagination offset

4. `GET /api/articles/{article_id}`
   Retrieves full details for a single article.

5. `POST /api/articles/{article_id}/extract`
   Triggers synchronous full-text extraction for the requested article, updates `full_text` in the database, and returns the parsed content.

6. `GET /api/stats`
   Returns high-level statistics: total articles, breakdown by category, breakdown by publisher, count of full-text extracted records, and last polling timestamp.

7. `GET /api/logs`
   Returns recent poller activity logs with duration and error tracking.

---

## Operating Instructions

### Environment Setup
Install required dependencies:
```bash
pip install -r requirements.txt
```

### Run Feed Verification Test
Verify connectivity and check feed health across all 25 sources:
```bash
python test_poller.py
```
To verify a single source:
```bash
python test_poller.py -s the-hindu
```
To test article extraction without persisting:
```bash
python test_poller.py -s the-hindu --extract
```

### Run the Background Poller
Starts the continuous polling loop:
```bash
python poller.py
```

### Run the Web API Server
Starts the REST API service on port 8000:
```bash
python main.py
```
Interactive documentation is available at `http://localhost:8000/docs`.

---

## Querying the Database Directly

The database can be inspected directly via SQLite command line:
```bash
sqlite3 -header -column news.db
```

Sample query for article distribution across categories:
```sql
SELECT category, count(*) AS total_articles
FROM articles
GROUP BY category
ORDER BY total_articles DESC;
```

Sample query for recent finance stories:
```sql
SELECT source, title, pub_date
FROM articles
WHERE category = 'finance'
ORDER BY created_at DESC
LIMIT 5;
```
