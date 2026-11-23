from __future__ import annotations
import hashlib
import logging
import os
import time
import httpx
from src.models import JobItem

logger = logging.getLogger(__name__)

try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS  # type: ignore


def _make_id(url: str) -> str:
    return f"search_{hashlib.sha1(url.encode('utf-8')).hexdigest()[:10]}"


def _query_searxng(
    client: httpx.Client,
    base_url: str,
    query: str,
    max_results: int,
) -> list[JobItem]:
    jobs: list[JobItem] = []
    endpoint = f"{base_url.rstrip('/')}/search"
    params = {
        "q": query,
        "format": "json",
        "time_range": "day",
        "language": "en",
    }
    resp = client.get(endpoint, params=params, timeout=20.0)
    resp.raise_for_status()
    payload = resp.json()
    for item in payload.get("results", [])[:max_results]:
        url = item.get("url", "")
        title = item.get("title", "")
        if not url or not title:
            continue
        jobs.append(
            JobItem(
                job_id=_make_id(url),
                title=title,
                company="Via Search",
                url=url,
                source="SearXNG Dork",
                location="Check JD",
                description=item.get("content", title),
                needs_smart_fetch=True,
            )
        )
    return jobs


def _query_ddgs(query: str, max_results: int) -> list[JobItem]:
    jobs: list[JobItem] = []
    with DDGS() as ddgs:
        results = ddgs.text(query, timelimit="d", max_results=max_results) or []
        for item in results:
            url = item.get("href") or item.get("url", "")
            title = item.get("title", "")
            if not url or not title:
                continue
            jobs.append(
                JobItem(
                    job_id=_make_id(url),
                    title=title,
                    company="Via DDGS",
                    url=url,
                    source="DDGS Fallback",
                    location="Check JD",
                    description=item.get("body", title),
                    needs_smart_fetch=True,
                )
            )
    return jobs


def fetch_all_search_sources(client: httpx.Client, cfg: dict) -> list[JobItem]:
    if not cfg.get("enabled", True):
        return []

    searxng_url = os.getenv("SEARXNG_URL", "http://localhost:8080").strip()
    queries: list[str] = cfg.get("queries", [])
    max_results = int(cfg.get("max_results_per_query", 8))
    delay = float(cfg.get("delay_seconds", 2.0))

    collected: list[JobItem] = []

    for idx, query in enumerate(queries):
        items: list[JobItem] = []
        if searxng_url:
            try:
                items = _query_searxng(client, searxng_url, query, max_results)
                logger.info("SearXNG query #%d returned %d results.", idx + 1, len(items))
            except Exception as exc:
                logger.warning("SearXNG failed on query #%d (%s); falling back to ddgs.", idx + 1, exc)

        if not items:
            try:
                items = _query_ddgs(query, max_results)
                logger.info("DDGS fallback query #%d returned %d results.", idx + 1, len(items))
            except Exception as exc:
                logger.warning("DDGS fallback also failed on query #%d: %s", idx + 1, exc)

        collected.extend(items)
        if idx < len(queries) - 1:
            time.sleep(delay)

    logger.info("Search/Dorking fetched %d total raw items.", len(collected))
    return collected