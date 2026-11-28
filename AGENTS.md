# AGENTS.md — RemoteJob_AI_Radar Developer & Agent Manual

## 1. Project Mission & Core Architecture
`RemoteJob_AI_Radar` adalah sistem pemantau dan kurasi lowongan kerja jarak jauh (*remote work*) otomatis tanpa biaya infrastruktur ($0 cost runtime), berjalan seutuhnya di atas **GitHub Actions** dengan jadwal *cron* setiap 3 jam (`0 */3 * * *`).

Sistem bertugas:
1. Mengumpulkan postingan lowongan kerja dari multi-sumber (*Direct APIs, RSS, ATS, Search Dorking*).
2. Melakukan deduplikasi dan retensi state berbasis masa aktif 30 hari.
3. Memfilter konten secara efisien melalui *Regex Pre-filtering* lokal untuk menghemat token LLM.
4. Mengekstrak artikel/deskripsi bersih via Trafilatura (*HTML to Markdown*).
5. Menilai kecocokan profil kandidat menggunakan LLM (Google Gemini via OpenAI-compatible endpoint).
6. Mengirim kartu notifikasi dan laporan ringkasan status via Telegram Bot API.
7. Memperbarui dan meng-commit *state* persistensi ke repositori.

## 2. End-to-End Pipeline Workflow (Alur Eksekusi main.py)
Setiap agen yang memodifikasi sistem ini WAJIB memahami urutan eksekusi di `src/main.py`:

[Cron / CLI Trigger]
       │
       ▼
1. Load Configuration (`config/profile.yaml`)
       │
       ▼
2. LLM Health Check (`src/ai_scorer.py` -> `check_llm_health`)
       ├── Gagal  --> Kirim Telegram alert & hentikan pipeline (exit early)
       └── Sukses --> Lanjut ke fetching
       │
       ▼
3. Job Ingestion (Multi-channel Dual Path)
       ├── Path A: `src/fetchers/direct_apis.py` (Remotive, ArbeitNow, RemoteOK, WWR, HN, Greenhouse, Lever)
       └── Path B: `src/fetchers/search_dorker.py` (SearXNG instance + DuckDuckGo fallback)
       │
       ▼
4. Deduplikasi & Normalisasi (`src/state.py` -> `JobStateStore`)
       ├── Cek normalisasi URL & kecocokan ID dengan `data/seen_jobs.json`
       └── Eliminasi lowongan yang sudah pernah diproses dalam 30 hari terakhir
       │
       ▼
5. Local Regex Pre-filtering (`src/prefilter.py`)
       └── Seleksi awal judul & snippet (membuang tech-stack non-relevan tanpa memanggil LLM)
       │
       ▼
6. Smart Content Enrichment (`src/extractor.py`)
       └── Fetch link lowongan -> Parse HTML ke Markdown (Trafilatura) terisolasi try/except per-job
       │
       ▼
7. Batch AI Scoring (`src/ai_scorer.py`)
       ├── Batching dinamis (default: 6 jobs/batch)
       ├── Model Cascade: Primary (`gemini-3.5-flash-lite`) -> Fallback (`gemini-3.8-flash`)
       └── Bounded HTTP 429 Rate-Limit Handling (max_retries=3 membaca header `Retry-After`)
       │
       ▼
8. Notifikasi Telegram (`src/notifier.py`)
       ├── Format HTML Cards untuk lowongan dengan skor di atas ambang batas (threshold)
       └── Kirim Ringkasan Eksekusi (Total Fetched, Filtered, Scored, Model Used)
       │
       ▼
9. State Persistence & Commit (`data/seen_jobs.json`)
       └── Tandai lowongan berhasil diproses -> commit & push otomatis via GitHub Actions


## 3. Directory & Responsibility Map
- **`src/main.py`**: Orkestrator utama seluruh *pipeline*.
- **`src/models.py`**: Skema validasi data Pydantic (`JobItem`, `ScoredJob`).
- **`src/state.py`**: Manajemen *state* persistensi `seen_jobs.json` dan pembersihan data kedaluwarsa.
- **`src/ai_scorer.py`**: Logika komunikasi LLM, *exponential backoff*, *rate-limit handling*, dan validasi skema JSON scoring.
- **`src/extractor.py`**: *Engine* ekstraksi konten web ke teks bersih Markdown.
- **`src/prefilter.py`**: Mesin aturan reguler (*regex*) berbasis profil kandidat.
- **`src/notifier.py`**: Generator pesan dan pengirim notifikasi Telegram.
- **`src/fetchers/`**:
  - `direct_apis.py`: Integrasi API publik dan *scraping* RSS/ATS (termasuk HackerNews paralel via *ThreadPoolExecutor*).
  - `search_dorker.py`: Kueri penelusuran tingkat lanjut melalui SearXNG dan DDGS dengan *timeout guard*.
- **`config/profile.yaml`**: Konfigurasi sentral preferensi pekerjaan, bobot skor, ambang batas, *scraping batch*, dan parameter LLM (*timeout*, *retries*).
- **`data/seen_jobs.json`**: Penyimpanan *state* lokal/remote lowongan kerja.
- **`.github/workflows/radar.yml`**: Definisi otomasi *runner* CI/CD.

## 4. Agent Safety Guardrails & Coding Rules
Setiap AI coding agent yang bekerja di repositori ini WAJIB mematuhi instruksi berikut:
1. **Bahasa Komunikasi:** Berikan penjelasan, respons, dan analisis selalu dalam **Bahasa Indonesia**. Pertahankan istilah arsitektur, Git, dan pemrograman dalam **Bahasa Inggris** (*tool calling, AST, context window, rate limit, dry-run, commit, push*).
2. **Perlindungan File Data (`data/seen_jobs.json`):** 
   - JANGAN PERNAH menghapus, me-reset, atau mengosongkan berkas `data/seen_jobs.json`. Berkas ini dikelola oleh GitHub Actions runner.
3. **No Hardcoded Constants:** 
   - Dilarang menanam nilai konstanta operasional (*magic numbers*) di dalam kode Python. Gunakan `config/profile.yaml` dan sediakan nilai *fallback default* yang aman.
4. **Resilience & Timeout Awareness:**
   - Semua panggilan jaringan (HTTP/LLM/Scraping) wajib memiliki *timeout* eksplisit.
   - Panggilan LLM wajib menerapkan *bounded retry* agar tidak membuat *runner* GitHub Actions menggantung (*hang*).
5. **Non-Destructive Git Actions:**
   - Dilarang menjalankan `git reset --hard` atau `git push --force`.
   - Perubahan kode harus selalu diverifikasi terlebih dahulu menggunakan `py_compile` dan uji impor modul.
