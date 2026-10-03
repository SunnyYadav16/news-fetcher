"""
SQLite database layer for article storage, deduplication, and polling statistics.
Schema aligned with:
    articles (id TEXT PRIMARY KEY, title, summary, full_text, image_url, source_url UNIQUE,
              source, category, pub_date, created_at)
"""

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import logging
import os
import sqlite3
from typing import Any, Dict, Generator, List, Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

logger = logging.getLogger(__name__)

# Primary database file constant
DB_FILE = os.getenv("NEWS_DB_PATH", "news.db")

# Tracking parameters to strip during URL normalization (utm_* is handled via startswith)
TRACKING_PARAMS = {
    "fbclid",
    "gclid",
    "gclsrc",
    "dclid",
    "msclkid",
    "mc_cid",
    "mc_eid",
    "_ga",
    "_hsenc",
    "_hsmi",
    "ncid",
    "ref",
    "sr_share",
    "cmpid",
}


def normalize_url(raw_url: str) -> str:
    """
    Normalize a URL for reliable deduplication:
    - Lowercase scheme and domain
    - Strip tracking parameters (utm_*, fbclid, etc.)
    - Remove fragment/anchor
    - Standardize trailing slashes
    """
    if not raw_url:
        return ""
    try:
        parsed = urlparse(raw_url.strip())
        scheme = parsed.scheme.lower() or "https"
        netloc = parsed.netloc.lower()

        # Remove default ports
        if netloc.endswith(":80") and scheme == "http":
            netloc = netloc[:-3]
        elif netloc.endswith(":443") and scheme == "https":
            netloc = netloc[:-4]

        # Filter query params
        query_items = parse_qsl(parsed.query, keep_blank_values=False)
        filtered_items = [
            (k, v) for k, v in query_items
            if k.lower() not in TRACKING_PARAMS and not k.lower().startswith("utm_")
        ]
        filtered_items.sort(key=lambda x: x[0])
        clean_query = urlencode(filtered_items)

        # Normalize path
        path = parsed.path or "/"
        if len(path) > 1 and path.endswith("/"):
            path = path[:-1]

        return urlunparse((scheme, netloc, path, parsed.params, clean_query, ""))
    except Exception as e:
        logger.warning("Error normalizing URL '%s': %s", raw_url, e)
        return raw_url.strip()


def generate_article_id(raw_url: str) -> str:
    """Generate a deterministic 16-character hex hash ID for an article URL."""
    clean = normalize_url(raw_url)
    return hashlib.sha256(clean.encode("utf-8", errors="ignore")).hexdigest()[:16]


@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager providing a SQLite connection with row factory
    and write-ahead logging enabled.
    """
    conn = sqlite3.connect(DB_FILE, timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Initialize database tables and indexes."""
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS articles (
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
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_category ON articles(category);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_created_at ON articles(created_at DESC);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_source ON articles(source);")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS poll_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id TEXT NOT NULL,
                polled_at TEXT NOT NULL,
                status TEXT NOT NULL,
                articles_found INTEGER DEFAULT 0,
                articles_new INTEGER DEFAULT 0,
                duration_ms INTEGER DEFAULT 0,
                error_message TEXT
            );
        """)

    logger.info("Database initialized successfully at %s", DB_FILE)


def insert_articles(articles: List[Dict[str, Any]]) -> int:
    """Insert a batch of articles with duplicate suppression (INSERT OR IGNORE)."""
    inserted_count = 0
    with get_db() as conn:
        for art in articles:
            try:
                cur = conn.execute("""
                    INSERT OR IGNORE INTO articles (id, title, summary, image_url, source_url, source, category, pub_date)
                    VALUES (:id, :title, :summary, :image_url, :source_url, :source, :category, :pub_date)
                """, art)
                inserted_count += cur.rowcount
            except sqlite3.Error as e:
                logger.debug("Database error inserting article: %s", e)
    return inserted_count


def get_article_by_id(article_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve a single article by ID."""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
        return dict(row) if row else None


def update_article_extraction(
    article_id: str,
    content: Optional[str],
    image_url: Optional[str] = None,
) -> None:
    """Update article full text and optional lead image after scraping."""
    with get_db() as conn:
        conn.execute(
            """
            UPDATE articles
            SET full_text = ?,
                image_url = COALESCE(NULLIF(image_url, ''), ?)
            WHERE id = ?
            """,
            (content, image_url, article_id),
        )


def list_articles(
    limit: int = 50,
    offset: int = 0,
    category: Optional[str] = None,
    source_id: Optional[str] = None,
    search: Optional[str] = None,
    has_content: Optional[bool] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Query articles with filters, pagination, and total count.
    Returns (articles_list, total_count).
    """
    conditions = []
    params: List[Any] = []

    if category:
        conditions.append("category = ?")
        params.append(category)

    if source_id:
        conditions.append("source LIKE ?")
        params.append(f"%{source_id}%")

    if has_content is True:
        conditions.append("full_text IS NOT NULL AND length(full_text) > 0")
    elif has_content is False:
        conditions.append("(full_text IS NULL OR length(full_text) = 0)")

    if search:
        conditions.append("(title LIKE ? OR summary LIKE ?)")
        search_param = f"%{search}%"
        params.extend([search_param, search_param])

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    with get_db() as conn:
        total_count = conn.execute(f"SELECT COUNT(*) FROM articles {where_clause}", params).fetchone()[0]
        query = f"""
            SELECT id, title, summary, full_text, image_url, source_url,
                   source, category, pub_date, created_at
            FROM articles
            {where_clause}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """
        cur = conn.execute(query, params + [limit, offset])
        articles = [dict(row) for row in cur.fetchall()]

    return articles, total_count


def record_poll_log(
    source: str,
    status: str,
    articles_found: int = 0,
    articles_new: int = 0,
    duration_ms: int = 0,
    error_message: Optional[str] = None,
) -> None:
    """Record an entry in the polling history log."""
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO poll_logs (
                source_id, polled_at, status,
                articles_found, articles_new, duration_ms, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source,
                now_iso,
                status,
                articles_found,
                articles_new,
                duration_ms,
                error_message,
            ),
        )


def get_recent_poll_logs(limit: int = 50) -> List[Dict[str, Any]]:
    """Retrieve recent polling history logs."""
    with get_db() as conn:
        cur = conn.execute(
            "SELECT * FROM poll_logs ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        return [dict(row) for row in cur.fetchall()]


def get_database_stats() -> Dict[str, Any]:
    """Retrieve aggregate database metrics."""
    with get_db() as conn:
        total_articles = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]

        by_category = {
            row["category"]: row["cnt"]
            for row in conn.execute(
                "SELECT category, COUNT(*) as cnt FROM articles GROUP BY category ORDER BY cnt DESC"
            )
        }

        by_source = {
            row["source"]: row["cnt"]
            for row in conn.execute(
                "SELECT source, COUNT(*) as cnt FROM articles GROUP BY source ORDER BY cnt DESC"
            )
        }

        extracted_count = conn.execute(
            "SELECT COUNT(*) FROM articles WHERE full_text IS NOT NULL AND length(full_text) > 0"
        ).fetchone()[0]

        total_polls = conn.execute("SELECT COUNT(*) FROM poll_logs").fetchone()[0]
        last_poll = conn.execute("SELECT polled_at FROM poll_logs ORDER BY id DESC LIMIT 1").fetchone()

        return {
            "total_articles": total_articles,
            "articles_by_category": by_category,
            "articles_by_source": by_source,
            "articles_with_full_text": extracted_count,
            "total_poll_executions": total_polls,
            "last_polled_at": last_poll[0] if last_poll else None,
        }
