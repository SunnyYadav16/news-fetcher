"""FastAPI backend server for the India News Ingestion Engine.
Provides endpoints for category-based article retrieval, on-demand full-text extraction & summarization,
and automated/manual feed polling.
"""

import asyncio
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from config import API_PORT, CATEGORIES, SOURCES, get_source
import db
from extractor import (
    async_scrape_and_clean_article,
    generate_extractive_summary,
)
from poller import NewsPoller

# NewsPoller worker instance
poller = NewsPoller()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle: initialize database and run background poller."""
    db.init_db()
    poller_task = asyncio.create_task(poller.start())
    yield
    poller.stop()
    poller_task.cancel()


app = FastAPI(
    title="India News Ingestion Engine",
    description="Automated multi-tier RSS news aggregator, deduplication engine, and extractive summarizer.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pydantic Response Models
class ArticleSummary(BaseModel):
    id: str
    title: str
    summary: Optional[str] = None
    image_url: Optional[str] = None
    source_url: str
    source: str
    category: str
    pub_date: Optional[str] = None
    created_at: Optional[str] = None


class ArticleDetail(ArticleSummary):
    full_text: Optional[str] = None


class ArticleListResponse(BaseModel):
    items: List[ArticleSummary]
    total: int
    limit: int
    offset: int


def _get_or_404(article_id: str) -> dict:
    """Retrieve article by ID or raise HTTP 404."""
    article = db.get_article_by_id(article_id)
    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Article not found.",
        )
    return article


async def _extract(article: dict):
    """Scrape, clean, and persist full-text content for an article."""
    src = get_source(article.get("source", ""))
    ext = await async_scrape_and_clean_article(article["source_url"], selectors=src.selectors if src else None)
    if ext.content:
        db.update_article_extraction(
            article_id=article["id"],
            content=ext.content,
            image_url=ext.image_url,
        )
        article["full_text"] = ext.content
    return ext


@app.get("/api/summary/{article_id}", tags=["News"])
async def get_summary(article_id: str):
    """Fetches article full-text on demand, updates DB cache, and returns summary."""
    article = _get_or_404(article_id)

    full_text = article.get("full_text")
    if not full_text:
        await _extract(article)
        full_text = article.get("full_text") or article.get("summary") or "Full text could not be extracted."

    summary = generate_extractive_summary(full_text)
    return {
        "article": article,
        "summary": summary,
        "full_text_length": len(full_text),
    }


@app.post("/api/poll/now", tags=["Polling"])
async def trigger_manual_poll():
    """Forces an immediate polling cycle across all registered publishers."""
    asyncio.create_task(poller.run_cycle())
    return {"status": "Polling cycle initiated in background."}


@app.get("/health", tags=["General"])
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "poller_running": poller.is_running}


@app.get("/api/categories", tags=["Sources"])
async def get_categories():
    """List all available news categories."""
    return {"categories": CATEGORIES}


@app.get("/api/sources", tags=["Sources"])
async def get_sources():
    """List all configured news sources, logos, categories, and article counts."""
    by_source = db.get_database_stats().get("articles_by_source", {})
    sources = [{**asdict(s), "stored_articles_count": by_source.get(s.name, 0)} for s in SOURCES]
    return {"sources": sources}


@app.get("/api/articles", response_model=ArticleListResponse, tags=["Articles"])
async def get_articles(
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    category: Optional[str] = Query(None, description="Filter by category"),
    source_id: Optional[str] = Query(None, description="Filter by source ID or name"),
    search: Optional[str] = Query(None, description="Search keyword in title/summary"),
    has_content: Optional[bool] = Query(None, description="Filter by content availability"),
):
    """Search and retrieve stored articles with pagination and filtering."""
    articles, total = db.list_articles(
        limit=limit,
        offset=offset,
        category=category,
        source_id=source_id,
        search=search,
        has_content=has_content,
    )
    return ArticleListResponse(items=articles, total=total, limit=limit, offset=offset)


@app.get("/api/articles/{article_id}", response_model=ArticleDetail, tags=["Articles"])
async def get_article(article_id: str):
    """Retrieve full article details, including cleaned body content."""
    return _get_or_404(article_id)


@app.post("/api/articles/{article_id}/extract", tags=["Articles"])
async def trigger_article_extraction(article_id: str):
    """Manually trigger or re-run full-text content extraction for an article."""
    article = _get_or_404(article_id)
    ext = await _extract(article)
    if ext.content:
        return {
            "message": "Content extracted successfully",
            "article_id": article_id,
            "content_length": len(ext.content),
        }
    return {
        "message": "Extraction failed",
        "article_id": article_id,
        "error": ext.error or "Failed to extract content",
    }


@app.get("/api/poll-logs", tags=["Polling"])
async def get_poll_logs(limit: int = Query(50, ge=1, le=200)):
    """Retrieve history of recent feed polling runs."""
    logs = db.get_recent_poll_logs(limit=limit)
    return {"logs": logs}


@app.get("/api/stats", tags=["General"])
async def get_stats():
    """Retrieve aggregate database statistics and ingestion metrics."""
    return db.get_database_stats()


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=API_PORT, reload=True)
