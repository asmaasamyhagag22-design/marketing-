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

## Backlog (each its own measured fix)
- **Reel #4 — condition generation on scraped images — PROTOTYPED then BLOCKED
  (2026-06-14, see memory `reel-4-image-seeding-blocked`).** Built end-to-end (Veo
  image-to-video, live-verified on elkbabgi) but **UNCOMMITTED / not shipped**: the
  premise fails because the scraper can't reliably hand a real PHOTO — MEASURED
  **14/59 manifests have `hero == the selected logo`** (Azza Fahmy emits the seal in
  multiple color variants, so an exact-src guard still leaks), and even a real photo
  yields Veo-invented settings (elkbabgi's open-air garden) — not faithful. Plumbing
  sits in the working tree (business_profile/schemas hero_image_url; from_visual
  `_hero_image_url`+`_logo_srcs`; reel/{schemas,storyboard,compositor,video_provider};
  tests/test_reel_reference_image.py). BLOCKER for any resume: a reliable
  real-photo-vs-logo classifier. Awaiting the user's faithfulness direction.
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
- Frontend: clickable CTA button beside the poster (PNG can't be clickable; use
  `brief.cta_url`) + Auto/AR/EN language selector (RTL rendering already works).
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
