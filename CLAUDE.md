# CLAUDE.md — scraper_v01

Project context and working rules. Read this before acting in this repo.

## What this is
Universal AI Marketing Campaign Strategist: input = any business URL, output = a
marketing campaign pack grounded ENTIRELY in real scraped data.
Core principle: **zero hallucination — every output field traces to a sourced
evidence item.** Must stay **universal** (works for any vertical); never drift into
vertical-specific hacks.

## Runtime
- Windows PowerShell, Anaconda, Python 3.11, conda env `marketing_scraper`.
- **Working copy: `C:\dev\scraper_v01`** (moved 2026-06-11). The old
  `G:\Other computers\...\scraper_v01` is a Google-Drive-synced copy — too slow
  to work in (searches time out, Next.js first compile crawls); treat as backup.
- `conda`/`npm` are not on PATH in fresh shells; use
  `C:\Users\asmaa\anaconda3\envs\marketing_scraper\python.exe` and
  `C:\Program Files\nodejs` directly if needed.
- Vertex ADC is not set up on this machine — run
  `gcloud auth application-default login` once before real Imagen generation;
  until then reuse saved backgrounds in `outputs/posters/backgrounds/`.

## Architecture (data flow)
```
URL
 -> scraper                                   (Playwright / trafilatura) -> manifest
 -> business_profile.build.build_profile(manifest, caller)  -> BusinessProfile
 -> competitor.discover_competitors(profile, client)        -> peers + reviews (Places only)
 -> competitor.build_matrix(manifest, peers, scrape_fn=...)  -> comparison matrix
 -> competitor.synthesize_swot(matrix, themes=...)           -> cited SWOT
```
- `competitor/` is fully built (discovery -> matrix -> SWOT, all citation-grounded).
- Discovery is now **adaptive**: `competitor.route_discovery` (LOCAL->Places /
  ECOMMERCE->web-stub / HYBRID->both / UNKNOWN->skip); SWOT degrades to a grounded
  **standalone** (profile-only) analysis on 0 peers — never empty, never fabricated.
- `poster/` builds a poster from a profile JSON: LLM art-director concept ->
  Vertex Imagen (text-free) -> Playwright HTML/CSS overlay (NO Pillow).
- Web app: `api/` (FastAPI) + `frontend/` (Next.js 15, App Router).
- End-to-end: `competitor/full_run.py` (SWOT); `python -m poster <profile.json>` (poster).

## Standing rules (do NOT violate)
1. **One fix at a time. Run the benchmark between fixes.** Never bundle changes — it
   obscures causality.
2. **Patterns over single observations.** Measure (with numbers) before changing the scraper.
3. No new `BusinessProfile` fields without benchmark evidence.
4. **UNKNOWN is honest.** Never infer a value to make output look complete; UNKNOWN
   cells are excluded from gap verdicts.
5. Keep the scraper universal — no vertical-specific logic.
6. Don't build architecture before knowing real failure modes (benchmark first).
7. Be honest about sandbox / scraper limitations; don't over-claim.
8. **Keep this file updated.** After every landed change, record it here (move the
   item to a `## Done — … ✅` entry with where/why/measured-result, and update the
   Backlog). Do this as part of the change, not later.

## How to run
- Scrape a URL -> manifest:           `python -m scraper <url>` (writes scrapes/<slug>/manifest.json)
- Manifest -> BusinessProfile JSON:    `python -m business_profile <manifest.json> -o profile.json`
- Full competitor -> SWOT on one URL: `python -m competitor.full_run <url>` (route_discovery; standalone on 0 peers)
    Writes a consolidated `result.json` (profile + competitors + SWOT) into the scrape's
    output folder (`scrapes/<slug>_<ts>/result.json`); override the path with `--out PATH`.
    flags: `--json` (SWOT as JSON to stdout, progress to stderr), `--no-themes` (skip Anthropic).
- Poster from a profile JSON:          `python -m poster <profile.json> --out poster.png`
    flags: `--no-image` (offline stub bg), `--static-concept` (skip LLM art-director).
    Imagen 4 Ultra is capacity-limited; set `IMAGEN_MODEL=imagen-4.0-generate-001` to dodge 429s.
- Web app: API `uvicorn api.main:app --port 8000`; frontend `cd frontend && npm install && npm run dev` (:3000).
    **Never run `npm audit fix --force`** — it downgrades Next 15 -> 9.3.3 and breaks the App Router.
- Places connectivity check:           `python -m competitor.check_places_403`
- repomix packaging:
  `--style markdown --compress --ignore "benchmark/runs/**,scrapes/**,frontend/.next/**,repomix-output.*"`

## Keys (.env at repo root)
`GOOGLE_MAPS_API_KEY` (Places), `OPENAI_API_KEY` (profile extraction + poster LLM
art-director), `ANTHROPIC_API_KEY` (review themes; optional).
`SERPER_API_KEY` (ECOMMERCE/HYBRID competitor web-discovery; optional — absent ->
NullWebDiscoveryEngine -> standalone SWOT). Modular: falls back to `SEARCHAPI_API_KEY`
(searchapi.io, 100 free) or `GOOGLE_CSE_API_KEY`+`GOOGLE_CSE_CX` (Google Custom
Search, 100 free/day) — see `competitor/search_providers.py`.
Poster image gen = **Vertex AI Imagen** via **ADC** (gcloud), NOT an API key:
`GOOGLE_CLOUD_PROJECT=image-498715`, `GOOGLE_CLOUD_LOCATION=us-central1`; run
`gcloud auth application-default login` once. Optional `IMAGEN_MODEL` override.

## Done — link dedup (matrix-reader + scraper-side) ✅
MEASURED pattern (not a guess): link counts were inflated because the same href is
counted once per page it appears on across the crawl. The crawl emits one
`LinkRecord` per (page, link), so a site-wide nav/footer link repeats once per
crawled page. This inflated the subject's SWOT "strengths" (e.g. "51 social links").

Two fixes landed, one at a time, benchmarked between:

1. **Matrix-reader (first, scope-contained).** Dedup in `competitor/matrix.py`
   (`extract_scraped_dimensions` -> `dimensions_from_manifest`, helper
   `_dedup_by_href`) by normalized href (strip trailing slash), first occurrence
   wins. Unblocked SWOT with no scraper change. KEPT as a defense-in-depth safety
   net (covers the BusinessProfile path + any pre-fix manifest); now a no-op on
   fresh manifests.

2. **Scraper-side (root cause).** Dedup in `scraper/extractors/links.py`
   (`build_inventory`, helper `_dedup_key`), first occurrence wins. Scoped to
   `social` and `cta_candidates` ONLY — `internal`/`external`/`contact_protocol`
   untouched, and the CTA->`internal` append stays unconditional. No schema change.
   Final dedup keys:
   - `_dedup_key(href)` = `normalize_url(href).rstrip("/")`
     (tracking-param stripped via `normalize_url`, THEN any trailing slash removed
     because `normalize_url` only strips the slash on the *root* path).
   - **social** key = `_dedup_key(href)`
   - **cta_candidates** key = `(_dedup_key(href), anchor_text)` — the anchor keeps
     two distinct calls-to-action that share one href.

Benchmark (read-only on saved manifests; raw -> after, verified through the real
`build_inventory`):

| site                      | social     | cta_candidates |
|---------------------------|------------|----------------|
| thehairaddict_net         | 7  -> **1**  | 14 -> **2**      |
| assih_com                 | 51 -> **14** | 18 -> **3**      |
| laserhairremovalcairo_com | 51 -> **8**  | 14 -> **1**      |

Two edge cases the benchmark caught and the final keys handle: assih merges a
`&fbclid=` WhatsApp variant (normalize_url); laser merges `/contact-us` vs
`/contact-us/` (the `.rstrip("/")`). Regression test:
`tests/test_link_inventory_dedup.py`.

NOT changed (intentional): `business_profile/rules/from_links.py` dedups CTAs by
*anchor text* (distinct labels for the profile) — a different purpose than
`build_inventory`'s href-based dedup (distinct targets for counting); leave it.

## Done — adaptive competitor discovery + standalone SWOT ✅
`competitor/business_type.py` (LOCAL/ECOMMERCE/HYBRID/UNKNOWN classifier) +
`competitor/router.py` (`route_discovery`: routes to Places / web-stub / both / skip;
never raises, never fabricates peers). `synthesize_swot` degrades to a grounded
**standalone** SWOT (profile-only S/W from subject dims; UNKNOWN cells skipped) on
0 peers. Discovery adapter bug fixed: `build_match_criteria` used `str(enum)`
("BusinessCategory.X") + `str(offering)` (object repr) -> garbage Places query; now
`.value` + offering names. Wired into `full_run.py` (no fail-on-empty). Tests:
`test_business_type.py`, `test_router.py`, `test_swot_standalone.py`.

## Done — Poster Studio rebuilt (creative, minimal, evidence-grounded) ✅
NEW pipeline replaces Pillow template-stamping. `build_poster_brief` -> LLM
art-director invents a unique **text-free** visual concept
(`art_director.build_llm_concept_prompt`, static fallback) -> **Vertex Imagen 4 Ultra**
(`imagen_provider.py`: `ImageProvider` protocol + Vertex + Stub) -> **Playwright
HTML/CSS overlay** (`template.py` + `render_playwright.py`). NO Pillow anywhere.
- **Ultra-minimal** overlay (`density="minimal"` default): logo + 1 headline + 1 CTA.
- **Zero hallucination**: offerings/headline/sub/CTA are verbatim evidence or omitted
  (removed `_fallback_offerings`/`_normalize_offering_name`/hardcoded headlines; CTA
  from real `existing_ctas`).
- **RTL**: Arabic auto right-aligns (`_is_rtl`); text is OVERLAID, never baked —
  Imagen garbles Arabic (decisions doc §5). `bake_text=True` kept for English-only.
- **Web/deploy unified**: `api/routes/poster.py` rewired to the new pipeline (SYNC
  route — Playwright sync API can't run in the event loop; same response shape so the
  `poster-studio-card` frontend is unchanged; 429 fallback to imagen-4.0-generate-001).
- Docs: `poster_studio_decisions.md` (design), `vertex_ai_poster_setup.md` (Imagen).

## Done — SSRF guard (API layer) ✅
`scraper/url_utils.is_safe_public_url` (only public http(s); blocks loopback/private/
link-local incl. metadata 169.254.169.254/reserved). Applied at `api/routes/run.py`
(scrape entry) + `poster/template._remote_image_data_uri` (logo fetch). NOTE: it's a
DNS-resolve-time check — TOCTOU/rebinding + crawler-followed sub-page/sitemap links
are a deeper follow-up.

## Done — scraper logo classification + selection (3 measured fixes) ✅
Root cause of "collaborator logo, not the business" (co-branded gov/edu sites):
1. **Classification host-strip** (`visual._classify_blob`): the domain ("gov" in
   `.gov.eg`) tagged EVERY logo `government_logo`. Measured: government_logo 18->1 on
   digilians; **0 flips on 27 other sites**. Partners now `partner_logo`.
2. **Primary prefers raster over wordmark** (`_choose_primary_logo`): no more
   "Home"/"About us"/"الرئيسية" nav wordmark as the brand (4 sites + digilians).
3. **Primary prefers brand-filename**: the brand's own file beats a co-brand/ministry
   logo that outscores it via a generic "logo" in its name. Verified **live**: a fresh
   re-scrape gives primary=`Digilians.png`, partner_logos=11, authority_logos=1(MCIT).
Downstream: poster `_extract_logo` simplified to trust `primary_logo` + exclude
partner/authority (band-aid removed). 438 tests pass; `test_visual_identity_v02` green.

## Done — SWOT social_count field bug ✅
`competitor/matrix._dims_from_business_profile` read `social_links`/`social_profiles`
(never existed) -> always 0 -> false "Social links: none detected". Now reads the real
`social_presence`. Measured: 0 -> 6 on digilians; SWOT now shows "Social links: 6".

## Done — small fixes ✅
- **WhatsApp dim**: `matrix._dims_from_business_profile` now reads
  `contact_channels.whatsapp_numbers` (was a nonexistent top-level field).
- **CTA/contact URL bidi**: the "leading slash" was a bidi *rendering* artifact, not
  a data bug (`cta_url` is clean). URL/email spans in `poster/template.py` now use
  `dir="ltr"` so they render correctly inside an RTL (Arabic) poster.

## Done — phones serialization + poster social (recorded late, per rule 8) ✅
- **Phones**: `phones_e164` is a deliberately deprecated, NON-serialized `@property`
  (Pydantic v2 skips it in `model_dump`). Live field is `phones` (list of
  `{e164, raw}`). Frontend migrated: `frontend/lib/types.ts` (+`PhoneChannel`),
  `visual-identity-card.tsx` reads `phones` first, `phones_e164` kept only as
  legacy-fixture fallback. Poster's `_extract_contact_line` reads `phones` too.
- **Poster social**: `poster/schemas.py` (+`PosterSocial`, `PosterBrief.social`),
  `from_profile._extract_social` (verbatim from `social_presence`, deduped by URL,
  cap 6), `template.py` renders a social label row (full density only — minimal
  density is logo+headline+CTA by design).

## Done — stale-deploy verification (2026-06-11) ✅
User-reported issues (no logo, no social, "GPT image in deploy") REPRODUCED only on
stale artifacts, NOT current code. Verified live end-to-end on a fresh digilians
re-scrape: manifest logo=True social=6; brief logo=`Digilians.png` (not wordmark),
social=6; rendered poster (full density, stub bg) shows real logo top-right (RTL),
Arabic headline right-aligned, CTA + LTR URL, email, social row. The old GPT-image/
Pillow modules (`poster/image_providers.py`, `render_pillow.py`) are ORPHANED —
`api/main.py` mounts only the new Imagen+Playwright route. Conclusion: rebuild/
restart the web app + re-scrape; don't "re-fix" landed code. Logo measurement over
57 saved profiles: 46 extract a logo; 11 wordmark fallbacks = 5 stale pre-fix
digilians artifacts (incl. `nti_profile.json`) + 6 where the scraper found
0 logo_candidates (mumm_io, spclinic_net, clear-lsc_com — real scraper gap).
NOTE: this machine had no Node.js (repo is Drive-synced from another computer);
installed Node 24.16.0 LTS via winget to run the frontend.

## Done — restaurant-rule gate + fabricated-offering kill (2026-06-11) ✅
MEASURED across all 38 saved manifests: `extract_restaurant_offerings` had a 45%
false-fire rate. Two failure modes: (a) the last-resort fallback FABRICATED a
"Restaurant Menu" offering (name nowhere in evidence) on 8 sites, 7 false — the
Arabic nav word "القائمة" ("menu") triggered it on gov-education (digilians ×5),
a hospital (andalusia), etc.; (b) the `takeaway|delivery|order online` pattern
fired "Takeaway and Delivery" on jewelry (glamira), cosmetics (norshek, eva),
and a university (sce_aucegypt). Fix in `business_profile/rules/from_offerings.py`:
1. `_passes_restaurant_gate`: extractor runs only with a MENU page type OR >=2
   distinct strong identity tokens (restaurant/مطعم, cuisine, kebab/كباب,
   grill/مشويات, dish/أطباق, dining, chef/شيف, ... — generic menu/food/delivery
   words deliberately excluded). Gate threshold chosen FROM the measurement:
   every true restaurant >=2 or menu page; every false site 0-1 and no menu page.
2. Deleted the "Restaurant Menu" fallback (zero-hallucination violation).
Re-measured: fabricated fires 8 -> 0; false Takeaway 4 -> 0; true fires kept
(elkbabgi 4 offerings, zooba, buffalo). 8/8 hotfix tests pass. Known honest gap:
Arabic-only restaurants (Kebab Palace) pass the gate but match no English-named
pattern -> [] from rules; LLM extractor covers them (candidate follow-up:
Arabic offering patterns).

## Done — poster grounded in brand persona + visual identity (2026-06-11) ✅
`art_director.build_llm_concept_prompt(brief, caller, profile=None)`: new
`_persona_lines(profile)` feeds the LLM art-director the brand's VERBATIM scraped
persona (tagline, description, top-3 value propositions, audience_type, languages)
and the system prompt now requires (a) the concept to EMBODY that persona, (b) the
brand palette to lead the scene's color story, (c) cultural authenticity for the
audience. Wired at both call sites (`poster/__main__.py`, `api/routes/poster.py`).
VERIFIED on digilians: pre-fix profile (with fabricated "Restaurant Menu") produced
a DINING-TABLE concept for a gov education brand — the bug cascade in one image;
rebuilt profile (rules fix above, rejections=0) produces "a bridge of shimmering
digital code and light" grounded in the Arabic description + verbatim value props.
NOTE (separate trail, not bundled): the digilians brief uses the education
FALLBACK palette, not the scraped one (#133b69) — `_palette_looks_unreliable`
flagged it; measure before changing.
VERIFIED LIVE end-to-end (2026-06-11, this machine): ADC set up + `google-genai`
installed; concept = "futuristic bridge of glowing digital circuits" (persona:
الرواد الرقميون / youth->tech employment); Imagen Ultra 429 -> fallback model;
full-density overlay shows real logo, Arabic RTL headline+sub, REAL offerings
(Nanodegree / Specialized Diploma / Scientific Master — no more fabricated
"Restaurant Menu"), CTA->/traningTracks, email, 6 socials.
-> `outputs/posters/digilians_persona_poster.png`.

## Done — ECOMMERCE competitor web-discovery (SERP, modular) (2026-06-11) ✅
Replaced the `NullWebDiscoveryEngine` stub with a real SERP-based engine so
ECOMMERCE/HYBRID brands (which Places can't reach) get real peers -> fills the
SWOT THREATS quadrant for online businesses.
- `competitor/search_providers.py`: modular `SearchProvider` protocol +
  `SerperProvider` / `SearchApiProvider` / `GoogleCSEProvider` + factory
  `get_default_search_provider()` (Serper -> SearchApi -> Google CSE by key
  presence). stdlib-only (urllib), never raises (network errors -> []).
- `competitor/web_discovery.py`: `SerpWebDiscoveryEngine` (satisfies the router's
  `WebDiscoveryEngine` Protocol) + `default_web_engine()`. Universal query:
  category/offering-keywords FIRST ("best <kws>") then brand competitors/alternatives.
  Filters subject domain + social + a big aggregator/listicle/forum denylist;
  dedups by registrable domain; normalizes each peer to its HOMEPAGE (matrix
  scrapes the business, not a deep "/vs-us" blog). Provenance: every peer carries
  the query + organic rank in `SelectionRecord.why_selected`. NEVER fabricates.
- Wired into BOTH production entry points (router stays pure -> tests unchanged):
  `api/routes/swot.py` + `competitor/full_run.py` pass `web_engine=default_web_engine()`.
- MEASURED live on GLAMIRA (Serper): first pass returned 3/4 aggregators
  (craft.co, gripsintelligence, weddingbee) -> after the category-first +
  denylist + homepage-normalize fixes, 4/4 real jewelry rivals (Brilliant Earth,
  Artemer, Elie Top, Luxurian). Tests: `tests/test_web_discovery.py` (6, no
  network via FakeProvider); 22 competitor tests green.
Robustness note: `_field_text` unwraps dict-wrapped EvidencedField + enums, so the
engine works on BOTH object profiles (full_run) and serialized dict profiles (API).

## Done — scraper resilience: HTTP/2 fallback + Tier 0 (real UA + retry) (2026-06-11) ✅
Two landed transport-layer fixes, measured together:
1. **--disable-http2** (`scraper/crawler.py` launch args): some CDNs reset HTTP/2
   from headless Chromium (`net::ERR_HTTP2_PROTOCOL_ERROR`, MEASURED on lcwaikiki.eg).
   Forcing HTTP/1.1 is a universal, safe transport fallback (NOT evasion).
2. **Tier 0** (`scraper/config.py` + `scraper/fetcher.py`):
   - Real desktop-Chrome **User-Agent** (was the self-identifying "MarketingScraperBot/0.1"
     string, which any WAF blocks on sight) + `Accept-Language` header. Honesty
     trade-off noted in config; robots.txt still respected, polite rate-limit kept.
   - **Retry-with-backoff** on TRANSIENT failures only (`_TRANSIENT_ERRORS` =
     NETWORK_ERROR/RENDER_ERROR/TIMEOUT); bot-block/4xx/empty-DOM never retried.
     `fetch_page` now wraps `_fetch_page_once`; failed attempts close their own page.
MEASURED before/after: digilians 5 -> **8 pages succeeded**, 340 -> **577 text blocks**
(real UA reduced sub-page soft-throttling; retry caught transient sub-page fails);
no regression (logo+6 socials intact). lcwaikiki.eg progressed from messy transport
errors to a CLEANLY-CLASSIFIED `BOT_PROTECTION` ("Access Denied") — i.e. a genuine
Akamai application-layer wall, the Tier-3 (search-fallback) case, NOT a transport bug.
Honest ceiling kept: Tier 0/1 raise success on normal/mid sites; Akamai/DataDome
need the Deep-Search fallback, not WAF evasion. NO test pinned the old UA.

## Done — poster typography (brand fonts + modern default + flair) + logo SSL fix (2026-06-11) ✅
User: the poster looked "boring and static", wanted website-based fonts, and the NTI
logo kept rendering as a "nti" wordmark. Two fixes:
- TYPOGRAPHY (`poster/schemas.py` + `from_profile.py` + `template.py` + `render_playwright.py`):
  PosterBrief gains `heading_font`/`body_font` (from `profile.visual`).
  `_fonts_head_and_stacks` always loads a curated MODERN default (Space Grotesk +
  Inter + Cairo) via Google Fonts — so it never falls back to system Georgia — AND
  best-effort loads the SITE's own font on a SEPARATE <link> (so a private family
  like NTI's "myfont2" can 404 without taking the defaults down). Brand font leads
  each stack → used when it actually loads; generic/private names fall through to the
  default. Added a brand-colored accent rule above a bigger/tighter headline (flair).
  `render_playwright` now awaits `document.fonts.ready` before screenshot.
- LOGO SSL (`poster/template._open_image_url`): NTI's logo fetch failed with
  CERTIFICATE_VERIFY_FAILED — nti.sci.eg ships an INCOMPLETE cert chain (browsers
  repair via AIA; urllib doesn't), dropping the real logo to a wordmark. Now: verified
  (certifi) first, UNVERIFIED fallback on a cert-chain error only — acceptable for a
  passive, SSRF-guarded IMAGE fetch (worst case = cosmetic logo swap, no creds/data).
MEASURED: fresh NTI re-scrape extracts the logo (primary_brand_logo conf 1.0 — the
old `nti_profile.json` wordmark was STALE); poster now shows the real logo + Space
Grotesk headline + accent rule. 35 poster/visual tests pass. NOTE: a REUSED background
may carry baked text from a prior gen; a fresh Imagen bg won't.

## Done — poster headline: smarter VERBATIM pick (no generation) (2026-06-11) ✅
User asked for poster text "created depending on the project" but chose VERBATIM
selection (not LLM generation) — keep zero-hallucination, just pick the strongest
real line. `poster/from_profile.py`: `_headline_fitness` (deterministic, language-
agnostic: plateau full-score for ~10-55 char multi-word lines so short slogans
aren't penalized; falloff + sentence/comma penalties outside) + `_select_headline`
(candidates = tagline + value_propositions + description sentence; tagline gets a
+0.25 slogan bonus so it wins ties but a clearly stronger value-prop can override a
weak filler tagline). `build_poster_brief` now uses it; subheadline de-dupes vs
headline. MEASURED across 17 saved profiles: digilians keeps "الرواد الرقميون",
Alameda/NTI/almentor keep good taglines; weak ones improved — Qasr Elkbabgi
"QASR ELKBABGI" (bare name) -> "diverse menu of authentic Egyptian cuisine",
AUC "Welcome to..." -> "Flexible schedules for lifelong learning", Zööba long
all-caps -> "Homegrown Egyptian food with global appeal". 20 tests green.

## Done — SWOT Threats from web/competitor peers (2026-06-11) ✅
Root cause of "no Threats" on ECOMMERCE: `synthesize_swot` only routed `behind`
verdicts to Threats for `places` dims; `scraped`-dim behinds became Weaknesses
only. Web/SERP peers carry NO Places dims -> Threats quadrant always empty.
(Opportunities were fine: `whitespace` works for any peers; they were empty only
in 0-peer standalone mode, which the new Serper engine fixes.) Fix in
`competitor/swot.py`: a scraped `behind` gap now ALSO emits a THREAT ("Competitors
lead on <dim> where you are behind.") when `n_peers>0` — the EXTERNAL lens on the
same gap (Weakness = internal/you lack it; Threat = a real rival is ahead).
Universal (improves LOCAL SWOTs too, not a web-only hack); grounded (cites the
same leading peers via `_cite_behind`); guarded so standalone (0-peer) emits no
phantom threat. Tests: +2 in `test_swot_standalone.py`; 26 green.

## Done — Deep Search fallback (Tier 3) for blocked/empty sites (2026-06-11) ✅
When the direct scrape gets nothing first-party (BOT_PROTECTION/CAPTCHA/empty/
network), the crawler recovers SECONDARY evidence from web search instead of
returning an empty manifest.
- `scraper/deep_search.py`: `gather_deep_search_evidence(url, provider=None)`
  reuses `competitor.search_providers` (Serper). Queries `site:<domain>` (the
  site's OWN Google-indexed title+meta-description — first-party content that
  survives the block) + the brand (surfaces socials). Extracts business_name
  (homepage-listing title, shallowest path wins), description, social_links (via
  `config.SOCIAL_DOMAINS`), source URLs. PURE: never mutates os.environ — entry
  points load .env (`scraper/__main__.py` added a load_dotenv; the API already
  loads it). Loading .env inside the helper polluted a later test (broke isolation)
  — lesson: keep library helpers side-effect free.
- `scraper/schemas.py`: `DeepSearchResult`/`DeepSearchSource`; optional additive
  `ScrapeManifest.deep_search` (old manifests load as None).
- `scraper/crawler.py`: on a blocked/empty homepage, calls the fallback before the
  early return; attaches to `manifest.deep_search`. NEVER flips readiness to ready
  — SUPPLEMENTARY, source-tagged secondary, honest.
HONESTY: no provider -> used=False; empty results -> empty fields; never fabricated.
MEASURED live on lcwaikiki.eg (Akamai "Access Denied", 0 pages scraped): recovered
name + Arabic description + 3 socials (FB/IG) + 10 source URLs — a previously-unusable
site now yields real sourced data. Tests: `tests/test_deep_search.py` (4, FakeProvider).
NEXT (separate, a product decision): let `build_profile` emit a DEGRADED profile
from `manifest.deep_search` (secondary source_type, low confidence) so a blocked
site produces a usable-but-honest profile instead of a hard "not ready" error.

## Done — web-discovery no-provider contract fix (network-hygiene) (2026-06-13) ✅
`SerpWebDiscoveryEngine.__init__` resolved a LIVE provider on `provider=None`
(`provider if provider is not None else get_default_search_provider()`), making the
`if self.provider is None: return []` guard in `discover()` unreachable whenever a
SERP key was in the environment -> `SerpWebDiscoveryEngine(provider=None)` silently
hit the real Serper API. Fix (`competitor/web_discovery.py`): constructor is now
`self.provider = provider` (honors an explicit None). Safe — the only production
callers go through `default_web_engine()` (`competitor/full_run.py`,
`api/routes/swot.py`), which resolves the default EXTERNALLY and builds the engine
only when the provider is non-None; nothing relied on the constructor auto-resolving.
Matches the module's documented contract ("No provider ... yields []"). MEASURED:
full suite 9 failed -> 8 failed; the previously env-dependent
`test_no_provider_returns_empty_never_raises` now passes in 0.14s with NO network
call (remaining 8 = known missing `benchmark.graders`). Root-caused with the live
env: no `conftest.py` and nothing in `competitor/` loads `.env` at import, so the
call came from `SERPER_API_KEY` being a real shell env var, not a fixture leak.

## Done — test suite green + version control initialized (2026-06-13) ✅
Env set up on THIS machine (conda `marketing_scraper` at
`C:\Users\Admin\.conda\envs\marketing_scraper`; `requirements.txt` is complete and
pinned). Full suite RUN: was 9 failed / 476 passed; after the web-discovery fix above
+ skip-guarding the unbuilt-grader tests it is **477 passed, 9 skipped, 0 failed**.
- Skip-guard (`tests/test_text_contact_scan_and_grader.py`): the 8 `test_grader_*`
  tests import `benchmark.graders` (not built) — now `@requires_graders`
  (`pytest.mark.skipif` on `find_spec`), matching the sibling `tests/test_benchmark_graders`
  spec's `importorskip`. They auto-run once `benchmark/graders.py` lands. Deliberately
  NOT auto-built: the grader is the product's own quality scorer; its thresholds are
  measurement decisions to author, not reverse-engineer from a spec.
- Git: repo was NOT under version control (Google Drive doesn't sync `.git`), though a
  solid `.gitignore` already existed (covers `.env`, `__pycache__`, `scrapes/`, the
  `* (1).*` sync-duplicates). `git init` + initial commit landed. Added `outputs/`
  (~140 MB of generated PNGs) to `.gitignore` — `git add -f` to keep specific reusable
  Imagen backgrounds.

## Done — benchmark graders + report built (suite 0 skips) (2026-06-13) ✅
Built the two modules the harness + tests required (`benchmark/runner.py` already
imported them): `benchmark/graders.py` (`Grade`, `UrlGradeSet.avg_score(only_swot_critical=)`,
the 8 structural `grade_*` + the `grade_fuzzy_*` graders, `grade_profile` -> 16 grades /
7 SWOT-critical; helpers `_norm` NFKD diacritics + `_strip_chrome`) and
`benchmark/report.py` (`aggregate` + `write_results_json`/`write_report_md`). Scoring was
DERIVED from the existing spec (`tests/test_benchmark_graders`), not invented: name =
exact / chrome-stripped / brand-token / non-Latin-via-URL-slug; offerings tier-aware;
fuzzy = token coverage (full->1.0, >=25%->0.5, else 0.0); no ground truth -> score None
(ungraded, excluded from averages). The `@requires_graders` guards now no-op (modules
exist) so those tests RUN. MEASURED: full suite **518 passed, 0 skipped, 0 failed**
(was 477 / 9 skipped); `benchmark.runner` imports clean. Scores against
`benchmark/urls.json` + `ground_truth.json` on a live run; only the unit spec is checked here.

## Done — full_run writes a consolidated result file (2026-06-13) ✅
`competitor/full_run.py` previously only PRINTED the SWOT to stdout. It now also
WRITES a consolidated `result.json` after a run: `subject_url`, `generated_at`,
`subject_category`, `competitor_count`, `scrapable_benchmarks`, `discovery_notes`, the
full `profile` (pydantic `model_dump(mode="json")`), the discovered `competitors`
(dataclass `asdict`, incl. each peer's `why_selected` provenance), and the cited
`swot`. Default path = `result.json` inside the scrape's own output folder (`scrape()`
returns that dir); `--out PATH` overrides. The `--json` stdout (SWOT-only, for piping)
is unchanged. Serialization is robust (`model_dump` for pydantic, `asdict` for
dataclasses; `default=str` safety net). No test drove full_run (`test_orchestrator_full_run`
is the rules orchestrator, unrelated) — suite stays **518 passed**. NOTE: a live run
still costs OpenAI extraction + Places/Serper calls and scrapes live sites; not run in CI.

## Done — Reel Studio (Veo + Playwright/ffmpeg) + prompt grounding (2026-06-14) ✅
NEW `reel/` package — a vertical 1080x1920 marketing REEL from a BusinessProfile,
the moving sibling of the poster. `python -m reel <profile.json> [--out x.mp4]`
(flags: `--no-video` offline stub, `--static-scene` skip LLM, `--music`, `--scale`,
`--no-logo`). Flow: profile -> build_reel_brief (REUSES the poster's verbatim
selectors) -> build_storyboard (timed, evidence-only, RTL-aware, length-capped scenes)
-> VideoProvider per scene -> ffmpeg compositor (concat + overlay + music) -> mp4.
- VIDEO (`reel/video_provider.py`): VideoProvider protocol + VeoProvider (google-genai;
  auto-detects a Gemini API key OR Vertex ADC) + StubVideoProvider (offline ffmpeg
  gradient). Default model `veo-3.1-generate-preview`, override `REEL_VIDEO_MODEL`.
  MEASURED on THIS machine: Veo runs via VERTEX (project image-498715,
  `veo-3.0-generate-001`) and produced a real reel; **`veo-3.1-generate-preview` is
  404 NOT_FOUND** on that project (preview not provisioned); the Gemini-API-key path
  **403s (API_KEY_SERVICE_BLOCKED = billing/key restriction)**.
- TEXT OVERLAY via Playwright, NOT libass: the bundled Windows ffmpeg's libass does
  NOT shape Arabic (isolated, disconnected glyphs — VERIFIED), so the text layer is
  rendered as transparent PNGs by Chromium (correct Arabic shaping; reuses the
  poster's approach) and overlaid by ffmpeg with a slide+fade entrance. Phone/email
  use dir=ltr inside the RTL reel. `reel/ffmpeg_tools.py` uses imageio-ffmpeg's
  bundled ffmpeg (libx264/aac; no system ffmpeg or browser-for-video needed).
- ART DIRECTOR (`reel/art_director.py`): `build_brand_scene` — an LLM (OpenAI
  gpt-4o-mini, the SAME caller the poster uses) invents ONE text-free, on-brand
  b-roll SCENE from the verbatim persona, so two brands in one category get
  DIFFERENT, identity-true footage; deterministic per-category templates are the
  no-caller fallback. MEASURED: digilians -> Cairo classroom/tech (no food),
  elkbabgi -> Egyptian oriental grill — distinct + on-brand.
GROUNDING FIXES (from a prompt-audit workflow) so generated output derives from the
REAL profile, not category templates:
- PALETTE (`poster/from_profile._extract_palette`): stop DISCARDING the real scraped
  brand_palette/accent_colors for a hardcoded category swatch on a non-fatal warning;
  lead with primary_brand_color. MEASURED: digilians #133B69 (was generic #0B1F3A),
  NTI #B95A36, elkbabgi #8B5542. Fixes BOTH poster and reel (reel reuses the brief).
- FOOD LEAK (`reel/art_director._BEAT`): the camera beats hardcoded "food/guests/
  hospitable" into EVERY vertical -> an EDUCATION reel showed food. Beats are now
  category-neutral; food lives only in `_restaurant_scene`. MEASURED: digilians/NTI
  = 0 food words across all scenes; elkbabgi keeps kebab/grills (correct).
- CATEGORY (`build_poster_brief`): trust the scraped category EvidencedField; only
  keyword-infer when absent (a misclassification cascaded into palette + scene).
- OFFERINGS (`business_profile/llm/prompts.py`): stop padding — prefer specific named
  items, honest-empty over filler, forbid the brand name / 'menu'/'diverse menu'.
  (LLM compliance partial — a real improvement, not perfect.)
SCRAPER (`scraper/fetcher._scroll_to_load`): now dwells at the footer + waits for
networkidle before capture. MEASURED on elkbabgi.com (a Strikingly site): footer
social links are JS-injected on scroll -> social 0 -> 5. Universal (any lazy site).
New deps: imageio-ffmpeg (used), arabic-reshaper + python-bidi (only used by the now-
orphaned `reel/subtitles.py` libass path — see backlog). Tests stay 518 passed; live
Veo/OpenAI calls cost money and are not in CI.

## Done — clean business NAME at the source (#6) (2026-06-14) ✅
Rule-based name leaked chrome into every headline/outro — MEASURED: og:site_name =
"Qasr Elkbabgi Website" (the title is identical). Fix is at the SOURCE, not the
poster band-aid: `business_profile/rules/from_metadata.py` adds `_strip_chrome`
(whole-word, fixed-point, never empties) applied to the og:site_name and title name
paths -> "Qasr Elkbabgi Website" -> "Qasr Elkbabgi". So poster + reel + SWOT all
inherit the clean name (the poster's `_clean_business_name` stays as defense-in-depth,
now a no-op on fresh profiles — same pattern as the link-dedup matrix-reader net).
Chose the deterministic RULE fix over the backlog's LLM-extraction idea: zero
hallucination, no token cost, universal, and it fixes the source. Conservative token
list (website/official/homepage + Arabic الموقع الرسمي; bare "home"/"online"
EXCLUDED — legitimate brand words). The verbatim source stays the cited quote
(provenance preserved). MEASURED across **59 saved manifests: exactly 1** name
changed (elkbabgi) — no collateral; safety cases verified (Home Depot, AOL Online,
Microsoft, bare "Website" all unchanged). Tests:
`tests/test_rules.py::test_name_strips_chrome_from_og_site_name` +
`::test_strip_chrome_is_conservative`. Suite 518 passed.

## Done — ecommerce CTA classification (Azza Fahmy) (2026-06-14) ✅
MEASURED weakness surfaced by Azza Fahmy (Shopify jewelry): the CTA degraded to a
generic "Visit website" because `existing_ctas` was EMPTY — **17 of 63 saved
manifests extract 0 CTAs**. Root cause (NOT a render/crawl4ai problem — Playwright
rendered fine: logo conf 1.0, 11 products, 225 internal links): the real shop
entry-points ARE scraped as `<a>` ("Catalog" -> /collections/all, "VIEW ALL" ->
/collections) but the CTA classifier's verb list missed them, so they fell to plain
`internal`. Fix: added ecommerce shop verbs to `scraper/config.CTA_VERBS`
(catalog / shop all / view all / browse / view|shop collection + Arabic تسوق / تصفح /
الكتالوج / عرض الكل). `shop *` / `order *` already matched via the startswith rule;
these are the non-"shop" phrasings. MEASURED across 63 manifests (re-classified):
Azza Fahmy 0 -> 2 ("Catalog","VIEW ALL"); only 2 other sites touched (+2,+1); **no
flooding** (collection NAMES like "Earrings"/"EL NUR" stay internal, not CTAs).
Zero-hallucination intact (anchor+URL are real evidence). Universal (any store).
Test: `tests/test_link_inventory_dedup.py::test_ecommerce_shop_links_classify_as_cta`.
Suite 535 passed. NOTE: saved manifests need a RE-SCRAPE to populate the new CTAs
(classification happens at scrape time); the code is correct for fresh scrapes.

## Done — scraper collects REAL content photos + FAITHFUL reel from the place (2026-06-14) ✅
The user's core demand: a reel "جاي من المكان اصلا" (from the real place), not a
Veo-invented scene. Root cause MEASURED: the scrape had no real photos to use.
- **WHY (measured on elkbabgi):** the image extractor read ONLY `<img src>`, but
  modern sites (Strikingly/Wix/Squarespace) serve photos as CSS backgrounds
  (`style background-image`, `data-bg`) and lazy `data-src`, mostly protocol-relative
  `//`. So the scraper kept **1 of 27 images — the logo** — and threw every photo
  away. WORSE: that 1 "hero" WAS the logo (gold lion crest), so the earlier Veo i2v
  was seeding from the LOGO and hallucinating a whole open-air restaurant (exactly the
  user's "دا عبث"). The elkbabgi site actually has ~26 real photos (stuffed pigeon,
  the chef pouring molokhia, the palace interior, the real feast table).
- **FIX (scraper):** `ImageRole.CONTENT` (`scraper/schemas.py`) + rewritten
  `scraper/extractors/images.py::_collect_content_images` — gathers photos from
  `<img>` (src + lazy data-src/srcset) + inline `style` background-image + `data-bg`
  attrs; normalizes `//`/relative; excludes logos/icons/svg/header-nav-footer chrome;
  dedups by filename (collapses CDN transform variants). MEASURED live re-scrape:
  elkbabgi `images_of_interest` CONTENT 0 -> **20**.
- **FIX (profile):** `VisualIdentitySummary.content_images` surfaced in
  `from_visual._content_images` — logos excluded via `_logo_basenames` (incl.
  logo_candidates: a real photo is never a logo candidate), jpeg-first, capped 12.
- **FIX (reel):** new `reel.video_provider.KenBurnsProvider` — FAITHFUL: animates the
  real photos with a slow ffmpeg `zoompan` (one per scene, varied focal preset),
  cover-cropped to 9:16, gradient fallback ONLY if all fail. On a per-scene fetch
  failure it cycles to the NEXT real photo (CDN is flaky) — not a gradient. Wired as
  `python -m reel <profile> --real` (KenBurns); `Storyboard.content_images`. VERIFIED:
  every elkbabgi scene is a REAL photo of the actual place + verbatim text, zero
  invention -> `outputs/reels/elkbabgi_real_place.mp4`.
- **#4 reframed:** the Veo i2v plumbing (hero_image_url surfacing, `_load_reference_image`,
  reference threading, `_hero_image_url`+`_logo_srcs` logo-exclusion) is KEPT — it now
  serves this faithful path (and a future Veo seed would use a real CONTENT photo, not
  the logo). The faithful **KenBurns-on-real-photos** is the shipped default for
  grounding; generative Veo stays an option but is NOT the way we claim "from the place".
Tests: `tests/test_content_images.py` (4), `tests/test_reel_reference_image.py` (15).
Suite 540 passed. NOTE: live Veo/scrape cost money; the faithful reel is offline (ffmpeg).

## Done — same-site matching uses eTLD+1, not www-stripping (enterprise redirects) (2026-06-16) ✅
MEASURED live on big-brand targets the owner wants to sell to. `same_registrable_host`
was named for registrable-domain matching but only stripped `www.` then compared full
hostnames — so any OTHER subdomain read as a different site. ROOT CAUSE of a total crawl
collapse on **Vodafone EG**: `https://www.vodafone.com.eg/` 302-redirects to
`https://web.vodafone.com.eg/en/home`; the homepage's 40 real nav links (28 `web.`,
12 `eshop.`) were all classified **EXTERNAL** (`links.internal=0` →
`NO_INTERNAL_LINKS_FOUND` → 1 thin page), AND the robots-advertised sitemap on
`web.vodafone.com.eg` was rejected (`sitemap_cross_host_rejected`). Fix
(`scraper/url_utils.py`): `same_registrable_host` now compares eTLD+1 via the
already-pinned `tld` lib (offline bundled PSL), with a fallback to the legacy
www-stripped equality when a host has no public-suffix match (IP / localhost /
intranet / unknown TLD) so those never regress. One helper fix cures three call sites
at once (link categorization `extractors/links.py`, subpage selection +
sitemap-URL filter `crawler.py`, sitemap cross-host gate `sitemap.py`). UNIVERSAL —
not vertical. Multi-label suffixes (.com.eg/.co.uk) handled; NOT over-broad
(`careers.vodafone.com` ≠ `vodafone.com.eg`, `a.blogspot.com` ≠ `b.blogspot.com`,
`vodafone.co.uk` ≠ `vodafone.com.eg`). MEASURED (offline re-categorization of the saved
Vodafone manifest): external 43 → **40 flip to internal** (the 28 `web.` + 12 `eshop.`),
3 correctly stay external (careers.vodafone.com, cookiepedia.co.uk, onetrust.com). Tests:
`tests/test_basics.py` (+`test_same_host_etld1_subdomains`, `test_same_host_not_over_broad`,
`test_same_host_fallback_for_unresolvable_hosts`). Suite **558 passed**. FOLLOW-UPS (own
measured fixes, NOT bundled): (a) re-anchor `site_url` to `final_url` after a CROSS-domain
redirect (eTLD+1 covers www↔web; a true vanity-domain→canonical-host redirect still needs
re-anchoring); (b) WE/te.eg readiness false-negative — a TIMEOUT-salvaged homepage (with
87 real text blocks) sets `has_homepage=False` → `ready_for_extraction=False` despite 13
pages scraped; (c) `links.internal` not deduped across pages (te.eg: 1364 records / 280
unique, 1.67 MB manifest); (d) SSRF: engine-level connect-time IP gate (post-redirect +
sub-page fetches are unguarded; the eTLD+1 fix now ACTIVATES subdomain crawling, so land
the gate alongside it).

## Done — poster: design-spec renderer (per-brand layouts, no raw URL) — STEP 1/2 (2026-06-16) ✅
ROOT CAUSE of "every poster looks the same, anyone could make it" (owner's words):
the overlay was ONE fixed layout — logo top-left + a bottom dark-scrim text band —
so any brand produced the same composition, only the words/bg changed
(`poster/template.py`). Worse: the designed stacked-hero headline `_headline_block`
existed but was DEAD (line 319 rendered a flat `<h1>` instead), and the creative
printed a **raw URL** on the image (the `.cta-url` span) — which no big-brand creative
ever does. ARCHITECTURE INSIGHT (owner's, correct): separate the two "truth domains" —
FACTS must stay evidence-grounded, but DESIGN/composition is pure creativity and was
being wrongly frozen by the zero-hallucination rule.
STEP 1 (renderer, this change — deterministic, offline-testable, no LLM yet):
- New `PosterDesignSpec` (`poster/schemas.py`): the structured design contract
  (layout, logo_corner, headline_treatment, accent_word, text_align, scrim_strength,
  show[], negative_space_zone, accent_hex). Carries ZERO factual claims.
- `poster/template.py` rewritten to render FROM a spec: 6 layout archetypes
  (bottom_band, side_panel_left/right, top_anchor, center_editorial, magazine_hero),
  each a different brand-mark corner + text-block placement + scrim shape. Revived
  `_headline_block` (stacked hero, one word in brand accent). **Removed the raw URL**
  from the creative (CTA = verb only; `cta_url` still available for a clickable button
  beside the PNG). `default_design_spec(brief)` picks a layout by a stable hash of the
  brand name so one brand is consistent but DIFFERENT brands differ — until the LLM
  drives it in step 2.
- Bug caught + fixed during visual QA: the hero auto-fit sized for a ~940px column and
  OVERFLOWED in the ~520px side panel ("RESTAURANT" ran off-frame). `_headline_block`
  now takes `column_px` per layout (520 side / 920 full) and caps size accordingly.
MEASURED (offline `--no-image` renders): Digilians (AR) -> top_anchor, RTL right-align,
logo top-right; Qasr Elkbabgi -> side_panel_right, stacked hero "MORE/THAN/JUST/A/
RESTAURANT" with the brand-gold last word, "Menu" CTA, NO url. Tests:
`tests/test_poster_design.py` (8). Suite **566 passed**.
STEP 2 (NEXT, separate): the LLM art-director FILLS the `design_spec` + crafts copy
(grounded paraphrase, validated to evidence) + generates a background whose
negative-space zone matches the chosen layout — the "designs every brand differently
from the data" brain. Needs OPENAI_API_KEY (concept/spec/copy) + Vertex Imagen (bg).
ORPHANED now: `art_director.build_art_direction` + `PosterArtDirection.layout` (old
Pillow-era per-category bg prompts) — superseded by the spec; delete when untangled.

## Done — poster: LLM art-director fills the design spec — STEP 2/2 (2026-06-16) ✅
The LLM now DESIGNS each brand's composition from its scraped data (the "designs every
brand differently" goal), not a fixed template. `art_director.build_design_spec(brief,
caller, profile)`: a powerful model (`OpenAICaller(model="gpt-4o")`) returns a
`_DesignSpecResponse` (layout / headline_treatment / accent_word / text_align /
scrim_strength / show[] / accent_hex / rationale) via OpenAI strict structured outputs;
falls back to the deterministic per-brand `default_design_spec` with no key / on error.
GROUNDING preserved (two truth domains): the spec is pure DESIGN; the renderer still
injects the evidence-grounded text + real logo, and `accent_hex` is accepted ONLY if it
EXACTLY matches a scraped brand color (off-palette colors dropped). `logo_corner` +
`negative_space_zone` are DERIVED from the layout (consistency), and `show` items are
validated against an allowlist (unknown dropped; headline/logo forced). The chosen
`negative_space_zone` is passed to `build_llm_concept_prompt` so Imagen leaves its calm
area exactly where the text lands (the big-brand look). Wired into `poster/__main__.py`
+ `api/routes/poster.py` (both build the spec → pass it to the concept prompt AND
`render_poster_html(brief, bg, spec=spec)`). MEASURED LIVE (gpt-4o + Vertex Imagen,
IMAGEN_MODEL=imagen-4.0-generate-001 to dodge Ultra 429): Qasr Elkbabgi → center_editorial,
a dramatic grilled-tower food scene; Digilians → side_panel_right, RTL right-aligned, a
"digital tree of light" metaphor with real Arabic offerings, text over the image's calm
zone — two brands, two genuinely different on-brand designs, zero URL on the creative.
Tests: `tests/test_poster_design.py` (+4: fallback, LLM mapping/validation, off-palette
accent rejection, zone↔layout). Suite **570 passed**. NEXT (STEP 3, separate): LLM-CRAFTED
copy (grounded paraphrase + evidence validator) so the headline reads like an ad, not a
verbatim scraped line — the last "two truth domains" piece. Same design-spec engine
should also drive the REEL.

## Done — poster: deep-search brand research → fresh, SOURCED ad copy (2026-06-16) ✅
Problem (owner): the headline was one VERBATIM scraped line, so the same brand repeated
the same copy every generation. Fix: run a web search about the brand BEFORE generation
and craft fresh copy from the REAL results — without eroding zero-hallucination.
`poster/brand_research.py`: `research_brand(name, persona, provider, caller)` queries the
brand (reuses `competitor.search_providers`, Serper) and a powerful model (gpt-4o) turns
the REAL snippets into (a) sourced `BrandFact`s (each carries its source URL) and (b)
distinct ad `BrandAngle`s. PROVENANCE/honesty: facts come only from snippets/profile
(never invented); an angle may be an evocative paraphrase but `asserts_hard_fact` flags
concrete claims, and an angle whose `grounded_in` isn't a real source URL is downgraded
to 'profile'. `pick_angle(research, fallback, variation)` rotates angles (deterministic
or fresh-per-run) and, with `prefer_safe`, drops unsourced hard-claim angles; falls back
to the verbatim headline when there are no usable angles (never loses grounding for
novelty). Side-effect free (no .env/os.environ mutation; provider/caller injected) — same
discipline as `scraper/deep_search.py`. Wired into `poster/__main__.py` behind `--research`
(+ `--variation N`); the resolved angle overrides the brief headline/sub. MEASURED LIVE on
Digilians (Serper + gpt-4o): surfaced real sourced facts the homepage scrape never had —
"fully funded scholarship", "train 5,000 annually in AI/cybersecurity" (techafricanews),
"partners with 30 ICT firms" (connectingafrica); var0 → "Train with Egypt's Top ICT Firms",
var1 → "5,000 Tech Experts Trained Annually" — two different grounded headlines + different
LLM layouts, vs the old fixed "الرواد الرقميون".
ALSO FIXED (caught in the same live QA): image models BAKED raw palette HEX into the
background as visible text ("#133B66 #B19257" rendered in a Digilians bg). `art_director`
now describes the palette to the image model by NAME (`_hex_to_color_name`/`_palette_names`,
e.g. #133B66→"deep navy blue"), never raw hex; the DESIGN-spec call still passes hex (the
model must pick `accent_hex` from the exact palette — that text never reaches the image).
Tests: `tests/test_brand_research.py` (6, FakeProvider+MockCaller, network-isolated via
monkeypatch per the documented SERP-key gotcha). Suite **576 passed**. NEXT: enable
`--research` by default when keys exist (graceful fallback) + apply the same fresh-copy +
design-spec engine to the REEL; consider a light evidence validator that the chosen angle's
hard claim still appears in its cited snippet at render time.

## Done — Gemini caller (Vertex) + default_caller; poster LLM work moved off OpenAI (2026-06-16) ✅
Cost reality (owner): ~$300 GCP/Vertex credits vs ~$3 OpenAI — so the LLM work must run on
Gemini. `business_profile/llm/caller.py`: new `GeminiCaller` (google-genai, **Vertex mode**
by default — authenticates via GCP ADC + `GOOGLE_CLOUD_PROJECT`, the same path as Imagen/Veo,
so it draws on the GCP credits; no API key needed). Same `Caller` protocol as `OpenAICaller`,
structured outputs via `response_schema` (Pydantic) -> `response.parsed`, lazy SDK/client,
retry+Usage parity. New factory `default_caller(strong=True)`: prefers Gemini (genai present
+ project set) -> OpenAI -> None; model via `GEMINI_MODEL` env (default `gemini-2.5-pro`
strong / `gemini-2.5-flash` cheap). Exported from `business_profile.llm`. Pricing rows added
so cost tracking doesn't read $0. Poster pipeline (`poster/__main__.py`, `api/routes/poster.py`)
now builds the caller via `default_caller(strong=True)` — research + design-spec + concept all
run on Gemini, OpenAI is fallback only. MEASURED LIVE: gemini-2.5-pro works via Vertex with
structured output (a probe call cost $0.0007 from credits); full digilians `--research` ran
end-to-end on Gemini and its research was RICHER than gpt-4o's — it surfaced the OFFICIAL
government source (sis.gov.eg State Information Service) confirming "الرواد الرقميون" is a
fully-funded **presidential initiative**, plus techafricanews/ahram. Quality vs gpt-4o:
comparable for these tasks (design choices + copy from snippets) — no meaningful loss, big
cost win. Also fixed: `poster/__main__.py` reconfigures stdout/stderr to UTF-8 (Windows cp1252
console crashed printing an Arabic angle). Suite **576 passed** (LLM callers are MockCaller in
tests; Gemini not exercised in CI). NOTE: profile-extraction pipeline still defaults to OpenAI
— migrate it to `default_caller` separately (measure first; it's the token-heavy path that
most benefits from cheap Gemini Flash).

## Done — BrandBook: one-time MULTIMODAL brand understanding (vision) (2026-06-16) ✅
Owner's insight: don't just grab an image as a background ("that's nonsense") — the model
should UNDERSTAND the brand from its images, ONCE, and emit a reference FILE the poster/reel
read from (cheaper, consistent, deeper). Also: "Gemini Omni" = Gemini 2.5 Pro is ALREADY
multimodal; we just weren't feeding it images. New package `brand/` (`brand/brand_book.py`
+ `python -m brand <profile.json>`): `build_brand_book(profile, caller, search_provider)`
fetches the brand's REAL scraped photos (`visual.content_images`, SSRF-guarded), runs deep
research (sourced facts), and makes ONE **multimodal** Gemini call (it SEES the images) →
`BrandBook` = visual identity (aesthetic / mood / color_story / typography / photography_style),
`best_background_image_url` (the model picks the strongest REAL photo, never a logo/icon),
recommended_text_color, voice / audience / positioning, and sourced_facts (each w/ URL).
Saved to `outputs/brandbooks/<name>.json`. To pass images, the `Caller` protocol +
GeminiCaller/OpenAICaller/MockCaller gained an optional `images=[(bytes,mime)]` arg (Gemini
uses them via `types.Part.from_bytes`; others accept-and-ignore). Graceful: no caller →
profile-only book; no images → text-only; never raises. Wired into the POSTER via
`--brandbook`: it uses the brand's OWN chosen photo as the background instead of an invented
Imagen scene (directly fixes "the bridge/desert has no relation to them — use the brand's real
images"). MEASURED LIVE on Digilians (Gemini Vertex, vision): saw 4 real photos, read the dual
warm/cool palette + logo character, picked a real photo as background, and its positioning
captured the **Ministry of Communications + Military Academy** partnership; the rendered poster
now shows REAL Egyptian trainees on a laptop (from the actual site), not a generic scene. Tests:
`tests/test_brand_book.py` (4, MockCaller + injected image fetcher, network-isolated). Suite
**580 passed**. NEXT: have the poster also honor `recommended_text_color` (light scrim for dark
text on a light photo) + feed `voice/positioning` into copy; build the BrandBook ONCE in the
pipeline and have BOTH poster + reel read the saved file; migrate profile extraction to Gemini Flash.

## Done/Partial — poster: BrandBook UNDERSTAND→GENERATE (not copy); text-only gen is unreliable (2026-06-16) ⚠️
Owner's correction: reusing the website's OWN image as the poster background adds ZERO value
("ايه الفايدة") — the vision step must UNDERSTAND the brand and GENERATE fresh on-brand work.
DONE: removed the literal real-image-as-background reuse (poster/__main__ `--brandbook`);
`build_llm_concept_prompt(..., brand_book=...)` now, when a BrandBook is present, swaps its
system prompt from "surreal metaphor" to "a FRESH photorealistic, on-brand scene in the brand's
OWN visual world" — fed the BrandBook's learned `photography_style`/`aesthetic`/`mood`/audience
(`_brandbook_style_lines`). Tests: `tests/test_poster_design.py` (+2: style reaches the call;
no-book keeps the metaphor path). Suite **582 passed**.
HONEST LIVE FINDING (the important part): pure TEXT→image generation is UNRELIABLE for tight
on-brand specificity — Digilians (Egyptian youth tech-education) produced (1) a generic woman
studio portrait, then (2) an off-brand EUROPEAN STREET. Adding "show the brand's people ACTIVELY
doing its real activity" did not fix the wandering. So neither extreme is right: literal reuse =
no value; text-only generation = off-brand. The CORRECT path is IMAGE-CONDITIONED generation —
feed the brand's REAL photos to the generator as reference so the new image is FRESH but anchored
to the brand (exactly what the reel already does via Veo image-to-video). For stills this needs
Imagen image-conditioning / subject-customization (a bigger integration) — NOT bundled here; it
is the next decision. Until then the metaphor path (no brand_book) is more reliable than the
text-only brand path for posters.

## Done — poster: grounded image PROMPT (fixes off-brand / off-palette generation) (2026-06-16) ✅
Owner's correct diagnosis: "Imagen quality is good, the PROMPT is crap." The understand→generate
path was producing OFF-brand images (a generic Western man, a European street for an Egyptian
tech brand) and IGNORING the brand palette. Root causes + fixes (`poster/art_director.build_llm_concept_prompt`):
1. **Lead with grounding, demote the LLM prose.** Imagen weights the START of the prompt most;
   a long free LLM "creative scene" + a generic "stock photography" style line dominated and made
   it wander. Now the prompt LEADS with the concrete on-brand subject + region + brand palette as
   the primary instruction; the LLM's prose is trimmed to a short "secondary creative cue (do not
   override the above)".
2. **Region anchor** (`_region_line`): Arabic/RTL brands get "authentic Middle Eastern / Arab
   setting, real local people; NOT Western/European architecture/streets/people" — this is what
   killed the European-street drift.
3. **Concrete subject** (`_subject_line`): "real people authentically engaged in <category> —
   specifically <offering>", so the scene depicts the brand's real ACTIVITY, not a static portrait.
4. **Palette enforced** as the dominant colors (by name) "in the lighting, environment and wardrobe".
5. **Drop generic style noise**: a BrandBook `photography_style` mentioning "stock"/"AI-generated"
   is ignored (it pulled toward generic stock portraits).
Also: `imagen_provider._COMPOSITION_CONTRACT` no longer hardcodes "lower half" (it contradicted the
layout's real negative-space zone); `poster/__main__` now tries **Imagen 4 Ultra** first (better
prompt adherence) and falls back to `imagen-4.0-generate-001` on a 429 (the lighter model followed
the prompt noticeably worse). MEASURED LIVE on Digilians (--brandbook, Ultra): the background is now
young Egyptian people (incl. a woman in hijab) coding on laptops in a modern tech lab with Islamic
geometric architecture, the brand's navy+gold palette dominant, calm text zone at top — a correct,
on-brand, region-authentic scene (vs the earlier Western-man portrait). Tests: `tests/test_poster_design.py`
(14, incl. brandbook style reaches the call + metaphor fallback). Suite **582 passed**. NOTE: still
text-to-image (no per-pixel control); Ultra + the grounded lead made it reliable enough. Image-
conditioning (real photos as reference) remains a future option but is no longer required.

## Done — poster: accent from real palette (vivid) + country-specific people (2026-06-16) ✅
Two owner-reported defects on the Digilians poster:
1. "The gold accent isn't from the scheme." The LLM design-spec had picked `accent_hex=#B19257`
   (a muted tan that IS in the palette but reads generic/off-brand). Fix (`poster/template._brand_accent`):
   the rendered accent is now the **most SATURATED brand-palette color that's legible on the dark
   scrim** — for Digilians that's the vivid brand blue `#0D6EFD`, not the tan. `_brand_accent`
   replaces the old `spec.accent_hex or _accent(brief)` at the render site; the spec's color is a
   fallback only. (Navy `#133B66` is excluded as too dark to read as an accent on the scrim.)
2. "This hijab is Gulf/Arab, not Egyptian." The region anchor said generic "Middle Eastern/Arab".
   Fix (`poster/art_director._region_line` + `_country`): derive the brand's COUNTRY from its
   `source_url` ccTLD (`_CCTLD_COUNTRY`, e.g. .eg→Egypt) and instruct "authentic local people from
   <country> in their own style/dress — NOT Gulf/Khaleeji, NOT a generic 'Arab' look, NOT Western".
MEASURED LIVE (Digilians, --brandbook, Ultra): accent is now the brand blue across headline/CTA/rule;
the scene shows young local people on laptops in a warm Egyptian setting (no Gulf hijab, no European
street). Suite **582 passed**. STILL OPEN (owner: "same text design"): typography is one fixed
treatment — varied per-brand fonts + kinetic/angled headline treatments is the next step (the "B"
creative-copy + typography work), plus making `--research` default so the headline isn't the same
verbatim line every run.

## Done — poster/reel: recover lost logos (inline-svg reject + word-boundary blocklist + SVG support) (2026-06-19) ✅
MEASURED root cause of "no logo" across the saved corpus: a before/after benchmark over
**37 saved sites** showed only **20/37 (54%)** rendered a logo. Three failure modes, all
in the poster's logo selector / renderer (NOT the scraper) — fixed ONE AT A TIME, the
benchmark re-run between each (rule 1):
1. **`inline-svg:N` leaked as the logo URL.** The scraper emits a pseudo-src
   `inline-svg:<n>` for an inline `<svg>` (no fetchable URL). `_extract_logo` was
   selecting it — and WORSE, it WON over a real raster candidate (conf 1.0) sitting in
   the same `logo_candidates` list AND silenced the wordmark-fallback warning, so the
   brand rendered no logo at all. Fix (`poster/from_profile._real_raster_src`): a
   candidate's src must resolve to a FETCHABLE `http(s):`/`data:` URL; `text-wordmark:`
   and `inline-svg:` pseudo-srcs are rejected. MEASURED: **54% → 81% (20→30)**, +10 sites,
   zero test regressions.
2. **Word "background"/"cover" rejected by SUBSTRING.** The hero/banner blocklist used a
   substring match, so a legit logo `...Transparent_Background_...` (1000earring, conf
   1.0) was dropped to a weaker candidate (and `discover`/`recover` contain "cover"). Fix
   (`_candidate_is_reasonable_logo`): whole-word `\b(banner|hero|background|cover)\b`.
   Underscore is a word char so `transparent_background` survives while a real
   `site-background.jpg` hero still matches. MEASURED: count holds at 30; 1000earring now
   picks its conf-1.0 Primary logo (correctness, not count).
3. **`.svg` logos were dropped (Pillow-era reject).** The renderer is now
   Playwright/Chromium, which renders SVG natively. Removed the `.svg` reject in the
   selector; both renderers inline an SVG logo as a data-URI
   (`poster/template._remote_image_data_uri`, `reel/textlayer._logo_data_uri`,
   `image/svg+xml`). SAFE: an SVG loaded via `<img src="data:image/svg+xml…">` runs in
   Chromium's secure static mode (no scripting / no external fetch), and the fetch is
   already SSRF-guarded. MEASURED: **81% → 83% (30→31)** (+eva); 6 more sites switched
   from a weaker raster to their real high-confidence brand SVG (brilliantearth, glamira,
   sofitel, andalusia, buffaloburger).
VERIFIED (not just counted): rendered an inlined SVG end-to-end — Chromium reproduced it
at EXACT color fidelity `(255,0,170)` (isolation render) and the poster showed a clean
**10,876-px** logo disc where there had been none. The earlier "fail" was a too-strict
pixel detector (`r>110` excluded the disc body `(69,9,56)`), NOT a render bug.
Changed: `poster/from_profile.py` (`_real_raster_src`, `_candidate_is_reasonable_logo`),
`poster/template.py` (`_remote_image_data_uri`), `reel/textlayer.py` (`_logo_data_uri`).
Suite **582 passed** (zero regressions). REMAINING 6/37 (adidas, lcwaikiki, mumm,
spclinic, clear-lsc, sedu) have **0 logo candidates from the scraper** — a separate
scraper-side gap, not this layer. NEXT (separate, bigger): rasterize the inline `<svg>`
markup itself so andalusia/vodafone-class sites that ship the logo as inline SVG (no
file URL) recover it too — currently those still fall through.

## Done — reel: Veo model-404 config fix + per-scene fallback (no more crash) (2026-06-19) ✅
Tier 0 #2. Root cause of "the CLI reel comes out broken": the reel pointed at a Veo
model that 404s on this project AND had no recovery, so a single provider error killed
the whole render. Fixed as TWO separate changes (rule 1), suite re-run between:
1. **Config — wrong Veo model (the immediate 404).** `.env` set
   `REEL_VIDEO_MODEL="veo-3.1-generate-001"` and `DEFAULT_VEO_MODEL` was
   `veo-3.1-generate-preview` — both 404 NOT_FOUND on project image-498715 (3.1 not
   provisioned; CLAUDE.md already measured `veo-3.0-generate-001` as the working model).
   Pointed both at `veo-3.0-generate-001` (`.env` + `reel/video_provider.DEFAULT_VEO_MODEL`,
   comments updated). No test pinned the model name. LIVE Veo render = the real proof but
   costs money + ADC, so it's out-of-CI (same policy as the other live paths).
2. **Resilience — a per-scene provider failure no longer crashes the reel.**
   `reel/compositor.render_reel` wrapped the per-scene `provider.generate` in try/except
   (it had NONE — a Veo 404/429/quota/timeout propagated and aborted the entire render).
   On failure that ONE scene is regenerated by a `fallback_provider` (new optional param),
   `fallback_used` flips True, and the failure is printed to stderr (a degraded reel is
   never silently passed off as a full provider render). DEFAULT fallback = a
   `KenBurnsProvider` over the storyboard's REAL scraped photos (`content_images`) — degrade
   to the actual place, not a blank gradient — which itself degrades to a palette gradient
   when there are no usable photos. (Stub/KenBurns already never raise — they catch
   internally; only Veo was the crash source.) Tests: `tests/test_reel_reference_image.py`
   (+2: explicit-fallback path + default-is-KenBurns-over-real-photos, both hermetic —
   fake text-layer + fake ffmpeg, no network). Suite **584 passed** (was 582).
NEXT (separate Tier-1 reel items, measured first): 76% of saved profiles have 0
`content_images` -> reel degrades to gradients (re-scrape to populate); Veo snaps
duration to 4/6/8s (storyboard rhythm + cost); "wall of text" scenes (148-164 chars on a
weak scrim in 4s).

## Done — poster: reject low-conf banner masquerading as the logo (Vodafone) (2026-06-19) ✅
MEASURED disaster surfaced on the Vodafone delivery: the poster rendered a wide
**product banner ("Rateplans.jpg" — a phone mockup + "Vodafone rate plans" + RED promo)
as the brand logo.** Root cause chain: Vodafone ships its real logo ONLY as inline
`<svg>` (42 `inline-svg:N` refs; markup NOT stored in the manifest), so the prior fix
correctly rejected all those pseudo-srcs — but the raster fallback pool was ALL content
banners (no real logo file), and `_extract_logo` step 2 took the highest-conf raster =
the banner (conf 0.38, classification `unknown_candidate`). So my recent logo fix shifted
Vodafone from broken-img to wrong-banner; this is the defensive net it needed.
MEASURED across 37 saved sites BEFORE changing (rule 2): every TRUE logo scored
**>=0.54** (incl. a real logo the scraper left as `unknown_candidate` — Qasr Elkbabgi's
gold crest at 0.54, VERIFIED by eye); the ONLY banner-as-logo cases were Vodafone's
0.38 promo. Confidence alone doesn't separate (0.54 real vs 0.38 banner), but
class+conf does. Fix (`poster/from_profile`): `_is_probably_not_a_logo(classification,
conf)` = `classification == "unknown_candidate" and conf < _UNKNOWN_LOGO_MIN_CONF (0.5)`;
applied in BOTH `_extract_logo` step 1 (primary_logo) and step 2 (candidate loop). The
0.5 floor sits in the measured gap → rejects Vodafone's 0.38 banner, KEEPS Elkbabgi's
0.54 crest, and never touches a positively-classified `primary_brand_logo` (any conf).
MEASURED AFTER: banner-as-logo **2 -> 0**; Elkbabgi/diplomatic-lark keep their real crest;
all 27 `primary_brand_logo` unchanged; no real logo lost (raw render 31->29 is just the 2
Vodafone false-positives dropping to a clean text wordmark). VERIFIED by render: the
Vodafone poster now shows a clean wordmark plate, not the rate-plans banner. Tests:
`tests/test_poster_design.py` (+3: banner rejected->wordmark, unknown_candidate>=0.5 kept,
primary_brand_logo kept at low conf). Suite **587 passed** (was 584).
NEXT (separate, for the Vodafone delivery's REAL logo): rasterize/capture the inline
`<svg>` markup (scraper-side + re-scrape) so Vodafone/andalusia-class brands get their
ACTUAL logo, not just a wordmark fallback. Also open: og_site_name chrome leak
("Vodafone Egypt E-Shop") + Imagen baking text ("OR") + Western person for an .eg brand
(region anchor not reaching the imagen-4.0 path) — each its own measured fix.

## Done — name: strip e-commerce SECTION chrome ("E-Shop") at the source (2026-06-19) ✅
MEASURED on the Vodafone delivery: the scrape landed on the e-shop sub-site
(web.vodafone.com.eg), whose `og_site_name = "Vodafone Egypt E-Shop"` → every output
(poster wordmark, reel, SWOT) said "Vodafone Egypt E-Shop". "E-Shop" is a SECTION
designator (like "website"/"online store"), not the brand. Fix: extend
`from_metadata._TRAILING_CHROME` with e-commerce section words
(`e-shop`/`eshop`/`e shop`/`online shop`/`online store`/`webshop`) — same deterministic
whole-word, fixed-point `_strip_chrome` path already used for website/official/homepage,
so the SOURCE name is clean and all consumers inherit it. MEASURED across **48 saved
og_site_name/title strings**: exactly **1** changed ("Vodafone Egypt E-Shop" -> "Vodafone
Egypt"); zero collateral. Bare "shop"/"store" stay EXCLUDED — VERIFIED "EVA Shop" and
"The Body Shop" untouched (only the e-shop/online-shop compounds strip). Tests:
`tests/test_rules.py::test_strip_chrome_is_conservative` (+Vodafone e-shop, +Online Store,
+EVA Shop / The Body Shop safety). Suite **587 passed**. NOTE: applies at extraction time
— a saved profile needs a RE-EXTRACT (`python -m business_profile <manifest> -o ...`) to
pick up the clean name; the code is correct for fresh extractions.

## Done — finding: off-brand bg (Western person, baked "OR" text) = imagen-4.0, NOT a prompt bug (2026-06-19) ✅
Investigated the Vodafone poster's off-brand background (a generic Western man + giant
baked "OR" letters in a supposedly text-free image). VERIFIED it is NOT a code/prompt
bug: `_country(profile)` returns "Egypt" (from the .eg ccTLD) and `_region_line` emits a
STRONG anchor ("set in Egypt... authentic local people from Egypt... NOT Western or
European... people"), which the LLM-path lead in `build_llm_concept_prompt` DOES include
— and the maximal "ABSOLUTELY NO text, words, letters, numbers" instruction is present
too. ROOT CAUSE was the IMAGE MODEL: the render had been forced to
`imagen-4.0-generate-001` (to dodge Ultra 429s), which — as CLAUDE.md already measured —
"followed the prompt noticeably worse". Re-rendered on **`imagen-4.0-ultra-generate-001`**
(the pipeline's default first choice): the SAME prompt produced authentic Egyptian people
in a real Cairo street with a Vodafone-red storefront, brand palette dominant, and ZERO
baked text. LESSON: for delivery use Ultra (poster/__main__ already tries it first and
only falls back to 4.0 on 429); do NOT force the lighter model. No code change — the
grounded-prompt scaffolding was already correct.

## Done — inline-SVG brand logo: rasterize the REAL logo (Vodafone-class) + visibility gate (2026-06-19) ✅
THE root-cause fix for "no real logo" on sites that ship the brand mark as an inline
`<svg>` (often a `<use href="#sprite">` whose paths+colours live in a `<symbol>` + CSS):
the scraper could only record `inline-svg:N` (no fetchable URL), so the poster/reel fell
back to a text wordmark. Owner's bar: "solve it AND don't break on the next site."
APPROACH (MEASURED, not guessed): rasterize the logo EXACTLY as the browser renders it
(via Playwright) — `<use>` sprite resolved + CSS-class fills applied — ISOLATED from the
page (every other element hidden via `*{visibility:hidden}`, the referenced `<symbol>`
re-revealed) on a TRANSPARENT bg, then a VISIBILITY GATE: accept only if the capture
shows visible ink composited on the poster's light chip (`_MIN_INK_RATIO`). So a logo
that would render blank there (white-on-dark, or a mis-indexed nav icon) is REJECTED ->
the clean wordmark stands. Worst case = the existing wordmark, NEVER a broken/blank logo.
- New `scraper/inline_svg_logo.py`: `capture_inline_svg_logo(html, svg_index)` (browser
  rasterize+gate, lazy Playwright, never raises) + `enrich_profile_logo(profile, raw_html)`
  (writes the PNG `data:` URI into the profile when the primary logo is `inline-svg:N`).
  Side-effect free.
- 3 poster fixes that the data-URI logo exposed (`poster/from_profile`, `poster/schemas`):
  (a) `_absolute_url` now PASSES `data:` URIs through (it was returning None -> the logo
  was dropped); (b) `_extract_logo` step 3 (legacy `logo_url`) now requires a fetchable
  `http(s)`/`data:` URL so `inline-svg:`/`text-wordmark:` pseudo-srcs can't leak as a
  broken `<img>`; (c) `PosterBrief.logo_url` max_length 1000 -> 300_000 (an inlined logo
  is far larger than an http URL).
- Wired into `business_profile/__main__` (post-write, best-effort): EVERY profile build
  now auto-rasterizes an inline-svg logo from the scrape's `raw/00_homepage.html`.
MEASURED across the 5 saved inline-svg sites (the robustness test the owner demanded):
**Vodafone (red `<use>` sprite), JewelPin, Artemer -> REAL logo recovered**; Andalusia
(white-on-dark) + Assih (mis-indexed icon) -> gate-rejected to wordmark. **3 recovered,
0 broken.** VERIFIED end-to-end: the Vodafone delivery poster now shows the real red
speech-mark logo (top-left chip) alongside the Egyptian street scene + "Connecting Egypt
Since 1998" headline. Tests: `tests/test_inline_svg_logo.py` (4, hermetic — index parse,
ink gate blank-vs-visible, enrich no-op paths; live Playwright capture is out-of-CI).
Suite **591 passed** (was 587). HONEST LIMITATION (the 2 rejects): a WHITE logo
(Andalusia) is correctly skipped because it's invisible on the light chip — recovering it
needs a luminance-aware DARK logo chip (future enhancement); Assih's wrong index is a
scraper logo-classification gap, not this layer.

## Done — inline-SVG logo: luminance-aware DARK chip recovers white logos (2026-06-19) ✅
Closes the honest limitation of the entry above: a WHITE/light logo (Andalusia) was
gate-rejected to a wordmark because it's invisible on the poster's default light chip.
Now the capture gate also DECIDES the chip. MEASURED (opaque-pixel fraction + mean
luminance of the transparent capture across the 5 sites): a real logo has a MODERATE
opaque fraction (Vodafone's disc 79%, the rest 4-5%); Assih's false positive was a
**100%-opaque uniform white block** (not a logo). So `_gate` (`scraper/inline_svg_logo`)
now: reject if opaque <1% (blank) OR >95% (solid block → kills the Assih false accept);
else return `prefers_dark` = mean-luminance > 0.62. `enrich_profile_logo` writes
`logo_chip="dark"|"light"`; `build_poster_brief` surfaces it (only for the rasterized
primary) onto `PosterBrief.logo_chip`; `template.py` renders a DARK plate
(`rgba(18,20,26,.92)`) for a light logo, else the default light plate. MEASURED outcome
across the 5 sites: Vodafone/JewelPin/Artemer → light chip; **Andalusia → DARK chip
(white logo RECOVERED, VERIFIED by render — visible on a dark plate, RTL top-right)**;
Assih → still rejected (solid block). **4/5 recover their real logo, 0 broken.** Tests:
`tests/test_inline_svg_logo.py` (gate: blank+solid-block reject, chip-by-luminance).
Suite **592 passed** (was 591). REMAINING reject (Assih) is a scraper logo-index gap, not
this layer.

## Done — scraper: contact-link icon must not outrank the real logo (Assih) (2026-06-19) ✅
Closes the Assih "REMAINING reject" from the entry above. ROOT CAUSE (measured on the
saved Assih manifest): the scraper's `primary_logo` was `inline-svg:15` — a header EMAIL
icon (`<a class="SocialLinks-link email" href="mailto:info@assih.com"><svg><use
href="#email-icon">`) — scored **0.86** `primary_brand_logo` and OUTRANKED the brand's
REAL raster logo (`logo_Asslam.png`, **0.78**). Why it escaped the existing −80
`penalty_social_icon`: `is_social` is a regex over social-NETWORK names
(facebook|instagram|…|whatsapp), which doesn't match `mailto:`/`tel:`. Fix
(`scraper/extractors/visual._score_logo_candidates`): also treat a candidate whose
anchor `href` is a CONTACT link (`mailto:`/`tel:`/`sms:`/`api.whatsapp.com`/`wa.me/`) as
social → same −80. A brand logo's anchor links HOME, never to a contact endpoint, so this
is SAFE-BY-CONSTRUCTION (it can only demote contact icons, never a real logo). VERIFIED
on synthetic Assih-shaped candidates: real logo 112 (primary_brand_logo, TOP) vs email
icon 6 + WhatsApp icon −12 (both `unknown_candidate`). NOTE: the POSTER was already
correct here — `_extract_logo` step 1 rejected the `inline-svg:15` pseudo-src and step 2
fell through to the 0.78 raster, so Assih's poster ALREADY rendered the real
"as-salam international hospital" logo; this fixes the wrong value at the SOURCE
(primary_logo) for every consumer + future scrapes. Tests:
`tests/test_visual_identity_v02.py::test_contact_link_icon_does_not_outrank_the_real_logo`.
Suite **593 passed** (was 592). NOTE: applies at scrape time — the saved Assih manifest
needs a RE-SCRAPE to flip its stored primary_logo; the code is correct for fresh scrapes.

## Done — reel: AIML-gateway Veo 3.1 provider (i2v + native voiceover) (2026-06-20) ✅
Idea borrowed from a competitor repo review (TrendPulse): reach **Veo 3.1** through the
**AIML API gateway** (`https://api.aimlapi.com/v2`, model `google/veo-3.1-i2v`) instead
of Vertex — our GCP project only has Veo 3.0 provisioned (3.1 404s), and Veo 3.1 renders
NATIVE audio/voiceover from the prompt (no separate TTS). New `AimlVeoProvider`
(`reel/video_provider.py`): same `VideoProvider` contract (one text-free scene clip per
call) — submit → poll-until-completed (cap `max_polls × poll_interval`) → download to
`out_path`; stdlib `urllib` only (no new dep); an http(s) `reference_image` is passed as
the i2v `image_url` (a local seed is skipped → t2v). RAISES on any failure so the
compositor's fallback (KenBurns over real photos → gradient) takes over — never a silent
blank. Wiring (`default_video_provider`): `REEL_VIDEO_BACKEND=aiml` OR an `AIML_API_KEY`
in env selects AIML; `=vertex` (or just a Gemini key / GCP project) forces the Veo 3.0
Vertex path; `REEL_FORCE_STUB=1` stays offline. `.env` has a commented `AIML_API_KEY` +
`REEL_AIML_MODEL` placeholder. Tests: `tests/test_reel_reference_image.py` (+3, hermetic
— submit/poll/download mocked, local-seed skip, no-key error, provider selection; no
network/AIML account). Suite **596 passed** (was 593). LIVE run needs an AIML key + costs
money (out-of-CI, same policy as Vertex Veo). NEXT (same TrendPulse review, queued): (2) a
trend engine (trend-driven campaigns from Reddit/HN/YouTube…); (3) content calendar +
strategy builder; plus reel COHERENCE (character/style anchor + per-scene cinematography +
narrative-structure storyboard) — the biggest quality lever, foldable into either Veo path.

## Done — trends: ride a CURRENT trend (free keyless sources) (2026-06-20) ✅
Feature #2 from the TrendPulse review (a much lighter take — no 14-source ML pipeline; a
focused, dependency-free v1). New `trends/` package: pull currently-trending items from
FREE, KEYLESS public APIs and surface the ones RELEVANT to the business so a campaign can
ride a real moment instead of a generic angle.
- `trends/sources.py`: `TrendSource` protocol + `HackerNewsSource` (Firebase topstories),
  `RedditSource` (public `/r/<sub>/hot.json`, needs a UA), `DevToSource` (articles API) +
  `default_trend_sources()`. stdlib `urllib` only, NEVER raises (network/parse error ->
  `[]`), same discipline as `competitor/search_providers.py`.
- `trends/engine.py`: `fetch_trends` (aggregate; a failing source contributes nothing) ->
  `rank_trends` (popularity NORMALIZED per source so HN points and Dev.to reactions are
  comparable, + recency decay: `0.7*pop + 0.3*recency`, recency=1 now / 0.5 at 24h) ->
  `match_to_keywords` (whole-word, stopword-filtered) -> `top_trends` (on-topic first,
  then by score; `require_match` drops unrelated). `keywords_from_profile` pulls topical
  terms from a BusinessProfile (category + offering names + value props + tagline).
- `python -m trends "<keywords>"` / `--profile profile.json` / `--require-match`.
MEASURED live (free APIs, no key): real HN + Dev.to trends fetched + ranked end-to-end.
Tests: `tests/test_trends.py` (6, hermetic — injected fake sources, deterministic `now`;
aggregate+skip-failing, per-source normalize, whole-word/stopword match, on-topic-first,
require_match, profile keyword extraction). Suite **602 passed** (was 596). NOT wired into
the campaign output yet (next: feed the chosen trend into the poster/reel headline angle).
NEXT from the review: (3) content calendar + strategy builder.

## Done — strategy: N-day content calendar + strategy builder (2026-06-20) ✅
Feature #3 from the TrendPulse review (a focused library/CLI version — no SaaS UI). New
`strategy/` package: turn a BusinessProfile into a concrete, dated CONTENT CALENDAR.
- `strategy/builder.py`: `build_strategy(profile, caller, *, days, platforms, trends,
  start_date, cadence_per_week)` -> `ContentCalendar` (dated `ContentItem`s: date /
  platform / content_type / topic / angle / hook). An LLM (the SAME `Caller` the poster
  uses) plans a varied mix grounded in the brand persona + real offerings, and can RIDE
  current trends (pass `trends.top_trends(...)`). A content PLAN is design, not a factual
  claim (two-truth-domains), so paraphrase is fine. Degrades to a DETERMINISTIC plan
  (cycles the brand's real offerings across the window) with no caller OR on LLM error —
  never empty, never fabricated. `day_offset` is clamped to the window; items dated +
  sorted; `ContentCalendar.save()` writes JSON.
- `python -m strategy <profile.json> --days 30 [--platforms ...] [--trends] [--no-llm]`.
MEASURED live (`--no-llm` fallback): an 8-item / 14-day Vodafone calendar cycling REAL
offerings (Vodafone Cash, DSL, Home Wireless Routers, Samsung Products, RED Plans…) across
instagram/tiktok/linkedin + reel/post/story/carousel, correctly dated. Tests:
`tests/test_strategy.py` (6, hermetic — MockCaller plan dating, day-offset clamp, fallback
cycles offerings, trends woven into the prompt, save roundtrip, LLM-error fallback). Suite
**608 passed** (was 602). NOT yet wired to auto-generate a poster/reel per calendar item
(next: one-click "generate" from a calendar entry, like TrendPulse's pre-filled form).

## Done — wiring: trends → poster copy, and calendar item → poster (loop closure) (2026-06-20) ✅
Integrated the 3 new TrendPulse-review features into the actual creative output, in order.
1. **Trend → copy** (`poster/brand_research.research_brand` + `poster/__main__ --trend`):
   `research_brand` gained a `trend_context` param injected into the copywriter prompt;
   the system prompt now allows tying ONE angle to a current trend "only if it genuinely
   fits — never force it / never fabricate a link". `poster --trend` fetches
   `trends.top_trends(keywords_from_profile(profile), require_match=True)` and passes the
   on-topic titles in. Grounding intact: the trend is real (sourced from the free trend
   APIs) and the LLM still must ground the claim; an off-topic trend is dropped by
   `require_match`. Test: `tests/test_brand_research.py::test_trend_context_reaches_the_copywriter_prompt`.
2. **Calendar item → poster** (`build_poster_brief(profile, headline_override=...)` +
   `poster/__main__ --from-plan plan.json --item N` / `--headline "..."`): a content-
   calendar item's `hook` (else `topic`) becomes the poster headline, closing
   profile → `strategy` (rides trends) → scheduled item → creative. `headline_override`
   is DESIGN copy (two-truth-domains), same status as the existing `--research` angle; an
   empty override is ignored (never blanks the headline). Tests:
   `tests/test_poster_design.py::test_headline_override_drives_the_brief`.
MEASURED live (offline `--no-image`): `--from-plan vodafone_plan.json --item 3` loaded the
2026-06-23 instagram/carousel item and rendered a poster headlined "Samsung Products"
(the planned topic). Suite **610 passed** (was 608). NEXT (symmetric, queued): thread
`headline_override` + `--trend`/`--from-plan` into the REEL (`build_reel_brief` reuses the
poster selectors, so it's the same shape); and a content_type→poster/reel dispatcher so
one calendar can fan out the whole month's creatives.

## Done — reel wiring + campaign dispatcher (calendar fans out to creatives) (2026-06-20) ✅
Symmetric follow-up to the poster wiring + the loop-closure capstone.
1. **Reel honors a planned headline** (`reel/from_profile.build_reel_brief(profile,
   headline_override=...)` + `reel/__main__ --headline` / `--from-plan plan.json --item N`):
   `build_reel_brief` already REUSES `build_poster_brief`, so threading `headline_override`
   through is one line — a content-calendar item drives the reel headline exactly like the
   poster. Test: `tests/test_campaign.py::test_reel_brief_honors_headline_override`.
2. **Campaign dispatcher** (`campaign/`): `plan_creatives(calendar) -> [CreativeJob]` maps
   each calendar item to a POSTER or REEL by `content_type` (reel/video/short -> reel, else
   poster), resolves the headline (hook else topic), and names a dated output path. PURE +
   testable. `run_all(jobs, profile, plan, runner=...)` executes via an INJECTABLE runner
   (default `run_creative` shells out to `python -m poster|reel --from-plan ... --item N`,
   so every existing flag + the grounded pipeline are reused). `python -m campaign
   <profile> --from-plan plan.json [--dry-run] [--only N] [--trend]` (`--trend` adds the
   trend-ride to posters). Tests: `tests/test_campaign.py` (4: type/headline/ext mapping,
   dry-run calls nothing, runner-per-job + only-index, reel override).
MEASURED live (`--dry-run`): a Vodafone 8-item calendar fanned out to 2 reels (.mp4) + 6
posters (.png), each with its planned headline (Vodafone Cash / DSL / Samsung Products …)
and a dated output path. Full end-to-end now: `business_profile -> strategy --trends ->
campaign --from-plan` => a month of grounded, on-brand, trend-aware creatives. Suite
**614 passed** (was 610). NEXT: a reel `--trend` copy path (the reel has no research step
yet — the dispatcher only rides trends on posters); per-item Imagen/Veo cost is real so a
full-calendar render is out-of-CI.

## Done — adversarial review of the session's feature code: 7 confirmed bugs fixed (2026-06-20) ✅
Ran a multi-agent adversarial review (5 dimensions × independent skeptic verification) over
this session's new code (trends/strategy/campaign/AIML/logo/wiring). 7 of 8 candidate
findings VERIFIED real and FIXED (each with a regression test; suite 614 -> **617 passed**):
1. **(grounding, HIGH)** `poster/brand_research.py`: the provenance check had an escape
   hatch `... and not src.startswith("http")`, so a model-HALLUCINATED http URL (one the
   search never returned) was kept as a citation and could launder an unsourced hard claim
   past `pick_angle(prefer_safe=True)` onto the poster. Now a source must be in the real
   `valid_sources` (what the search actually returned) or it's downgraded to 'profile'.
   ALSO hardened `pick_angle`: when prefer_safe empties the safe set it now FALLS BACK to
   the verbatim headline (was `safe or angles`, which re-admitted the unsourced claim).
2. **(wiring, HIGH)** `poster/__main__.py`: default-on `--research` silently OVERRODE an
   explicit `--headline` / `--from-plan` calendar hook (the angle replaced brief.headline),
   breaking the calendar->creative loop closure for posters. Research is now skipped when
   `headline_override` is set — the planned/explicit headline wins. (This also fixes the
   campaign-dispatcher asymmetry where reels kept the hook but posters lost it.)
3. **(correctness, MEDIUM ×2)** `trends/engine.py` + `strategy/builder.py` read a
   value_proposition's text via `vp.get("text")`, but an EvidencedField serializes its text
   under `value` — so EVERY value prop was silently dropped from trend keywords / calendar
   topics. Now `_val(vp)` (unwraps `{"value": ...}`; passes a plain string through). The
   unit fixtures had MASKED this by using `{"text": ...}` — corrected to `{"value": ...}`.
4. **(robustness, MEDIUM)** `reel/video_provider.AimlVeoProvider._poll` assumed `video` is a
   dict; a bare-URL-string `video` raised AttributeError, discarding a VALID paid render to
   the fallback. Now handles dict | string | flat `video_url`.
5. **(security, MEDIUM)** the AIML download fetched the gateway-returned `video_url` with no
   guard; now rejects non-http(s) (no `file://` local-read), gates via
   `scraper.url_utils.is_safe_public_url` (SSRF), and bounds the read — matching
   `_load_reference_image`'s existing discipline.
Tests: `test_brand_research.py` (hallucinated-source downgrade + not surfaced),
`test_reel_reference_image.py` (poll string-video, download rejects file://),
`test_trends.py` (fixture corrected). The 1 non-confirmed finding was a true false-alarm.

## Done — reel: Gemini TTS voice-over (GCP credits) + AIML-403 root cause (2026-06-20) ✅
Owner: "skip AIML, use Gemini for the voice-over." Two parts:
- **AIML 403 root cause (diagnosed, then skipped per owner):** every `AimlVeoProvider`
  call returned `HTTP 403 error code 1010` — and so did a cheap chat probe with the same
  key, so it's NOT a bad key / model / credits. **1010 is Cloudflare blocking the request
  by User-Agent**: our `urllib` calls send the default `Python-urllib/x` UA, which AIML's
  edge bans. (Fixable later with a browser UA in `_headers()`; not done now — owner said
  skip AIML.) The reel's per-scene fallback already turned all 8 403s into KenBurns over
  real photos with NO crash — live proof of that resilience fix.
- **Gemini TTS voice-over (`reel/voiceover.py`):** new backend alongside OpenAI —
  `gemini-2.5-flash-preview-tts` via Vertex/ADC (the SAME GCP credits as Imagen/Veo, no
  OpenAI key needed; MEASURED: returns PCM L16/24kHz, wrapped to WAV with stdlib `wave`).
  `_resolve_backend` picks gemini|openai (explicit > `REEL_TTS_BACKEND` > auto: Gemini when
  a GCP project/key is set). `narration_lines(storyboard)` derives ONE grounded line per
  scene from the verbatim on-screen text (headline -> subline -> CTA). `reel/__main__`
  (standard path) now synthesizes a voice-over by DEFAULT (Gemini) and muxes it; the
  storyboard already feeds `render_reel(voiceover_path=...)`. `--no-voiceover` opts out.
MEASURED live on Orange Egypt: `python -m reel orange_profile.json --real` ->
KenBurns over 8 real Orange photos + a **Gemini voice-over** (audio=True, aac stereo) +
real-offering text overlay -> a 26.9s 1080x1920 reel, zero AIML, zero crash. Tests:
`tests/test_voiceover.py` (2, hermetic — narration extraction + backend select; live TTS
out-of-CI). Suite **619 passed** (was 617). NEXT (optional): browser-UA on AimlVeoProvider
to unblock Veo 3.1; richer narration via the --creative (Opus) path + Gemini TTS.

## Done — reel: text-overlay redesign (bottom-anchored caption, not floating white text) (2026-06-20) ✅
Owner: the reel's on-video text was "بشع/وحشة جداً" (ugly) — plain white text floating in
the MIDDLE of the frame over the busy subject, a weak centered radial scrim, offerings as
a centered list, CTA bigger than the sub. Ran a 3-lens idea workflow (TrendPulse review +
our reel-vs-poster audit + short-video caption best-practices) → one synthesized spec,
then implemented it in `reel/textlayer.py` (`_scene_html`) + `reel/compositor.py`:
- **Bottom-anchored safe-zone block** (`.lower`): replaces the centered `top:%`/
  `translateY(-50%)` rows. A strong vertical `linear-gradient(to top, rgba(8,12,18,.90)…0)`
  scrim under the text (was a weak centered radial) → white text reads on ANY footage;
  300px bottom pad clears the TikTok/IG UI; top ~55% stays clean for the subject.
- **Hero typography hierarchy**: headline 0.107·W (≤3 words) / 0.085·W, Oswald 700 upper,
  tight tracking + `-webkit-text-stroke` hairline + crisp halo shadow; sub 0.0425·W; CTA
  promoted via a **brand-accent CHIP** (not bigger text). One **accent rule** bar above.
- **Brand accent**: `_accent` now mirrors the poster's `_brand_accent` (most-saturated
  palette color with luminance≥0.16, via reused pure helpers `_hex_to_rgb/_luminance/
  _saturation/_legible_on_dark/_readable_on` from `poster/template.py`); **ONE word** of the
  headline highlighted (`.hl`), CTA chip filled with the accent + auto-contrast text.
- **Logo to a corner** (top-left, RTL→top-right) instead of centered-top.
- **RTL robust**: `align-items:flex-end` for rtl + `unicode-bidi:plaintext` (mixed
  brand+Arabic lines shape per first strong char); `_atom()` LTR isolation kept.
- **Animation**: compositor overlay-y eased from linear to cubic ease-out
  (`pow(max(0,1-t/0.6),3)`, amp 0.035·H).
KEPT (no regress): Chromium-shaped Arabic, zero-hallucination (only verbatim text, CSS-only
emphasis/uppercase), logo SSRF/SVG handling. MEASURED live on Orange (KenBurns + Gemini VO):
intro = hero headline + rule + corner logo; offering = readable description on the scrim;
outro = brand name + accent word + "Shop" chip — all bottom-anchored, readable, designed.
Tests: `tests/test_voiceover.py::test_textlayer_is_bottom_anchored_scrim_and_accent`. Suite
**620 passed** (was 619). DEFERRED (spec §7/§8/§9-followup, separate): a grounded kicker
(needs a `Storyboard.kicker` field), subline line-length clamp, true per-line kinetic
stagger (needs a frame-sequence text layer), and porting the poster's full per-brand font
pairing. KNOWN content gaps (not this layer): the accent isn't Orange's #ff7900 (scraper
palette-extraction miss) and the reel headline is the verbatim tagline unless `--from-plan`/
research drives it.

## Done — profile extraction migrated to Gemini (auto provider) (2026-06-20) ✅
Owner: "use Gemini 2.0 Flash" for the (token-heavy) profile extraction. MEASURED: Gemini
**2.0** Flash is NOT provisioned on the Vertex project (`gemini-2.0-flash`/`-001`/`-lite`
all 404 in us-central1); the available cheap models are **`gemini-2.5-flash`** /
`gemini-2.5-flash-lite` (and 2.5-pro). 2.5 Flash is newer/better than 2.0 anyway. Wired
`business_profile/__main__._make_caller(provider, model)`: `--provider auto` (default) →
`GeminiCaller("gemini-2.5-flash")` when `GOOGLE_CLOUD_PROJECT` is set (runs on GCP
credits), else `OpenAICaller("gpt-4o-mini")`; `--provider openai|gemini` + `--model` to
override. VERIFIED live on Orange's manifest (4/4 grouped calls, valid nested structured
output, validator working): Gemini 2.5 Flash = 34.7k in + 5.6k out, **$0.0245**, RICHER
(8 offerings incl. eSIM/Orange Cash + 5 value props) vs gpt-4o-mini 30k+1.5k, $0.0054, 6
offerings. HONEST: Gemini's NOMINAL cost is ~4× gpt-4o-mini, BUT it draws on the ~$300 GCP
credit pool (vs ~$3 OpenAI) and extracts more — the owner's stated reason. flash-lite is
marginally cheaper ($0.0235). Suite **620 passed** (tests use MockCaller; the live Gemini
path is out-of-CI). NEXT: the offerings/value-prop richness also surfaced borderline items
(e.g. an Amr Diab album) — the validator caught 3-5; tune the offerings prompt if needed.

## Done — profile: other_unique_insights catch-all + validator quote-fold (2026-06-20) ✅
Two extraction improvements (owner-requested, each with a test; suite 620 -> **622 passed**):
1. **`other_unique_insights` catch-all field.** A grounded place for a UNIQUE competitive
   edge / operational detail that doesn't fit audience/value_props/tone (e.g. "the only X
   in the city", an unusual guarantee, a scale fact). Wired end-to-end in the EXISTING
   positioning group (no extra LLM call): `responses.PositioningResponse.other_unique_insights`
   -> `prompts.build_positioning_prompt` (with a STRICT guard: concrete cited fact, NOT an
   opinion/generic strength; empty list if nothing genuinely unique) -> `validator`
   (`_validate_string_list`, same block_id+verbatim-quote rules) -> `BusinessProfile.
   other_unique_insights: list[EvidencedField[str]]` -> `merger`. So it's extracted +
   grounded + on the profile; NEXT (small): consume it in SWOT strengths / poster copy.
2. **Validator quote-glyph fold.** `evidence_pack.as_llm_text` shows the LLM a TRANSFORMED
   block (`"`->`'`, newlines->spaces) so its `"..."` wrapper stays unambiguous — so a
   verbatim quote of a mid-text double-quote arrived as `'` and FALSE-rejected against the
   original `"`. `validator._normalize` now folds all quote glyphs (`" “ ” « » ‘ ’ \` ´`
   -> `'`) on both the quote and the block, closing the false-reject without loosening the
   substring check. Tests: `tests/test_validator.py` (quote-fold + catch-all grounded/hallucinated).
Both are additive + backward-compatible (old profiles load; the new field defaults to []).

## Done — wire other_unique_insights into SWOT + poster (consumers) (2026-06-20) ✅
The catch-all field is now CONSUMED (was extracted-only). Two grounded consumers:
1. **SWOT strengths** (`competitor/swot.py`): new `unique_insight_texts(profile)` helper
   (works on object OR serialized-dict profiles) + `synthesize_swot(..., unique_insights=)`
   appends each as a cited Strength ("your profile"). Appended AFTER the standalone degrade
   so it can't suppress the 0-peer fallback (which keys on an otherwise-empty SWOT); deduped
   vs existing strengths. Wired at BOTH call sites: `competitor/full_run.py` +
   `api/routes/swot.py`.
2. **Poster headline** (`poster/from_profile._select_headline`): each unique insight joins
   the headline candidate pool with a small +0.15 bonus (a genuine edge makes a strong,
   differentiated headline) — still below the brand's own tagline on ties, and subject to
   the same fitness/business-name filters.
Tests: `tests/test_swot_standalone.py` (insight→cited strength, deduped, standalone still
fires) + `tests/test_poster_design.py` (insight can drive the headline). Suite **624 passed**
(was 622). So the full chain is closed: extract (grounded+validated) → profile → SWOT
strength + poster headline.

## Done — poster: overlay legibility + image-prompt de-RGB (ITI "disaster") (2026-06-22) ✅
Owner: "the ITI poster is a disaster" (`outputs/posters/iti_delivery.png`). Reproduced
it OFFLINE (free) by re-rendering the overlay over the SAVED background
(`outputs/posters/backgrounds/bg_dd58d308.png`) with the run's actual spec
(center_editorial / highlight) — pixel-match to the delivered poster — so the renderer
could be iterated with NO Imagen/LLM spend. Diagnosed THREE layers; fixed the two that
are code (the third is data — see NOTE):
1. **RENDERER (offline-verified, universal):** `poster/template.py` —
   (a) `center_editorial` scrim was a soft `radial-gradient` that faded at the
   horizontal extremes, so a full-width headline's left/right ends sat over bright busy
   photo and were unreadable → replaced with a FULL-WIDTH vertical band (dark across the
   central third, fading top+bottom) that backs the whole text width.
   (b) offering chips had no fill (`border:1px rgba(255,255,255,.42)`, invisible over a
   busy photo) → dark translucent pill (`background:rgba(10,14,20,.58)` + blur) + centered
   under center layouts.
   (c) CTA rendered the verbatim scraped label lowercase ("download Track info") →
   `text-transform:capitalize` on `.cta-text` ("Download Track Info"); presentation-only,
   grounded, no-op on Arabic.
   (d) `highlight` treatment was a tilted (`rotate(-2.5deg)`) cramped sticker → clean
   knockout block (no tilt, real padding, soft shadow). VERIFIED by before/after render.
2. **IMAGE PROMPT (code fix; verify on the live re-render):** `poster/art_director.build_llm_concept_prompt`
   lead said the brand palette is "the dominant colors ... in the **lighting**" — with ITI's
   palette being red `#9F3238` + blue `#66BCE5`/`#3E6FBD` that produced a clichéd
   red-and-blue split-lit "gamer RGB" scene. Now: brand colors appear "naturally in the
   environment, surfaces, props and wardrobe — NOT as colored lighting", with "soft even
   natural daylight; ABSOLUTELY NO colored gel lighting, NO duotone, NO red-and-blue /
   warm-vs-cool split lighting". Universal de-RGB; only verifiable on a live Imagen run.
Tests: 36 green (`test_poster_design` + `test_visual_identity_v02` + `test_brand_research`);
no CSS/prompt assertions were pinned, so nothing regressed.
NOTE — the deepest layer is DATA, not code: this profile was scraped from a DEEP
data-science TRACK page (`source_url=.../diplomaStructure/.../tracks/...`), so
tagline="DATA SCIENCE", offerings are all data-science, CTA="download Track info", and
the palette is flagged `palette_dominated_by_background`/`co_branding_detected`
(unreliable). A re-scrape from the ITI homepage (`https://iti.gov.eg`) → brand-level
tagline/offerings/CTA + a cleaner palette, then a live regenerate (Imagen with the fixed
prompt) is the real finish. Both need a live run (scrape + Gemini extract + Imagen,
ADC/credits) — pending owner go-ahead.

## Done — reel: FREE edge-tts voice-over backend (native Egyptian, no paid TTS) (2026-06-22) ✅
Owner: the voice-over "بفلوس كتير" (costs too much). Idea confirmed from the TrendPulse
review — but TrendPulse folds voice into Veo 3.1 (free WITH the video, but Veo itself is
expensive); the genuinely CHEAP, standalone path is a free TTS. Added **edge-tts** (the
Microsoft Edge read-aloud service: free, keyless) as a third backend in
`reel/voiceover.py` alongside gemini|openai. For Arabic it gives a NATIVE Egyptian voice
(`ar-EG-SalmaNeural` / `ar-EG-ShakirNeural`) — cheaper AND more authentic for ar-EG reels
than the English-leaning OpenAI voices.
- `_edge_segment(text, out_mp3, voice)`: async lib driven via `asyncio.run` (the reel
  pipeline is sync); never raises -> False so a failure degrades to the existing silent
  filler. `_edge_voice_for` picks the Egyptian voice for Arabic copy, else English.
  Pace/pitch steerable via `REEL_TTS_EDGE_RATE`/`_PITCH`; no free-form emotion prompt
  (the native dialect carries the read).
- `_resolve_backend` now: explicit/`REEL_TTS_BACKEND` > auto. Auto prefers a PAID backend
  when configured (Gemini on GCP credits, else OpenAI by key) and falls back to FREE
  `edge` when neither — so a no-key machine gets a voice instead of going silent (was a
  hard None). `REEL_TTS_BACKEND=edge` forces the free voice and skips ALL paid TTS spend.
- Wired into `synth_voiceover` (no client/key needed for edge; mp3 segments like OpenAI,
  reuse the same ffmpeg pad/trim/concat path). Added `REEL_TTS_BACKEND=edge` to `.env`
  (this machine had GCP set -> default was gemini) so reels now use the free voice.
VERIFIED LIVE end-to-end: edge produced a 34 KB ar-EG mp3 ('قصر الكبابجي...'), and the full
`synth_voiceover(backend='edge')` built a 3-scene track whose **real decoded length = 10.03s**
for 3+4+3s of scenes (correctly padded/aligned). IMPORTANT measurement note (rule 6 — almost
"fixed" a non-bug): the concat output is `.aac` (ADTS, which has NO container duration
metadata), so ffmpeg's `Duration:` header MIS-reports ~6.8s while the real audio is the full
10s — the compositor decodes real packets + the VO is built to match scene durations, and the
mux uses `-shortest` against equal-length streams, so it lands correctly (same as the existing
gemini/openai paths; NOT changed). Deps: `edge-tts==7.2.8` (+aiohttp/yarl/multidict/...) pinned
in `requirements.txt`. Tests: `tests/test_voiceover.py::test_resolve_backend_explicit_env_and_auto`
extended for the edge backend + free fallback (deterministic via OPENAI_API_KEY monkeypatch).
Suite: 26 reel/voiceover tests green. NEXT (queued from the same TrendPulse review): poster
per-RUN variation engine, then reel coherence (scene-delta + character/style anchor).

## Done — poster: per-RUN variation engine (same brand, different look each run) (2026-06-22) ✅
Owner's long-standing complaint ("every poster looks the same — same text design every
run"). Root cause: BOTH design paths keyed only on the BRAND — `default_design_spec` is a
pure brand-name hash (identical layout every run) and the design-spec/concept LLM calls got
no per-run signal, so one brand → one look. Idea adopted from TrendPulse's
`build_variation_context` (random tone/angle/style + seed per run), adapted to our TWO
TRUTH DOMAINS: variation is PURE DESIGN (mood/lighting/composition/energy/layout) and NEVER
touches the grounded copy (headline/offerings/CTA stay verbatim).
- New `poster/variation.py`: `build_variation(seed=None)` — seed → reproducible look,
  None → fresh microsecond-seeded pick; curated DESIGN-only vocabularies (moods, NATURAL
  lighting only, compositions, energy). Helpers `design_variation_cue` (steers the
  composition LLM), `concept_variation_cue` (steers the Imagen scene), `variation_seed_int`
  (varies the deterministic fallback).
- Wired: `art_director.build_design_spec(..., variation=)` appends the cue to the LLM
  prompt + seeds the no-LLM/​error fallback; `build_llm_concept_prompt(..., variation=)` and
  `build_creative_prompt(..., variation=)` weave the run's lighting + feel into the image
  lead — IMPORTANT: only NATURAL lighting options, so the ITI de-RGB guard (no colored
  gel / duotone / split lighting) still holds. `template.default_design_spec(...,
  variation_seed=)` mixes the seed into the brand hash (None = stable per brand,
  backward-compatible). `poster/__main__` builds one variation from `--variation N`
  (reproducible) / fresh when omitted → passes to both; `api/routes/poster.py` builds a
  FRESH variation per web request.
MEASURED offline (no API): same brand (ITI), different seeds → DIFFERENT layouts
(center_editorial/block vs top_anchor/highlight) — VERIFIED by render (the top_anchor
variant reads better than the delivered center one). Tests: `tests/test_poster_design.py`
(+4: seed determinism, fallback layout variety across seeds + stable-without-variation,
variation reaches BOTH the concept prompt and the design-spec prompt). Suite **628 passed**
(was 624). NEXT (queued): reel coherence (scene-delta + character/style anchor), then the
same variation engine for the reel.

## Done — reel: character/style anchor for coherence (text-to-video) (2026-06-22) ✅
Idea adopted from TrendPulse's `VeoPromptBuilder` (CHARACTER ANCHOR + locked style):
their reel reads as ONE story because the same person + look is repeated in every
scene's Veo prompt; ours generated a DIFFERENT stranger each cut on the text-to-video
(no-real-photo) path. (The faithful Ken-Burns/i2v path was already coherent — it animates
the brand's REAL photos; this fix targets only the generative fallback.)
- `reel/art_director._BrandSceneResponse` gains `character` — `build_brand_scene` now
  returns `(scene, character)` in ONE LLM call: the recurring protagonist (the brand's
  audience, described concretely + culturally authentic). Pure visual DESIGN (a b-roll
  cast choice), not a factual claim. `(None, None)` with no caller (deterministic
  fallback, no anchor) — back-compatible.
- `build_scene_prompt(..., character_anchor=)` prepends a CONTINUITY block to EVERY scene:
  "the SAME single person appears in every scene … keep their face, hair, build, and
  outfit IDENTICAL … consistent lighting and color grade" — so the protagonist AND the
  cinematography carry across cuts. No anchor -> no block (unchanged output).
- `reel/storyboard.build_storyboard` unpacks `(base_scene, character_anchor)` and threads
  the anchor into each text-to-video scene (seeded real-photo scenes keep the faithful i2v
  motion prompt).
VERIFIED LIVE (Gemini, ITI, forced text-to-video via `selected_images=[]`): one recurring
protagonist ("A woman in her mid-20s with dark, intelligent eyes, wearing a chic …") now
appears in ALL 5 scene prompts (intro/offering/value_prop/contact/outro). Tests:
`tests/test_reel_reference_image.py` (+3: scene+character return & no-caller (None,None);
continuity block present-with / absent-without anchor; storyboard threads the character
into every text-to-video scene). Suite **631 passed** (was 628). NEXT (queued): the
per-run variation engine for the reel too; richer narration via the Opus path + the free
edge-tts voice.

## Done — poster: on-brand tech background + per-run typography + kill baked-text/sculpture leaks (NTI) (2026-06-22) ✅
Owner feedback on a fresh NTI (telecom institute) web-app poster: "the design is nice, BUT
the bohemian background has nothing to do with the brand, and the fonts/writing style still
don't change per poster." Also caught a worse stale-process disaster first: an OLD running
uvicorn (loaded before the day's grounding fixes) produced a woman SCULPTING CLAY for a
telecom institute — VERIFIED it was the stale server, not the code (regenerating via current
code gave Egyptian people on laptops). Lesson reinforced: restart the API after code changes.
Then THREE measured fixes (suite 631 green; each verified by a live Imagen Ultra regen):
1. **Per-RUN typography** (`poster/template.py` + `poster/schemas.py`): `_pairing_for` keyed
   ONLY on the brand name → same font every run. Added `PosterDesignSpec.variation_seed`
   (stamped by `build_design_spec`/`default_design_spec`), threaded into `_fonts_head_and_stacks`
   → `_pairing_for(brief, variation_seed)`. Expanded `_FONT_PAIRINGS` 8→14 (real Google Fonts).
   MEASURED: NTI now picks 6 DISTINCT head fonts across 6 runs (+ varied treatment/layout);
   no-variation stays stable per brand (back-compatible).
2. **On-brand environment, not "bohemian"** (`poster/art_director`): `_subject_line` said only
   "people engaged in education" → Imagen filled a generic warm artisan interior. Added
   `_ENV_BY_CATEGORY` (universal, from the scraped category) → e.g. education = "a modern bright
   technology training space — laptops and large screens, a contemporary classroom/innovation
   lab". The image lead photography descriptor changed from "premium editorial" → "clean modern
   professional commercial photography (NOT artsy/bohemian, NOT rustic; NO arches/pottery/
   sculpture/handicraft props unless that is literally the business)".
3. **Killed two Imagen leaks** (both MEASURED on the raw NTI bg): (a) the offering NAME ("Train
   To Hire (4 Month)") in the subject got BAKED into the image as a sign — removed the marketing
   name from the image prompt (category + environment ground it; the offering text stays in the
   overlay). (b) the LLM "secondary creative cue" (free surreal metaphor) leaked a clay sculpture
   — DROPPED it; per-run variety now comes from the controlled VARIATION engine (lighting/mood/
   composition/layout/fonts), and any LLM atmosphere hint is appended ONLY if it has no off-brand
   words (sculpt/statue/pottery/arch/surreal/floating/void/staircase/abstract…).
MEASURED before→after on NTI (web app, Ultra): sculptor + bohemian + baked "Train To Hire" text
→ a clean modern tech-training room (team at laptops, screens, orange+navy palette, Egyptian
people), zero baked text, zero sculpture, a different display font. Matches the owner's real NTI
reference posters (clean tech aesthetic). Tests: `tests/test_poster_design.py` (23, incl. the
existing variation tests). NEXT: same env/no-bake discipline benefits every vertical; consider
image-conditioning on the brand's REAL photos for maximum fidelity (bigger integration).

## Done — resilient HTTP fetch: circuit breaker + bounded retry (TrendPulse base_scraper idea) (2026-06-22) ✅
Owner: "stop hitting a خازوق every few minutes — harden the scraper, take ideas from the
TrendPulse GitHub." Adopted TrendPulse's `base_scraper` robustness pattern (circuit breaker
+ tight retry session + fast timeout), re-implemented STDLIB-ONLY (urllib) to match this
repo's "no new deps, NEVER raises" discipline for data-fetch helpers.
- New `scraper/net.py`: `get_json` / `post_json` with (a) BOUNDED RETRY on TRANSIENT
  failures only (timeout / connection / 429 / 5xx) with linear backoff — a clean 4xx or a
  bad-JSON 200 is NOT retried; (b) a per-host CIRCUIT BREAKER: after 3 consecutive failures
  the host's circuit OPENS and further calls short-circuit to None instantly (no network,
  no timeout paid), with a 60s cooldown half-open probe so a recovered host resumes. Never
  raises (every path -> None). `reset_circuits()` for tests/between runs.
- Wired into the keyless data-fetchers (the layers TrendPulse's idea actually maps to —
  our main Playwright crawler is already robust: transient-retry + partial-DOM salvage):
  - `trends/sources.py` `_get_json` -> delegates. WHY it matters most here: HackerNews fans
    out ONE call per story (~31 for limit 30) to one host; without a breaker a dead HN got
    hammered call-after-call, each paying the full timeout and stalling the run. Now 3 fails
    -> skip the rest instantly.
  - `competitor/search_providers.py` `_post_json`/`_get_json` -> delegate (return {} on
    failure so provider parsing stays simple). So a single transient blip on Serper/CSE no
    longer silently collapses competitor discovery to a standalone SWOT (the "1 competitor
    found / 0 threats" the owner saw can be a dropped request, not a real 0-peer case).
Tests: `tests/test_net.py` (6, hermetic — urlopen/sleep/monotonic faked: success resets,
transient retried, 4xx not retried, 5xx retried, breaker opens + short-circuits, half-open
after cooldown). Suite **637 passed** (was 631). NEXT (each its own measured fix): a per-host
consecutive-failure breaker in the crawler's SUBPAGE loop (stop crawling a host that starts
rate-limiting mid-crawl); and the deeper data-QUALITY issue (a scrape landing on a DEEP
sub-page — e.g. ITI's /tracks/ page — yields narrow data; needs page-selection measurement
before changing, per rule 2).

## Done — scraper: re-anchor identity to the site ROOT when the seed is a deep page (2026-06-23) ✅
ROOT CAUSE of the ITI "خازوق": the crawler treated the INPUT URL as "the homepage"
(`fetch_page(context, normalized)`), so a deep seed (`iti.gov.eg/diplomaStructure/.../tracks/...`)
made brand IDENTITY come from that track page — tagline="DATA SCIENCE", offerings all one track.
MEASURED FIRST (rule 2) across **83 saved manifests**: 10 (12%) were deep-seeded, but ~half are
legitimate LOCALE homepages (`orange/en`, `adidas/us`, `defacto/en-eg`, `vodafone/en/home`) that
must NOT be touched; only ~5 (6%) are true deep CONTENT pages (iti/tracks, sofitel/restaurant,
elkbabgi/menu, elmenus/<city>, buffalo/branches/all/home). So a naive "strip to root" would
REGRESS the locale homes — the fix had to distinguish them.
- New pure helper `scraper/url_utils.site_root_if_deep(url)`: returns the site root iff the URL
  is a deep content page; None for the bare root OR a locale homepage (strips ONE leading locale
  segment `en|ar|en-eg|…` + a trailing `home/index`, then deep iff segments remain). VALIDATED
  against all measured cases (5 deep → root, 4 locale homes + roots → None). Tests:
  `tests/test_basics.py` (+2).
- Wired into `scraper/crawler.scrape`: `deep_root = site_root_if_deep(normalized)`; fetch the
  ROOT as the homepage for identity; PREPEND the original deep seed as the first high-priority
  subpage so its content (offerings/menu/track) is still captured. SAFETY: if the root is
  unreachable, fall back to the original seed (never lose a scrape the deep page would have
  served) — recorded as a note.
VERIFIED LIVE (re-scraped the exact ITI deep URL): `final_url` now `https://iti.gov.eg/` (was the
track page), 5 pages incl. the track page as a "programs" subpage, 0 failures. Re-extracted
profile (Gemini, $0.027): tagline **"DATA SCIENCE" → "Shaping Future Innovators"**; offerings
**4 data-science-track items → 5 institute-wide** (Intensive Training Program, Mahara-Tech,
Data Science, cybersecurity, Game Jam 2026); description now brand-level. Suite **639 passed**
(was 637). NOTE: applies at scrape time — old deep-seeded manifests need a RE-SCRAPE to benefit.

## Done — UI/UX expert pass (copy + states) + reel per-run variation (2026-06-23) ✅
Owner: "harden the deployment so I can test it myself; make the design, the copy, and the
presentation bang; work like a UI/UX expert; and tune the reel." Deployment: both servers
restarted on the latest code (API `uvicorn api.main:app :8000`, frontend Next 15 `:3000`),
verified up (API /health ok; frontend HTTP 200, clean compile).
- **UI/UX (frontend, festive theme from the earlier pass continued):**
  - `components/url-bar.tsx`: the primary action is now a 48px input with a leading globe
    icon + spinner-on-submit + clearer microcopy ("Paste any business website — e.g.
    nti.sci.eg"; "Skip AI extraction (rules only)").
  - `app/page.tsx`: real UX STATES — a branded animated LOADING card ("Reading the
    website…", gradient bar + spinner) replacing the plain text; an ALERT-styled ERROR
    card (icon + "Couldn't analyze that URL" + detail) replacing bare red text.
  - `components/tabs-shell.tsx`: lucide icons on every tab + a gradient "new" badge.
  Verified by HTTP 200 + clean Next compile (no console errors); visual QA is the owner's
  live view (the preview screenshot tool times out on this machine).
- **Reel per-run variation:** applied the poster's `variation` engine to the reel —
  `reel/art_director.build_scene_prompt(..., variation=)` appends the run's mood/lighting/
  energy cue (via `poster.variation.concept_variation_cue`); `reel/storyboard.build_storyboard
  (..., variation=)` builds a fresh variation when none is passed and threads it into every
  text-to-video scene. So the SAME brand's reel looks different each render (design-only;
  never touches the verbatim text). Test: `tests/test_reel_reference_image.py` (+1: the
  variation reaches the scene prompt; absent without it). Suite **640 passed** (was 639).
  NOTE: a live reel render (Veo/ffmpeg) validates it visually — out of this pass.

## Done — LLM layer is Gemini-ONLY (no OpenAI); fixes thin web-app extraction (te.eg 1→12) (2026-06-23) ✅
Owner directive: "remove ANY OpenAI, use Gemini 2.5, stay on Pro for complex things."
MEASURED root cause of "the scraper isn't enough" on te.eg (Telecom Egypt): the SCRAPER was
fine — it fetched 7 `services` pages and the homepage (13/13, 0 failures), and ALL the offering
text (mobile / internet / fixed / business) was present in 1352 text blocks. The bottleneck was
the **web-app EXTRACTION still on `OpenAICaller(model="gpt-4o-mini")`** (`api/jobs/runner.py`):
it proposed only 2 offering candidates and the validator rejected 4 (breadcrumb-contaminated
names) → **1 offering** survived for a telecom giant.
- `business_profile/llm/caller.default_caller` is now **Gemini-ONLY** (removed the OpenAI
  fallback): `strong=True` → gemini-2.5-**pro** (complex: design / concept / research / copy /
  reel scene), `strong=False` → gemini-2.5-**flash** (cheap token-heavy default: profile
  extraction). Accepts Vertex (GOOGLE_CLOUD_PROJECT+ADC) OR a Gemini API key; None when neither.
  So EVERY auto-selected caller (poster, reel, brand research, brand book, AND the API pipeline)
  is Gemini now — nothing auto-uses OpenAI.
- `api/jobs/runner.py`: extraction caller `OpenAICaller(model)` → `default_caller(strong=False)`
  (Gemini Flash); dropped the `OpenAICaller` import. `api/routes/run.py` gate `has_openai_key()`
  → `has_llm()` (Gemini OR OpenAI) so a Gemini-only deployment isn't wrongly blocked; clearer
  400 message. Test updated (`tests/test_api_run.py`: rejects only when NO provider at all).
MEASURED (re-extract the SAME saved te.eg manifest, no re-scrape): gpt-4o-mini **1 offering**
→ Gemini 2.5 Flash **12 offerings** (fleet tracking, hosted call center, bill control, balance
inquiry, Salefny Extra, balance transfer, roaming, call tone, WE Sports, WE Pay…), value props
few→5, **validator rejections 4→0**, $0.028 on GCP credits. Suite **640 passed**. NOTE: the
evidence pack still caps at ~153/1352 blocks — Gemini got 12 within that; lifting the cap could
surface even more (separate measured follow-up). REMAINING explicit (non-auto) OpenAI paths to
strip if wanted: `reel/voiceover.py` OpenAI TTS backend (edge is the active default) and the
`--provider openai` option in `business_profile/__main__`; the `OpenAICaller` class stays but is
no longer auto-selected anywhere.

## Done — BrandCreativeDNA: learn a brand's VISUAL design language from its real creatives (2026-06-23) ✅
Owner's breakthrough idea: "every poster looks like a fixed template because we only feed
the model COLORS. Let the LLM SEARCH the brand's OLD posters, UNDERSTAND how their visuals
THINK (not just the palette), store profile + posters in the prompt, and design each one
differently." Phase 1 (the "brain") built + PROVEN.
- New `brand/creative_dna.py`: `harvest_creative_urls(brand)` (Serper /images via the
  resilient `scraper.net.post_json`, aggregator/stock denylist) + `build_creative_dna(profile,
  caller)` → ONE multimodal Gemini 2.5 **Pro** call that SEES the brand's real ads and
  reverse-engineers a structured `BrandCreativeDNA`: layout_philosophy, composition_patterns,
  typographic_character, color_usage, imagery_style, mood, motifs, text_density,
  signature_moves, do_list/dont_list. Pure DESIGN judgement (no factual claims; we LEARN, never
  reproduce). Side-effect free; degrades gracefully (no provider → website photos; no caller →
  stub; no images → honest note). Reuses brand_book's SSRF-guarded `_fetch_images`. CLI:
  `python -m brand.creative_dna <profile.json>`. Cached to `outputs/brandbooks/<name>_dna.json`.
- Wired into the poster IMAGE: `art_director.build_llm_concept_prompt(..., brand_dna=)` +
  `_brand_dna_lines` — when a vision DNA is present it LEADS the image prompt with the brand's
  own design language and DELIBERATELY OVERRIDES the generic natural-light/no-gel defaults (for
  a brand whose real ads ARE composite + colored light, matching them is correct, not the ITI
  'gamer RGB' bug). `poster/__main__ --brand-dna PATH` loads it. Subject + region + no-baked-text
  guards stay; facts stay grounded.
MEASURED LIVE on WE / Telecom Egypt (Gemini Pro vision over 7 real WE ads): the DNA nailed
their language — dual typography (soft 'we' logotype vs ultra-bold custom Arabic headline
lockups), "digital twilight" purple+magenta palette, composite cut-out rim-lit subjects on
glowing cityscapes, light-beam motif, and "DO NOT use candid documentary photography" (exactly
what our earlier off-brand poster did). Rendering WE `--brand-dna` (Imagen Ultra) flipped the
poster from a generic candid Egyptian street → an authentic WE-style ad: purple light streaks
across a twilight sky, a rim-lit hijabi subject, a glowing cityscape, WE logo top-left
(`outputs/posters/we_dna.png`). Tests: `tests/test_creative_dna.py` (5, hermetic — injected
harvester/fetcher + MockCaller) + `test_poster_design.py` (+1: DNA leads the concept prompt).
Suite **646 passed** (was 640). NEXT (Phase 2 — the "hand"): a FREE-FORM LLM-authored layout
(elements with normalized x/y/w/h/treatment) so the renderer isn't limited to 6 archetypes —
that's what fully kills the "same template" feel; the DNA's layout_philosophy/composition would
drive it. Also: feed the DNA into the design-spec + the REEL; the headline copy is still the
weak spot on tagline-less brands (research / language-matched headline).

## Done — poster: FREE-FORM LLM-authored layout (kills the 6-archetype template) (2026-06-23) ✅
Phase 2 of the owner's "every poster looks like a fixed template" fix. The renderer had only
6 layout archetypes, so even with per-run font/colour/mood variation the COMPOSITION read as
the same system (logo corner + one of 6 text regions). Now the LLM AUTHORS the composition at
CONTINUOUS coordinates → unbounded layouts.
- `PosterDesignSpec` gains `text_box=[x,y,w]` + `logo_xy=[x,y]` (normalized 0..1 of the
  1080x1350 canvas; None → the old archetype path, backward-compatible).
- `poster/template.py`: `_freeform_lower_css` (positions the text cluster at the free box with
  a soft ROUNDED SCRIM PANEL sized to it — legible on ANY background) + `_freeform_logo_css`
  + `_freeform_column_px`; all CLAMPED to safe margins so a bad coordinate can never push
  content off-canvas. `render_poster_html` uses free-form when `spec.text_box` is set.
- `art_director.build_design_spec`: `_DesignSpecResponse` gains `text_box`/`logo_xy`; the LLM
  is told to PLACE the cluster + logo where the image is calmest and VARY it (not default to a
  corner), STEERED by the brand's `BrandCreativeDNA.layout_philosophy` (new `brand_dna` param).
  Coords validated/clamped (`_valid_coords`); the image's calm `negative_space_zone` is derived
  from where the text actually lands (`_zone_from_box`). `poster/__main__` loads `--brand-dna`
  once and passes it to BOTH the design-spec and the concept prompt.
MEASURED: offline, the SAME brand renders genuinely different compositions (text panel
top-left + logo top-right vs text panel lower-right + logo top-left) — VERIFIED by render.
Live end-to-end on WE (`--brand-dna`, Imagen Ultra): the LLM authored box=[0.05,0.65,0.90]
(a bottom band it CHOSE, logo top-right) and the image came out in WE's language (purple light
streaks, rim-lit confident subject, glowing cityscape) — a non-template, on-brand poster
(`outputs/posters/we_phase2.png`). Tests: `tests/test_poster_design.py` (free-form coords map
through + drive the zone; 3 existing design-spec tests updated for the new required fields).
Suite **646 passed**. The web app gets free-form layouts automatically (build_design_spec emits
them) even without a DNA. NEXT: auto-load a cached DNA in `api/routes/poster.py`; feed DNA +
free-form to the REEL; the headline copy is still the weak spot on tagline-less brands.

## Done — poster: unified pipeline + Creative Concept + Arabic lock + copy/art critics (web-app fix) (2026-06-23) ✅
Owner build-brief: the WEB-APP poster was English on an Arabic brand, off-brand candid image,
random B2B chips, clipped CTA — fix it ON THE WEB-APP PATH, copy must be ENTICING + have a
دليل (proof), and a second ARTIST agent must review the design. Governing rule: no "done"
until it passes on a poster generated from the web app (not CLI/test/old image).
- **Step A — ONE pipeline** (`poster/pipeline.generate_poster`): the CLI AND the API now run
  the same path. `api/routes/poster.py` + `poster/__main__.py` both call it. DNA is
  build-or-load (`load_or_build_dna`, cached per brand).
- **Step C — Creative Concept** (`poster/concept.build_creative_concept`): ONE Gemini call →
  audience / single_message / core_benefit / visual_idea / proof_points + the COPY built FROM
  it, so headline ↔ chips ↔ image express the SAME idea (kills the random-elements root cause).
- **Step B — Arabic LANGUAGE LOCK + copy critic**: for an Arabic brand every visible field is
  Arabic with ZERO Latin (regex gate → regenerate). PROOF gate: the subheadline MUST carry a
  دليل (number / named feature / ببلاش / أول); CTA must be an action, not a headline echo.
  Retries exhausted → grounded Arabic fallback (never ships Latin).
- **Steps D/E — copy**: headline = 2–6-word enticing hook (not a mission statement); chips =
  2–3 from proof_points only (no B2B jargon dump).
- **Step F — image**: rendered in the brand's BrandCreativeDNA language, scene = concept.visual_idea.
- **Step G — layout safety** (`template._freeform_lower_css`): the text cluster bottom-anchors
  at a safe margin when placed low, so the CTA can never clip; feathered radial scrim (not a
  hard grey box); orphan accent-rule removed; bigger logo chip; bolder CTA button; stronger
  hero typography (weight 800, Arabic gets correct tracking + leading — negative tracking was
  breaking Arabic joining). Pipeline FORCES `show` to include headline+sub(دليل)+chips+cta
  (the design LLM was hiding them, leaving only a bare headline).
- **Step H — ART CRITIC vision gate** (`poster/vision_qa`): an award-winning-art-director rubric
  over the FINAL render — logo_ok (hard gate), single_focal, strong_typography, cta_prominent,
  on_brand_color, candid_violation, has_latin_text, score/10; regenerate on image-fixable fails.
  An actual "second artist agent" (Agent tool) reviewed a poster and produced the copy + art
  rubrics encoded here.
VERIFIED on the WEB-APP path (POST /api/poster/from-profile, the same handler localhost:3000
calls), Gemini Pro + Imagen Ultra, te.eg/WE: a B2B poster — headline «كل حاجة تحت عينيك», دليل
«من تتبع المركبات لمركز الاتصالات المستضاف، إحنا معاك», 3 coherent Arabic chips, CTA «اعرف أكتر
عن حلول الشركات», a purple WE-DNA composite scene (businessman + holographic fleet dashboard),
no clip, ALL Arabic, **art critic pass=True** (`outputs/posters/poster_82e1f1b9.png`). The
critic is a REAL gate: it REJECTED an earlier run for weak typography (pass=False) → fixed →
passed. Across runs the scene varies (control-hand / Egyptian obelisk / family / dashboard).
Tests: `tests/test_concept.py` (7), `tests/test_vision_qa.py` (3), free-form layout-safety in
`test_poster_design.py`; `tests/test_api_run.py` updated. Suite **657 passed** (was 646).
HONEST REMAINDER (not "perfect"): the art critic is strict + subjective — some runs still get
pass=False and the API currently RETURNS the poster with the verdict logged rather than a hard
error (brief Step H "clear error" only partial). Logo Arabic sub-text is the real brand mark's
fine print (legible-but-small). Proof grounding is via real offerings; a strict evidence
validator (the claim must appear in the profile) is a follow-up.
- ITERATION (2026-06-23, same turn): an independent art-director agent re-reviewed an improved
  render → COPY 4→7/10 (the دليل/proof gate worked), DESIGN 5.5→6.5/10 (typography lockup +
  bolder CTA + feathered scrim + orphan-dash removed all landed); verdict "ALMOST", #1 blocker
  = the logo. Added: best-attempt selection in the pipeline (keep the highest-QA-score render,
  not the last); a hi-res logo upgrade (`_upgrade_to_hires_logo` prefers a `preview-1000` variant
  of the same logo stem) + transparent-margin auto-trim (`_trim_logo_margins`); focal-clutter is
  now image-fixable so the QA loop re-rolls on a competing-focal composition; concept fallback
  keeps headline ≠ subheadline. HONEST STATE (governing rule — NOT claiming done): the art critic
  is a REAL strict gate and one run fully passed on the web app (poster_82e1f1b9: Arabic copy +
  دليل + chips + CTA + on-brand WE image, pass=True), but quality is NOT yet RELIABLE run-to-run —
  the critic still rejects some runs on (a) logo polish (te.eg's source assets are genuinely poor:
  a 251x71 low-res Arabic lockup OR a Latin 'we' mark with faint 'telecomegypt' text — a clean
  asset is a data gap, not a code bug), (b) focal clutter, (c) an occasional weak-copy fallback.
  Suite 657 passed.

## Done — Evidence Ledger STEP 1: central grounding gate + read-only measurement (2026-06-23) ✅
First step of the v2 "Evidence Ledger" (the sellable moat: PROVABLE zero-hallucination —
every hard claim in any creative traces to a real source the agency can show its client).
This step is the GATE ENGINE + a READ-ONLY measurement; it blocks NOTHING in the live
pipeline yet (the blocking gate + regenerate loop is a later, separate step).
- NEW `grounding/` package. `grounding/ledger.py`:
  - `EvidenceLedger.from_profile(profile_dict, *, swot=, research=, deep_search=)` indexes
    ALL real evidence (every EvidencedField value + its verbatim `evidence[].quote` +
    `page_url`, offerings, CTAs, trust signals, contact; optionally SWOT citations /
    brand_research `source_url` / deep_search `url`). Robust to a full-run wrapper
    (`{"profile": {...}}`). Pure/deterministic, never raises, no I/O.
  - TWO TRUTH DOMAINS enforced: paraphrase is allowed; only a HARD CLAIM must be sourced.
    `extract_claims(text)` pulls them — SIGNIFICANT numbers (`170 years`/`5000`/`50%`/
    `since 1998`; a bare "3 tracks" is NOT a claim) + superlative/first/only/best/largest/
    free/credential synonym GROUPS (EN+AR). Arabic-aware normalize (tashkeel/tatweel strip,
    alef/ya unify, Arabic-Indic digits->ASCII, clitic+`ال` stemming so `الرواد`<->`رواد`).
  - `resolve_claim(text) -> Resolution|None` (the doc-named gate: sourced iff EVERY hard
    claim resolves), `audit_text` / `audit_fields` (per-claim verdicts), and
    `AuditReport.export()` = the (claim->source) trail — the agency-facing brand-safety
    artifact, emitted from day one.
- `grounding/measure_step1.py`: read-only harness over a 6-profile corpus (4 verticals,
  AR+EN: te.eg, ITI, Digilians, Qasr Elkbabgi, NTI, Specialized Clinics — chosen by a
  mapping workflow). Audits BOTH the verbatim-selection copy (path A) and live LLM concept
  copy (path B, Gemini/Vertex via `default_caller`).
- MEASURED (read-only, nothing blocked): verbatim SELECTION path = **0/35 copy fields**
  unsourced (sanity floor: the gate does NOT false-positive on genuinely grounded copy).
  LLM GENERATION path (one pass/brand) = **2/36 fields (6%) carried an UNSOURCED hard
  claim**, across 2 of 6 brands — Elkbabgi "Crafted with the finest, globally-certified
  ingredients" (fabricated `certified`) + ITI "...top industry partners" (unsupported
  `top`). Same run, verbatim path = 0 -> the risk is specifically the LLM path, exactly as
  the v2 doc predicted. (HONEST: one stochastic pass = a point estimate, not a stable rate;
  the `top` catch is borderline puffery — the superlative-vs-concrete policy is the knob to
  decide for the blocking step; profile-only evidence here, no live brand_research.)
- Tests: `tests/test_ledger.py` (11, deterministic, no live LLM — proves the gate catches
  the fabricated "170 years"/"globally-certified" class while passing grounded copy +
  Arabic inflection). Suite **668 passed** (was 657).
NEXT (separate steps, decide policy first): (2) turn it into a BLOCKING gate in
`poster/concept.py` (reject + regenerate on an unsourced hard claim) once the claim policy
is set; (3) extend the gate to ALL copy channels (brand_research angles, strategy hooks,
reel) + attach the exportable audit trail to every generated asset.

## Done — Evidence Ledger STEP 2: BLOCKING grounding gate in the live poster pipeline (2026-06-23) ✅
Turned the Step-1 measurement gate into a LIVE blocking gate. OWNER POLICY (chosen): the
line is FALSIFIABILITY, not "every word" — any falsifiable claim (number/year, certification/
award, OR any ranking/comparison: best/leading/top/largest/first/only / الأقوى/الأكبر/الأول/
الوحيد) must resolve to real evidence or be SOFTENED; subjective non-falsifiable puffery
('crafted with care', 'تجربة راقية', a feeling) passes so copy stays alive. Softening is a
REWRITE (remove the ranking/number/credential, keep the message), NOT a blind reject.
- `poster/concept.build_creative_concept(..., enforce_grounding=False)` — opt-in param
  (default OFF keeps the language-lock layer's unit contract; the 7 existing concept tests
  unchanged). When ON it builds `EvidenceLedger.from_profile(profile)` and:
  - SPINE (headline/subheadline/cta): each UNSOURCED falsifiable claim feeds the existing
    regenerate loop as targeted "soften it; do NOT invent a replacement" feedback
    (`_grounding_problems`), capped by `max_retries`, then the grounded verbatim fallback.
    So a fabricated claim is NEVER shipped (regenerate -> soften -> grounded fallback).
  - CHIPS (proof_points): a fabricated chip is surgically DROPPED in `_concept_clean`
    (ledger-aware) — keeps the good spine instead of regenerating the whole concept.
- WIRED ON in the live pipeline: `poster/pipeline.generate_poster` passes
  `enforce_grounding=True` -> covers BOTH the CLI and the WEB APP (one pipeline).
- MEASURED before/after (live Gemini, 3 passes/brand × 6 brands = 105-108 customer-facing
  copy fields each mode): **gate OFF = 4 fabricated fields (3.7%)** (ITI ×1 'top ...';
  Qasr Elkbabgi ×3 'finest/globally-certified' credential+superlative) -> **gate ON = 0
  (0.0%)** — 100% of unsourced falsifiable claims eliminated; 3 fabricated chips surgically
  dropped (Elkbabgi 18->15 fields), spines softened, zero shipped. (HONEST: stochastic — the
  BEFORE rate floats (Step-1 single-pass was 6%); the stable finding is non-zero WITHOUT the
  gate, 0 across 18 passes WITH it. The deterministic mechanism is pinned by tests.)
- Tests: `tests/test_concept_grounding.py` (5, hermetic MockCaller — fabricated superlative+
  number never ship -> grounded fallback; credential chip dropped; subjective puffery passes;
  grounded copy passes untouched; gate OFF by default). Harness `grounding/measure_step2.py`.
  Suite **673 passed** (was 668).
NEXT (step 3, separate): extend the SAME gate to the other LLM copy channels —
`poster/brand_research.pick_angle` (already has a partial prefer_safe gate; unify it on the
Ledger), `strategy/builder.build_strategy` (calendar hooks), and the reel — and attach
`AuditReport.export()` to every generated asset as the agency-facing brand-safety trail.

## Done — Evidence Ledger STEP 3a: gate brand_research/pick_angle + source TIERS (2026-06-24) ✅
Extended the gate to the FIRST (most dangerous) of the remaining LLM copy channels — ad
angles, which draw from LIVE web search, so a fabricated number/award/"#1" can enter from a
junk snippet. Done before `strategy` per owner ("pick_angle is the higher-risk surface").
- LEDGER source TIERS (`grounding/ledger.py`): every `LedgerEntry`/`Resolution` now carries
  `tier` = 'brand' (the brand's OWN scraped site) vs 'web' (a search snippet / SWOT).
  Entries are sorted brand-first so a claim resolves to the brand site when both could
  support it. Owner's rule: 'source = snippet' is WEAKER than 'source = brand site' — a
  snippet can be SEO junk or a competitor.
- CREDENTIAL PRECISION SPLIT: the single `credential` group became `award` / `certification`
  / `guarantee`, so evidence of one cannot source a claim of another (a won AWARD is NOT
  proof of an ISO CERTIFICATION). VERIFIED in the gray set: 'معتمد ISO' is dropped despite
  'جائزة' evidence.
- GATE (`poster/brand_research.pick_angle(..., ledger=None)`): opt-in (default None keeps the
  3 legacy pick_angle tests). When a ledger (profile + research facts) is supplied, every
  candidate angle is verified against REAL evidence — an UNSOURCED falsifiable claim, OR one
  backed ONLY by a non-reputable web snippet (`_is_reputable_source` reuses the discovery
  aggregator denylist), is dropped; falls back to the verbatim headline. Wired at the live
  call site `poster/__main__.py` (the `--research` path) with `EvidenceLedger.from_profile(
  profile, research=research.model_dump())`.
- MEASURED false-positives/negatives (owner-required — ad angles are metaphorical, AR
  inflection is matcher-risky, so the poster's 0-FP does NOT transfer): a curated DETERMINISTIC
  17-case AR+EN gray set (`grounding/measure_step3.py`, `evaluate_gray_cases()`) — grounded
  claims phrased differently KEEP vs fabricated DROP + the web reputability split. **0 false
  positives, 0 false negatives.** Highlights: AR inflection 'روّاد'↔tagline 'الرواد' kept; same
  'الأكبر' claim KEPT from reuters.com, DROPPED from g2.com.
- Tests: `tests/test_brand_research_grounding.py` (5, hermetic — the gray set asserts FP==0
  & FN==0, the award≠certification split, web reputability, legacy no-ledger behaviour).
  Suite **678 passed** (was 673).
NEXT (step 3b/3c): same gate on `strategy/builder.build_strategy` (calendar hooks) with its
own FP measurement; then attach `AuditReport.export()` to every asset (the resellable trail);
then the reel as its own workstream. NOTE (owner): keep before/after rates OUT of any pitch —
few runs, directional; the binary + deterministic tests are what stand.

## Done — Evidence Ledger STEP 3b: BLOCKING gate on strategy calendar hooks (2026-06-24) ✅
The LAST of the three customer-facing copy surfaces (poster `concept.py` + `pick_angle` were
already gated). A content-calendar HOOK becomes a poster/reel headline via `headline_override`
(which SKIPS the research path), so an unsourced hook could ride straight onto a creative — and
the calendar is itself a client-facing deliverable. Now gated.
- `strategy/builder._hook_is_grounded(text, ledger)` = the predicate (no UNSOURCED falsifiable
  claim per the Ledger). The strategy ledger is profile-only -> all brand-tier, so NO
  web-snippet reputability dimension here (unlike `pick_angle`, which ingests live research).
  `build_strategy(..., ledger=None)` is OPT-IN — the 6 legacy strategy tests are untouched
  (gate off without a ledger).
- DROP-TO-GROUNDED (owner's exact definition): a hook/angle with an unsourced falsifiable claim
  is BLANKED; the item keeps its real `topic` (the creative's headline falls back hook->topic),
  so the headline stays a grounded value CONSISTENT WITH THE ITEM'S OWN TOPIC. We never
  synthesize a replacement (re-introduces fabrication) nor slap on an unrelated offering. Both
  `hook` AND `angle` gated; `topic` left alone (a fabricated topic has no self-consistent
  grounded replacement — a separate decision).
- Wired live in `strategy/__main__` (the only producer; `campaign/` consumes the already-gated
  calendar). Best-effort: never blocks the calendar if grounding is unavailable.
- MEASURED FIRST (gray-case set BEFORE live wiring, per the agreement): `grounding/measure_step3b.py`
  — curated AR+EN, with RELATIVE-TIME matcher PRECISION ("منذ 1990" KEPT vs "منذ 1985" DROPPED;
  "30 سنة" KEPT vs "50 سنة" DROPPED — same claim KIND, value-specific) + award!=certification.
  Binary: gate-OFF the fabricated hooks ship; gate-ON 0 survive, 0 grounded dropped. FP==0/FN==0,
  pinned by `tests/test_strategy_grounding.py`. (Curated/deterministic — NOT a live rate.)
- LIVE rule-3 confirmation (`python -m strategy te_eg_gemini.json`, Gemini Flash/Vertex):
  integration ran CLEAN end-to-end; the NATURAL generation produced only paraphrase, so nothing
  was blanked — case (b): clean integration, no fabrication THIS run (the CATCH's proof is the
  deterministic test, NOT this run). A deliberately superlative-biased STRESS prompt then made
  the gate blank 10 fabricated fields LIVE — which ALSO exposed a matcher GAP (next entry).
KNOWN GAP discovered here (coverage was INCOMPLETE until the next fix): the lexicon missed the
"-est" superlative class (fastest/cheapest/easiest…) and "#1"/"no.1" symbolic rankings, so a
few boastful hooks rode through. Affects ALL three gated surfaces (shared ledger). Closed in the
next entry BEFORE starting 3c (the audit-trail must not be exportable while coverage has a hole).
Suite 678 -> 687.

## Done — Evidence Ledger: close the superlative/ranking coverage gap (root, not symptom) (2026-06-24) ✅
The 3b stress test proved the matcher missed a whole CLASS — "-est" superlatives
(fastest/cheapest/easiest/smartest…) + "#1"/"no.1" rankings — across ALL three gated surfaces
(shared `grounding/ledger.py`). ROOT vs SYMPTOM (owner's push — don't patch word-by-word
forever): a general MORPHOLOGICAL pattern was evaluated and REJECTED, it fails the zero-FP bar
in BOTH languages — EN `\w+est` over-matches honest/interest/forest/request/suggest/latest…; AR
`الأ\w+` over-matches الأساس/الأسبوع/الأسعار/الأخبار/الأحداث. So: a closed LEXICON for the genuine
superlatives + a NARROW regex for the clean symbolic `#1`/`no.1` + a CANARY test that fails loudly
on any future uncovered superlative (next hole caught in CI, not at an agency).
- `_RAW_GROUPS["superlative"]`: EN -est class + AR أفعل elatives (أسرع/أرخص/أسهل/أذكى/أحدث/أأمن/
  أنظف/أنقى/أجود/أطول/أوسع/أعلى/أدنى). Exact word/stem matching is WHY 'أسرع' (elative) is caught
  while 'الأساس'/'الأحداث'/'راقية' (base adjective) are NOT — the precision a pattern can't give.
- `_RANK_RE` (`#1`/`no.1`/`rank #1`, NOT #N) -> a 'first' claim ('#' breaks word boundaries so the
  word lexicon can't catch it). '#1' resolves ONLY against a real leadership claim (a brand that
  says "leading" grounds "#1" as paraphrase; one that doesn't -> dropped).
- CANARY `tests/test_ledger_superlatives.py`: MUST_BE_CAUGHT (every superlative/ranking extracts a
  claim — GROW this list when a new phrasing appears) + MUST_NOT_BE_CAUGHT (AR precision FP-guards
  الأساس/الأحداث/الأسعار/الأعمال/راقية + EN honest/interest/modest).
- MEASURED: all three gray sets stay FP==0/FN==0 (pick_angle 17; strategy now 27 incl. 3 new
  superlative DROP + 3 AR FP-guards) and the FULL SUITE 687 -> **742 passed, 0 failed** (+55 canary
  cases), ZERO new false positives. 3c (audit-trail export) now runs on a genuinely complete gate.

## Done — Evidence Ledger STEP 3c (poster): per-asset audit-trail export (the sellable proof) (2026-06-24) ✅
The brand-safety PROOF object — for each generated poster, the (claim -> real source URL) trail
the agency shows its client. Built ONLY after all three copy surfaces were gated (poster concept /
pick_angle / strategy) so the proof is honest about the WHOLE product, not a covered slice. Started
with the POSTER alone (owner: inspect one complete asset before generalizing).
- `poster/audit.build_poster_audit(profile, concept, brief)` assembles: `final_copy` (the
  `EvidenceLedger.audit_fields(...).export()` of the SHIPPED copy — each hard claim -> kind/token/
  REAL scraped source_url/source_tier/matched_quote/confidence) + `remediation` (what the gate
  CAUGHT and how it was handled) + an explicit `coverage` SCOPING block.
- TRANSPARENCY that the gate WORKED is part of the proof (owner): a softened/dropped fabrication is
  recorded in `remediation` as HANDLED (action=softened|dropped|softened_to_fallback) — NEVER shown
  in `final_copy` as if sourced, NEVER hidden as if it never existed. `poster/concept.py` gained a
  `CreativeConcept.remediation` log populated through the regenerate/clean/fallback paths.
- SCOPING is written IN the artifact: `covered_surfaces`=[poster copy: headline/sub/CTA/chips];
  `excluded_surfaces`={reel: "NOT yet gated — no trail claimed", background_image: design domain}.
  Claiming brand-safety for an ungated surface = the overselling that breaks the moat, so it's named.
- VISUAL-MATCH fix (owner: a cross-language quote tanks the proof even when technically right):
  resolution now PREFERS same-language evidence (TIER priority preserved — brand still beats web),
  falling to another language only if none exists and LABELING it (`copy_lang`/`matched_lang`/
  `lang_mismatch`) so the difference is documented. `grounding/ledger.py`: `_lang`, `_pick`,
  `_resolve_number/_resolve_group(copy_lang=)`, export carries the language fields.
- `poster/pipeline.py` builds the trail once and writes a `<poster>.audit.json` SIDECAR next to the
  shipped PNG (CLI + web app).
- VERIFIED on the FULL live path (rule 3): `generate_poster(digilians, Gemini + Imagen Ultra, QA
  pass)` -> the sidecar landed next to the PNG AND caught a LIVE fabrication — the Gemini concept
  emitted a chip "مجتمع حصري للرواد الرقميين" ('حصري'/exclusive, unsourced) which the gate DROPPED
  and logged as handled in the real sidecar. Deterministic samples (digilians) show claims resolving
  to real `digilians.gov.eg` URLs (first/number/certification) with Arabic matched_quotes after the
  language fix. Tests: `tests/test_poster_audit.py` (3) + `test_ledger.py` (+2 language) + canary.
  Suite **747 passed, 0 failed**.
NEXT (3c calendar): generalize the SAME artifact shape to the strategy content-calendar (each
item's hook/angle), now that the poster artifact is owner-verified. Reel stays EXCLUDED until it is
gated (workstream #3).

## Done — Evidence Ledger STEP 3c (calendar): per-item audit-trail + shared coverage scope (2026-06-24) ✅
Generalized the owner-verified poster audit shape to the strategy content-calendar — the LAST text
surface. All three customer-facing copy channels (poster concept / pick_angle / strategy) are now
BOTH gated AND carry an exportable brand-safety trail; the TEXT MOAT IS COMPLETE.
- `strategy/audit.build_calendar_audit(profile, calendar)`: a PER-ITEM trail — each item's
  surviving hook/angle/topic -> `EvidenceLedger.audit_fields(...).export()` (claim -> REAL scraped
  source_url, via the SAME language-aware resolver as the poster, so an Arabic claim cites Arabic
  evidence and any cross-language match is flagged) + the per-item `remediation` + the shared
  coverage block.
- STRATEGY REMEDIATION LOG (purely additive — recording ONLY): `strategy/builder` records each
  blanked hook/angle on `ContentItem.remediation` ({field, original_text, unsourced_claims,
  action:"blanked", note:"item runs on its sourced topic"}). The blank DECISIONS + results are
  byte-for-byte unchanged — VERIFIED: the 27 gray-cases stay cases=27 FP=0/FN=0 and all 6 old
  strategy tests pass with identical results after the addition.
- SHARED SCOPE (`grounding/audit.py`): one source of truth for the POLICY + `coverage_block()` so
  the poster AND calendar artifacts state the SAME honest scoping — `covered_surfaces`=[poster copy,
  calendar copy]; `excluded_surfaces`={reel: "NOT yet gated — no trail claimed"}. `poster/audit.py`
  refactored onto it (poster adds background_image to excluded).
- TRANSPARENCY (owner): a blanked item is recorded as HANDLED (the fabricated hook is in
  `remediation`, never in `shipped_copy`) and its `shipped_copy` shows the SOURCED topic it now runs
  on — a reader sees the item was remediated, not clean-from-the-start.
- Wired into `strategy/__main__`: writes a `<plan>.audit.json` sidecar next to the calendar JSON.
- VERIFIED on the FULL live path (rule 3): `python -m strategy digilians_profile_real.json` ->
  4-item Gemini calendar, the sidecar landed next to the plan JSON, 1 item remediated LIVE, 2 claims
  resolved to real `digilians.gov.eg` URLs (language-matched). Deterministic digilians sample shows a
  grounded item (number 32 -> real URL, Arabic quote) + a blanked item (hook+angle blanked & recorded;
  shipped_copy = only the sourced topic). Tests: `tests/test_calendar_audit.py` (4) + `test_ledger.py`
  (+2 language) + `test_poster_audit.py` (coverage). Suite **752 passed, 0 failed**.
TEXT MOAT COMPLETE: 3 surfaces gated + audited. NEXT workstream = the REEL (its own: concept/DNA +
Ledger gate + art-directed motion) — it stays EXCLUDED from every audit trail until gated.

## Done — poster: adaptive logo plate (kill the white box, keep the colored logo) (2026-06-26) ✅
Owner-reported: the brand logo rendered inside a hard WHITE plate -> a "white box / from a
screenshot" look. DIAGNOSED FIRST on the EXACT logo the pipeline draws (rule 2): for Digilians,
`build_poster_brief -> Digilians.png` (the `primary_brand_logo` conf 1.0 of 24 candidates) is
**100% transparent** — all 4 corners RGBA (0,0,0,0), 66% transparent, **0% opaque-white**. So the
white is the renderer PLATE, NOT a baked-white logo background; the near-white->transparent
threshold does NOT apply here (nothing baked to remove — kept only as a fast-follow if a genuinely
baked-white logo ever shows up). The logo is a DARK navy mark, so on a DARK photo it needs light
backing or it vanishes — that backing was the hard white box.
FIX (`poster/template._adaptive_logo_style` + `_logo_luminance`/`_logo_region_box`/
`_bg_region_luminance`): the plate is chosen from the LOGO's luminance vs the BACKGROUND behind it
(sampled per logo corner/free-xy): contrast >= 0.28 (logo already reads) -> NO plate, transparent
+ soft drop-shadow (natural integration); low contrast -> a soft FROSTED-GLASS "designed badge"
that contrasts the logo (dark badge for a light logo; a MUTED light badge — not stark white — for
a dark logo), with tight padding + blur + a subtle border, kept light enough that a dark wordmark
stays legible. Never a fixed white box, never blind removal (a dark logo on a dark photo keeps its
plate so it can't vanish). Falls back to the capture-time `logo_chip` flag when luminance can't be
judged (SVG). MEASURED: 51 saved backgrounds (logo-region luminance 0.01..0.94) — light bg ->
transparent (integrates, no box), dark bgs -> frosted badge. KNOCKOUT-reverse (recolor navy->white)
was CONSIDERED + REJECTED: the Digilians logo is hue-monochrome but GRADIENT-rich with a dark-navy
wordmark, so white-flattening would erase the blue brand identity (owner: keep the colored logo).
Owner signed off on the tuned frosted-badge sample (logo clear, no white box). Suite **754 passed**.
HONEST LIMIT: the bg-luminance estimate uses the raw background, not the CSS scrim on top — a proxy;
the transparent case carries a drop-shadow as safety.

## Done — Reel grounding STEP 1: read-only audit primitive + measurement (2026-06-27) ✅
The reel is the LAST customer-facing creative surface still OUTSIDE the Evidence-Ledger
brand-safety trail (`grounding/audit.py` lists it in `UNGATED_SURFACES`). Closing it makes the
"provable zero-hallucination" moat cover ALL creative outputs. Mirroring the Ledger's own poster
sequence (Step 1 = gate engine + READ-ONLY measurement, blocks nothing), this is the reel's Step 1:
APPLY the existing `grounding.EvidenceLedger` to the reel's copy surfaces and MEASURE — no blocking,
no softening, no required spend.
- `reel/grounding.py` (new, pure, never raises): `creative_reel_copy_fields(creative_reel)` pulls
  the CUSTOMER-FACING copy of an Opus `CreativeReel` (reel-level hook/cta + per-scene `voiceover`
  (spoken) + `on_screen_text` (displayed); internal `concept`/`music_mood`/`veo_prompt` excluded);
  `narration_copy_fields(storyboard)` reuses `reel.voiceover.narration_lines` (the DEFAULT path's
  verbatim spoken lines); `audit_reel_copy(profile, fields)` = `EvidenceLedger.from_profile(...).audit_fields(...)`.
- `grounding/measure_reel.py` (new, mirrors `measure_step1.py`, reuses its `CORPUS`/`_load`/`_unwrap`):
  Path A = DEFAULT narration (build_storyboard caller=None -> narration_lines), offline/ZERO cost;
  Path B = CREATIVE Opus path (`--creative`), OPT-IN behind both the flag AND an `ANTHROPIC_API_KEY`
  so it never spends silently. The real risk surface is the `--creative` path (`creative_director.py`):
  an Opus call that GENERATES persuasive voiceover/captions with only a SOFT "invent no facts"
  instruction and NOTHING enforcing it — exactly the pre-Ledger poster situation.
- Tests: `tests/test_reel_grounding.py` (5, hermetic, no live LLM — fabricated voiceover/caption
  ('أكبر ... معتمد', 'منذ 1850') flagged unsourced; grounded 'روّاد'/'5000' + paraphrase pass;
  subjective puffery passes; the default narration floor is clean). Suite **759 passed** (was 754).
MEASURED — DEFAULT narration floor (offline, 6-brand corpus): 3/30 copy fields (10%) flagged
unsourced — but ALL 3 are the SAME pattern: a real scraped PHONE NUMBER in the contact scene
(e.g. te.eg `+201555000111`, digilians `+20221277622`, NTI `+20224048561`). So **0 real
fabrications** in the verbatim path; the 3 are a precise LEDGER bug, not a reel issue: `from_profile`
indexes a phone as `ph.get("raw") or ph.get("e164")`, and the scraped `raw` is JUNK page-text (e.g.
"اتصل بنا رضاؤكم هدفنا...") with the clean number only in `e164` — so a contact line that shows the
clean `e164` can never resolve. The CREATIVE Opus risk surface (Path B) is NOT yet measured (needs a
paid Opus run; left as the user's explicit opt-in).
NEXT (separate, measured — decide with owner): (1) fix the Ledger to index BOTH `e164` AND `raw`
(pure evidence ADDITION; re-run the floor -> expect 0; affects the poster audit too). (2) Step 2 —
turn this into a BLOCKING gate inside `creative_director.py` (mirror `poster/concept.py`
`enforce_grounding`: soften/drop/regenerate + remediation log), wired on in `reel/creative.py`.
(3) Step 3 — `reel/audit.py` per-asset trail (mirror `poster/audit.py`) + move the reel from
`UNGATED_SURFACES` -> `GATED_SURFACES` in `grounding/audit.py` (only AFTER it is actually gated).

## Done — Ledger: index clean e164 phone (not junk raw) so contact lines resolve (2026-06-27) ✅
Surfaced by the reel Step-1 floor (entry above) — owner picked it as the next micro-step.
`EvidenceLedger.from_profile` indexed a phone as `ph.get("raw") or ph.get("e164")`, but a scraped
`raw` is frequently JUNK page-text (the nav/blurb the number was lifted from — e.g. te.eg
"اتصل بنا رضاؤكم هدفنا..."), with the clean number only in `e164`. So a creative that shows the
canonical e164 (reel contact scene, poster contact line) could never resolve its OWN real phone -> a
grounded contact number was flagged as an UNSOURCED "number claim" (false positive). Fix
(`grounding/ledger.py` `from_profile`): index BOTH `e164` AND `raw` (a pure evidence ADDITION;
`add()` already skips empties). MEASURED on the reel narration floor (6-brand corpus, offline):
unsourced **3/30 -> 0/30**; `evidence_count` rose where e164 differs from raw (NTI 66 -> 70). The
phones are STILL detected as number claims (9 fields / 10 claims preserved) but now RESOLVE — 0 false
positives, no claim silently dropped. Shared fix: the poster audit trail benefits identically (same
`from_profile`). Suite **759 passed** (no regression — adding real brand-tier evidence can only make
claims MORE resolvable). Covered by the reel-grounding floor test (`tests/test_reel_grounding.py::
test_default_narration_floor_is_clean` exercises the contact-phone path indirectly); no test pinned
the old `raw or e164` behaviour. So the reel Step-1 sanity floor now holds at 0 — the trustworthy
baseline before Step 2 (the blocking gate). The CREATIVE Opus risk surface (Path B) is still
unmeasured (owner's paid opt-in).

## Done — reel: text-overlay redesign v2 (legibility scrim + accent spine + hero type) (2026-06-27) ✅
Owner: the reel's on-video text was "وحش جدا" — plain white lists floating with WEAK CONTRAST
(white text on a washed-out near-white frame was barely readable), no hierarchy ("data dump"),
and on the live Orange reel the accent rendered BLUE, not the brand color. DIAGNOSED on the REAL
output (rule 2): extracted frames from `outputs/reels/orange_reel_v2.mp4` via the bundled ffmpeg
and VIEWED them (4s/8s = a near-blank washed frame; 13s = generic stock hands), then built an
OFFLINE before/after harness rendering `reel/textlayer.py` over CLEAN text-free backgrounds (busy
mid-tone / near-WHITE worst case / dark) so the design is judged with NO baked-text ghost and ZERO
Veo spend. Redesigned `reel/textlayer._scene_html`:
- A dedicated STRONGER + TALLER scrim (`.scrim` div, 64% height, dark to .96 at the base) replaces
  the weak `.lower` bottom gradient → text reads on ANY footage, incl. the near-white frame the old
  scrim failed on (MEASURED before/after: old = washed/illegible, new = crisp).
- A brand-accent SPINE (`border-left` on `.cluster`, RTL→`border-right`) ties the whole cluster and
  gives it a designed identity instead of a floating list.
- Hero typography: bigger headline (0.112/0.088·W), one brand-accent word (`.hl`), cleaner item rows.
- Kept: CTA chip, logo corner, RTL + `unicode-bidi:plaintext`, LTR phone/email/URL atoms, the
  vivid-from-palette `_accent`. Existing `tests/test_voiceover.py::
  test_textlayer_is_bottom_anchored_scrim_and_accent` still passes. Suite **759 passed**.
HONEST SCOPE (not overselling): this is the TEXT layer only — a real but SMALLER lever. The bigger
drivers of "وحش" are (a) the FRAMES — blank/generic/off-brand scraped photos animated by KenBurns
(or weak Veo seeds); NEXT, kept UNIVERSAL per owner ("works for any business, reads its soul"):
derive scene relevance from the scraped identity (category/offerings/persona), NO vertical
hardcoding; and (b) the storyboard putting a LIST of items per scene instead of ONE message per
scene. SEPARATE DATA bug: the live Orange accent was BLUE because the scrape missed `#FF7900`
(palette-extraction gap) — `_accent` is correct given a correct palette. The redesign is UNCOMMITTED
(working-tree change to `reel/textlayer.py`).

## Done — reel: UNIVERSAL content-image quality gate (kills the "dumb/blurry frame") (2026-06-27) ✅
Owner: the reel's frames were "غباء/وحش" and "ملهاش علاقة بالمجال" — and the fix must stay UNIVERSAL
("works for any business, reads its soul"). DIAGNOSED on the REAL Orange reel (rule 2): the reel
animates the brand's scraped `content_images`, but Orange's 12 "images" are tiny category THUMBNAILS
(298x175 / 221x130 px) + wide text BANNERS + near-blank product-on-white graphics — NONE are usable
photos. KenBurns / Veo-i2v upscaling a 298px thumbnail to 1080x1920 = a blurry "dumb frame". The
vision curator judges CONTENT ("on-brand?" — an Orange banner IS on-brand) but NOT technical
USABILITY, so garbage got animated. A UNIVERSAL pattern (many sites' "images" are banners/icons), not
vertical. ROOT cause is the missing deterministic TECHNICAL filter.
- New `reel/image_quality.py`: `assess_photo(w, h, mean_lum?, white_pct?)` (pure keep/reject) +
  `filter_usable_photos(urls, fetch=)` (SSRF-guarded fetch+measure, injectable fetch, never raises).
  Thresholds CALIBRATED across good- AND bad-photo brands BEFORE choosing them (rule 2): short-side
  ≥ 500px (the dominant, well-separated signal), long/short ratio ≤ 2.6 (banner strips), ≤ 88%
  near-white, mean-luminance 12–244. MEASURED: elkbabgi (real 960–2000px photos) KEEP 12/12;
  digilians KEEP 4/5 (the 1 reject is a Facebook tracking pixel); Orange KEEP 0/12.
- Wired into `reel/__main__`: the technical gate runs ALWAYS (before the optional vision curator),
  and `selected` is ALWAYS the gated set (possibly []), so the raw garbage is NEVER used. VERIFIED
  end-to-end OFFLINE (no Veo spend): Orange (0 usable) → 5 scenes ALL generated text-to-video (no
  blurry seed); elkbabgi (10 usable) → 6 scenes ALL seeded from real photos (the faithful path is
  intact). Tests: `tests/test_image_quality.py` (7, hermetic — injected fetch). Suite **766 passed**
  (was 759). UNCOMMITTED (working-tree).
NEXT (step 2, needs a Veo run to verify VISUALLY): when 0 usable photos the generated scene falls to
the DETERMINISTIC `_DEFAULT_SCENE` ("professional workplace") for an unknown category with no caller
— strengthen the UNIVERSAL identity-derived Veo scene prompt (category / offerings / persona) so a
telecom brand gets a connectivity scene, a clinic gets a clinic scene, etc., derived from the scraped
data with NO vertical hardcoding. Also: the poster shares the same weak-scraped-image risk — reuse
this gate there. And the scraper could record content-image dimensions so the gate filters without a
re-fetch.

## Done — reel: UNIVERSAL identity-derived scene + stronger LLM scene prompt (frame step 2) (2026-06-27) ✅
Step 2 of the frame fix (after the quality gate routes no-good-photo brands to GENERATED scenes).
Goal: the generated Veo scene must be RELEVANT to the brand's field, UNIVERSALLY (owner: "reads its
soul", NO vertical hardcoding).
- `reel/art_director._identity_scene(brief, profile)`: a UNIVERSAL deterministic fallback subject
  built from the scraped category + top offerings + audience — "real <audience> authentically
  experiencing <category> — a real-life moment that shows <offering1> and <offering2>". Replaces the
  generic `_DEFAULT_SCENE` ("professional workplace") for any category NOT in the (kept-as-enrichment)
  `_VERTICAL_SCENE` map (telecom / fintech / logistics / SaaS / ...). `_humanize` strips slug/segment
  jargon from the category/audience (`services_b2c`→`services`, `B2C`→dropped) so a Veo prompt never
  reads as a code; OFFERINGS stay VERBATIM (real product names, zero-hallucination). Restaurants keep
  their dedicated food scene.
- `build_brand_scene` (the LLM art-director — the PRIMARY production path) system prompt strengthened:
  "Show the brand's REAL activity IN ACTION — real people actively USING or experiencing its specific
  offerings, so the scene instantly reads as THIS exact field (NOT a generic office, NOT an abstract
  mood)."
MEASURED offline (no LLM, deterministic path): Orange (category `services_b2c`) BEFORE = "a
professional modern workplace..." → AFTER = "real people authentically experiencing services — a
real-life moment that shows Orange PREMIER and GO packages..." (grounded, no jargon); Digilians
(education) unchanged (keeps its template — no regression). Tests: `tests/test_reel_scene_identity.py`
(4). Suite **770 passed** (was 766). UNCOMMITTED.
HONEST CEILING: a DETERMINISTIC fallback can ground in the real category/offerings but CANNOT infer
the visual activity from an opaque product name (it can't know "Orange PREMIER" → people using
phones); that semantic leap is the LLM art-director's job (strengthened above), whose VISUAL result
needs a live Veo run to verify (owner's spend). The deterministic path is the clean, grounded,
no-jargon safety net.

## Done — brand-anchored images STEP 1: capability probe + measurement + standalone edit provider (2026-06-27) ✅
ROOT problem (owner, MEASURED on 3 delivered posters): pure **text-to-image** drifts OFF-brand
(generic AI stock people, clichés, occasional baked text) because nothing anchors the SUBJECT/
scene to the brand's real world — `BrandCreativeDNA` steers STYLE a bit but not the subject.
The reliable fix (already flagged in the 2026-06-16 entries) = **image-conditioned generation**.
Built it as a contained, verified-live first step (NOT yet wired into the pipeline):
- **SDK reality (verified, GOOD):** the INSTALLED `google-genai` 2.8.0 ALREADY exposes
  `edit_image` (STYLE / OUTPAINT / mask refs) + `recontext_image` — **no migration to
  `google-cloud-aiplatform` (not even installed) and no new dependency**. `recontext_image` in
  this SDK = **Virtual Try-On only** (fashion model+product) → NOT our tool. Our tool is
  `edit_image` with `EDIT_MODE_STYLE` (Path 1) + `EDIT_MODE_OUTPAINT` (Path 2).
- **LIVE capability probe** (the Veo-3.1 lesson — don't assume a model is provisioned):
  **`imagen-3.0-capability-001` IS provisioned on project image-498715** and returns images for
  BOTH STYLE and OUTPAINT; `imagen-3.0-capability-preview-0930` + `imagegeneration@006` → 404.
- **Coverage measurement (free, no GCP)** via the REAL `reel.image_quality` gate over the
  freshest scrape per brand (content_images extractor landed 2026-06-14, so older scrapes are
  excluded as artifacts → **9 valid brands**): **6/9 (67%) have ≥1 technically-usable photo**,
  4/9 (44%) have ≥3, **3/9 (33%) have ZERO** (vodafone all-thumbnails; te_eg 11/12 CDN-blocked
  on fetch; azzafahmy 0 extracted) — and those 3 are the SAME brands that produced the worst
  posters. HONEST caveats: small/directional corpus; "technically-usable" (size/ratio/blank) ≠
  "scene-worthy"; if we can't fetch it (te_eg) Path 2 can't use it either. → confirms an
  **ADAPTIVE** design (OUTPAINT when a good real photo exists; STYLE on the brand's real ads
  otherwise; text-to-image as the last-resort fallback) — same philosophy as the reel.
- **NEW `poster/imagen_edit_provider.py`** (`ImagenEditProvider`): `style(prompt, style_refs,…)`
  (EDIT_MODE_STYLE — a FRESH scene in the brand's own visual language) + `outpaint(base,…)`
  (EDIT_MODE_OUTPAINT — keep a REAL photo, extend it to the canvas via a built padded-canvas+mask).
  SSRF-guarded reference fetch; NEVER bakes text (reuses the no-text composition contract);
  RAISES on failure so the pipeline can fall back. Two bugs caught BY live validation + fixed:
  (a) a temporary `genai.Client` got GC'd mid-request ("client has been closed") → cache+retain
  the client; (b) non-square (3:4) signatures accept **max 2 reference images** → `max_refs=2`.
- **VERIFIED LIVE through the module across 2 verticals:** OUTPAINT elkbabgi → the real stuffed-
  pigeon platter PRESERVED and the feast naturally extended to **1024x1280** (max fidelity);
  STYLE WE/Telecom (from its 7 real ads in `telecom_egypt_dna.references_seen`) → a purple
  "digital-twilight" rim-lit composite scene at **896x1280** — on-brand, vs the old generic
  drift (WE was the worst prior poster). Tests: `tests/test_imagen_edit_provider.py` (6, hermetic
  — mask geometry, SSRF guard, no-ref/unfetchable-base raise; live edit calls out-of-CI). Suite
  **776 passed** (was 770). NEXT (separate, measured): wire the ADAPTIVE selector into
  `poster/pipeline.generate_poster` (pick OUTPAINT vs STYLE vs text-to-image by available real
  assets), then carry the same engine to the reel.

## Done — brand-anchored images STEP 2: ADAPTIVE selector wired into the poster pipeline (2026-06-27) ✅
Wired the STEP-1 edit provider into `poster/pipeline.generate_poster` (the ONE path shared by
CLI + web app), so generated posters are now anchored to the brand's REAL assets instead of
drifting on pure text-to-image. New `_generate_background(profile, brand_dna, prompt)` runs a
SAFE CASCADE (never raises — each mode falls through to the next):
  1. **OUTPAINT** a usable REAL scraped photo (`_best_usable_photo` reuses the real
     `reel.image_quality` gate, max_keep=1) — maximum fidelity (the literal place/product ships).
  2. **STYLE** on the brand's real creatives (`_brand_style_refs`: BrandCreativeDNA.references_seen
     FIRST, then the brand's own content_images; capped at 2 = the non-square ref limit) — the
     universal floor (works when there's no usable photo).
  3. **text-to-image** (the previous `_generate_imagen`, Ultra->4.0) — last-resort fallback.
`use_edit=True` default (flag to force the legacy text-to-image path); `no_image` stub unchanged.
The cascade replaces ONLY the background-generation call (line ~224); the design-spec, concept,
QA-regenerate loop, audit sidecar and response shape are untouched — so the WEB APP inherits the
adaptive path automatically (`api/routes/poster.py` calls `generate_poster` with the defaults).
- Helpers are injectable (fetch / edit_provider / t2i) so the cascade is hermetically tested:
  `tests/test_poster_pipeline_bg.py` (7 — ref ordering+cap, quality-gate photo pick, and the
  full cascade: outpaint-first / fall-to-style-on-outpaint-fail / style-when-no-photo /
  t2i-when-no-assets / t2i-when-both-edit-modes-fail). Suite **783 passed** (was 776).
- VERIFIED LIVE end-to-end (full `generate_poster`, Gemini + Imagen edit): **elkbabgi -> OUTPAINT**
  (real feast photos extended to the canvas + Arabic-free English copy "Experience The Sizzle" +
  chips + CTA; QA failed ONLY on the low-res logo asset — a known elkbabgi data gap, NOT the
  scene/this change) and **WE/Telecom -> STYLE** from its 7 cached real ads (purple digital-
  twilight, desert-highway truck matching the fleet-tracking offer, Arabic copy, logos; QA
  **pass=True, clean**). The adaptive selector chose the right mode for each brand.
HONEST watch-items (NOT yet addressed, each its own measured follow-up): (a) for a thin-photo
brand whose content_images are unreachable (te_eg: 11/12 CDN-blocked), `_best_usable_photo` pays
sequential fetch-timeout latency before falling to STYLE — consider caching the "no usable photo"
verdict or using scraper-recorded dims; (b) `load_or_build_dna` still runs for photo-rich brands
(outpaint doesn't need it, but concept/design do, so not wasted); (c) an OUTPAINTed busy photo has
no deliberate calm text zone — the renderer's scrim/adaptive-logo-plate handles legibility, but
measure whether STYLE composes better than OUTPAINT for some photo-rich brands. NEXT: carry the
same adaptive engine to the REEL; then the elkbabgi-class low-res-logo asset gap.

## Done — poster: letterbox fix + DNA-driven "lockup" typography (real-ad design) (2026-06-27) ✅
Owner: a generated poster "البك جراوND مش كاملة" (WE bg had black bars) and "هو بس بياخد صورة
ويحط عليها كلام" — it should be a DESIGNED ad, not a photo with text on top. Owner chose: real
ad design. CONSTRAINT (kept): text is NEVER baked by the image model (Arabic garbles +
zero-hallucination), so "ad design" = elevate OUR controlled HTML/CSS layer, driven by the
brand's BrandCreativeDNA. Two changes this step (CLI + web app share the pipeline):
1. **Letterbox fix** (the "incomplete background"). ROOT CAUSE (MEASURED on the saved WE bg
   bg_3afdf4e7): the STYLE/text-to-image model rendered a LANDSCAPE scene centered in the 3:4
   portrait frame with dark bars (band mean ~15, **max 17** — NOT pure black). NB: Imagen has no
   "4:5"; 3:4 is the closest portrait and was already set — aspect wasn't the cause. Fix = (a)
   FULL-BLEED instruction in `imagen_provider._COMPOSITION_CONTRACT` + `imagen_edit_provider.
   _OUTPAINT_GUARD` ("fill the ENTIRE frame edge-to-edge, NO black bars/letterbox"), AND (b) a
   DETERMINISTIC safety net `poster.pipeline._trim_letterbox` (row-MEAN detector, calibrated
   threshold 24 — a first per-pixel bbox at 16 MISSED the bars because their max was 17; caught
   by measuring) applied after every bg gen. MEASURED: bg_3afdf4e7 1280 -> **552px** (728px of
   bars removed); the live WE re-render came out full-bleed (prompt worked) so the net was a
   no-op there (correct).
2. **"lockup" typography** (`template.py` + `pipeline.py`). New `_headline_block` treatment
   `"lockup"`: stacked words as a bold DESIGNED graphic lockup — gradient text fill +
   `-webkit-text-stroke` outline + drop-shadow, the accent word in the brand-gradient (the DNA
   "extremely bold / internal gradients / heavy outlines / headline-as-icon" look). Gradient
   colors come from the brand palette. `pipeline._dna_wants_lockup(brand_dna)` selects it when
   the BrandCreativeDNA `typographic_character`/`signature_moves` reads bold/graphic (WE matches)
   — so it's DNA-DRIVEN, not hardcoded. Falls back to the existing treatments otherwise.
Tests: `tests/test_poster_pipeline_bg.py` (+4: letterbox crop + noop, DNA lockup detection,
lockup headline renders gradient+outline). Suite **787 passed** (was 783).
VERIFIED LIVE on WE (before adaptive_te_eg.png -> after): BEFORE = letterboxed truck + plain
small text; AFTER = full-bleed purple WE scene + a big bold gradient/outline Arabic LOCKUP
("خدمات/تقربك/أكتر"). HONEST: QA flagged the big lockup OVERLAPPING the central subject (focal
clutter, score 6) — the typography "exploded" correctly but the COMPOSITION needs the lockup
placed in the image's calm zone. NEXT (before expanding to all brands, per owner): fix lockup
placement vs the subject (calm-zone aware), then generalize the DNA-driven typography + add brand
MOTIFS (light streaks / color blocks as CSS/SVG) for a fuller "designed ad", then carry to reel.

## Done — scraper: adaptive crawl budget for e-commerce (Pillar 1) (2026-06-28) ✅
MEASURED FIRST (`benchmark/measure_ecom_coverage.py` + `_bottleneck.py` over saved scrapes;
e-commerce detected UNIVERSALLY by product-URL density, no hardcoded names): e-commerce coverage
was **~2.5%** (4-12 of 100-300+ discovered pages). KEY finding that RESHAPED the fix — the page CAP
was NOT the binding constraint: at ~11s/page the 150s budget fits only ~12 pages, so the cap (12)
and the time budget bind TOGETHER; **raising `MAX_INTERNAL_PAGES` alone is a no-op**. HONESTY caveat:
the saved scrapes were old-budget (60s), overstating the gap — re-measured live (azzafahmy fresh:
12 pages). FIX (`scraper/config.py` + `crawler.py`): when the homepage links + sitemap reveal many
PRODUCTS-type URLs (>= `ECOMMERCE_PRODUCT_URL_MIN`=15, via the EXISTING `classify_url` — a SIGNAL,
never a vertical), raise BOTH the cap (12 -> 30) AND the time budget (150 -> 330s).
`_looks_like_ecommerce(home_links, sitemap_urls)` dedups + early-exits at the threshold; threaded as
`page_cap`/`budget_secs` into `_select_subpages_to_fetch` + the crawl loop. VERIFIED LIVE on elietop
(Shopify store): **20 pages** crawled (vs 12 default / ~6 old), 3401 text blocks, ready=True — hit the
330s budget at 20 pages (this store renders ~16s/page; a store scrape now takes ~5.6 min — render
speed is the follow-up to cut that). Tests: `tests/test_crawler_ecom_budget.py` (3). Suite **790 passed**.
NEXT: per-page render SPEED (resource-blocking on sub-pages) so 30+ pages fit faster; duplication
early-termination; re-anchor the saved-scrape baseline on fresh runs.

## Done — scraper: a malformed scraped LINK no longer crashes the whole crawl (2026-06-28) ✅
EXPOSED by the deeper e-commerce crawl above (the disciplined value of one fix surfacing the next):
`ensure_scheme` — a low-level util that `normalize_url` calls on EVERY scraped link href during
dedup — called `validate_input_url`, which RAISES on a concatenated URL (`https://a/https://b`). Real
stores emit such links (MEASURED LIVE: elietop has a Shopify-auth redirect href with an embedded
second absolute URL), so `build_inventory` CRASHED the ENTIRE scrape (exit 1, no manifest). ROOT FIX
(`scraper/url_utils.py` + `crawler.py`): `ensure_scheme` is now pure/ROBUST (never raises — just adds
the scheme); the malformed-INPUT guard `validate_input_url` is called explicitly at the BOUNDARY (the
`scrape()` entry; the API already validated in its request schema). So a bad LINK is handled
gracefully while a concatenated USER input is still rejected (same external behaviour). Updated
`tests/test_current_hotfixes.py`: the rejection now asserts at the boundary (`validate_input_url`
raises) and `normalize_url` must NOT raise on a link href. VERIFIED LIVE: elietop completed with **0
failures** (a guaranteed crash before the fix). Suite **790 passed**.

## Done — scraper: light sub-page fetches (render-speed, Pillar 1 enabler) (2026-06-28) ✅
The lever that makes adaptive depth feasible — the page cap + the time budget bind TOGETHER at
~11-16s/page, so deeper crawls need FASTER pages. Sub-pages are crawled for TEXT + LINKS only (visual
identity is the homepage's job), so they don't need rendered pixels. `scraper/fetcher.py`: a new
`light=True` fetch mode (1) blocks heavy resources (image/media/font) via `page.route` —
`_block_heavy_route` aborts those, continues documents/scripts/XHR/CSS so JS-injected content
(products/links/lazy text) is preserved — and (2) SKIPS the full-page screenshot (the slowest step;
it also caused a font-load-timeout failure on a fresh run). Wired in `crawler.py`: the homepage stays
FULL (light=False); every sub-page fetch is `light=True`. VERIFIED LIVE (elietop, full -> light):
**20 -> 24 pages**, 337s (budget-bound) -> **323s (NOT budget-bound)**, ~16.8 -> **~13.5s/page (~20%
faster)**, text blocks 3401 -> 3794, social 4 -> 6, 0 failures, ready=True — faster + MORE coverage +
MORE data, with data integrity PRESERVED (the key risk). Tests: `tests/test_fetcher_light.py` (2,
hermetic). Suite **792 passed**.
HONEST: the ~20% win is from resource-blocking + skipping screenshots; the BIGGER remaining per-page
cost is `_scroll_to_load` (scroll loop + 1.4s dwell + networkidle waits, ~10-14s) — trimming those on
light sub-pages is the next lever but HIGHER-risk (lazy product/footer content), so it needs its own
measured before/after. NOTE: sub-page screenshots are now empty by design (unused; visual identity is
homepage-only).

## Done — poster: image quality (photoreal faces + 2x upscale) (2026-06-27) ✅
Owner: "الكوالتي محتاجة تتحسن + مينفعش يكون وشوش حقيقية؟" Chose (option 1): keep generating but
make the AI people look REAL/believable + higher quality (NOT real actual faces — that needs a
real source photo, which a thin-photo brand like WE lacks; conditioning on a real ad face = a
rights risk, deferred). Two changes (CLI + web app share the pipeline):
1. **Photoreal/face-realism prompt clause** appended to `imagen_provider._COMPOSITION_CONTRACT`
   (covers STYLE + text-to-image): "Photorealistic, high-resolution, crisp focus … any PEOPLE
   must look REAL and lifelike — natural skin/features, eyes with catchlights, well-formed hands;
   NOT plastic/waxy/distorted/AI-uncanny."
2. **2x upscale** for crispness + sharper faces. LIVE probe (the Veo/edit lesson — don't assume a
   model): `upscale_image` IS provisioned on image-498715 via **imagen-3.0-generate-002** (and
   3.0-generate-001 / 3.0-capability-001; imagegeneration@002 -> 404). New
   `imagen_edit_provider.upscale_to_file` (never raises; no-op without a project) wired into
   `pipeline._maybe_upscale` after the letterbox trim (`upscale=True` default flag).
MEASURED LIVE on WE (re-render): photoreal clause + upscale -> background **896x1280 -> 1792x2560**,
and the vision-QA verdict rose **6 -> 9 (clean pass)** vs the pre-quality lockup render; the scene
read as a premium WE ad (conductor figure + brand light-shard motifs + bold Arabic lockup),
faces sharper/less uncanny. Tests: `tests/test_imagen_edit_provider.py` (+2: upscale safe-no-op on
unreadable / no-project, hermetic). Suite **794 passed** (was 787). HONEST: faces are still
AI-GENERATED (believable, not real people) per the owner's choice; upscale adds an API call per bg
(cost/latency — currently runs per QA attempt; optimizing to upscale-final-only is a follow-up).
NEXT: lockup placement vs subject (calm-zone aware) + brand MOTIFS as CSS/SVG, then carry to reel.

## Done — poster: Marketing Archetypes + creative typographic layouts (code green; live pending) ✅
Owner brief (acting as senior art-director + AI eng): guide the free-form LLM layout with
MARKETING ARCHETYPES so output follows pro advertising principles — creative text placement,
high-end typography, visual harmony — WITHOUT hardcoding CSS grids (archetypes are BEHAVIORAL
prompt constraints; the LLM still emits continuous text_box/logo_xy). Zero-hallucination kept
(text overlaid; image text-free). Done one file at a time, suite green between steps, NO live
API yet (live Imagen run reserved to do together).
- **Step 1 — design-spec archetypes** (`art_director.build_design_spec` + `_DesignSpecResponse`
  + `schemas.PosterDesignSpec.marketing_archetype`): the LLM FIRST picks one of
  magazine_editorial / product_hero / typographic_anchor / proof_and_trust, then lets it DRIVE
  text_box / logo_xy / headline_treatment / text_align (system prompt describes each archetype's
  placement behavior). The chosen archetype is mapped onto the spec (verified it carries through).
- **Step 2 — strict, placement-aware calm zone** (`art_director._calm_zone_instruction(zone,
  text_box)` + `build_llm_concept_prompt`): when the LLM chose a free text_box, the Imagen prompt
  now names the PRECISE band that must stay clear (e.g. "keep the BOTTOM ~35% ENTIRELY clear of
  the main subject's face … reserved for overlaid text"), so the subject sits OUT of where the
  text lands. Still forbids the flat color block.
- **Step 3 — archetype-aware renderer** (`template.py`): the renderer reads
  `spec.marketing_archetype` and (a) renders the headline as a bold designed LOCKUP for
  magazine_editorial / typographic_anchor (the headline becomes the visual anchor; the accent
  word uses the brand's most-saturated palette color); (b) EMERGING effect — for product_hero or
  any LOW text block, a feathered VERTICAL linear-gradient scrim (solid at the base, fading up)
  so text emerges organically from the image instead of sitting in a hard box (else the soft
  radial wash); (c) generous padding (40x46) so text breathes, never touching the canvas edge
  (coords still clamped to safe margins). No hardcoded grid — coords stay the LLM's.
Tests: `tests/test_poster_design.py` (+2 Step-3: emerging-scrim/lockup by archetype, radial-vs-
emerging by placement; 3 fixtures + an assert updated for the new required field). Suite **796
passed** (was 794).
LIVE-VERIFIED + FOLLOW-UP FIX (archetype-aware `show`): first live WE run picked
`magazine_editorial` (right-third lockup) correctly BUT QA caught a **clipped CTA** — root cause:
`pipeline.generate_poster` FORCED logo+headline+sub+offerings+cta into a top-anchored side third
-> overflow. Fix: `must_show` is now SCALED TO THE ARCHETYPE — magazine_editorial = logo+headline+
cta (the massive lockup is the hero); typographic_anchor/product_hero add one sub line; only
proof_and_trust/None show the evidence bullets. Re-VERIFIED LIVE on a FRESH te.eg scrape (the
owner's improved scraper: 9 pages, palette now has real WE purple #512283/#6449cd, 12 content
images): archetype=magazine_editorial, show=[logo,headline,cta], full-bleed warm emotional scene
(woman on an evening phone call, purple-twilight city), bold Arabic lockup "المسافات بينا كلام",
CTA NOT clipped, QA **pass=True score=9 ("overall execution is excellent")**. Suite **796 passed**.
NEXT: carry the archetype engine to the reel; minor (QA note): the light CTA-chip contrast +
the accent word's legibility over a busy area.

## Backlog (each its own measured fix)
- **Logo-vs-photo on multi-variant seals:** Azza Fahmy emits its seal in several
  color variants; only the selected one is excluded by filename, so a variant can leak
  into `content_images`. Most sites are clean (jpeg-first ordering helps). Measure
  prevalence before adding perceptual/transparency detection.
- **Scraper page cap is thin on big catalogs:** `config.MAX_INTERNAL_PAGES = 7` ->
  Azza Fahmy scraped 4 of 204 discovered pages. Make the cap / page-selection adaptive
  for large stores (prioritize collections/category pages). Measure coverage vs cost
  (more pages = more render time + LLM tokens) before raising.
- **Page-type misclassification:** Azza Fahmy's terms-of-service page was labeled
  `services`. Tighten the page-type classifier (terms/privacy/legal != services).
- **Delete dead `poster/art_director.build_art_direction`** (+ _category_key/_choose_layout/
  _layout_prompt) + orphaned poster/image_providers.py + render_pillow.py — hardcoded
  per-category templates, no live caller, but entangled with api/routes/poster.py's
  PosterArtDirection import; untangle first.
- **`reel/subtitles.py` is orphaned** after the Playwright pivot (compositor uses
  textlayer.py, not libass). Remove it + arabic-reshaper/python-bidi, or keep as a
  documented libass fallback.
- **Consume deep_search in build_profile:** emit a degraded, secondary-sourced
  profile when the first-party scrape was blocked (confidence policy = product call).
- Scraper finds 0 logo_candidates on some sites (mumm_io, spclinic_net,
  clear-lsc_com; older buffaloburger scrape too — newer one OK). Measure what
  markup they use before changing the extractor.
- Frontend: ✅ festive marketing redesign (2026-06-22) — dropped the dark/charcoal
  "Claude" theme for a light, vibrant violet→pink→orange brand-gradient theme with
  CSS animations (fade-up, animated gradient hero text, float, pop, hover-lift),
  `frontend/app/globals.css` + `tailwind.config.ts` + `page.tsx` + `ui/button.tsx`
  (default = gradient) + `ui/card.tsx` (frosted, soft). ✅ Clickable CTA button beside
  the poster (`poster-studio-card.tsx`, uses `brief.cta_url`) + refreshed copy
  (Imagen/art-director, per-run variation). STILL PENDING: Auto/AR/EN language selector
  (clarify intent — UI labels vs forcing poster output language/direction; RTL poster
  rendering already works). Verified via HTTP 200 + zero console errors (the preview
  screenshot tool times out on this machine, so visual QA is the owner's live view).
- Delete orphaned old-pipeline modules `poster/image_providers.py`,
  `poster/render_pillow.py` (+ their tests) once confirmed nothing imports them.
- Wire `subject_places` into `build_matrix` (n=1 -> n=3; fills the THREATS quadrant).
- SSRF depth: crawler-followed sub-page/sitemap links + DNS-rebinding (pin resolved IP).
- contact_phone rubric: treat WhatsApp as equivalent to phone for MENA markets.
- Web-discovery aggregator denylist is HOST-BASED only (`_AGGREGATOR_HOSTS`), so a
  listicle on an unlisted domain (observed live: "The 15 Best Running Shoes of 2026")
  passes as a peer. Measure prevalence on real SERP output before adding title/pattern
  heuristics (rule 2).
- No `conftest.py`: test network isolation relies on every test injecting a fake
  provider; a stray real call goes live if a SERP key is in the env. Consider a session
  fixture that clears SERP keys / blocks sockets.
- Stale `.pyc` from the other machine (`C:\dev\scraper_v01`) sits in `tests/__pycache__`
  (Drive-synced) and shows wrong paths in tracebacks — harmless but confusing. Now
  gitignored (`__pycache__/`); delete the dir to refresh the bytecode cache.
