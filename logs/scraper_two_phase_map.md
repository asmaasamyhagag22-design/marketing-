# Scraper two-phase footprint fix — PARKED (frozen 2026-07-13, resumes after the reel front closes)

Status: **FROZEN mid-design** per owner sequencing ruling (reel front takes priority; do NOT run
both fronts in parallel). Nothing here is shipped. All findings below are from a pure code-reading
dependency map (workflow wf_cc3c2b3a-a92) — no external site hits.

## The goal (owner ruling D-429.3)
Cut homepage request footprint (~300 → target ~50-70 during the decision crawl) WITHOUT losing the
106 product images (the same data U1 fought for). Two-phase: PHASE A collects text/prices/
offerings + image URLs (cheap text); PHASE B downloads ONLY what's used (screenshot asset + the
poster/reel candidate images that pass the quality gate). `--thorough` preserves old full-image
behavior; two-phase is the new DEFAULT. Coverage regression >5% = revert.

## The regression the map CAUGHT pre-ship (why the mandate mattered)
Blocking ALL homepage image bytes regresses **logo detection**:
- `visual.py` reads `getBoundingClientRect` width/height for logo candidates (`visibleBox`, ~L293).
  An `<img>` whose bytes are aborted and which has NO explicit CSS/attribute size collapses to
  ~0×0 (or a tiny broken-image box) — it never reports its real logo dimensions.
- `_suitable_logo_shape` (visual.py ~L549) then returns False → the real logo LOSES the `+12`
  shape bonus and can fall below PRIMARY_LOGO_THRESHOLD (55) → `no_confident_primary_logo`.
- The structural-independent **floor rescue** `_floor_ok` (visual.py ~L726) HARD-REQUIRES
  `"suitable_logo_shape" in reasons` → blocking bytes DISABLES the exact recovery path built for
  opaque-DOM raster logos (elkbabgi: real logo scored 54 WITH the bonus → 42 without, unrecoverable).
- Survives fine: image URL collection (DOM attributes), text/products/links, logo COLOR
  (`_logo_pixel_signals`/`_logo_svg_signals` download the ONE chosen logo by URL, SSRF-guarded).
- Screenshot is consumed ONLY by the raw pixel palette (secondary evidence) — NOT saved to disk,
  NOT shown in the dashboard (`_brand_assets` renders text). So a lighter screenshot is tolerable.

## OWNER RESOLUTION (folds the finding into the ruling) — implement this when resumed
Do NOT abandon two-phase; do NOT fetch all 106. **Block PRODUCT-image bytes ONLY, while ALLOWING
dimensions/bytes for LOGO candidates** (the logo is 1-2 images, not 106). Preserves the footprint
win where it matters (product images are the bulk) AND keeps logo detection intact.
- Implementation sketch: the route handler must distinguish a logo/brand-chrome image (header/nav
  region, logo-named, small, above-fold, or a favicon/og candidate) from a product/content image
  (below-fold grid, cdn product path). Allow bytes for the former, abort for the latter. Image
  URLs for BOTH are still collected from the DOM regardless.
- Then the MANDATED before/after on a NON-hammered site (let the IP cool ~15 min first, capped
  diagnostics per `diagnostic-isolation-shared-ip`): report homepage request count + logo-pick +
  products/prices coverage. Revert if >5% regression.

## Where the live sites stood (2026-07-13, do not re-hammer)
topshoes/bobana/rawafrican all serve 200 to sequential requests; the crawler (headless) hit 429
mainly from the shipped concurrency double-fire + my own uncapped diagnostics (now a hard rule).
Shipped fixes this round: analyze concurrency guard, 429=transient retry, patient homepage 429
retry, tracker blocklist, honest 429 messaging. All green in suite 1405.

Full raw map: tasks/wo6m5he4n.output (workflow wf_cc3c2b3a-a92).
