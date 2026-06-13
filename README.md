# Scraper v0.1 — Universal Business Website Evidence Collector

The first stage of the **Universal AI Marketing Campaign Strategist** pipeline.

Given any business URL, this scraper produces a structured manifest of
everything downstream stages will need — text blocks with stable IDs,
visual identity, contact info, forms, links, metadata, language mix,
and a readiness report. **No downstream stage should ever need to
re-fetch the website.**

---

## Quick start

### 1. Install Python deps

```bash
python -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Install Playwright browsers (one time)

```bash
playwright install chromium
```

### 3. Scrape one URL

```bash
python -m scraper https://example.com
```

This will:

1. Normalize the URL and check `robots.txt`.
2. Fetch the homepage with Playwright (rendered DOM + screenshots).
3. Walk discovered internal links and pick the top 7 (HIGH/MEDIUM tier).
4. Fetch each within a 60-second total budget.
5. Extract text blocks, metadata, visual identity, contact info, links, forms.
6. Write everything to `scrapes/<domain>_<timestamp>/`.
7. Print a summary table.

Output:

```
scrapes/example_com_20260514_120000/
├── manifest.json          # the contract for downstream stages
├── raw/
│   ├── 00_homepage.html
│   ├── 00_homepage_full.png
│   ├── 00_homepage_viewport.png
│   ├── 01_contact.html
│   ├── 01_contact_full.png
│   └── ...
└── clean/
    ├── 00_homepage.txt
    └── ...
```

### 4. Run the benchmark

Put 15 real business URLs in `benchmark/urls.txt`, then:

```bash
python -m benchmark.run
```

Produces `benchmark/summary.csv` with a row per URL summarizing
extracted signals. Eyeball it; fix failure modes; rerun.

---

## What's in the manifest

Top-level fields in `manifest.json`:

| Field | Purpose |
|---|---|
| `scrape_meta` | URLs, duration, byte count, version, budget flag |
| `robots` | What robots.txt said and whether we respected it |
| `readiness` | Booleans: `has_homepage`, `has_contact_signals`, ..., `ready_for_extraction` |
| `languages` | Detected language proportions (e.g. `[{ar: 0.7, en: 0.3}]`) |
| `pages[]` | Per-page records: text blocks, forms, paths to artifacts |
| `site_metadata` | Title, description, OG tags, schema.org JSON-LD |
| `visual` | Color palette, fonts, primary button color, logo |
| `contact` | Phones (E.164), emails, WhatsApp, addresses, map embeds |
| `links` | Categorized: internal, social, contact_protocol, external, cta_candidates |
| `images_of_interest` | Only logo, hero, og_image (high-confidence roles) |
| `failures` | Per-failure: code from the fixed `ErrorCode` enum, message, page |
| `notes` | Free-form warnings for debugging |

### Text blocks are the foundation for evidence

Every text-bearing DOM element gets a `TextBlock`:

```json
{
  "block_id": "home_h1_0003",
  "page_url": "https://example.com/",
  "tag": "h1",
  "text": "Premium catering for Cairo events",
  "section": "main",
  "selector": "main > section:nth-of-type(1) > h1",
  "bbox": {"x": 64, "y": 220, "width": 800, "height": 56},
  "above_fold": true,
  "is_link": false,
  "href": null
}
```

Every downstream claim should trace back to one or more `block_id`s.

---

## Architecture

```
scraper/
├── schemas.py          # Pydantic data contract (the single source of truth)
├── errors.py           # Fixed ErrorCode enum
├── config.py           # Constants, bilingual patterns, CTA verbs, social domains
├── url_utils.py        # URL normalization and dedup
├── robots.py           # robots.txt fetch + policy
├── fetcher.py          # Playwright wrapper with bot-detection + scroll-to-load
├── language.py         # langdetect over rendered text
├── readiness.py        # Compute readiness booleans
├── crawler.py          # Orchestrator (the brain)
├── classify/
│   └── page_type.py    # Bilingual EN+AR URL/anchor classifier
└── extractors/
    ├── text_blocks.py  # DOM walker producing TextBlocks (the big one)
    ├── metadata.py     # head tags, OG, schema.org JSON-LD
    ├── visual.py       # ColorThief palette + computed CSS + logo
    ├── contact.py      # phonenumbers, emails, wa.me, map iframes
    ├── links.py        # categorize all <a href>
    ├── forms.py        # form fields, methods, surrounding text
    └── images.py       # logo, hero, og_image only
```

### Design rules

1. **Schemas first.** Every stage reads/writes through `ScrapeManifest`. No raw HTML touching downstream.
2. **No interpretation in the scraper.** Observe, don't infer. "This is the brand tone" is a downstream call; we just record evidence.
3. **Evidence everywhere.** Phones, emails, addresses, and links carry an `evidence_block_id` or page URL.
4. **Failures are structured.** Every failure has a code from `ErrorCode` and a page URL.
5. **Budget enforced.** Hard caps: 60 s wall-clock, 7 internal pages, 20 s per page nav.
6. **Bilingual by default.** EN + AR patterns for page-type classification and CTA detection.

---

## Tests

```bash
pip install pytest
pytest tests/
```

The tests cover URL normalization and the bilingual page-type classifier — the
two pure-Python modules where regressions would silently break the pipeline.

---

## What's NOT in v0.1 (intentionally deferred)

- Sitemap discovery (v0.2)
- Cookie banner handling (v0.2)
- Mobile screenshots (v0.2 if scorecard needs it)
- Marketing-stack detection (Meta Pixel, GA, etc.) (v0.2)
- Numeric page-importance scoring (using tiers only is enough)
- Gallery / product image classification
- Content-hash caching

See `docs/v02-backlog.md` (TODO) for the deferred list.

---

## Troubleshooting

**Playwright fails to launch on first run.** You probably didn't run
`playwright install chromium`.

**Many sites time out.** Some sites have slow servers; the per-page
20 s default is already generous. If a specific site reliably times
out, that's usually bot protection — check the manifest for
`BOT_PROTECTION` or `CAPTCHA_DETECTED`.

**Arabic text shows as `?????` or mojibake.** Check your terminal's
encoding; the files on disk are UTF-8. On Windows: `chcp 65001`.

**ColorThief errors on some sites.** Falls back gracefully — palette
will just be empty. Check `manifest.visual.color_palette`.

**Phone numbers not detected.** The `phonenumbers` library defaults
to `EG` region. If you scrape non-Egyptian sites, edit the
`default_region` in `crawler.py`'s call to `extract_contact()`.

---

## API (Day 1)

A thin FastAPI wrapper around the same pipeline the CLI runs. The
existing CLI still works — the API is purely additive.

### Run locally

```bash
pip install -r requirements.txt
export OPENAI_API_KEY=sk-...                # only needed for LLM runs
uvicorn api.main:app --reload --port 8000
```

### Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET  | `/api/health` | Liveness check |
| POST | `/api/run` | Kick off a pipeline job → returns `{job_id}` |
| GET  | `/api/jobs/{job_id}` | Snapshot: status + full event history |
| GET  | `/api/jobs/{job_id}/stream` | Server-Sent Events stream of stage progress |
| GET  | `/api/jobs/{job_id}/result` | Final BusinessProfile JSON (409 until done) |

### Example flow

```bash
# 1. Start a job (rules-only — no API key needed)
curl -X POST http://localhost:8000/api/run \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://spclinic.net/","skip_llm":true}'
# → {"job_id":"abc123..."}

# 2. Watch the stages stream in real time
curl -N http://localhost:8000/api/jobs/abc123.../stream
# → event: stage
#   data: {"job_id":"abc123","stage":"scrape","status":"started",...}
#   event: stage
#   data: {"job_id":"abc123","stage":"scrape","status":"done","duration_ms":18293,...}
#   ...

# 3. Fetch the final result
curl http://localhost:8000/api/jobs/abc123.../result | jq .
```

### Stage events

Each `data:` payload in the SSE stream has this shape:

```json
{
  "job_id": "abc123",
  "stage": "llm",
  "status": "done",
  "timestamp": "2026-05-16T12:34:56.789Z",
  "duration_ms": 18293,
  "payload": {
    "calls": 4,
    "cost_usd": 0.0094,
    "input_tokens": 3200,
    "output_tokens": 850,
    "model": "gpt-4o-mini"
  }
}
```

Stages: `scrape, rules, evidence_pack, llm, validate, merge, final`.
`status` is one of: `started, done, error`.

### Persistence

By default `POST /api/run` also writes `business_profile.json` to disk
in the same directory as the manifest (`scrapes/<domain>_<ts>/`).
Pass `"persist_to_disk": false` in the request body to skip.

### Notes

- In-memory job store; jobs older than 1 hour after completion are
  evicted. Override via `JOB_TTL_SECONDS` env var.
- CORS allows `http://localhost:3000` by default for the Day 2 frontend.
  Override with `CORS_ALLOW_ORIGINS=...` (comma-separated).
- Single-process only. For multi-worker, swap the JobStore for Redis-backed storage.

---

## Frontend (coming Day 2)

Next.js + Tailwind + shadcn/ui dashboard for the pipeline. See
`frontend/` (currently empty placeholder).
