from __future__ import annotations
import html
import logging
import os
import time
import httpx
from src.models import JobItem, ScoredJob

logger = logging.getLogger(__name__)


def send_telegram_status(message_html: str, client: httpx.Client) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing.")

    endpoint = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message_html[:4000],
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        resp = client.post(endpoint, json=payload, timeout=15.0)
        resp.raise_for_status()
        return True
    except Exception as exc:
        logger.error("Failed to send Telegram status report: %s", exc)
        return False


def _format_card(job: JobItem, scored: ScoredJob) -> str:
    title = html.escape(job.title)
    company = html.escape(job.company)
    source = html.escape(job.source)
    salary = html.escape(scored.salary_range)
    work_mode = html.escape(scored.work_mode)
    stack = html.escape(", ".join(scored.tech_stack) if scored.tech_stack else "Tidak spesifik")
    reason = html.escape(scored.match_reason)
    flags = (
        "\n".join(f"• {html.escape(f)}" for f in scored.red_flags)
        if scored.red_flags
        else "• Tidak ada red flag mencolok"
    )
    pitch = html.escape(scored.pitch_hook)
    safe_url = html.escape(job.url, quote=True)

    badge = "🔥" if scored.score >= 85 else "🎯"

    card = (
        f"{badge} <b>Skor {scored.score}/100 — {title}</b>\n"
        f"🏢 <b>Perusahaan:</b> {company} <i>({source})</i>\n"
        f"🌍 <b>Mode/Lokasi:</b> {work_mode}\n"
        f"💰 <b>Gaji:</b> {salary}\n"
        f"🛠 <b>Tech Stack:</b> <code>{stack}</code>\n\n"
        f"✅ <b>Alasan Cocok:</b>\n{reason}\n\n"
        f"⚠️ <b>Red Flags:</b>\n{flags}\n\n"
        f"✍️ <b>Draf Hook / Pitch:</b>\n<blockquote>{pitch}</blockquote>\n\n"
        f"🔗 <a href=\"{safe_url}\">Lamar Sekarang →</a>"
    )
    return card[:4000]


def send_telegram_cards(
    matched_pairs: list[tuple[JobItem, ScoredJob]],
    client: httpx.Client,
    max_cards: int = 8,
) -> int:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing.")

    sorted_pairs = sorted(matched_pairs, key=lambda x: x[1].score, reverse=True)[:max_cards]
    endpoint = f"https://api.telegram.org/bot{token}/sendMessage"
    sent_count = 0

    for job, scored in sorted_pairs:
        payload = {
            "chat_id": chat_id,
            "text": _format_card(job, scored),
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        try:
            resp = client.post(endpoint, json=payload, timeout=15.0)
            resp.raise_for_status()
            sent_count += 1
            time.sleep(0.6)
        except Exception as exc:
            logger.error("Failed to send Telegram card for %s: %s", job.url, exc)

    logger.info("Sent %d/%d Telegram cards.", sent_count, len(sorted_pairs))
    return sent_count