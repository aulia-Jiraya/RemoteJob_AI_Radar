from __future__ import annotations
import html
import logging
import re
import httpx
import trafilatura
from src.models import JobItem

logger = logging.getLogger(__name__)

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9,id;q=0.8",
}


def clean_html_to_text(raw_html: str, max_chars: int = 3500) -> str:
    if not raw_html:
        return ""
    wrapped = raw_html if "<html" in raw_html.lower() else f"<html><body>{raw_html}</body></html>"
    extracted = trafilatura.extract(
        wrapped,
        output_format="markdown",
        include_comments=False,
        include_tables=True,
        favor_precision=False,
    )
    if extracted and len(extracted.strip()) > 60:
        return extracted.strip()[:max_chars]

    # Fallback ringan untuk fragmen HTML pendek dari API
    no_tags = re.sub(r"<[^>]+>", " ", raw_html)
    unescaped = html.unescape(no_tags)
    collapsed = re.sub(r"\s+", " ", unescaped).strip()
    return collapsed[:max_chars]


def enrich_job_description(job: JobItem, client: httpx.Client, max_chars: int = 3500) -> JobItem:
    if not job.needs_smart_fetch and len(job.description) >= 350:
        job.description = clean_html_to_text(job.description, max_chars=max_chars)
        return job

    try:
        resp = client.get(job.url, headers=BROWSER_HEADERS, timeout=12.0, follow_redirects=True)
        if resp.status_code == 200 and resp.text:
            md = trafilatura.extract(
                resp.text,
                output_format="markdown",
                include_comments=False,
                include_tables=True,
            )
            if md and len(md.strip()) > len(job.description):
                job.description = md.strip()[:max_chars]
                return job
        else:
            logger.info("Smart fetch skipped/blocked (%s) for %s; using snippet.", resp.status_code, job.url)
    except Exception as exc:
        logger.info("Smart fetch error for %s (%s); using snippet.", job.url, exc)

    job.description = clean_html_to_text(job.description, max_chars=max_chars)
    return job