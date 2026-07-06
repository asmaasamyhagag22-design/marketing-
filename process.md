# process.md — Universal AI Marketing Strategist

**The single source of truth for this project.** Replaces the historical
change-log. Read this before acting in this repo. Last full revision: 2026-07-04.
Test suite: **1045 passed, 0 failed** (2026-07-05/06; grew from 880 as each audit fix
below shipped with its hermetic regression tests).

**Active work — adversarial audit (2026-07-05):** a deep verified audit found 1 CRITICAL
+ 8 HIGH + a medium/low tail + finder-flagged leads (full list in the session +
`memory/audit-2026-07-05-findings`). Fixed in priority order, one at a time, suite green
between fixes. **C2 (2nd CRITICAL, from a finder lead): the Evidence Ledger falsely
'verified' fabricated numbers** — bare-digit resolution certified "Save 50%" against
"50 years" in the client-facing Compliance Sheet (and passed it through every gate). Fixed
with unit-class resolution (§5.C + §8). Residual: bare-number-vs-bare-number and superlative
subject context are still context-blind (documented follow-up). **ALL CRITICAL+HIGH DONE
(suite 880 → 926):** C1 (phone-region fabrication), H1 (mid-crawl e-commerce budget
re-evaluation), H2 (redirect/duplicate-final dedup), H3 (frontier scheme/slash dedup),
H4 (social-domain exact/subdomain match, no substring), H5 (multilingual CTA verbs),
H6 (poster external-headline grounding gate), H7 (`--trend` now feeds the concept copy),
H8 (salvaged-homepage readiness) — details in §5 + §8. **Medium/low tail — landed:** cookie
false-drop (banner-specific patterns, not `\bcookie`), RSC/code-payload gate, validator
wrong-block_id quote-recovery + word-boundary blacklist, strategy variety + Arabic filler +
even day-distribution, trends stopwords/numeric filter, campaign dispatcher robustness, and
**grounding reputable-web now enforced at ledger-BUILD** (`is_reputable_web_source` in
`from_profile.add` — a web claim sourced only by an aggregator/junk host is dropped for
EVERY gate, not just `pick_angle`; poster keeps a thin alias). **Remaining tail:** the
finder-flagged leads needing re-verification and the un-audited logo/palette pipeline.

---

## 1. Vision (from the concept PDF)

From **one business URL**, produce a complete, on-brand marketing campaign pack —
**poster, short-form reel, competitor-grounded SWOT, multi-day content calendar** —
governed by one non-negotiable principle:

> **Provable zero-hallucination.** Every factual claim in any customer-facing output
> traces to a real, sourced piece of evidence — exportable as an audit trail
> (the Ad Compliance Sheet). Not "AI that makes posters": AI that produces
> agency-grade creative you can PROVE is brand-safe.

**The two truth domains** (the core architectural idea):
- **FACTS** (offers, figures, claims) — extracted deterministically + validated;
  the LLM is an extraction/verification tool, never a source of truth.
- **DESIGN** (words' form, image, layout, story) — creative and free, but bounded by
  the brand's identity and by the verified evidence.

**Universality rule:** works for any vertical, any language, any country. Never add
vertical-specific hacks; category-specific *guidance* selected by a universal signal
is fine (e.g. the restaurant gate, the marketplace offering rules).

The PDF also promises an **Intelligent Media Buying** layer (objective deduction,
competitor live-ads intelligence via the Meta Ad Library API, kill-switch campaign
governance) and enterprise layers (Compliance Sheet ✅ built, A/B/C/D testing packs).
Their status is tracked honestly in §6 (roadmap) — Section-04 media buying is NOT
built yet.

---

## 2. Standing working rules (do NOT violate)

1. **One fix at a time. Measure between fixes.** Never bundle — it obscures causality.
2. **Patterns over single observations.** Measure with numbers before changing the
   scraper or any extraction behavior.
3. No new `BusinessProfile` fields without benchmark evidence.
4. **UNKNOWN is honest.** Never infer a value to make output look complete. A wrong
   competitor/logo/claim is worse than an empty slot.
5. Keep the scraper universal — no vertical-specific logic.
6. Don't build architecture before knowing real failure modes (benchmark first).
7. Be honest about limitations; never over-claim (in code, docs, or to clients).
8. **Keep this file updated** as part of every landed change — feature state, gaps,
   and measured lessons. (This file replaced the old per-change log; keep entries
   CONDENSED here: state + the lesson, not the full narrative.)
9. Every bug the owner catches becomes a **gate + a test**. The gates are the product.

---

## 3. Runtime & operations

- Windows, Anaconda, Python 3.11 — conda env `marketing_scraper`.
  - This machine (Admin): repo at `C:\Users\Admin\Desktop\dev\scraper_v01`,
    env at `C:\Users\Admin\.conda\envs\marketing_scraper`.
  - Other machine (asmaa): repo is the Google-Drive copy (slow — scope searches).
- **Keys (.env at repo root):** `GOOGLE_CLOUD_PROJECT=image-498715` + gcloud ADC
  (Gemini / Imagen / Veo — the ~$300 GCP credit pool), `GOOGLE_MAPS_API_KEY` (Places),
  `SERPER_API_KEY` (SERP; free tier is flaky under bursts), `ANTHROPIC_API_KEY`
  (review themes), `OPENAI_API_KEY` (legacy fallback only). `.env` is gitignored.
- **Model map (deliberate, measured):** extraction = Gemini 2.5 **Flash**
  (evidence-bounded — Pro adds cost, not quality); concept/design/research/story =
  Gemini 2.5 **Pro** (`default_caller(strong=True)`); one-shot poster image =
  `ONESHOT_IMAGE_MODEL=gemini-3-pro-image-preview` (measured quality ceiling;
  3.1-flash passes but follows palette/layout mandates worse); judges/OCR/planner =
  Flash; reel video = **Veo 3.1** (`veo-3.1-generate-001`, Vertex; renders NATIVE
  speech); image edit/upscale = imagen-3.0-capability-001 / imagen-3.0-generate-002.
  **Probe model availability before assuming** (documented 404 lessons).
- **Run:**
  - API: `python -m uvicorn api.main:app --port 8000` — **restart after ANY code
    change** (`--reload` misses new files on Windows; stale servers produced
    "already fixed" bugs twice).
  - Frontend: `cd frontend && npm run dev` (:3000). **Never `npm audit fix --force`**
    (downgrades Next 15 and breaks the App Router).
  - CLI: `python -m scraper <url>` · `python -m business_profile <manifest> -o p.json`
    · `python -m competitor.full_run <url>` · `python -m poster <profile>` ·
    `python -m reel <profile>` · `python -m strategy <profile>` ·
    `python -m campaign <profile> --from-plan plan.json` · `python -m trends "<kws>"`.
- Tests: `python -m pytest tests/ -q` — hermetic (no network/LLM); live paths are
  verified manually and cost money (out-of-CI by policy).

---

## 4. Architecture

```
URL
 └─ scraper (Playwright crawl, universal)          → ScrapeManifest
     └─ business_profile (rules + Gemini + RAG + validator) → BusinessProfile (all fields evidence-cited)
         ├─ competitor (router → Places/SERP → matrix → SWOT → TOWS)
         ├─ grounding  (Evidence Ledger — the central gate + audit + Compliance Sheet)
         ├─ brand      (BrandCreativeDNA / BrandBook — vision understanding of identity)
         ├─ poster     (concept → variation → one-shot OR classic render → QA gates)
         ├─ reel       (story → Imagen stills → Veo i2v + native VO → captions → end-card)
         ├─ strategy   (content calendar) → campaign (fan-out to creatives)
         └─ trends     (free keyless trend sources)
api/ (FastAPI, :8000) + frontend/ (Next 15, :3000)
```

Packages: `scraper/`, `business_profile/`, `grounding/`, `competitor/`, `brand/`,
`poster/`, `reel/`, `strategy/`, `campaign/`, `trends/`, `api/`, `frontend/`,
`benchmark/` (measurement harnesses), `tests/`.

---

## 5. Feature inventory — BUILT ✅ (by subsystem, with the load-bearing details)

### 5.A Scraper (universal ingestion)
- **Adaptive crawl budget**: default 12 pages/150s; e-commerce detected by product-URL
  density (incl. `/plp/`,`/pdp/`) → 30 pages/330s. Light sub-page fetches (block
  images/fonts/media, skip screenshots) ≈20% faster.
  - **H1 mid-crawl re-evaluation**: the store signal is no longer a one-shot read of the
    homepage snapshot (a JS store can under-render it — MEASURED: nahdi flipped 6-vs-24
    pages on the same store, same morning, with a dead sitemap). The frontier is built at
    the ecommerce max cap and the signal is re-run over ACCUMULATED links after each
    subpage; crossing the product-URL threshold upgrades page-cap + time budget once
    (`E-commerce detected mid-crawl` note). Offline-validated: nahdi's failing 6-page run
    had 15 product URLs across the pages it did fetch. ⚠ live re-scrape confirmation of
    the end-to-end page-count recovery is still pending (a paid run).
- **Never homepage-only**: `MIN_SUBPAGE_ATTEMPTS=5` — the budget guard stops the tail,
  never prevents the start (nahdi lesson: dead sitemaps ate the whole budget → 1-page
  scrape of a 300-link store → "no prices").
- **Sitemap stage guards**: per-fetch 5s timeout + consecutive-unreachable breaker
  (2 fails → stop) + 20s stage cap.
- **Deep-seed re-anchor**: a deep content URL re-anchors identity to the site root
  (locale homepages like `/ar-sa` are respected, not stripped).
- **eTLD+1 everywhere** (bundled PSL): subdomain-heavy enterprises (web./eshop.)
  crawl correctly; `.com.eg`-class hosts don't collapse into one key.
- **Links**: per-page dedup by `(href, page, anchor)` — a CTA sharing a nav href is
  never swallowed (daturial "Book a Meeting" lesson; measured corpus-wide, zero junk).
  CTA verbs cover ecommerce/restaurant/Arabic + `explore/استكشف`, and **(H5)** the major
  expansion-market languages (FR/ES/DE/IT/PT/TR) — a French store scored 0 CTAs on 310
  links before; MEASURED +CTAs only on the French site, zero EN/AR inflation (Italian
  "registrati" dropped: it prefixes English "Registration"). CTA detection is still
  verb-list-bound (a truly language-agnostic structural/LLM detector is a follow-up).
  **(H4)** social-platform classification matches a host EXACTLY or as a subdomain, never
  as a substring — the old `dom in host` mislabeled xerox/box/netflix/fedex.com (contain
  `x.com`) as twitter and could strip a subject's own links from the frontier.
- **Frontier dedup (H2/H3 gates)**: the crawl budget is the binding constraint on ~45%
  of scrapes, so a page fetched twice is a real page lost. **H3** collapses http/https +
  trailing-slash variants PRE-fetch via a scheme/slash-insensitive `url_utils.dedup_key`
  (the fetch url stays the faithful `normalize_url` form — forcing https would break
  http-only sites). **H2** dedups POST-fetch on the normalized FINAL (post-redirect) url
  (`_register_fetched_or_skip`), catching different URLs that redirect to one page
  (WordPress internals, empty collections). MEASURED: 9/110 manifests had duplicate
  pages (daturial fetched its homepage 5×; orange.eg http+https+slash) = 22 wasted
  fetches now skipped, with a `redirect_duplicate_skipped` note.
- **Visual identity**: brand palette from **logo pixels + header + footer** (owner's
  rule — page screenshots alone vote photo colors; measured: Orange #000000→#fc6c0c).
  Logo pipeline: host-stripped keyword/brand matching (a CDN named after the brand
  granted 432 promo tiles `brand_name_match` — nahdi lesson), "shop by brands"
  listing penalty, footer-logo rescue (signature = logo_keyword + brand_name_match +
  score≥45), structural-independent floor (a UNIQUE, hosted, site-wide-repeated content-only
  mark for opaque-DOM SaaS-builder sites — §6 elkbabgi), inline-SVG rasterization with
  visibility gate + dark-chip for white logos, contact-icon penalty, raster-over-wordmark
  preference.
- **Content images**: real photos from `<img>`/lazy/CSS-bg collected (`CONTENT` role);
  homepage full screenshot saved + surfaced on the profile
  (`visual.homepage_screenshot_path`).
- **RSC/JS-payload gate** (`content_quality._looks_like_code_payload`): a Next.js React
  Server Components 'flight' payload (`1:"$Sreact.fragment" 2:I[56700,[],"default"]…`) is
  NOT prose. trafilatura's density gate passed it, so pages with ZERO real text blocks were
  flagged `has_meaningful_content=True` and their junk stored as `cleaned_main_text` —
  inflating the pages-with-text diagnostic and feeding the readiness/pricing signals
  (MEASURED: 31 nahdi product pages; detector flags exactly those, 0 false positives on the
  other 514 meaningful pages). Now returns `(None, False)`.
- **Phone region (C1 gate)**: a bare national number (no `+`) is parsed against the
  SITE's own region from a RELIABLE universal signal — URL locale path (`/ar-sa`→SA) then
  ccTLD (`.com.eg`→EG) via `url_utils.region_from_site` — before falling back to the
  home market (`_HOME_MARKET_REGION=EG`). A blanket "EG" had turned the Saudi hotline
  920024673 into a valid-looking WRONG +20920024673 on the flagship demo. `html lang` is
  deliberately NOT a signal (`en-US` boilerplate mislabels EG sites). Measured: nahdi ×3
  → +966…, zero corpus regression on the tel: path.
- **Resilience**: real-UA + transient retry, HTTP/2 fallback, robots respected,
  malformed hrefs never crash, Deep-Search fallback (Serper `site:` recovery) for
  blocked sites, `scraper/net.py` breaker+retry for keyless JSON fetchers.
- **Screenshot failure is non-fatal**: the full-page screenshot runs AFTER html/text/links
  are captured, so its failure must not discard the page. It no longer sets an error_code
  (`_capture_screenshots` flags `screenshot_failed` + a manifest note); visual identity
  degrades gracefully to logo pixels + header/footer colors. MEASURED: azzafahmy.com was
  getting 0 pages (all text/offerings lost) on a SCREENSHOT_FAILED — the same class as H8.
- **Readiness (H8)**: a timeout-SALVAGED homepage that carries real content counts as a
  homepage — `compute_readiness` gates on content (`_homepage_is_usable`), not `not
  p.failures`. The salvage attaches a benign TIMEOUT failure; the old test discarded the
  whole scrape (MEASURED: nahdi 226 blocks + te.eg 87 blocks were marked not-ready). A
  hard-failed homepage never becomes a HOMEPAGE record (early return), so requiring
  content still correctly rejects an empty salvage (buffaloburger 0 blocks).
- **SSRF guard** (`is_safe_public_url`) at API entry + every remote image fetch.

### 5.B Business Profile (grounded extraction)
- Rules layer (deterministic) + 4 grouped Gemini Flash calls; **every field carries
  verbatim evidence** (`block_id` + `page_url` + quote); the validator rejects any
  citation not literally present (quote-glyph folding for Arabic).
- **Validator quote-recovery**: a citation whose `block_id` is wrong (or points at the
  wrong block) but whose quote is VERBATIM in another real block is RECOVERED with the
  corrected block_id, not discarded — a mis-attribution used to throw away real, citable
  evidence. Same substring strictness across all blocks + a length floor so a stop-word
  can't be laundered; a quote in NO block is still rejected (fabrication). (Real recovery
  rate needs a live extraction run — rejected citations aren't persisted to measure offline.)
- **Evidence-pack cookie filter is banner-specific** (2026-07-05): the boilerplate filter's
  `\bcookie` pattern deleted the FOOD "cookie" as if it were a consent banner — losing real
  dessert menu blocks from the pack (MEASURED: 186 blocks over 8 sites — buffaloburger "Cookie
  Dough"/"SPOON ME COOKIE", mcdonalds "Chocolate Chip Cookie"). Now only cookie-CONSENT
  phrasing (accept/reject/manage/use/policy/settings/…) is boilerplate; the food is kept.
- **RAG (Pillar 2)**: full uncapped evidence pack + per-group semantic retrieval
  (Gemini embeddings, cosine top-K in-process — **no vector DB by design** at this
  scale); validator sees the full pack. Measured: te.eg 153→265 blocks seen.
- **Offerings**: category-aware cap (30 default / 12 ecommerce); **marketplace HARD
  RULES** (departments-first from the store's own nav evidence; pack-size/count names
  are SKUs → family once; breadth over depth, one family ≤2 entries) — measured:
  nahdi flipped from "22 coffee-dominated SKUs" to 24 pharmacy departments.
  ⚠ Guidance is keyed by the **rules** category which can be None → the hard rules
  ALSO live in `_generic` as a conditional block (the fix that actually landed).
- **Unsubstantiated-claim blacklist is WORD-BOUNDARY** (2026-07-05): the tokens (halal/iso/
  organic/certified/…) are matched with `\b…\b`, not raw substring. Substring both
  false-rejected real offerings ("iso" inside poison/comparison, "healthy" inside unhealthy)
  and LAUNDERED a claim through a quote that merely contained the substring ("comparison"
  grounding "iso"). Multi-word/hyphenated tokens ("gluten-free", "fda approved") still match.
- Name chrome stripping at the source (Website/E-Shop/الموقع الرسمي), restaurant-gate
  (2+ identity tokens or a menu page), `other_unique_insights` catch-all (consumed by
  SWOT strengths + poster headline pool).
- **Brand name = the BRAND, not a marketing sentence (2026-07-06)**: og:site_name / `<title>`
  is often "Brand - Tagline" or "Brand | categories"; taking it verbatim made the NAME a whole
  sentence (MEASURED: rawafrican.net = "Raw African's Beauty Hub - Get the Raw Experience!"). The
  name is the identity anchor on the poster/reel/dashboard/SWOT, so `_pick_brand_segment` now
  splits on separators and keeps the segment that ECHOES the DOMAIN (rawafrican -> "Raw African"),
  falling back to first-segment (og, brand-first) / shortest (title, legacy). A possessive
  descriptor is trimmed only when a real descriptor trails it AND the head reconstructs the domain
  exactly, so possessive brands that END at "'s" (Levi's, McDonald's) and qualifiers ("Orange
  Egypt") are never touched. Verbatim source stays the cited quote. (`from_metadata.py`; +2 tests.)

### 5.C Evidence Ledger — the moat (`grounding/`)
- **Claim extraction** (AR-aware normalize; tashkeel/alef/ya/digits): significant
  numbers/years, superlatives incl. the `-est` class + `#1/no.1`, first/only,
  credentials **split** award/certification/guarantee (evidence of one never sources
  another), free-offers. Canary test suite guards coverage regressions.
- **Number resolution is unit-class-aware (C2)**: a %/price/duration/scale number is
  'verified' only by evidence carrying the SAME kind of number. The old bare-digit match
  certified fabrications — "Save 50%" resolved against "50 years", "99% pure" against a
  "99 EGP" price — producing FALSE 'verified' rows in the client-facing Compliance Sheet
  AND passing the poster/reel/strategy/TOWS gates. Safe by default: only a positively-
  identified strong unit tightens, so no legitimate claim regressed.
- **Subject-context judge (C2 residual)**: the remaining hole was bare-number-vs-bare-number
  ("100 gifts" ← "100 stores") and superlative SUBJECT ("best coffee" ← "best regards"). A
  token/stem heuristic can't fix this — it can't tell an acceptable synonym/inflection
  ("5000 experts"↔"5000 youth", رقمي↔رقميون) from a fabrication (both are token-disjoint;
  MEASURED: a heuristic broke 4 legit tests). So the ledger takes an OPTIONAL `subject_judge`
  (`grounding.make_subject_judge(caller)`): the deterministic scaffold detects the ambiguous
  token-disjoint case, a CHEAP Flash call decides same-subject (cached, fires only on
  ambiguous claims), and any error/absence → LENIENT (the project's number-only grounding),
  so nothing regresses without a judge. Wired into the poster concept gate. Mechanism is
  hermetically tested (13 tests, mock judge + mock caller). **Live ACCURACY VERIFIED
  2026-07-05** (owner-authorized Flash run, `grounding/measure_subject_judge.py`, 45 labeled
  bilingual EN+AR pairs): **98% (44/45); 25/25 fabrications CAUGHT (0 missed — incl. subtle
  adversarial ones: years-vs-awards, Michelin-stars-vs-locations, purity%-vs-count); 19/20 real
  claims kept** (the 1 error is a SAFE over-block on a borderline AR "largest pharmacy" vs
  "biggest pharmacy chain"); 0 abstentions. The lenient-when-unsure bias did NOT wave through any
  fabrication — the moat's strict mode holds. Re-run: `python -m grounding.measure_subject_judge`.
- **Source tiers**: brand site > web snippet (web must be reputable; media outlets are
  reputable EVIDENCE but are NOT competitors — two separate host-lists). The reputability
  check runs at ledger-BUILD (`is_reputable_web_source` in `from_profile.add`), so a claim
  sourced only by an aggregator/junk host is unsourced for EVERY gate — not just
  `pick_angle`, which was the only enforcer before. `poster._is_reputable_source` is now a
  thin alias delegating to the shared `grounding` predicate (single source of policy).
- Language-aware resolution (Arabic claim cites Arabic quote; mismatch labeled).
- **Blocking gates live on**: poster concept copy (soften/drop/regenerate + remediation
  log), research angles (`pick_angle`), calendar hooks/angles (blank-to-topic), reel
  captions + voiceover lines + hook (drop-to-grounded).
- **Per-asset audit trail** sidecars (`.audit.json`) + **Ad Compliance Sheet**
  (`grounding/compliance.py`): claim → verified(source URL+quote) / softened / dropped
  / no-checkable-claims; verdict PASS/NEEDS_REVIEW; shown & downloadable in the web UI
  and written as `.compliance.json`. Coverage block states honestly what is NOT yet
  gated (see §6).

### 5.D Competitor intelligence & SWOT
- **Router**: LOCAL→Places · ECOMMERCE→SERP · HYBRID→both · UNKNOWN→SERP (never skip).
- **Places path**: adaptive peer discovery + reviews; **subject's own listing** found
  by domain / exact name / cross-script brand-unanimity (Arabic listings for a Latin
  profile name) → fills the rating/volume THREAT quadrant.
- **SERP path (globally robust — the layered design)**:
  1. **LLM query planner** (Flash, ~$0.001): writes the query a real customer would
     type — right language + market (market inferred from any evidence incl. URL
     locale `/ar-sa`); brand-name leakage dropped. (Deterministic identity-terms +
     market-hint remain as the no-caller fallback.)
  2. Aggregator/marketplace/directory denylist + media/listicle host list.
  3. Relevance gate (identity-term overlap on title/snippet/URL).
  4. **Reject-only LLM judge** ("when unsure, DROP — a wrong competitor is worse than
     a missing one"); judge failure keeps all (never breaks discovery). Its keep-list is
     REQUIRED (2026-07-05) so an OMITTED judgment can't be read as pydantic's default `[]`
     and silently drop every real peer; an explicit `[]` is still a genuine "keep none",
     and a drop-all is logged for traceability.
  Measured: nahdi 0 → 4 real Saudi pharmacies; El Ezaby math-test peers eliminated.
- **Lite peer scrape** on the sync web path: plain-HTTP homepage → cheap comparable
  dims (social/CTA/WhatsApp/booking); unknown stays UNKNOWN. A JS-only shell (no anchors in
  the server HTML) now returns None (UNKNOWN) instead of "0 social / no WhatsApp" — that
  absence is JS-hidden, and evidence-of-absence must not read as knowledge (rule 4). A REAL
  page with genuine zeros still reports them.
- **SWOT**: mechanical synthesis from the gap matrix (every item cited);
  `claim_strength` ladder (validated / directional_not_validated /
  internally_supported); own-site S/W floor in competitive mode; review-theme
  complaints → Threats, unmet needs → Opportunities; standalone degrade never empty.
- **TOWS grounding gate fails CLOSED** (2026-07-05): a ledger error on a strategy's text
  now returns not-grounded → the pairing keeps its GROUNDED deterministic template instead
  of shipping the LLM's unverified text (was fail-open — an error let unverified strategy
  copy through the moat; the pairing is kept either way, so failing closed loses only LLM
  phrasing, never a fabricated claim).
- **TOWS layer** (adopted from teammate Rawda's BI platform — HER synthesis thinking,
  OUR grounding; her prompt-only trust model was explicitly not taken): SO/ST/WO/WT
  strategies with anchors validated against real SWOT ids, Ledger-gated text
  (fabrication → grounded template), ranked priority actions + posture. In result.json
  and the web UI. Competitors are LISTED in the UI (name/site/rating/why-selected).

### 5.E Poster Studio
- **One pipeline** (CLI = web): DNA → research → concept → variation → engine → gates.
- **BrandCreativeDNA**: Gemini-Pro vision over the brand's real ads (tiered ownership
  filter: own site/social, or reputable portfolio WITH the brand named) **+ the
  homepage screenshot as always-available identity evidence** (the page AS DESIGNED is
  identity by construction; embedded photos may be stock/supplier — the prompt reads
  design SYSTEM, not photo subjects). Cached per brand in `outputs/brandbooks/`.
- **Concept** (Pro): one campaign idea → copy derived from it. Language lock
  (AR = zero-Latin, validated + regenerated), دليل/proof gate, copy critic,
  **Ledger enforce** (+ live web research facts feed both the prompt AND the ledger so
  researched numbers survive), remediation log.
- **Copy variation engine**: per-run rhetorical FORM (question/statement/command/
  benefit/contrast/number-lead/story) × VOICE (direct/playful/premium/urgent/warm/
  expert) — kills the fixed hook+proof formula; facts stay gated regardless of form.
- **External-headline grounding (H6)**: an override headline — `--headline`, a content
  calendar hook OR **topic** (the calendar `topic` is ungated in the strategy layer), or a
  trend — is verified against the Evidence Ledger before it replaces the gated concept
  headline (`_verified_external_headline`); an unsourced claim falls back to the grounded
  concept headline. Previously a calendar topic like "Egypt's #1 pharmacy" rendered
  verbatim, bypassing the moat.
- **Trend-aware concept (H7)**: `--trend` fetches on-topic trends and threads them into the
  concept prompt as INSPIRATION (`trend_context`), so a trend shapes the copy's angle while
  the grounding gate still blocks any fabricated claim. Was a silent no-op on every
  campaign-dispatched poster (trends were read only inside the `--research and no headline`
  branch).
- **Design variation**: mood/lighting/composition/energy + per-run font pairing.
- **ONE-SHOT engine (default web engine)** — Gemini image model composes the whole
  creative; hard gates:
  - concept scene mandate (ONE idea, execute THIS scene; ≤3 props; calm text zone;
    TEXT CONTRAST non-negotiable),
  - **brand integrity**: logo only as the attached real asset; NEVER paint the brand
    onto objects (painted-brand OCR gate: >2 brand lines → reject),
  - **REAL PRODUCT PROPS**: up to 2 quality-gated real product photos attached; their
    OCR'd real labels become ALLOWED text; invented labels (≥3 junk lines) → reject
    ("real medicine with its real name" — the owner's rule),
  - character-exact OCR **verbatim-copy gate** (Arabic-aware; dialect-preserving OCR),
  - **art-critic vision QA** (clutter/contrast/focal) with retry + best-attempt.
  Falls back to the **classic engine** (adaptive background STYLE-first→outpaint→t2i,
  letterbox trim, 2x upscale, free-form LLM layout + marketing archetypes, lockup
  typography, emerging scrim, adaptive logo plate, brand fonts) — never an error.
- **Language option** (auto/ar/en) end-to-end; audit + compliance sheet on every
  poster; engine + model surfaced in the UI.

### 5.F Reel Studio
- **Pipeline**: brand story (Pro) → Imagen stills (DNA imagery themes, natural skin,
  no colour dye — the "purple people" lesson) → **Veo 3.1 image-to-video** per scene
  (real motion) → xfade assembly → brand end-card → kinetic caption overlay.
- **Video provider = Veo 3.1, the ONLY i2v engine** (`veo-3.1-generate-001` on our Vertex
  project). `default_video_provider()` AUTO-selects our provisioned Veo. **Runway was REMOVED
  2026-07-05** (owner directive): a stale len-132 `RUNWAY_API_KEY` in `.env` had silently
  overridden Veo (the factory preferred Runway whenever the key was present) and Runway returned
  HTTP 400 on every scene → the reel degraded to Ken-Burns stills, no real motion (seen in the
  end-to-end demo; the Veo re-run produced real cinematic motion). The `RunwayProvider` class and
  all `RUNWAY_API_KEY` branches are gone; AIML remains an opt-in Veo-3.1 gateway via
  `REEL_VIDEO_BACKEND=aiml`. NOTE: the leftover `RUNWAY_API_KEY` in `.env` is now inert — safe to
  delete (owner action; `.env` is never touched by code). 6 hermetic precedence tests.
- **Story**: IDENTITY ANCHOR (the world must be unmistakably what the business IS;
  first/last scenes especially; offerings are a SAMPLE = props only — the "pharmacy
  became a coffee ad" lesson) + **diverse offering sample** (dedup by family, from the
  full profile) + description as the world anchor + recurring protagonist +
  DNA themes + fresh Ledger-gated hook (not the verbatim tagline).
- **Native voiceover**: Veo speaks the story's lines — ONE consistent **narrator**
  (gender/age/tone, repeated in every scene clause; lines are one continuous
  narration, grammatical gender locked incl. the hook, neutral viewer address).
  Captions + voiceovers + hook all pass `grounded_captions` (drop-to-grounded).
- **Audio chain correctness** (measured 0ms A/V gap): per-clip `apad=whole_dur`
  (never `apad`+`-shortest` — muxer overshoot), acrossfade mirrors xfade, endcard
  apad, overlay without `-shortest`.
- Kinetic typography overlay (hero/support lockup, RTL-correct via Chromium, pill CTA,
  safe margins), persistent corner logo fading into the end-card, calm pacing
  (~4s shots), image-quality gate on any real photos, Ken-Burns per-scene fallback,
  free edge-tts backend for the CLI voiceover path, language option (auto/ar/en).
- **Caption TYPE is tone-aware (2026-07-05 polish)**: a luxury/fashion/beauty brand
  (`_reel_theme` off tone_of_voice + category) renders the hero in a refined display SERIF
  (Fraunces / Amiri for Arabic), title-case, ivory-warm, italic accent word — instead of the
  chunky Oswald uppercase that read "سخيف" on a jewelry reel. Hero size now caps by the LONGEST
  word so a wide serif word never overflows the frame. Non-elegant brands keep the punchy bold.
- **Voice-over rebuilt (2026-07-05 polish)**: was per-scene (a SEPARATE synth call each scene →
  the voice/energy CHANGED every scene) and hard-trimmed to the scene length (chopped long lines
  mid-word → "بيقطع"). Now ONE continuous script → ONE call → ONE voice/performance, TIME-FIT to
  the footage (gentle `atempo` only if it runs long, else pad — never a mid-word cut). The
  delivery brief is tone-aware and no longer hardcodes an "appetizing food ad" (a vertical leak).
- **End-card redesigned — logo always visible, elegant, no fake button (2026-07-06)**: the brand
  end-card put the LOGO on the brand's OWN primary colour, so a GOLD jewelry logo VANISHED on a
  gold ground (owner: "انت بظت اللوجو"); the name was chunky sans ("الكلام بشع"); and a solid
  white "Catalog" BUTTON sat in a non-interactive video ("الزار دا إيه لازمته"). Now: the
  background is chosen by the LOGO's luminance — a light/gold/white logo gets a DEEP brand-tinted
  charcoal card (the real luxury gold-on-black look), a dark logo gets a brand-tinted IVORY card —
  so the logo ALWAYS has contrast, plus a brand-colour halo behind it. Typography is tone-aware
  (refined **Fraunces/Amiri serif** for luxury via `_reel_theme`, clean Space Grotesk otherwise).
  The fake button is gone: elegant cards show the brand URL as the real "where to go"; non-elegant
  cards use a hairline outlined chip. VISUALLY VERIFIED across 3 archetypes (Azza Fahmy gold→dark,
  As-Salam navy→light, Orange orange→dark). (`endcard.py`; +5 hermetic tests.)
- **Creative-director is tone/vertical-aware (2026-07-06)**: the Opus reel director's system
  prompt hard-coded FOOD dynamics into EVERY reel ("steam/smoke, flames, mouth-watering") — wrong
  for a jewelry house. `_vertical_mode(profile)` now swaps the motion + delivery vocabulary:
  **elegant** (luxury tone OR jewelry/fashion/accessories) directs the product WORN / admired on
  skin, light glancing off metal & stones, refined slow moves, grace — no food dynamics; **food**
  keeps the appetising motion; **generic** stays neutral. Every mode now asks for ONE coherent
  STORY arc (heritage-aware: tell the REAL founding story, never invent) and enforces a
  MINIMAL-TEXT policy — a caption on AT MOST the hook + CTA scene, empty for all others (owner:
  "الكلام مكتوب بشوع… يبقا قليل"). LIVE-VERIFIED on Azza Fahmy (luxury→elegant): a celestial
  heritage story, jewelry "resting on skin / worn on an elegant hand", captions on only 2/5 scenes.
  (`creative_director.py`; +4 hermetic tests.)

### 5.G Strategy, Campaign, Trends
- `strategy/`: N-day content calendar (Gemini or deterministic), hooks/angles
  Ledger-gated (blank-to-topic), `.audit.json` sidecar. CLI-only for now.
  - **Fallback quality (2026-07-05)**: items spread EVENLY over the whole window (was
    front-loaded — a 30-day/17-item plan filled only days 0-16, tail empty); the last-resort
    filler is LANGUAGE-matched (an Arabic brand no longer gets hardcoded English topics that
    render as English poster headlines — the language lock); the real `tagline` is used as
    one more grounded topic; the LLM prompt carries a language directive + "spread evenly".
    (True topical VARIETY on a single-offering brand still needs the LLM path — the
    deterministic degrade cycles format/platform.)
- `campaign/`: calendar → poster/reel jobs fan-out (`--from-plan`, `--dry-run`).
  - **Robustness (2026-07-05)**: `plan_creatives` tolerates a hand-edited/malformed plan
    (non-dict calendar / missing `items` / non-dict item → skipped, no traceback); `run_all`
    catches a per-job launch failure so ONE bad job no longer aborts the whole fan-out
    (records it rc=1, continues); the CLI now returns NON-ZERO when any creative failed (a
    silent exit 0 hid failed renders from automation) and rejects an out-of-range `--only`.
- `trends/`: free keyless sources (HN/Reddit/Dev.to), normalized ranking, profile
  keyword matching; feeds poster `--trend` and strategy `--trends`.
  - **Relevance + resilience (2026-07-05)**: the sources are TECH-skewed, so keyword matching
    dropped bare years/numbers + a broader generic/tech-ambiguous stopword set — a non-tech
    brand no longer false-matches an irrelevant tech trend into its copy (MEASURED: 24/45
    corpus profiles false-matched a sample tech title before, 0/45 after). `fetch_trends`
    now LOGS a down/schema-drifted source instead of silently swallowing it. (Deeper
    relevance — the "apple" ambiguity — still wants an LLM judge or better sources: follow-up.)

### 5.H Web app
- Scrape pipeline with SSE live progress; tabs: Profile / Evidence (citations) /
  SWOT (competitors list, quadrants with strength badges, TOWS, notes incl. discovery
  diagnostics) / Diagnostics / **Poster Studio** (engine toggle, language, versions,
  compliance sheet + download, CTA button) / **Reel Studio** (language, versions,
  mode label, download).
- API: `/api/run` (async job + SSE), `/api/swot/from-profile`,
  `/api/poster/from-profile`, `/api/reel/from-profile`, `/api/health`, `/` hint page.
- **Baseera dashboard** (`dashboard/build.py`, `python -m dashboard <competitor.json> --profile
  --plan --poster --out`): ONE self-contained HTML page (inline CSS + base64 images + system
  fonts, NO external CDN/web-fonts — opens & publishes anywhere) that "prints everything" from a
  run in the Baseera design language — brand + KPIs, the CITED SWOT (citations + claim-strength
  badges on screen = the moat visible), discovered competitors (peer-fit + why-selected), the
  TOWS strategies + posture, the content calendar, and the embedded poster. 3 hermetic tests.
- **One-command demo** (`dashboard/run.py`, `python -m dashboard.run <url> [--fast] [--open]`):
  a URL in, a finished dashboard out — drives the real pipeline as subprocesses
  (competitor.full_run → strategy → poster(one-shot) → dashboard), each stage best-effort with a
  clean stage-by-stage progress log for a LIVE demo. `--fast` skips the poster for speed.
  `run_pipeline(..., on_progress=(event,label,msg)→None)` streams stage boundaries to a live UI.
- **Everything in one dashboard (2026-07-06)**: the dashboard now embeds the **reel** (an inline
  `<video>`, base64 so the page stays self-contained) alongside the poster in the Creative section
  (`build_dashboard(..., reel_path=)`, `python -m dashboard --reel`). `dashboard.run` grew a reel
  stage (Opus-directed, Veo 3.1, best-effort, `--fast` skips it) and the live server's progress
  chips include it, so a full run produces a dashboard showing profile → SWOT → competitors → TOWS
  → calendar → poster → **reel** in one place (owner: "كل حاجة تظهر في الداش بورد"). VISUALLY
  VERIFIED (poster + 9:16 reel player + evidence note render side by side). +2 tests.
- **Local INTERACTIVE studio** (`dashboard/server.py`, `python -m dashboard.server [--port 8770]
  [--no-open]`): the owner wanted to sit IN the dashboard and DRIVE it, not get a one-shot report
  ("عايزة أبقى في قلب الداش بورد… أجنريت صورة… أطلّع الفيديو… أشوف السوات"). Flow: paste a URL →
  **Analyze** streams the FAST core over SSE (`GET /analyze?url=` → scrape/profile/competitors/SWOT
  /calendar, NO heavy generation) → redirect to `GET /studio?slug=`, an interactive page that
  embeds the report (hero/KPIs/cited SWOT/competitors/TOWS/calendar via `build_dashboard_html`,
  standalone=False) PLUS a **Creative Studio** with on-demand **Generate/Regenerate** buttons:
  `GET /generate/poster?slug=` and `/generate/reel?slug=` stream progress over SSE, then the asset
  loads in-panel from `GET /asset?slug=&kind=` (poster PNG / reel MP4, Range-served, slug-guarded).
  `GET /dashboard?slug=` exports the full self-contained dashboard. `run.py` was split into
  `analyze` / `generate_poster` / `generate_reel` / `build_dashboard_file` (composed by the CLI
  `run_pipeline`). Stdlib-only (`http.server` + threads). 8 hermetic tests (pipeline FAKED —
  analyze→studio→generate→asset flow, slug guard, SSE framing). VISUALLY VERIFIED (studio renders
  report + poster/reel panels with Regenerate).

---

## 6. Honest gaps & known limitations (current)

- **Logo threshold calibration (RESOLVED 2026-07-05 — structural-independent floor)**:
  elkbabgi.com (= its diplomatic-lark Strikingly subdomain; ONE site captured 8×) has a real
  header logo that scored **54** — `logo_keyword`+raster+`suitable_logo_shape`+`repeated` — and
  missed the 55 gate by 1 because a SaaS site-builder's opaque DOM denies EVERY structural
  signal (in_header/near_nav/links_to_home). Visually confirmed genuine (gold crowned-lion mark).
  Fix: a last-resort `_floor_ok` conjunction in `_choose_primary_logo` (`scraper/extractors/
  visual.py`) — promote a content-only mark ONLY when it's a HOSTED raster (not `data:`),
  logo-named, logo-shaped, repeated site-wide (≥4), penalty-free, AND the UNIQUE such image on
  the page. Threshold/weights UNCHANGED (a conjunction adds no points — cannot regress a passer
  or shift a score). Two guards, both adversarially found & closed: (1) the uniqueness check
  refuses a third-party logo-WALL (press/client/payment tiles named `*-logo.png` — the multi-
  tile ambiguity we can't disambiguate without structure → honest UNKNOWN); (2) the floor runs
  AFTER footer-rescue so a real footer logo is never suppressed. The `data:` guard refuses the
  measured marasim "Client Five logo" placeholder twin (byte-identical reason set to elkbabgi).
  MEASURED (real patched selector, floor on-vs-off over 110 manifests): **+8 gained / -0 lost /
  0 changed** — the elkbabgi cluster and nothing else; re-score harness validated 8080/8080
  candidate scores. 7 hermetic tests in `tests/test_visual_identity_v02.py`. Chosen over a
  threshold-nudge (promotes a bare near-nav wordmark at 54) and a repeated-cap bump (promotes
  the marasim twin) via a design panel + 3 adversarial verifiers. The 16 no-logo corpus sites
  are FAILED/BLOCKED scrapes (bot wall, robots, HTTP error, timeout), not logo-pipeline bugs.
  WATCH-ITEM: the floor rests on the ambient `logo_keyword`; if a HOSTED client-strip FP is ever
  seen, add "client"/"clients"/"our-clients" to `PARTNER_KEYWORDS` (auto-voids via
  `classified_partner_logo`) — NOT by lowering `_FLOOR_MIN_REPEAT`.
- **Palette calibration (INVESTIGATED 2026-07-05 — NOT a current bug; measure-first)**: the
  audit flagged pale-blue primaries on iti.gov.eg (#c5d6e9) and te.eg (#91a8bc) beating the
  real maroon/purple. An OWNER-AUTHORIZED live re-scrape (8 sites; the palette's `color_signals`
  input is NOT persisted, so offline re-score was impossible) proved these DON'T reproduce on
  current code + homepage: te→#54249c purple ✓, orange→#fc6c0c ✓ (stale said #000000), iti
  homepage→#203947 navy (maroon also in-palette) — a defensible two-color brand — and
  vodafone/kfc/mcdonalds unchanged-correct. The stale misses were ARTIFACTS: te = old-code
  staleness (same URL now correct); iti = identity taken from a DEEP track page whose only strong
  signal was a pale button (`button_bg rgb(197,214,233)`, `palette_dominated_by_background`).
  Current crawler already anchors deep seeds to the site root for identity
  (`url_utils.site_root_if_deep`: iti deep→`iti.gov.eg/`), so the homepage drives identity and
  the miss can't recur. NO scoring change made (don't change what measured-correct). Pinned with
  a regression test (`test_saturated_brand_color_beats_a_pale_high_dominance_button`).
- **End-to-end live demo (2026-07-05, eg.azzafahmy.com) — remaining problems surfaced** (the
  pipeline ran all 7 stages; the moat + QA gates behaved honestly; these are the open weaknesses):
  1. **Poster garbled Arabic logo — FIXED (one-shot) + routed 2026-07-05/06.** The image model
     re-draws/bakes the brand logo and garbles Arabic ("عزة فهمي"→"ةفهمص"). **One-shot engine:**
     the prompt now RESERVES a clean corner (draws no logo), the logo is not attached to
     generation, and `poster.pipeline._overlay_real_logo` COMPOSITES the real logo asset there
     deterministically (PIL, opaque plate + soft shadow) — pixel-exact, never garbled. **Classic
     engine (default):** its Imagen STYLE background bakes a garbled logo at an UNPREDICTABLE
     location (measured on Azza Fahmy: bottom-right ~96%h) — trying to "cover" it is unwinnable
     whack-a-mole (it just adds a competing logo), so we do NOT patch the classic path. Instead:
     (a) an ARABIC-copy brand with a logo now auto-prefers the one-shot engine; (b) a new
     `python -m poster --engine oneshot` flag lets ANY brand use it (needed for an Arabic-LOGO
     but English-COPY brand like Azza Fahmy, where the copy-language signal is absent). The
     classic garble that remains is caught by the vision-QA gate (pass=False, flagged not shipped).
     3 hermetic tests (reserve-corner prompt; deterministic composite; unchanged).
  2. **`creative_dna` vision 400 `Provided image is not valid` — FIXED 2026-07-06.** A single
     undecodable brand-ad reference (an SVG, a truncated download, an HTML error page returned as
     bytes) 400'd the WHOLE vision call → the brand lost its DNA signal. Fix:
     `brand.creative_dna._sanitize_vision_images` decodes + re-encodes every reference to a clean
     JPEG the model accepts and DROPS the undecodable, before the call; if none survive, vision is
     skipped honestly (`used_vision=False`). Tests feed valid tiny images now.
  3. **Trends sources tech-centric — FIXED 2026-07-06.** HN/Dev.to/generic-Reddit gave a jeweller
     "buttons/AI/compilers". Now sources are VERTICAL-AWARE (`trends/sources.py`): a new
     `SerperTrendSource` searches the brand's own salient keywords + "trends" via the configured
     SERP provider (the reliable consumer source — measured: Azza Fahmy → Forbes/Elle/Marie
     Claire/Net-a-Porter "Jewelry Trends 2026"); Reddit picks subreddits by vertical (jewelry →
     r/jewelry,femalefashionadvice; food → r/food …, best-effort since Reddit's public JSON is
     largely blocked now); the TECH feeds (HN, Dev.to) are added ONLY for a brand with a WHOLE
     tech keyword (word-level match, so "techniques"/"keychains" don't drag them in — the measured
     bug). `python -m trends` now loads `.env` for the SERP key. 3 hermetic tests.
  4. **Social links absurdly over-counted — FIXED 2026-07-06.** `social_presence` counted SHARE
     buttons as accounts (Azza Fahmy: 20 "social links" = facebook/sharer.php, twitter/intent/tweet,
     pinterest/pin/create/button on every product page — only 5 real accounts). `_social_platform`
     now returns None for a share/intent URL (`scraper.extractors.links._is_share_url`: path markers
     + a `?u=/url=/text=http` query), so a share button is never a social account. Fixes the bogus
     "23 social links above peer average" SWOT strength. 1 hermetic test.
  5. **Poster logo had an ugly white PLATE — FIXED 2026-07-06.** `_overlay_real_logo` drew an opaque
     box behind the mark (needed once for the reverted classic-cover attempt). The one-shot reserves
     a clean corner, so the real logo is now placed DIRECTLY with only a soft drop-shadow — no plate.
- **Reel is still officially UNGATED in the coverage block**: captions/voiceover/hook
  ARE gated, but Veo extends speech beyond the provided lines (ungated model speech)
  and there is no per-reel audit trail yet. → closing items in §7 Phase 1.
- **Classic poster path** can still bake garbled labels in STYLE backgrounds (the
  junk-label OCR gate covers one-shot only).
- Offerings family names can come out in English on an Arabic site (cosmetic; output
  copy is language-locked anyway).
- Deterministic (no-LLM) reel scene fallback still uses the brief's capped offerings.
- Media buying (PDF §04) does not exist in code. A/B/C/D packs: variation engine
  exists, no batch endpoint. Funnel/TOFU-MOFU-BOFU/media-plan: not built.
- Productization: no auth / rate limiting / cost caps or tracking / CI / Docker;
  jobs are in-memory (restart loses them); poster/reel routes are sync-blocking
  (~1-3 min / 10-15 min) with a spinner-only UI; Windows-only tested.
- SSRF: DNS-resolve-time check (TOCTOU/rebinding + crawler-followed links deeper gate
  pending). Serper free tier throttles bursts.
- Old scrapes/profiles don't carry the new fixes — **re-Analyze before judging**.
- **Phone region residual (C1)**: a non-Egyptian business on a GENERIC TLD (.com/.net)
  with NO locale path can still fall back to EG and mis-parse a bare national number —
  the honest edge of what a universal signal can prove. Sites with a ccTLD or `/xx-yy`
  locale are correct. (Reliable-signal-else-EG chosen over drop-if-unknown to avoid
  regressing the many Egyptian .com sites; drop-if-unknown is a one-line change if the
  zero-fabrication bar must be absolute.)

---

## 7. Roadmap — in order

### Phase 1 — finish the PDF's shipped story (highest value / lowest effort first)
1. **Reel brand-safety completion**: transcription gate on the full Veo audio
   (transcribe → Ledger-audit → mute/regenerate on unsourced hard claims) +
   `reel/audit.py` per-asset trail → move reel to GATED_SURFACES.
2. **Compliance Sheet for the calendar** in the web UI (transform exists; wire like
   the poster's).
3. **A/B/C/D testing pack**: one endpoint/button → N variants (seeded variation:
   different form/voice/layout/scene per variant) + a pack manifest; each variant
   carries its own compliance sheet. (PDF enterprise feature; engine already exists.)
4. **Calendar + campaign in the web UI** (strategy is CLI-only today).
5. **Async jobs for poster/reel** (reuse the scrape job/SSE pattern) — progress
   stages instead of a 15-minute spinner.
6. Classic-path junk-label OCR gate (parity with one-shot).

### Phase 2 — PDF Section 04: Intelligent Media Buying (the unbuilt half of the pitch)
7. **Objective deduction** from profile+SWOT (lead-gen vs conversion vs awareness) —
   rules + one Gemini call over data we already have; output = a cited objective memo.
8. **Competitor live-ads intelligence**: Meta Ad Library API (official, free) —
   competitors' running ads → longevity = proven winners; platform/format inference.
   Feeds the SWOT (ad-presence dim) and the media plan.
9. **Media plan report**: budget split, platform per segment, target CPA — consumes
   profile + SWOT + objective (report only; no spend execution — human stays in
   control, per the PDF).
10. **Funnel-aware pack** (TOFU awareness reel / MOFU proof poster / BOFU conversion
    ad) — a consumption layer over existing generators.
11. Campaign governance (kill-switch rules, fatigue prediction) — needs live campaign
    data; design the schema first.

### Phase 3 — productization (before any external/paid exposure)
12. Auth + per-key rate limiting; cost tracking + per-run caps (a reel ≈ 10 paid
    calls); job persistence; Docker/Linux; CI (GitHub Actions: pytest + tsc).

### 💡 Suggested additions (NOT previously requested — clearly marked)
- **(💡) Brand Kit export**: one JSON/PDF per brand (logo assets, palette, fonts, DNA,
  voice) — reusable across campaigns and a nice client deliverable.
- **(💡) Multi-format renders**: same creative → 1:1 post, 9:16 story, 16:9 banner
  (the one-shot prompt is ratio-parametric; cheap win for the testing packs).
- **(💡) Approval workflow**: a "draft → approved" state on each asset in the UI with
  a reviewer note — makes the PDF's human-in-the-loop explicit and sellable.
- **(💡) Performance feedback loop**: paste/import post metrics per published asset →
  feed winning form/voice/layout back into the variation engine (real "learning" media
  buyer over time; pairs with Phase 2).
- **(💡) Cross-run brand memory (lightweight vector store)**: only when multi-client
  SaaS starts — cache embeddings + DNA + research per brand across sessions.
- **(💡) Watermark/draft mode** for unapproved renders (protects against accidental
  publishing of ungated drafts).
- **(💡) Competitor visual benchmarking**: run the DNA vision step on competitors' ads
  (once Ad Library lands) → "their visual language vs yours" slide in the SWOT.

---

## 8. Measured lessons (never re-learn these — condensed from the old change-log)

**Generation:**
- Imagen/image models BAKE raw hex codes and any quoted text into pixels → palettes by
  NAME only in image prompts; verbatim copy only in the one-shot (whose OCR gate
  verifies it).
- STYLE-conditioning on text-heavy brand ads reproduces GARBLED text — attach real
  assets (logo/products) for fidelity; use DNA as TEXT for style.
- Veo/Imagen/Gemini model availability differs per project/region — **probe before
  building** (veo-3.1-preview 404'd for weeks; image models resolve on
  location="global").
- Coloured "brand" lighting on people = alien skin; brand colours belong to
  environment/props, never skin (reel + ITI de-RGB lessons).
- ffmpeg: `apad`/infinite-src + `-shortest` OVERSHOOTS (muxer interleave race) — pad
  to explicit durations; `-shortest` only with finite streams. libass can't shape
  Arabic — all text via Chromium capture.
- Vision OCR readers silently "correct" Arabic dialect (أكتر→أكثر) — demand
  character-exact, dot-counting OCR in gates.

**Extraction/scraping:**
- Serialized (dict) vs object profiles: EVERY adapter must unwrap
  `{"value":...}` — this class of bug appeared 3 times (discovery query, matrix dims,
  web engine).
- The offerings guidance is keyed by the RULES category (often None) — universal
  instructions must live in the generic branch too.
- A CDN host that contains the brand name poisons ANY substring brand-match — always
  host-strip before keyword matching.
- Deterministic heuristics for language/market/identity hit ceilings fast — the
  pattern that works: deterministic scaffolding + ONE cheap LLM call at the point of
  infinite variety (query planning, relevance judging), with reject-only/fallback
  contracts so the LLM can never fabricate.
- `same_registrable_host` must be real eTLD+1; naive last-two-labels breaks .com.eg.
- `normalize_url`'s output is the FETCH url, not just a dedup key — forcing a scheme
  there would break http-only sites. For dedup that must fold http/https + trailing
  slash, use a SEPARATE key (`dedup_key`) and keep fetching the faithful form. And a
  page can be fetched twice via a redirect the frontier can't see pre-fetch — dedup
  again POST-fetch on the normalized final url.
- A one-shot signal read from the homepage SNAPSHOT is nondeterministic on JS sites (the
  same store rendered 2 vs 164 product links across runs). A signal that gates crawl
  depth (or any budget) must be RE-EVALUATED over accumulated evidence during the crawl,
  not frozen at page 1 — build the frontier wide and raise the cap live when it flips.
- A token/stem heuristic cannot judge SUBJECT identity — it can't separate an acceptable
  synonym/inflection ("experts"↔"youth", رقمي↔رقميون) from a fabrication ("gifts"↔"stores");
  both are token-disjoint (MEASURED: a subject-overlap heuristic broke 4 legit grounding
  tests + the Arabic-inflection match). This is the "heuristics hit ceilings" lesson — the
  fix is deterministic scaffold + ONE cheap LLM judge on the ambiguous case, with a LENIENT
  fallback so it never regresses without the judge. (Measure-first caught the bad heuristic
  before it shipped.)
- Selecting ONE element from a `set` via `next()` is PYTHONHASHSEED-dependent — it made the
  C2 number-class verdict nondeterministic across processes (a pre-commit review caught it).
  When a gate decision depends on a set, use the WHOLE set (accept if evidence matches ANY
  class) or a deterministic order, never an arbitrary pick.
- A verifier that matches a claim's VALUE without its CONTEXT certifies fabrications: a
  bare-digit ledger match "sourced" "Save 50%" from "50 years" and "best coffee" from
  "best regards", printing a FALSE 'verified' row in the compliance sheet (the moat's
  proof) — worse than an ungated surface. Number resolution now requires unit-class
  agreement (%/price/duration/scale); tighten only on a POSITIVE strong-unit signal so no
  real claim regresses. (Superlative + bare-number SUBJECT context remain open.)
- A bare phone number (no `+`) is a DIFFERENT real number in every country — parsing it
  under a hardcoded region fabricates a valid-looking WRONG number (nahdi Saudi
  920024673 → +20920024673 under blanket "EG"). Derive region from a RELIABLE per-site
  signal (locale path, ccTLD) first; `html lang` is NOT reliable (`en-US` is a common
  template default on non-US sites). Home-market fallback only when no signal exists.

**Process:**
- Restart uvicorn after every backend change; restart cleanly when adding route files.
- Byte-identical LLM outputs across runs = your change never reached the prompt.
- The owner's live testing is the best QA in the project: each caught failure became
  a permanent gate + test (912→913 and counting). Keep that loop.

---

## 9. Where things live (quick map)

| Concern | Files |
|---|---|
| Crawl budget/links/sitemap | `scraper/config.py`, `scraper/crawler.py`, `scraper/sitemap.py`, `scraper/extractors/links.py` |
| Logo + palette | `scraper/extractors/visual.py`, `scraper/inline_svg_logo.py` |
| Profile extraction | `business_profile/llm/{prompts,extractor,validator,rag,embeddings}.py`, `business_profile/rules/*` |
| Ledger + compliance | `grounding/{ledger,audit,compliance}.py`, `poster/audit.py`, `strategy/audit.py`, `reel/grounding.py` |
| Discovery + SWOT + TOWS | `competitor/{router,discovery,web_discovery,lite_scrape,matrix,swot,tows,themes}.py` |
| Brand identity (vision) | `brand/{creative_dna,brand_book}.py` |
| Poster | `poster/{pipeline,concept,oneshot,art_director,variation,from_profile,template,vision_qa,brand_research}.py` |
| Reel | `reel/{generate,art_director,motion,text_overlay,textlayer,endcard,video_provider,image_quality,grounding}.py` |
| Web | `api/routes/*`, `frontend/components/*` |

---

*This file is the single source of truth for the project — read it before acting here.*
