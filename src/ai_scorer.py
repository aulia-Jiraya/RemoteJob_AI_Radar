from __future__ import annotations
import json
import logging
import os
import re
import time
import httpx
from src.models import BatchScoreResponse, JobItem, ScoredJob

logger = logging.getLogger(__name__)

DEFAULT_API_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
DEFAULT_PRIMARY_MODEL = "gemini-3.5-flash-lite"
DEFAULT_FALLBACK_MODEL = "gemini-3.8-flash"


def _get_llm_config() -> tuple[str, str, str, str]:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Environment variable GEMINI_API_KEY is missing.")
    api_url = os.getenv("GEMINI_API_URL", DEFAULT_API_URL).strip()
    primary_model = os.getenv("GEMINI_MODEL", DEFAULT_PRIMARY_MODEL).strip()
    fallback_model = os.getenv("GEMINI_FALLBACK_MODEL", DEFAULT_FALLBACK_MODEL).strip()
    return api_key, api_url, primary_model, fallback_model


def _strip_json_fences(raw_text: str) -> str:
    text = raw_text.strip()
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return text


def _call_openai_compat(
    client: httpx.Client,
    api_url: str,
    api_key: str,
    model: str,
    prompt: str,
    expect_json: bool = True,
    max_tokens: int | None = None,
) -> str:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload: dict = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
    }
    if expect_json:
        payload["response_format"] = {"type": "json_object"}
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens

    resp = client.post(api_url, headers=headers, json=payload, timeout=45.0)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def check_llm_health(client: httpx.Client) -> tuple[bool, str, str]:
    """
    Mengecek apakah koneksi ke endpoint LLM berjalan normal.
    Mengembalikan: (is_ok, active_model, status_detail)
    """
    api_key, api_url, primary_model, fallback_model = _get_llm_config()
    models_to_try = [primary_model]
    if fallback_model and fallback_model != primary_model:
        models_to_try.append(fallback_model)

    errors: list[str] = []
    for idx, model in enumerate(models_to_try):
        try:
            reply = _call_openai_compat(
                client=client,
                api_url=api_url,
                api_key=api_key,
                model=model,
                prompt="Reply with exactly one word: OK",
                expect_json=False,
                max_tokens=10,
            )
            label = "Primary" if idx == 0 else "Fallback"
            logger.info("LLM Health Check OK (%s: %s) -> %s", label, model, reply.strip())
            return True, model, f"OK ({label}: {model})"
        except Exception as exc:
            err_msg = f"{model}: {exc}"
            logger.warning("LLM Health Check failed for %s", err_msg)
            errors.append(err_msg)

    return False, "", "GAGAL (" + " | ".join(errors) + ")"


def _build_prompt(profile: dict, batch: list[JobItem]) -> str:
    candidate = profile.get("candidate", {})
    skills_text = "\n".join(
        f"- {s['name']}: {s['detail']}" for s in candidate.get("core_skills", [])
    )

    jobs_payload = [
        {
            "job_id": j.job_id,
            "title": j.title,
            "company": j.company,
            "source": j.source,
            "location": j.location,
            "salary_hint": j.salary,
            "url": j.url,
            "description": j.description[:2800],
        }
        for j in batch
    ]

    return f"""You are a ruthless, precision AI career curator evaluating job postings for a specialist candidate.

CANDIDATE PROFILE:
- Headline: {candidate.get("title")}
- Target Work Preference: {candidate.get("work_preference")}
- Timezone Context: {candidate.get("timezone_note")}
- Core Skills:
{skills_text}

SCORING RUBRIC (1-100):
- 85-100: Direct match for AI Systems Engineering, RAG pipelines, LLM orchestration, or Context Engineering AND 100% Remote Global/Async friendly.
- 75-84: Strong AI/LLM Engineering or Architecture overlap with remote global/APAC eligibility.
- 50-74: General backend/ML role with partial AI overlap, or unclear remote/timezone constraints.
- 1-49: Mismatch (e.g., frontend-only, non-AI role, strictly US/EU-only residency/work authorization, or onsite-only).

STRICT RULES:
1. Evaluate EVERY job in the JSON list below and return one entry per job_id.
2. Penalize heavily (score <= 45) if the job requires US/EU/UK-only residency or work authorization.
3. For `match_reason` and `red_flags`, write concisely in Indonesian.
4. For `pitch_hook`, write 2-3 punchy English sentences tailored specifically to the job's pain points using the candidate's Local-First RAG, Context Engineering, and AI Systems Architecture strengths.
5. Never invent salary numbers; if absent, write "Tidak dicantumkan".
6. Return ONLY valid JSON matching this exact schema:
{{
  "results": [
    {{
      "job_id": "string",
      "score": 85,
      "salary_range": "string",
      "work_mode": "string",
      "tech_stack": ["Python", "RAG"],
      "match_reason": "string in Indonesian",
      "red_flags": ["string in Indonesian"],
      "pitch_hook": "string in English"
    }}
  ]
}}

JOBS TO EVALUATE (JSON):
{json.dumps(jobs_payload, ensure_ascii=False)}
"""


def score_jobs_in_batches(
    jobs: list[JobItem],
    profile: dict,
    client: httpx.Client,
    batch_size: int = 12,
    preferred_model: str | None = None,
) -> tuple[dict[str, ScoredJob], set[str], str]:
    """Returns (scored_map, processed_job_ids, last_used_model)."""
    api_key, api_url, primary_model, fallback_model = _get_llm_config()

    model_order: list[str] = []
    for m in [preferred_model, primary_model, fallback_model]:
        if m and m not in model_order:
            model_order.append(m)

    scored_map: dict[str, ScoredJob] = {}
    processed_ids: set[str] = set()
    last_used_model = model_order[0]

    for start in range(0, len(jobs), batch_size):
        batch = jobs[start : start + batch_size]
        prompt = _build_prompt(profile, batch)
        batch_num = (start // batch_size) + 1

        success = False
        for model in model_order:
            for attempt in range(1, 3):
                try:
                    raw_content = _call_openai_compat(
                        client=client,
                        api_url=api_url,
                        api_key=api_key,
                        model=model,
                        prompt=prompt,
                        expect_json=True,
                    )
                    cleaned = _strip_json_fences(raw_content)
                    parsed = BatchScoreResponse.model_validate_json(cleaned)

                    for item in parsed.results:
                        scored_map[item.job_id] = item
                    for j in batch:
                        processed_ids.add(j.job_id)

                    last_used_model = model
                    logger.info("Batch #%d (%d jobs) scored successfully via %s.", batch_num, len(batch), model)
                    success = True
                    break
                except Exception as exc:
                    wait_sec = 10 * attempt
                    logger.warning(
                        "Batch #%d model=%s attempt=%d failed (%s). Retrying in %ds...",
                        batch_num,
                        model,
                        attempt,
                        exc,
                        wait_sec,
                    )
                    time.sleep(wait_sec)
            if success:
                break
            logger.warning("Switching to fallback model for batch #%d...", batch_num)

        if not success:
            logger.error("Batch #%d failed on all models; jobs left unmarked for next cycle.", batch_num)

        if start + batch_size < len(jobs):
            time.sleep(5.0)

    return scored_map, processed_ids, last_used_model