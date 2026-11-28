# 🛰️ RemoteJob AI Radar

**Autonomous, Zero-Cost Career Intelligence & High-Signal Remote Opportunity Radar.**

Stop drowning in noisy job boards and irrelevant listings. RemoteJob AI Radar continuously scouts global remote ecosystems, evaluates every opportunity against your exact AI engineering profile using Google Gemini, and delivers curated, high-scoring job cards—complete with tailored application pitch hooks—directly to your Telegram.

---

## ✨ Core Features & Resiliency

| Feature | Description |
|---------|-------------|
| 🎯 **Precision AI Matchmaking** | Evaluates roles against your custom technical profile, timezone compatibility, and remote-work eligibility—filtering out location-restricted noise before it reaches your inbox. |
| ✍️ **Ready-to-Send Pitch Hooks** | Every qualified opportunity comes with a custom-crafted, role-specific English opening pitch tailored to your core engineering strengths, ready to copy-paste into job applications. |
| 🩺 **Built-In LLM Health Monitoring** | Verifies AI endpoint connectivity before every scan and sends real-time operational status reports straight to Telegram. |
| 🛡️ **Resilient Dual-Model Architecture** | Powered by `gemini-3.5-flash-lite` primary model with seamless automatic fallback to `gemini-3.8-flash` for uninterrupted reliability. |
| ⚡ **Bounded HTTP 429 Rate-Limit Handling** | Rate limits are handled via `Retry-After` header with a bounded retry limit (`max_retries`); the final attempt throws an exception so the fallback model can take over, preventing GitHub Actions runners from hanging indefinitely. |
| 🧠 **Smart State Memory** | Tracks previously evaluated listings through `data/seen_jobs.json` with 30-day retention, ensuring you never receive duplicate alerts. |
| 🧹 **Local Regex Pre-Filter** | Early-stage title and snippet filtering via regex to conserve LLM tokens before AI invocation. |
| 📄 **Smart HTML-to-Markdown Extraction** | Clean web content extraction to Markdown via Trafilatura, isolated per-job with `try/except` so a single failure cannot halt the entire enrichment pipeline. |
| 🔄 **Multi-Source Fetching** | Direct APIs and ATS (Remotive, ArbeitNow, RemoteOK, WeWorkRemotely, HackerNews, Greenhouse, Lever) plus Search Dorking (SearXNG with DDGS fallback). |
| 💸 **Zero Infrastructure Overhead** | Runs entirely on GitHub Actions runners at `$0` hosting cost, scheduled every 3 hours via cron. |

---

## 🏗️ System Architecture

The execution pipeline in `src/main.py` runs through nine sequential stages:

```
[Cron / CLI Trigger]
       │
       ▼
1. Load Configuration (config/profile.yaml)
       │
       ▼
2. LLM Health Check (src/ai_scorer.py → check_llm_health)
       ├── Failure → Send Telegram alert & halt pipeline
       └── Success → Proceed to fetching
       │
       ▼
3. Job Ingestion (Dual Path)
       ├── Path A: Direct APIs / ATS (src/fetchers/direct_apis.py)
       └── Path B: Search Dorking (src/fetchers/search_dorker.py)
       │
       ▼
4. Deduplication & Normalization (src/state.py → JobStateStore)
       ├── URL normalization & ID matching against data/seen_jobs.json
       └── Elimination of listings processed within the last 30 days
       │
       ▼
5. Local Regex Pre-Filtering (src/prefilter.py)
       └── Early title and snippet filtering without LLM invocation
       │
       ▼
6. Smart Content Enrichment (src/extractor.py)
       └── Fetch link → Parse HTML to Markdown (Trafilatura), isolated per-job
       │
       ▼
7. Batch AI Scoring (src/ai_scorer.py)
       ├── Dynamic batching (default: 6 jobs per batch)
       ├── Model cascade: Primary → Fallback
       └── Bounded HTTP 429 handling (Retry-After)
       │
       ▼
8. Telegram Notification (src/notifier.py)
       ├── HTML job cards for listings above the scoring threshold
       └── Execution summary (Total Fetched, Filtered, Scored, Model Used)
       │
       ▼
9. State Persistence & Commit (data/seen_jobs.json)
       └── Automatic commit via GitHub Actions
```

### File Responsibility Map

| File | Responsibility |
|------|----------------|
| `src/main.py` | Main orchestrator of the entire pipeline |
| `src/models.py` | Pydantic data validation schemas (`JobItem`, `ScoredJob`) |
| `src/state.py` | Persistent state management for `seen_jobs.json` and expiration cleanup |
| `src/ai_scorer.py` | LLM communication, bounded retry, rate-limit handling, JSON scoring schema validation |
| `src/extractor.py` | Web content extraction engine to clean Markdown text |
| `src/prefilter.py` | Regex-based rule engine aligned with candidate profile |
| `src/notifier.py` | Message generator and Telegram notification sender |
| `src/fetchers/direct_apis.py` | Public API and RSS/ATS scraping integration, including parallel HackerNews via `ThreadPoolExecutor` |
| `src/fetchers/search_dorker.py` | Advanced search queries via SearXNG and DDGS with timeout guards |
| `config/profile.yaml` | Central configuration: job preferences, scoring weights, thresholds, scraping batch, LLM parameters |
| `data/seen_jobs.json` | Job listing state storage (managed by GitHub Actions runner) |
| `.github/workflows/radar.yml` | CI/CD runner automation definition |
| `AGENTS.md` | Developer manual and coding agent work standards |

---

## 🔑 Prerequisites (Bring Your Own API Keys)

This project operates on a **BYOK (Bring Your Own Key)** model. To run your own instance, you must provide personal API credentials from your own accounts:

1. **Google Gemini API Key** — Obtain a free or pay-as-you-go API key from [Google AI Studio](https://aistudio.google.com/).
2. **Telegram Bot Credentials** — Create your own bot via [@BotFather](https://t.me/BotFather) to get a **Bot Token**, and retrieve your personal **Chat ID** via [@userinfobot](https://t.me/userinfobot). *(Be sure to send `/start` to your new bot first).*
3. **GitHub Account** — With **GitHub Actions** enabled and repository workflow permissions set to **Read and write**.

---

## ⚙️ Quick Configuration

### 1. Repository Secrets

Add the following three credentials in your repository under **Settings → Secrets and variables → Actions**:

| Secret Name | Description |
|-------------|-------------|
| `GEMINI_API_KEY` | Your personal Google AI Studio API key |
| `TELEGRAM_BOT_TOKEN` | HTTP API token generated by `@BotFather` |
| `TELEGRAM_CHAT_ID` | Your personal Telegram numeric user ID |

### 2. `config/profile.yaml` Configuration

Customize **`config/profile.yaml`** at any time to tailor:

- Your headline, timezone preferences, and **Core Skills**
- Minimum match score threshold (`min_score`) and alert limits (`max_cards_per_run`)
- Target company job boards and search keywords
- **`llm` block**: `timeout_seconds` (default `75.0`), `max_retries` (default `3`)
- **`scraping` block**: `batch_size` (default `6`)

Example structure:

```yaml
llm:
  timeout_seconds: 75.0
  max_retries: 3

scraping:
  batch_size: 6
```

All operational constants are no longer hardcoded in Python source code; adjust them directly in YAML without modifying source files.

---

## 📜 Changelog & Update History

### `v1.3.0` — 2026-11-27 | Pipeline Hardening & Configuration Externalization

- **[Resilience]** **Bounded HTTP 429 Rate-Limit Handling** in `src/ai_scorer.py` — Added `max_retries` (default `3`) with `Retry-After` header support; the final attempt throws an exception to activate the fallback model. Prevents GitHub Actions runners from hanging indefinitely.
- **[Performance]** **HackerNews Fetcher Concurrency** in `src/fetchers/direct_apis.py` — Replaced sequential loop with `ThreadPoolExecutor(max_workers=5)`; each story is isolated in its own worker with `10s` timeout, so a single failure does not cancel other stories.
- **[Performance]** **DDGS Search Dorker Timeout Guard** in `src/fetchers/search_dorker.py` — Added `timeout_sec=15.0` via `ThreadPoolExecutor` to prevent unbounded blocking when DuckDuckGo search is slow or unresponsive.
- **[Configuration]** **Operational Constant Centralization** to `config/profile.yaml` — `llm` block (`timeout_seconds`, `max_retries`) and `scraping` block (`batch_size`) moved from Python code to YAML with safe default values.
- **[Governance]** **Comprehensive `AGENTS.md` Manual** — Architecture documentation, end-to-end pipeline flow, file responsibility map, and coding agent work standards (English language, technical terms in English, prohibition of hardcoded constants, resilience and timeout awareness, non-destructive git actions).

### `v1.2.0` — 2026-11-23 | Precision Filtering & Core-Skill Expansion

- **Title-Level Pre-Filtering:** Added `title_include_patterns` to eliminate non-engineering roles prior to AI evaluation.
- **Zero-Timeout Optimization:** Introduced per-cycle candidate capping (`max_candidates_per_run`) and micro-batching (`batch_size: 6`) to ensure rapid, reliable completion within runner limits.
- **Expanded AI Skill Taxonomy:** Broadened candidate evaluation criteria to capture adjacent high-value roles across Full-Stack AI Web Development, Applied RAG, LLM API Integration, Conversational Assistants, and AI Workflow Automation.

### `v1.1.0` — 2026-11-23 | OpenAI-Compatible Endpoint, Model Fallback & Health Check

- **Lightweight REST Integration:** Migrated LLM evaluation to Google's OpenAI-compatible endpoint (`v1beta/openai/chat/completions`) via `httpx`.
- **Automatic Model Failover:** Configured `gemini-3.5-flash-lite` as the primary scoring engine with automatic fallback to `gemini-3.8-flash`.
- **Pre-Flight Health Check & Telegram Diagnostics:** Added automated LLM connectivity checks, Telegram cycle status reports, detailed API error logging, and resilient JSON sanitization.

### `v1.0.0` — 2026-11-23 | Initial MVP Release

- Launched modular repository structure with multi-source job aggregation, URL normalization, 30-day deduplication state tracking, Markdown content extraction, and HTML-formatted Telegram job cards.

---

## 📄 License

Distributed under the MIT License. Feel free to fork, customize, and deploy your own personal career radar.
