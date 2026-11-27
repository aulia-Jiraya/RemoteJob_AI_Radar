from __future__ import annotations
import hashlib
import logging
import feedparser
import httpx
from concurrent.futures import ThreadPoolExecutor, as_completed
from src.models import JobItem

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": "RemoteJob_AI_Radar/1.0 (+https://github.com)",
    "Accept": "application/json, application/xml, text/xml;q=0.9, */*;q=0.8",
}


def _make_id(prefix: str, url: str) -> str:
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
    return f"{prefix}_{digest}"


def fetch_remotive(client: httpx.Client) -> list[JobItem]:
    jobs: list[JobItem] = []
    try:
        resp = client.get("https://remotive.com/api/remote-jobs?limit=60", headers=DEFAULT_HEADERS, timeout=20.0)
        resp.raise_for_status()
        for item in resp.json().get("jobs", []):
            url = item.get("url", "")
            if not url:
                continue
            jobs.append(
                JobItem(
                    job_id=_make_id("remotive", url),
                    title=item.get("title", "Untitled"),
                    company=item.get("company_name", "Unknown"),
                    url=url,
                    source="Remotive API",
                    location=item.get("candidate_required_location", "Remote"),
                    salary=item.get("salary") or "Not specified",
                    description=item.get("description", ""),
                    needs_smart_fetch=False,
                )
            )
    except Exception as exc:
        logger.warning("Remotive fetch failed: %s", exc)
    return jobs


def fetch_arbeitnow(client: httpx.Client) -> list[JobItem]:
    jobs: list[JobItem] = []
    try:
        resp = client.get("https://www.arbeitnow.com/api/job-board-api", headers=DEFAULT_HEADERS, timeout=20.0)
        resp.raise_for_status()
        for item in resp.json().get("data", []):
            if not item.get("remote", False):
                continue
            url = item.get("url", "")
            if not url:
                continue
            jobs.append(
                JobItem(
                    job_id=_make_id("arbeitnow", url),
                    title=item.get("title", "Untitled"),
                    company=item.get("company_name", "Unknown"),
                    url=url,
                    source="Arbeitnow API",
                    location=item.get("location", "Remote"),
                    description=item.get("description", ""),
                    needs_smart_fetch=False,
                )
            )
    except Exception as exc:
        logger.warning("Arbeitnow fetch failed: %s", exc)
    return jobs


def fetch_remoteok(client: httpx.Client) -> list[JobItem]:
    jobs: list[JobItem] = []
    try:
        resp = client.get("https://remoteok.com/api", headers=DEFAULT_HEADERS, timeout=20.0)
        resp.raise_for_status()
        data = resp.json()
        for item in data:
            if not isinstance(item, dict) or not item.get("position") or not item.get("url"):
                continue
            url = item["url"]
            if url.startswith("/"):
                url = f"https://remoteok.com{url}"
            sal_min = item.get("salary_min")
            sal_max = item.get("salary_max")
            salary = f"${sal_min:,} - ${sal_max:,}" if sal_min and sal_max else "Not specified"
            jobs.append(
                JobItem(
                    job_id=_make_id("remoteok", url),
                    title=item.get("position", "Untitled"),
                    company=item.get("company", "Unknown"),
                    url=url,
                    source="RemoteOK API",
                    location=item.get("location") or "Worldwide",
                    salary=salary,
                    description=item.get("description", ""),
                    needs_smart_fetch=False,
                )
            )
    except Exception as exc:
        logger.warning("RemoteOK fetch failed: %s", exc)
    return jobs


def fetch_weworkremotely(client: httpx.Client) -> list[JobItem]:
    jobs: list[JobItem] = []
    rss_url = "https://weworkremotely.com/categories/remote-programming-jobs.rss"
    try:
        resp = client.get(rss_url, headers=DEFAULT_HEADERS, timeout=20.0)
        resp.raise_for_status()
        feed = feedparser.parse(resp.text)
        for entry in feed.entries[:40]:
            url = entry.get("link", "")
            if not url:
                continue
            raw_title = entry.get("title", "Untitled")
            company, title = ("Unknown", raw_title)
            if ":" in raw_title:
                parts = raw_title.split(":", 1)
                company, title = parts[0].strip(), parts[1].strip()
            jobs.append(
                JobItem(
                    job_id=_make_id("wwr", url),
                    title=title,
                    company=company,
                    url=url,
                    source="WeWorkRemotely RSS",
                    location=entry.get("region", "Remote"),
                    description=entry.get("summary", ""),
                    needs_smart_fetch=False,
                )
            )
    except Exception as exc:
        logger.warning("WeWorkRemotely RSS fetch failed: %s", exc)
    return jobs


def fetch_hackernews_jobs(client: httpx.Client, limit: int = 25) -> list[JobItem]:
    jobs: list[JobItem] = []
    try:
        ids_resp = client.get("https://hacker-news.firebaseio.com/v0/jobstories.json", timeout=15.0)
        ids_resp.raise_for_status()
        story_ids = ids_resp.json()[:limit]

        def fetch_story(sid: int) -> JobItem | None:
            try:
                item_resp = client.get(
                    f"https://hacker-news.firebaseio.com/v0/item/{sid}.json",
                    timeout=10.0,
                )
                if item_resp.status_code != 200:
                    return None
                item = item_resp.json() or {}
                title = item.get("title", "")
                url = item.get("url") or f"https://news.ycombinator.com/item?id={sid}"
                if not title:
                    return None
                return JobItem(
                    job_id=_make_id("hn", url),
                    title=title,
                    company="YC / Hacker News",
                    url=url,
                    source="Hacker News API",
                    location="Check JD",
                    description=item.get("text", title),
                    needs_smart_fetch=True,
                )
            except Exception:
                return None

        # Parallel fetch with max 5 concurrent workers
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(fetch_story, sid): sid for sid in story_ids}
            for future in as_completed(futures):
                result = future.result()
                if result:
                    jobs.append(result)

    except Exception as exc:
        logger.warning("Hacker News fetch failed: %s", exc)
    return jobs


def fetch_greenhouse_boards(client: httpx.Client, slugs: list[str]) -> list[JobItem]:
    jobs: list[JobItem] = []
    for slug in slugs:
        api_url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
        try:
            resp = client.get(api_url, headers=DEFAULT_HEADERS, timeout=15.0)
            if resp.status_code == 404:
                logger.info("Greenhouse board '%s' not found (404); skipping.", slug)
                continue
            resp.raise_for_status()
            for item in resp.json().get("jobs", []):
                url = item.get("absolute_url", "")
                if not url:
                    continue
                loc = (item.get("location") or {}).get("name", "Unspecified")
                jobs.append(
                    JobItem(
                        job_id=_make_id(f"gh_{slug}", url),
                        title=item.get("title", "Untitled"),
                        company=slug.capitalize(),
                        url=url,
                        source=f"Greenhouse ({slug})",
                        location=loc,
                        description=item.get("content", ""),
                        needs_smart_fetch=False,
                    )
                )
        except Exception as exc:
            logger.warning("Greenhouse (%s) fetch failed: %s", slug, exc)
    return jobs


def fetch_lever_boards(client: httpx.Client, slugs: list[str]) -> list[JobItem]:
    jobs: list[JobItem] = []
    for slug in slugs:
        api_url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
        try:
            resp = client.get(api_url, headers=DEFAULT_HEADERS, timeout=15.0)
            if resp.status_code == 404:
                logger.info("Lever board '%s' not found (404); skipping.", slug)
                continue
            resp.raise_for_status()
            for item in resp.json():
                url = item.get("hostedUrl", "")
                if not url:
                    continue
                cats = item.get("categories") or {}
                loc = cats.get("location", "Unspecified")
                desc = item.get("descriptionPlain") or item.get("description", "")
                jobs.append(
                    JobItem(
                        job_id=_make_id(f"lever_{slug}", url),
                        title=item.get("text", "Untitled"),
                        company=slug.capitalize(),
                        url=url,
                        source=f"Lever ({slug})",
                        location=loc,
                        description=desc,
                        needs_smart_fetch=False,
                    )
                )
        except Exception as exc:
            logger.warning("Lever (%s) fetch failed: %s", slug, exc)
    return jobs


def fetch_all_direct_sources(client: httpx.Client, cfg: dict) -> list[JobItem]:
    results: list[JobItem] = []
    if cfg.get("enable_remotive", True):
        results.extend(fetch_remotive(client))
    if cfg.get("enable_arbeitnow", True):
        results.extend(fetch_arbeitnow(client))
    if cfg.get("enable_remoteok", True):
        results.extend(fetch_remoteok(client))
    if cfg.get("enable_weworkremotely", True):
        results.extend(fetch_weworkremotely(client))
    if cfg.get("enable_hackernews", True):
        results.extend(fetch_hackernews_jobs(client))

    gh_slugs = cfg.get("greenhouse_boards", [])
    if gh_slugs:
        results.extend(fetch_greenhouse_boards(client, gh_slugs))

    lever_slugs = cfg.get("lever_boards", [])
    if lever_slugs:
        results.extend(fetch_lever_boards(client, lever_slugs))

    logger.info("Direct API/RSS/ATS fetched %d total raw items.", len(results))
    return results