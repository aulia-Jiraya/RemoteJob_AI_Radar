from __future__ import annotations
import html
import logging
from pathlib import Path
import httpx
import yaml
from src.ai_scorer import check_llm_health, score_jobs_in_batches
from src.extractor import enrich_job_description
from src.fetchers.direct_apis import fetch_all_direct_sources
from src.fetchers.search_dorker import fetch_all_search_sources
from src.models import JobItem
from src.notifier import send_telegram_cards, send_telegram_status
from src.prefilter import passes_prefilter
from src.state import JobStateStore, normalize_url

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("RemoteJob_AI_Radar")

ROOT = Path(__file__).resolve().parent.parent
PROFILE_PATH = ROOT / "config" / "profile.yaml"
STATE_PATH = ROOT / "data" / "seen_jobs.json"


def load_profile() -> dict:
    return yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8"))


def main() -> None:
    profile = load_profile()
    scoring_cfg = profile.get("scoring", {})
    prefilter_cfg = profile.get("prefilter", {})

    min_score = int(scoring_cfg.get("min_score", 75))
    max_cards = int(scoring_cfg.get("max_cards_per_run", 8))
    batch_size = int(scoring_cfg.get("batch_size", 12))
    retention_days = int(scoring_cfg.get("state_retention_days", 30))

    state = JobStateStore(STATE_PATH, retention_days=retention_days)

    with httpx.Client() as client:
        # 0. Health Check Koneksi Endpoint LLM sebelum mulai
        llm_ok, active_model, llm_status = check_llm_health(client)
        if not llm_ok:
            alert = (
                "🚨 <b>RemoteJob AI Radar — LLM Endpoint GAGAL</b>\n"
                f"📡 <b>Status:</b> <code>{html.escape(llm_status)}</code>\n"
                "⚠️ Siklus dihentikan sementara agar lowongan tidak terlewat. Cek API Key / nama model."
            )
            send_telegram_status(alert, client)
            raise RuntimeError(f"LLM Health Check failed: {llm_status}")

        # 1. Jalur Cepat (API/RSS/ATS) + 2. Jalur Pencarian (SearXNG + DDGS Fallback)
        raw_jobs: list[JobItem] = []
        raw_jobs.extend(fetch_all_direct_sources(client, profile.get("direct_sources", {})))
        raw_jobs.extend(fetch_all_search_sources(client, profile.get("search_dorking", {})))

        # Deduplikasi dalam 1 siklus & buang yang sudah pernah dilihat
        unique_new: list[JobItem] = []
        seen_in_run: set[str] = set()
        for job in raw_jobs:
            norm = normalize_url(job.url)
            if norm in seen_in_run or state.is_seen(norm):
                continue
            seen_in_run.add(norm)
            unique_new.append(job)

        logger.info("Raw: %d | Unique new jobs: %d", len(raw_jobs), len(unique_new))

        # 3. Pre-filter regex lokal
        candidates: list[JobItem] = []
        include_patterns = prefilter_cfg.get("include_patterns", [])
        exclude_patterns = prefilter_cfg.get("exclude_patterns", [])

        for job in unique_new:
            if passes_prefilter(job, include_patterns, exclude_patterns):
                candidates.append(job)
            else:
                state.mark_seen(job.url)

        logger.info("Passed local pre-filter: %d jobs", len(candidates))

        if not candidates:
            state.save()
            summary = (
                "🛰️ <b>RemoteJob AI Radar — Laporan Siklus</b>\n"
                f"🟢 <b>Koneksi LLM:</b> <code>{html.escape(llm_status)}</code>\n"
                f"🔎 <b>Dipindai:</b> {len(raw_jobs)} raw | {len(unique_new)} baru | 0 lolos pre-filter"
            )
            send_telegram_status(summary, client)
            logger.info("No matching candidates this cycle. State saved.")
            return

        # 4. Smart Fetch (HTML -> Markdown via Trafilatura, fallback ke snippet)
        enriched: list[JobItem] = [enrich_job_description(job, client) for job in candidates]

        # 5. Kurasi & Scoring Batch via Gemini OpenAI-Compatible Endpoint (dengan Fallback)
        scored_map, processed_ids, last_model = score_jobs_in_batches(
            enriched,
            profile,
            client=client,
            batch_size=batch_size,
            preferred_model=active_model,
        )

        matched_pairs = []
        for job in enriched:
            if job.job_id in processed_ids:
                state.mark_seen(job.url)
            scored = scored_map.get(job.job_id)
            if scored and scored.score >= min_score:
                matched_pairs.append((job, scored))

        logger.info("Qualified jobs (score >= %d): %d", min_score, len(matched_pairs))

        # 6. Kirim Laporan Status Koneksi LLM + Ringkasan ke Telegram
        summary = (
            "🛰️ <b>RemoteJob AI Radar — Laporan Siklus</b>\n"
            f"🟢 <b>Koneksi LLM:</b> <code>{html.escape(llm_status)}</code>\n"
            f"🧠 <b>Model Scoring:</b> <code>{html.escape(last_model)}</code>\n"
            f"🔎 <b>Dipindai:</b> {len(raw_jobs)} raw | {len(candidates)} lolos filter | <b>{len(matched_pairs)} cocok (skor ≥ {min_score})</b>"
        )
        send_telegram_status(summary, client)

        # 7. Pengiriman Kartu Lowongan Telegram
        if matched_pairs:
            send_telegram_cards(matched_pairs, client, max_cards=max_cards)

    state.save()
    logger.info("Radar cycle complete. State updated.")


if __name__ == "__main__":
    main()