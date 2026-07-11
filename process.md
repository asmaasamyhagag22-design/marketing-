# process.md — Universal AI Marketing Strategist

**The single source of truth for this project.** Replaces the historical
change-log. Read this before acting in this repo. Last full revision: 2026-07-04.
Test suite: **1200 passed, 0 failed** (2026-07-11; grew from 880 as each audit fix
below shipped with its hermetic regression tests).

**U1 GATE — first measured number (2026-07-11): objective 57% / destination 46% — FAIL vs ≥80%.**
Owner ratified all 14 `expected_objective`/`expected_destination` labels in `ground_truth.json`;
`python -m benchmark.grade_u1` now prints a real number. (First run read 0% — a wiring bug, not
deduction: `grade_u1` was the ONE entrypoint in the repo not loading `.env`, so `default_caller`
saw no creds and the builder honest-degraded to None on all 13. Fixed: `_load_env()` at
entrypoint-only + hermetic never-overrides test.) **Miss decomposition (offline signal dump, no
LLM):** 8/14 objective-correct. The 6 misses are ~all SIGNAL COVERAGE, not reasoning: (a) the
`online_store` signal requires ecom-category OR cart-ish URL hints, so **buffalo_burger** (22 priced
offerings on `/menu`) and **norshek** (12 priced on homepage, category='') expose NO store surface →
the LLM obeys the hard rule and picks Leads; (b) **mcdonalds_eg** (11 offerings, 0 priced) +
**zooba** (2 offerings, 0 priced) — prices never extracted → Traffic; (c) **alameda** profile exposes
ONLY `website` (no phone/form for a hospital — extraction gap) → Awareness; (d) **mumm** = no profile
(bot protection, permanent unless re-scraped) → ceiling is 13/14 = 93%. **andalusia** is a label
nuance (deduced LEADS ✓ via phone/form surface; owner label says dest=website). Proposed fix order
(ONE at a time, measured): FIX-1 broaden `online_store` signal universally (N≥3 priced offerings on
own domain OR order-ish URL hints) → predicted +2 = 71%; FIX-2 extraction gaps (mcdonalds/zooba
prices, alameda contact channels, norshek category — overlaps the norshek/almentor 0.50 outliers) →
predicted ceiling ~93%. Awaiting owner approval.

**BASELINE (post-audit, new project, 2026-07-10):** first full 14-URL benchmark on the fresh GCP
project (`radiant-octane-501919-v1`, Vertex ADC — old `image-498715` was dunning-suspended). This is
the REFERENCE POINT for every measured change from here. `benchmark/runs/20260711_055349/`:
**13 graded** (mumm excluded — bot protection, expected), **11/13 ready (85%)** (> 0.786 gate ✅),
**avg SWOT-critical 0.846** (JUST under the 0.85 gate — marginal FAIL by rounding). Per-vertical: clinic
0.92 · ecommerce 1.00 · restaurant 0.83 · skincare 0.81 · education 0.75 (all > 0.70 floor). Two
outliers drag it: **norshek 0.50 + almentor 0.50** (both not-ready — investigate as a quality follow-up,
NOT the U1 gate). CAVEAT: this is a **STRUCTURAL-only** average — the 3 fuzzy SWOT-critical fields
(audience/value_propositions/tone_of_voice) are UNGRADED until `ground_truth.json` is labelled; the real
SWOT-critical number will differ once they are. Headline: the prompt audit + Gemini migration did NOT
regress extraction (11/13 ready, most URLs 0.75–1.0). **Quota diagnosis: per-MINUTE** — the first run
429'd on rapid cached re-extraction; this run (fresh scrapes pacing it, quota reset between runs)
completed with 0 backoff events. The `run_extract` backoff is the safety net for fast re-extraction.
**Quota resolution (2026-07-11):** no manual increase — owner enabled the Vertex **Quota adjuster**
(Quotas → Configurations → Enable; auto-raises adjustable quotas gradually from usage). Two nets now:
runner backoff (code) + adjuster (console). Future-429 map: the "…**with audio input**…" rows are System
limits (`Adjustable=No`, dim `base_model_id_and_resolution`) — NOT the throttle; the tokens quota (10^10)
is never it. **CONFIRMED it's DSQ:** filtering dim `base_model:gemini-2.5-flash-ga` returns only two token
rows — per-**minute** input tokens = "Unlimited", per-**day** = 10^10 (~0% used); there is **no
requests/min quota row**. So the 429 was transient Dynamic-Shared-Quota contention, not exhaustion —
nothing to raise, the adjuster is a no-op here, and the only levers are backoff (have it) + paid
Provisioned Throughput if a 0-429 SLA is ever needed.

**U1 Media Plan — schemas + builder (the real U1 gate) shipped (2026-07-07):** the priority v2.2 unit
(the defense asks about the objective, not prompt hygiene). New additive `media_plan/` package
(INTERFACES.md §F), profile pipeline untouched. **Schemas** (`schemas.py`, strict/PD-5): the 6
`MetaObjective` (ODAX `.value` = Ads-API string, imports to Ads Manager untranslated) + `FunnelStage`
/`GeoMode`/`Destination` enums, `KPITarget` (positivity-bounded), `EvidenceRef` (resolution-wrapper — a
claim is a fact only once Ledger-resolved), `Persona` (every axis an `EvidenceRef` → grounded, not a
guess), `GeoTargeting` (mode-consistent + mutually-exclusive), `CampaignObjective`
(funnel_stage/budget_allocation_pct/num_ad_sets/test_budget + `_learning_floor` 3×-CPL gated to
cost-metrics), `MediaPlan` (allocations sum==100, single-objective auto-100, weakest-link `is_grounded`
folding in objectives+persona+geo). A 15-agent adversarial review (owner: overkill — 3 lenses next time)
found+verified 4 real "silent-math" bugs, all fixed (is_grounded ignored persona/geo; negative target
silently disabled the floor; floor misfired on non-cost metrics; geo modes not mutually exclusive).
**Builder** (`builder.py`, the gate): `build_campaign_objective(profile, caller)` deduces objective +
destination TOGETHER from real facts, GROUNDS the destination in actual conversion surfaces
(`conversion_signals`: WhatsApp/checkout/phone/form/address/site → resolved EvidenceRef); a deduced
destination with no signal → honest `is_grounded=False` (advisor flags, never fabricates a store); no
caller/thin profile → None. +19 hermetic tests (MockCaller, offline). Owner decisions: kept 3× (budget
floor) + ticketed ~50-conversion learning-phase exit as a U3 guardrail (T-4); declined global
`strict=True` (breaks U6 json-dict round-trip); objective↔destination compat is the builder's job (inferential).
**Blocker:** Gemini billing still 403 dunning on `image-498715` (106225033713) — the 14-URL baseline
benchmark waits on the owner's console reactivation; U1 is offline and did not.

**Batch 3 (poster image) — COMPLIANCE_CONTRACT + shared image negative; Batch 5 calendar (2026-07-07):**
owner's Batches 3–5. Shipped the SAFE, high-leverage core this pass; the vertical→shape restructures +
persona strip are the next unit (heavy test coupling — the reel `_system_prompt` alone has 50+ substring
assertions). **(1) `COMPLIANCE_CONTRACT`** (owner's #1 fix — real ad-safety, was buried in 5 aesthetic
prompts and MISSING on the LLM + reel paths): `poster/contracts.compliance_for(category)` is now the ONE
source (medical → no patients/before-after/procedures/guaranteed-results; skincare/beauty → no
before-after/clinical-claims/skin-disease; finance/legal → no guaranteed returns; else empty). Wired into
`build_llm_concept_prompt` (the LLM image path that had NO compliance) and the reel `_system_prompt` (also
none) — additive + empty for non-medical, so the 50+ reel assertions + all image tests stay green. It also
feeds the future Meta Policy Linter (one compliance truth). **(2) `IMAGE_NEGATIVE_CONTRACT` +
`IMAGE_NEGATIVE_TERMS`** — the shared text-free/artefact-free image negative, promoted verbatim from
art_director's per-call `negative_prompt` (zero-change consolidation). **(3) Batch 5 calendar** — explicit
trend-weighting in the content-calendar prompt (trends shape timing/angle of GROUNDED content, never invent;
most stays evergreen). +4 tests. **Batch 4 keystone — reel persona stripped (2026-07-07):** the owner's "strongest single anti-convergence
move". The reel `_system_prompt` opened with "SENIOR CREATIVE DIRECTOR with 15 years in performance-
marketing and TikTok/Reels" — the most homogenizing primer in the catalog (it made a heritage jeweller and
a discount grocer sound identical). Replaced with `CRAFT_CONTRACT` + a brand-DERIVED register ("a luxury
house is unhurried; a youth brand is fast; a clinic is calm — do NOT default every brand to high-energy
TikTok pacing"). The ad-SPINE (HOOK→WHAT-IT-IS→BENEFIT→PROOF→CTA), the SUBJECT+STYLE+CAMERA+LIGHTING+MOTION
agency formula, BANNED WORDS, FRAMING, and the "OBSESSED with realism" emphasis are ALL kept verbatim.
+de-primed "must feel premium"→"polished". 1 test updated (persona→craft-bar+register).

**DEFERRED (next unit, need config-map decision + heavy test rework):** collapse
`build_art_direction` 5 vertical prompts → ~3 scene shapes on the Batch-1 category→shape map (reusable —
`_shape_for` is importable); restructure reel `_MOTION_GUIDANCE` 4 keys → motion shapes + re-key
`_DELIVERY_EG`; promote `_MOTION_TAIL` → `MOTION_CONTRACT`; strip "award-winning" primers in
`build_design_spec`/`build_llm_concept_prompt`; the `build_creative_prompt` surreal-default alignment.
**Measure-first tickets (blocked by Gemini billing 403):** oneshot negative→positive reframe (B2), scene-QA
compliance criterion (B4), `bake_text` reachability (B3), cross-lingual RAG recall (B1).

**Batch 2 prompt refactor — poster concept/copy/fidelity chain (2026-07-07):** owner's expert 5-lens
critique of the 11 poster prompts. Two systemic weaknesses: copy-side aesthetic PRIMING that made every
brand's copy converge on the same imagined award-show ad (finding 3), and judge-side Arabic blindness
(the QA gate only checked "no Latin", never whether the Arabic was well-formed). Fixes: **(1) two shared
contracts** in new `poster/contracts.py` (the Batch-1 pattern applied to poster): `CRAFT_CONTRACT` — a
BAR not a brag ("would this brand actually ship it"), earn attention through the ONE specific real thing,
bans the empty primers (premium/world-class/award-winning/cutting-edge/…), states the philosophy "facts
gated, form free"; `VERBATIM_RENDER_CONTRACT` — the frozen-strings rule shared by the one-shot renderer
AND the OCR read-back reader so both speak one language (Arabic dot-counts ت=2/ث=3, ة vs ه). **(2) concept
de-primed** — stripped "senior advertising CREATIVE DIRECTOR", injected `CRAFT_CONTRACT`, kept the
excellent STRANGER TEST verbatim as the positive engine, added an anti-convergence line ("two businesses
must never produce interchangeable concepts") + a jargon→customer-language instruction; the regenerate
loop now re-asserts the Stranger Test so a fix doesn't break the glance. **(3) oneshot** — de-primed +
injected `VERBATIM_RENDER_CONTRACT` (the full negative→positive restructure is TICKETED measure-first:
confirm OCR pass-rate on the paid benchmark before locking — blocked now by the Gemini billing 403).
**(4) vision-QA Arabic gate** — new `script_wellformed` criterion: for non-Latin copy the rendered text
must be correctly SHAPED/CONNECTED with correct dots, not merely "no Latin"; a no-Latin-but-garbled-Arabic
poster now FAILS (code-side hard gate, re-ANDed like logo_ok). This composes with the existing OCR
character-fidelity gate (pipeline.py:512, catches wrong CHARACTERS) — together they cover both failure
modes (wrong chars + visual malformation). KEPT untouched (owner: exemplary): `_grounding_problems`, the
Arabic OCR dot-counting user prompt, `copy_style_cue`, the variation cues. +6 tests.

**All text/reasoning migrated OFF Anthropic → Gemini 2.5 Pro (2026-07-07):** owner directive —
"the whole project uses Gemini 2.5 Pro" + "no Claude, don't write the word in any file". Three code
paths still called the Anthropic SDK directly (and the ANTHROPIC_API_KEY was set, so they ran):
`business_profile/domain_schema.py` (domain-adaptive schema), `competitor/themes.py` (review themes),
`reel/creative_director.py` (the reel director — WITH images). All three now route through the shared
`default_caller(strong=True)` = `GeminiCaller(gemini-2.5-pro)` with a Pydantic response_schema
(structured output, no manual JSON strip): new `_RawDomainResponse`, `_ThemesResponse`, `_ReelResponse`
models; the reel's real photos go to Gemini as `images=[(bytes,mime)]` (it's natively multimodal) via
the renamed `_image_parts`. Every grounding/validation stayed byte-for-byte (the `_is_grounded` field
filter, the review-citation support floor, the scene clamping) — the moat is CODE, not the model.
Honest-degrade preserved: no Gemini caller (creds/SDK) → None/[]. `AnthropicThemeExtractor` renamed to
`ReviewThemeExtractor` (callers + exports updated, no alias). `anthropic==0.106.0` dropped from
requirements. Result: **zero `anthropic`/`claude` anywhere in code** (only the required nothing — the
API is Gemini now). Also fixed a real bug the migration exposed: `grounding/measure_reel.py` gated the
creative path on `ANTHROPIC_API_KEY` → now checks Gemini creds. +13 tests (each path: injected-caller
happy path + honest-degrade + grounding-drops-fabrication). ⚠️ Gemini billing on the GCP project was
DENIED (403 dunning) when measured — these paths (and all other Gemini calls) only run once billing is
restored; until then the reel director that used to run on Opus returns None (expected, per the
all-Gemini directive). **Model stack now:** text/reasoning = Gemini 2.5 Pro/Flash; poster image =
gemini-3-pro-image-preview (oneshot, for exact-text fidelity) + Imagen 4 Ultra (classic); reel video =
Veo 3.1 (highest Veo 3). See the Model map below.

**Discovery routing — REACH businesses compete by category, not proximity (2026-07-07):** owner's ITI
follow-up ("who should a specialized institute's competitors be? IT institutes / bootcamps / online
platforms?"). Root cause: `business_type.classify_business_type` had `education` in `_LOCAL_CATEGORIES`,
so ITI → LOCAL → Places-proximity ONLY, which returns broad-category NEIGHBOURS (universities, the
faculty of education, the brand's own branch) — proximity is the WRONG relevance model for a business
that competes by category across a city/country/online. Fix: new `BusinessType.REACH` +
`_REACH_CATEGORIES = {education, professional_services, services_b2b, agency}`; education removed from
`_LOCAL_CATEGORIES`. A reach business with NO local footprint → REACH (web-discovery only); WITH a
campus address → HYBRID (Places local peers + web category peers), never pure proximity-LOCAL. The
router routes REACH → the SERP web engine, whose LLM relevance judge finds true category peers and drops
universities/directories (`topuniversities.com` etc. already block-listed). The production path
(`full_run.py`, `api/routes/swot.py`) already wires `default_web_engine()`, and `SERPER_API_KEY` is set,
so this is LIVE — ITI now routes to category web-discovery instead of Places noise. Universal (no
IT-institute hack): the signal is "competes by reach/category", not the specific vertical. +5 tests.
Pairs with the earlier cross-script self-match fix (ITI was listing its own branch as a peer).

**Batch 1 prompt refactor — one GROUNDING_CONTRACT + catalog shapes (2026-07-07):** owner ran an
expert 5-lens critique of the 10 business_profile prompts and asked to "fix these first prompts." The
root problem was DUPLICATION, not bad instructions: nine prompts each re-stated the grounding rules,
and the copies had drifted (one call stricter than another). Mapped exhaustively first (a 5-agent
workflow: exact source + the ONLY consumer `extractor.py` + every test-asserted substring + the
category→guidance mechanism), then adversarially reviewed the diff before committing. Changes:
**(1) `GROUNDING_CONTRACT`** — the canonical block (5 non-negotiable rules + a positive coverage line +
the lifted anti-cliché "specificity is the filter" rule), stated ONCE and injected into the shared
`SYSTEM_PROMPT`; the 4 group USER prompts inherit it instead of re-litigating (SYSTEM_PROMPT is sent as
the system role for all groups). **(2) identity** — tagline is COPY-verbatim, description is
COMPOSE-but-every-claim-cites-a-block_id (the implicit mode-switch made explicit); category enum
hardened ("'other' only when nothing fits, never a shortcut for 'unsure'" — it routes downstream
specialization). **(3) offerings** — dropped the prose FORBIDDEN-CLAIMS block (redundant with contract
rule 3 + the `UNSUBSTANTIATED_CLAIM_TOKENS` validator); kept the own-name ban + honest-empty + the
1-2-broad-category cap. **(4) `_OFFERINGS_GUIDANCE` (18 vertical keys) → `_CATALOG_SHAPES` (4 universal
shapes: broad_catalog / named_menu / programs / default) + `_CATEGORY_TO_SHAPE` map** — the central
fix: config keyed by a universal signal with a universal default (rule 5), so `_shape_for(None/unknown)
→ default` BY CONSTRUCTION and the documented fail-open None-key bug is impossible; every hard-won
specific (DEPARTMENTS-FIRST, SKU≠offering, breadth, named-menu discipline) preserved inside the shapes.
**(5) trust** — deleted "Skip vague self-praise" (the contract's specificity rule covers it).
**(6) same-subject judge** — its 400-char truncation is now WINDOWED on the shared token (a head-slice
clipped the proving sentence on long blocks); `_window` coerces inputs so it can't break the judge's
never-raise→None guarantee; `_SYSTEM` (measurement-locked 98%) untouched, short claims byte-identical.
**(7) domain_schema** — attributes must be marketer-ACTIONABLE (targeting axis / message angle / proof
point), not trivia. NOT touched (measure-first): `_GROUP_QUERIES` cross-lingual recall (ticketed).
+7 tests; docs/PROMPTS.md updated (§1: `_CATALOG_SHAPES`, GROUNDING_CONTRACT).

**Poster primary color must DOMINATE + never self-list a competitor (2026-07-07):** two more
"continue on the best solutions" fixes. **(1) on-brand color dominance** (owner: the ITI poster read
navy when the brand is red — "the brand color should DOMINATE, not just the CTA"): the palette DATA was
already fixed (logo-SVG extraction leads with ITI's red `#9c3c3c`; navy is 5th and never reaches the
top-4 `_palette_names`), but the one-shot COLOR SYSTEM mandate let the model satisfy "make it present"
with only the CTA button (the old "or a dominant color field" was optional). Strengthened: the first
palette color is the PRIMARY and must occupy a LARGE color field (background zone / major panel / hero
graphic area) so the poster reads as this brand at a glance; neutrals may support but never out-weigh
it, and the model may not drift to a generic default navy. Universal; the render is still measured by
the paid benchmark. +1 test. **(2) no self-competitor across scripts** (owner: irrelevant "competitors"
for ITI — the saved run in fact listed ITI as its OWN peer): the Places result «معهد تكنولوجيا
المعلومات - ITI» (an Alexandria branch, no website) beat both `_is_self` checks — the profile carried
its URL only in `source_url` (so the domain check never ran) and the exact-name check compared English
"Information Technology Institute" to the Arabic listing. `_is_self` now also reads `source_url` and
adds a cross-script brand-label check: the subject's registrable-domain label ("iti" from iti.gov.eg,
PSL-correct) matched as a distinct token in the candidate name catches a different-script branch of the
same brand; guarded by a generic-label stoplist + ≥3-char rule so it never drops a real peer sharing a
common word. +4 tests.

**Reel pre-render plan-eval + poster service-prop gate + PROMPTS.md catalog (2026-07-07):** three
landed under the owner's "continue on the best solutions" authority. **(1) evaluate the reel BEFORE it
comes out** (owner's explicit ask): new `reel/plan_eval.evaluate_reel_plan(reel, profile, featured)`
scores a plan against the stranger test + caption craft (names the brand −30 / names an
offering-or-category −20 / CTA on the last scene −15 / caption-driven −15 / captions ≤6 words −10 /
scene variety for non-featured −10) and returns `ReelPlanVerdict(ok, score, issues)`. Deterministic —
no LLM/network — so it's a cheap pre-flight: `render_creative_reel` runs it after the Opus design, and
regenerates the plan ONCE (a cheap call) when it fails, keeping the higher-scoring plan, all BEFORE the
10-15 min Veo render (the compositor's per-clip scene_qa still runs after). +3 tests. **(2) poster
service-prop gate** (fixes ITI clutter/framed-face): a whole-brand poster for a SERVICE brand
(education/clinic/agency/government/…) was compositing its scraped content images as one-shot "product
props", but those are BUILDINGS and PEOPLE → clutter + a hallucinated framed face. `_gather_product_props`
now attaches NO whole-brand props for `_SERVICE_NO_PROP_CATS`; product/food brands (and any unknown
category) keep the prop path; a user-PICKED product always attaches regardless of category. +1 test.
**(3) `docs/PROMPTS.md`** (owner's explicit ask, "a file with all the project's prompts"): the single
catalog of all 53 LLM/image/vision prompts across the 5 subsystems, each indexed by file:line
(clickable), receiving model, kind, purpose, and a representative excerpt, opening with the
two-truth-domains map (LLM designs, code renders + validates).

**Reel captions DESIGNED + paced + voice not flat (2026-07-07):** owner: "the reel text is written with
no design, too fast, boring, unlistenable — study how big brands do it." A 3-agent workflow (research
top-brand short-form craft + audit our rendering + synthesize a spec) found the root cause: the CREATIVE
reel put every caption into `sublines` with `kind="gallery"`, so they rendered with the plainest
template rule (`.item`: Inter 600, ~50px, flat white, one soft fade) — the rich designed lockup /
accent-CTA-chip / logo only fired for intro/outro. Fixes: **(1) designed captions** —
`build_creative_storyboard` routes scene 0's caption → `headline` (kind=intro → hero lockup + logo), the
last → `cta_text` (kind=outro → accent CTA chip + logo), middle captions → `headline` (the big display
`.headline`, not the tiny flat `.item`); `.headline` gains readability ARMOR (`-webkit-text-stroke:2px`
+ `paint-order:stroke fill`). **(2) readable pacing** — a captioned scene holds `max(3, words*0.4+1.5)`s
(was ~2s → the "too fast" flash). **(3) caption-driven** — the director prompt wants a SHORT 2-4 word
caption on MOST scenes (benefit/proof too), with the reading-speed duration + split-if-over-7-words rule.
**(4) voice not flat** — the free edge-tts path derives rate/pitch from tone (playful +9%/+4Hz, default
+4%/+2Hz, luxury -4%) instead of a flat +0%/+0Hz monotone. +6 tests. Deferred (needs timing infra):
word-synced karaoke active-word highlighting. Grounded in research (OpusClip/Blitzcut caption specs,
3-7 words @ 2-3s, 12-17 CPS, white+black-stroke, 1s hook).

**Reel director — say what the brand DOES, vary the scene, pace the text (2026-07-07):** owner's reel
feedback (same STRANGER-TEST point as the poster): (1) "in every reel I need to understand what the
brand does; if it's a service, name the service" — the prompt was entirely product-centric ("the
product", "Shop the mist"), useless for a service brand (ITI). Fixed: WHAT-IT-IS beat is now the
STRANGER TEST (voiceover must convey WHO + WHAT IT DOES/category + the SPECIFIC named product OR
service); BENEFIT generalised to "a PRODUCT mid-use OR a SERVICE delivered in its real setting (a
learner coding in the lab, a graduate hired)"; HARD RULE + SELF-CHECK now demand product-OR-service.
(2) "the background must NOT stay behind me the whole reel" — new SCENE VARIETY rule: every scene is a
DIFFERENT setting/angle/moment; never one backdrop held the whole reel; even with one photo, change
framing/distance/action each scene (no frozen wallpaper). (3) "the text goes by too fast, and no
feeling (but not over-the-top)" — captions ≤4-5 words and must stay on screen LONG ENOUGH TO READ (a
captioned scene needs ≥3s); voiceover delivery is REAL/warm but MEASURED (never flat/robotic, never
melodramatic/over-acted). +1 test; existing 17 preserved. Pairs with the poster stranger-test prompt —
both assets now anchored in the concrete offering, not a vibe.

**SPA logo capture — the "poster with no logo" bug (ITI, 2026-07-07):** owner: the ITI poster shipped
with NO logo. Root cause found in `visual.py`: ITI's real mark IS captured (`<img
src=.../ColoredLogo.svg class="header__image">`, scored 42) but the custom Angular header
(`<app-header>`, not a `<header>`) never fired the +30 in-header bonus, so it landed as a sub-threshold
`unknown_candidate` and `logo_url` came out NONE. Fix: a **NAMED-LOGO rescue** in
`_choose_primary_logo` — a last resort (only when every other path found nothing) that promotes an
**SVG** whose filename is a **PURE brand-mark** (`ColoredLogo`/`WhiteLogo`/`logo`/`brand-logo`, via
`_is_pure_logo_filename`), excluding partner/authority/sponsor/favicon marks, preferring the coloured
variant over the white/footer inverse. Restricted to SVG + pure-name so it can NOT reopen the
floor-rescue's deliberate refusals (all of which are PNG/data-uri third-party walls / low-repetition
tiles). VERIFIED LIVE: ITI now `Logo found: True`, `primary_logo=ColoredLogo.svg` (was None). +2 tests.
Combined with the SPA XHR-capture + the poster stranger-test prompt, a re-generated ITI poster now has
a real logo + 12 grounded programs to anchor on.

**API-driven SPA scraping — recover content from same-site JSON (ITI, 2026-07-07):** owner (via the new
Scraper-QA panel) caught ITI (iti.gov.eg) finishing in 53s with only 4 pages + 0 offerings. DIAGNOSED
live: ITI is a full **Angular SPA** — its homepage exposes only 4 static `<a href>` links, and ALL real
content (the programme catalogue, contacts, partners) loads at runtime from **same-site JSON APIs**
(`pgateway.iti.gov.eg/OldApi/ProgramCategory/…`, navigated by the Angular router with NO href). A
link-following crawler sees a news-heavy shell → 0 offerings. Fix (universal): new
`scraper/xhr_capture.py::extract_json_text` flattens captured JSON bodies to their human-readable
strings (names/titles/descriptions; drops guids/urls/filenames/dates/hashes). `fetcher._fetch_page_once`
attaches a `page.on("response")` listener that captures **same-registrable-domain** JSON during the
render (`same_registrable_host`, so `pgateway.iti.gov.eg` ≡ `iti.gov.eg`; bounded 30×400KB), stores it
on `FetchResult.api_text` (+ appends to rendered_text). `crawler._process_fetched_page` turns
`api_text` into **CITABLE `tag="api"` text_blocks** (real block_ids, Section.MAIN) so offerings/contacts/
partners extracted from it survive the evidence validator. VERIFIED LIVE end-to-end: ITI homepage
text-blocks 370→684 (82 API blocks: Post Graduates / Under Graduates / Tech-Business / Vodafone / Fawry /
Work Phone …), and a full profile build now extracts **12 offerings (was 0)**. Non-SPA sites are
unchanged (no same-site JSON → empty capture). +5 tests.

**URL-less 'modal' details (NTI) — resolve the URLs JS builds from a data-attribute (2026-07-06, slice
1):** owner: NTI's course catalogue shows each course as a card; clicking opens a modal with the real
details (Overview/Prerequisites/Hours) but the modal has NO URL, so the crawler (which follows hrefs)
can't reach it ("شال الزايدات واسكراب nti نفسها"). DIAGNOSED live: `text_blocks.py` skips
`display:none` content, AND — the real cause — NTI's `js/popupCourse.js` does
`$('#popover-cont').load("pages/modules/" + link.getAttribute('data-target') + ".html")`, so each
course's detail page lives at `pages/modules/<data-target>.html` — a URL ASSEMBLED IN JS that never
appears in the HTML. New `scraper/ajax_details.py::extract_ajax_detail_urls(html, base_url, js_texts)`:
learns the `.load(PREFIX + el.attr + SUFFIX)` template from the page's JS (getAttribute / .attr / .data
/ dataset.x variants; drops the cache-buster query; skips `data-target="0"` sentinels) and applies it to
every trigger element → real absolute detail URLs. VALIDATED live on NTI: resolved all 6 course module
URLs (pages/modules/2631.html …) from the actual rendered page. Universal for the very common jQuery
`.load()` reveal pattern. +4 tests. **Slice 2 (DONE): wired into the crawler.**
`ajax_details.discover_ajax_details(html, base_url, fetch=…)` gathers a page's inline + SAME-ORIGIN
external JS (skips CDN jQuery; caches the shared script body per crawl) and resolves the detail URLs.
`crawler.py` calls it on the homepage AND every fetched sub-page (`_add_ajax_details`), SPLICING the
resolved URLs into the frontier right after the current page (so they're fetched next, not lost in the
tail) and bumping `page_cap` by the count added so they get their OWN slots (bounded by `_AJAX_MAX=40`;
time budget still applies; light/competitor mode skips). VERIFIED LIVE end-to-end: scraping NTI's
`coursesev.php?catID=205` now fetches all 6 `pages/modules/<id>.html` course pages with full content
(Module Name/Duration/Prerequisites/Hours/Description) — previously 0. +2 tests (discover gathers
same-origin external + inline JS). So a url-less-modal catalogue (the exact NTI case) is now fully
scraped, and each course flows into the profile/products like any page.

**Scrape a product by its URL — for an item the crawl never reached (2026-07-06, slice 1):** owner:
"لو اليوزر عايز يعمل [إعلان/بوستر] لمنتج مش موجود في الاسكرابر، يدّي لينك المنتج وأروح أسكرابه — صورته
وبياناته." The full crawler deliberately re-anchors a deep URL to the brand homepage
(`url_utils.site_root_if_deep`, so one deep page can't hijack the brand profile) — the OPPOSITE of this
need. New `scraper/product_page.py`: `parse_product(html, url)` (pure, hermetic) pulls ONE product's
name / image / price / description — JSON-LD schema.org `Product` FIRST (parsed directly, since
`extract_structured_data` intentionally skips JSON-LD; walks `@graph`), then og:/meta/`<h1>` fallback,
relative image URLs resolved. `scrape_product_page(url)` fetches the page via Playwright then parses.
VALIDATED on a real rawafrican page (extracted name+image live). +5 tests. **Slice 2 (DONE): wired into
the studio** — the product picker now has a "paste a product link not in the list" input; JS `addByUrl()`
→ `GET /product_by_url?url=` → `_serve_product_by_url` (public-URL guarded via `is_safe_public_url`) →
`scrape_product_page` → returns {name,image,price} → a new picker chip is added AND auto-selected, so it
flows straight into the reel/poster via the existing `pname/pimg` path. +4 tests (route ok/reject-non-
public/no-product + the studio UI). So a product the crawl never reached is one paste away from an ad.

**Reel SCENE QA gate — reject Veo hallucinations, don't just prompt against them (2026-07-06):**
owner watched a real render and caught three failures the prompt CANNOT stop (Veo i2v drifts from the
seed over a few seconds): the product is not faithful to the real photo, it 'magically' VANISHES
mid-scene, and it presses a SEALED pump ("هو سحر؟"). The system prompt asks Veo not to; it does anyway.
Honest fix = inspect the actual clip, not trust the prompt. New `reel/scene_qa.py::check_scene`:
extracts 3 frames (start/mid/end) from the generated clip, hands them + the REAL product photo (as the
reference) + the product name to a vision caller, and returns a structured verdict
(product_faithful / product_persists / action_plausible / overall_pass). Wired into
`compositor.render_reel(qa_caller=…, qa_product_hint=…, qa_reference_image=…)`: a clip that fails QA is
regenerated ONCE, then falls back to the FAITHFUL real-photo KenBurns — so a hallucination NEVER ships
(worst case = the true product with simple motion, not a vanished/redrawn one). `render_creative_reel`
turns the gate on for a FEATURED product (builds a Gemini caller, fetches the seed bytes via
`_load_reference_image`). QA is OFF (identical old behaviour, all prior tests green) when qa_caller is
None. This complements the creative-director playbook (prompt-level realism) with an OUTPUT-level gate —
the prompt reduces bad scenes, the gate removes the ones that slip through. +8 hermetic tests (verdict
logic + compositor reject→regen→faithful-fallback + pass-keeps + qa-off back-compat). Live proof render
pending owner go. NOTE the deferred `--product-image`/reel already seeds every scene from the real
photo; the remaining drift is a Veo-model limit the gate now catches.

**Picked product now drives the POSTER's IMAGE too, not just its name (2026-07-06):** owner: "عملت حوار
الراج وظبطت أنا أختار المنتج اللي عايزة أعمله الإعلان أو البوستر" — the studio RAG product-picker feeds
BOTH the ad (reel) and the poster. AUDIT of the poster path found a gap: `poster/__main__.py`'s
`--product-image` was declared but "reserved" — never wired — so picking a product set it as the hero
OFFERING (name → concept) but the poster's IMAGE-conditioning still composited whatever the first two
`content_images` were, NOT the picked product's real photo (the reel used the real image; the poster
didn't). Fixed by threading `product_image` through `generate_poster → _try_oneshot →
_gather_product_props`, where the picked photo is now the PRIMARY composited prop — kept even if the
quality gate would drop it (the user chose it), second slot filled from the gated rest, its real label
OCR'd into the fidelity allow-list. The studio poster uses `--engine oneshot` (dashboard/run.py), which
is exactly the composited-prop path, so the picker now makes the poster SHOW the exact chosen product
with its correct label (parallel to the reel's featured seed). +1 test. (Classic engine, CLI-only,
still conditions on content_images generically — a measured follow-up if ever needed.)

**Reel creative-director upgraded to the agency PERFORMANCE-AD playbook (2026-07-06):** owner supplied a
detailed Senior-Creative-Director brief (Hook→Body→CTA spine; the SUBJECT+STYLE+CAMERA+LIGHTING+MOTION
prompt formula; explicit camera/lighting terms; a banned-words list "slow zoom"/"refined"/"dreamy"; a
physics Logic-Check). `reel/creative_director.py::_system_prompt` now encodes all of it: a 15-yr
performance-marketer persona obsessed with realism; a HOOK that opens on a proven hook TYPE (the mistake
/ 3 reasons / before-after / provocative question) with a reacting FACE + a DELIBERATE macro detail; a
BENEFIT shown mid-use (never at-rest on a shelf/in a bag); a PROOF beat that uses real social proof only
if grounded (never fabricated); a CTA whose on-screen caption and voiceover say the SAME written action
line; the per-`veo_prompt` formula with explicit CAMERA (macro/tracking/hand-held/dolly-in) + LIGHTING
(soft natural/diffused/high-contrast); a BANNED-WORDS list; and a SELF/LOGIC-CHECK for impossible
physics. The draft was then ADVERSARIALLY AUDITED by a 3-critic + synthesis workflow (coverage /
contradiction / craft) against the owner's spec → 10 findings, all applied: chief among them the
close-up-vs-"nothing cropped" contradiction (now: intentional macro on the hook, product WHOLE on the
establishing/CTA scenes), the at-rest-context collision, the "CTA verbatim from brand" vs "invent no
facts" bind (CTA is written COPY, only its claims are grounded), and product-identity-stays-while-pose-
changes. TWO findings ("Shop Now button", "render the logo") were applied Veo-SAFELY — on-screen text
and the brand logo are composited in POST (caption overlay + auto end-card), so the footage renders
NEITHER (Veo would garble fake UI/wordmarks). A re-verify pass confirmed all 10 resolved + caught one
residual (non-featured image_index still said "a DIFFERENT photo per scene" → reworded to "a different
SHOT/angle of the ONE hero"). +5 tests. Fully live on the FEATURED single-product reel (see below); a
final proof render on the upgraded director is pending owner go.

**Single-product REEL — one item, realistic, framed-for-9:16 (2026-07-06):** owner: "أنا هعملّ ريل
على منتج بعينه مش ميت منتج ... يكون منطقي مش يضغط والغطا مقفول ... الصورة كأنها مقصوصة ... صمم الفريم
في الأصل على ريل". Three faults fixed together in the creative path (studio picks the product; §5.G):
**(1) ONE product, not a montage** — `reel/__main__.py` `--product-image` is now EXCLUSIVE (`selected =
[img]`, was "picked + 2 supporting"), and `featured_product` threads picked-name → `render_creative_reel`
→ `design_creative_reel` → `_system_prompt(featured=…)`, so EVERY scene is the SAME product (real photo
index 0), varied only by SHOT/ACTION (macro → in-hand → in-use → result), never a different item.
**(2) REALISM** — `_MOTION_TAIL` now forbids impossible actions: "if the product has a cap/lid/pump/
dropper, the person REMOVES or FLIPS it BEFORE dispensing … NEVER pressing a sealed pump / pouring from
a closed bottle" (owner: "مش يضغط والغطا مقفول"). **(3) FRAMING** — a FRAMING block makes the director
compose vertical-first for the 1080x1920 frame ("product FULLY visible … NEVER a wide/landscape shot
that gets cropped … NOTHING is cut off"), and when a product is featured the seed defaults to
`REEL_SEED_FILL=pad` — CONTAIN the whole photo over its OWN background colour (`_edge_bg_color` samples
the four border strips), so a studio product shot pads SEAMLESSLY (no crop AND no band). VERIFIED live
(Hair Growth, Veo 3.1): 1080x1920, 21s + branded end-card, all 5 scenes the SAME product, a real model
spraying the mist onto glossy hair (physically-logical use, not a static zoom), ad-arc HOOK→use→result→
CTA "Get The Raw Experience". First pass used the earlier `blur` seed and left a faint band on the two
seed-hugging scenes → switched the default to the seamless `pad` seed (`_to_vertical_seed` gained a
'pad' mode; +3 seed tests). Re-render on `pad` pending owner go.

**Crawl reaches INDIVIDUAL products, not just categories (2026-07-06):** owner: azza/rawafrican came
out with category-level offerings only (RINGS/EARRINGS; Face/Hair Care). A multi-agent analysis found
the crawl discovers 200+ pages but fetches ~12-30, AND (worse) `/collections/rings` and
`/products/<slug>` classify IDENTICALLY (PageType.PRODUCTS), so the stable frontier sort let
collections (discovered first) fill every slot while individual product pages sat in the discarded
tail. Slice 3: `page_type.is_product_detail(url)` distinguishes a PDP (`/products|/product|/pdp/<slug>`)
from a list — a pure boolean, no PageType enum change (zero ripple). Slice 4:
`crawler._reserve_product_quota` gives ~65% of the frontier to individual products, DIVERSIFIED across
parent collections (`_diversify_by_parent` round-robin), interleaved with the top landing/collection
pages — so the SAME page budget now captures a spread of real products (name/image/price) that the
product picker + reel need, item-by-item. Non-store frontiers are unchanged. +3 tests. **Slice 5
(DONE): store cap 30 -> 50 + budget 330 -> 560s** (config.py) + `MAX_SITEMAP_URLS` 200 -> 300 — the
crawl goes DEEPER, and because the frontier reserves the budget for product-DETAIL pages, the extra
slots buy ~50 real PRODUCTS not more collections (store scrape ~8-9 min). Remaining follow-ups: Slice 1
cut per-page overhead on light sub-pages (the ~11s/page floor is hard-coded homepage-footer waits, not
page weight) to bring the time back down; Slice 2 a per-page wall-clock timeout for safety.

**Reel/poster coherence — content_images are now PRODUCTS, not shop-fronts (2026-07-06, root cause):**
the engineer: "I can't tell what the reel advertises." A multi-agent analysis found the true cause in
ONE line — `business_profile/rules/from_visual.py::_content_images` sorted role=content images by file
extension (`.jpg/.webp` first, `.png` last), so a brand whose STORE-LOCATION photos are webp/jpg (Mall
of Arabia, City Stars, pharmacy) and whose real PRODUCT mockups are `.png` got content_images = 8-9
shop-front photos. The reel animated kiosks while the grounded voice-over sold beauty products =
incoherent. Fixed by `_content_rank`: demote location/stockist/banner tokens (mall/pharmacy/branch/
kiosk/banner/…), promote real products (from `/products|/collections` URLs or a product alt), stable
sort. MEASURED: rawafrican content_images flipped from 8-9 store photos → all 12 real products (Floral
Blast Hair Mist, Follicle Booster Oil, Face Cleanser…). One-file fix, benefits reel default + `--real`
+ poster. +3 tests. (Reel-coherence slices since DONE: the picked product NAME+details now thread into
the creative director as a single-product ad-arc system prompt — see the single-product REEL entry at
the top. Remaining: an identifying caption + the product on the end-card.)

**Studio product-picker (2026-07-06, engineer suggestion #1):** the studio now lets the user CHOOSE
which product to advertise, grounded in the RAW scrape. `dashboard/products.py::products_for_slug`
extracts pickable products from the freshest manifest (names from real `/collections|/products/<slug>`
pages, images from role-tagged images_of_interest; banners/logos excluded) — NOT the profile's
`content_images` (which for rawafrican were store-location photos). `GET /products?slug=` feeds a
thumbnail picker in the Creative Studio; the chosen product flows `pname/pimg` → `_stream_generate`
→ `generate_poster/reel(product_name, product_image)` → `--product-name`/`--product-image` on both
CLIs: the poster makes it the HERO offering, the reel uses its real image as the footage. Whole-brand
stays the default. Also FIXED: `append_endcard_to_reel` (branded logo end-card) was defined but NEVER
called by either reel path — every reel shipped with no logo; now wired in (owner: "الريل مفيهوش
لوجو"). MEASURED: rawafrican → 6 real products (Hair Growth, Face/Lip/Nail Care, …); reel end-card
verified (real logo on brand green). Live product-featured OUTPUT verification pending (paid run).

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
  `SERPER_API_KEY` (SERP; free tier is flaky under bursts),
  `OPENAI_API_KEY` (legacy fallback only). `.env` is gitignored.
- **Model map (deliberate, measured; owner directive 2026-07-07 — ALL text/reasoning on Gemini,
  NO Anthropic):** extraction = Gemini 2.5 **Flash** (evidence-bounded — Pro adds cost, not
  quality); concept/design/research/story + **reel director + domain-schema + review-themes** =
  Gemini 2.5 **Pro** (`default_caller(strong=True)` — the last three migrated OFF Anthropic/Opus
  this day, see log); one-shot poster image =
  `ONESHOT_IMAGE_MODEL=gemini-3-pro-image-preview` (measured quality ceiling;
  3.1-flash passes but follows palette/layout mandates worse); judges/OCR/planner =
  Flash; reel video = **Veo 3.1** (`veo-3.1-generate-001`, Vertex; renders NATIVE
  speech, highest Veo 3); classic poster image = **Imagen 4 Ultra**
  (`imagen-4.0-ultra-generate-001`); image edit/upscale = imagen-3.0-capability-001 /
  imagen-3.0-generate-002 (no Imagen-4 edit variant confirmed yet).
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
- **Tolerates invalid TLS certs (2026-07-06)**: `make_browser_context` sets
  `ignore_https_errors=True`. A real brand site with an expired/misconfigured cert
  (`net::ERR_CERT_AUTHORITY_INVALID`, MEASURED: marasimltd.com) made Chromium refuse it → the whole
  scrape returned 0 pages in ~23s ("finished in 23 seconds and produced nothing"). We only READ
  public marketing content (no credentials submitted), so a cert-authority error must not block the
  crawl. (Common on MENA small-business sites.) +1 test. NOTE: a site returning HTTP 403 (active
  bot-block / IP rate-limit after repeated runs) is a SEPARATE, transient condition — not fixed by
  this and not evaded (out of bounds); the realistic Chrome-131 UA is already set.
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
- **Brand-level Strengths (2026-07-06, SWOT-quality Slice 1)**: owner called the SWOT "stupid —
  all page attributes, not brand-level" (Strengths read "Number of CTAs: 3", "Social links: 20"
  for a heritage jewelry house). The rich profile was thrown away — `value_propositions` /
  `domain_schema` appeared ZERO times in swot.py/matrix.py; only offering/trust COUNTS leaked in.
  Now `competitor/brand_signals.py::strengths_from_profile(profile, ledger)` mines the grounded
  profile — distinctive `value_propositions` + proof-carrying `trust_signals` (generic checkout
  boilerplate filtered) — into Strengths, each **Ledger-gated** (same `all(v.sourced for v in
  ledger.audit_text(text))` gate as TOWS/strategy; fail-closed) and cited to its profile field,
  `internally_supported`. `synthesize_swot(..., profile=None)` gains the param and **prepends**
  them so the SWOT LEADS with brand strategy; the mechanical gaps stay as a secondary signal.
  `profile=None` is byte-identical (regression-safe); added after the standalone check so it can't
  suppress the 0-peer fallback. MEASURED: Azza Fahmy Strengths 4 page-attribute → 9 (5 brand-level
  first: heritage, 18kt gold, craftsmanship, service, shipping); Raw African +7 (incl. "Loved by
  17k+ Customers", "Cruelty-Free"). Universal (jewelry + skincare, no vertical hacks). Wired at
  full_run.py + api/routes/swot.py. +4 hermetic tests.
- **Strategist phrasing (2026-07-06, SWOT-quality Slice 2)**: the mechanical own-site lines still
  read as a raw attribute dump ("Number of CTAs: 3", "Online booking: not detected on site").
  `brand_signals.phrase_dimension(dim_key,label,kind,value,positive)` re-phrases the SAME
  scrape-grounded cell into strategist language ("Clear conversion paths (3 calls-to-action)",
  "No WhatsApp contact channel", "Single-language site (missing Arabic/English)") — TEXT only,
  citation/evidence/claim_strength unchanged — in `_standalone_from_subject`. Keyed off dim.key
  with a clean label fallback (a new dimension never regresses to a dump). +2 tests (2 legacy
  standalone assertions updated).
- **Trend-driven Opportunities/Threats (2026-07-06, SWOT-quality Slice 3)**: the SWOT had no
  market-shift signal — an online brand with no Places peers and no reachable reviews got EMPTY
  O/T. `brand_signals.opportunities_threats_from_trends(profile, trends)` maps on-topic
  `TrendItem`s to Opportunities ("Rising interest in {terms}: {title}") or Threats (decline/
  regulation/ban keywords → "Category headwind on {terms}: {title}"), each citing the trend URL,
  `directional_not_validated`. GROUNDED: junk/aggregator hosts dropped via `is_reputable_web_source`
  then every line **Ledger-gated** (candidates indexed as web evidence, `from_profile(..., swot=)`).
  `synthesize_swot(..., trends=None)` gains the param and PREPENDS them (market signals lead);
  `None`/`[]` is byte-identical (regression-safe). Callers (`full_run.py`, `api/routes/swot.py`)
  fetch `top_trends(keywords_from_profile(profile), require_match=True, top_k=6)` best-effort
  (any failure → [], never blocks). MEASURED: Raw African O/T 0/0 → 2 opps + 1 threat from
  synthetic trends (regulation → threat; junk host + off-topic dropped). +3 hermetic tests.
- **Readiness-gap Weaknesses (2026-07-06, SWOT-quality Slice 4 — DONE, all 4 slices shipped)**:
  `brand_signals.weaknesses_from_readiness(profile, ledger)` adds brand-foundation Weaknesses from
  the grounded `readiness.swot_quality_signals`, but ONLY for a WHITELISTED signal explicitly False
  (tagline / value_propositions_3plus / trust_signals_2plus / offerings_3plus / pricing_posture_known
  / multi_page_evidence). `locations_with_geo` / `hours_known` are deliberately EXCLUDED — False for
  every online brand and not a weakness there (rule #4: never a weakness for something irrelevant).
  Phrased without numbers (pure paraphrase → passes the gate), cites the readiness audit,
  `internally_supported`, APPENDED after the concrete weaknesses (`_append_unique`). MEASURED:
  well-scraped Azza/Raw African add 0 (correct); a thin profile surfaces 3 real gaps (no tagline,
  thin value prop, single-page) and NOT hours/geo. +3 hermetic tests. **SWOT-quality program
  COMPLETE** — the SWOT now LEADS with brand-level strengths (S1), reads like a strategist (S2),
  has market-shift O/T (S3), and flags real foundation gaps (S4); the mechanical matrix is a
  cited secondary signal, all Ledger-gated. profile=None/trends=None stay byte-identical.
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
  report + poster/reel panels with Regenerate). The studio **auto-runs** whatever isn't generated
  yet on load (missing poster/reel → auto-start, streaming into its panel; existing assets stay put
  with Regenerate) so they don't sit idle after Analyze (owner: "شغّلهم"). **Light generating state
  (2026-07-06)**: the empty/generating asset stage was a big near-black box (owner: "طلع سواد" while
  the poster/reel were still generating) — now a light blush-tinted placeholder with the brand icon,
  a "Generating your poster/reel…" label + shimmer, switching to a dark frame only once a real asset
  is present; a failed generation shows a light "Couldn't generate — press Regenerate" state, never
  a black void.

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
