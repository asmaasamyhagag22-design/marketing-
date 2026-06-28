# Pillar 1 — Dynamic Crawl Budget: MEASURED findings (read-only; NO fix made)

> Measure-first deliverable. Produced autonomously; NO scraper code was changed (the
> high-impact fixes need LIVE re-scraping to verify — see "Why no blind change" below).
> Tools: `benchmark/measure_ecom_coverage.py` + `benchmark/measure_ecom_bottleneck.py`
> (run from the repo root). E-commerce is detected UNIVERSALLY by product-pattern
> internal-link density (>= 8 distinct product/collection links) — no hardcoded names.

## Key numbers (15 e-commerce sites, latest scrape each)
| metric | value |
|---|---|
| coverage (scraped / unique-internal discovered) | **77 / 3072 = 2.5%** (avg 4.9%/site) |
| pages crawled per store | **4–6** (vodafone 12) |
| per-page render time | **avg 11.5 s** (max ~36 s) |
| total scrape time | **~70 s** for most stores |
| product pages actually crawled | **19** across all 15 stores (of 1347 product links discovered) |

Worst: glamira 4/1011 (0%), luxurianjewels 2/261, jewelpin 1/124, eg_azzafahmy 4/103.
Non-e-commerce sites average **33%** coverage — the cap rarely binds there. The gap is
E-COMMERCE-specific, as the spec predicted — but the ROOT CAUSE is NOT the page cap.

## CRITICAL caveats (honesty — the saved data OVERSTATES the current problem)
1. **The saved scrapes were made with the OLD 60-second budget** (and old 7-page cap). The
   current code is `TOTAL_BUDGET_SECONDS = 150` + `MAX_INTERNAL_PAGES = 12` (commit 12e79a4).
   So `budget_exceeded=True` + ~70 s duration on these manifests = the OLD 60 s budget being
   hit, NOT the current 150 s. A fresh scrape with current code would crawl ~12 pages, not 4–6.
   **→ Re-measure on FRESH scrapes before changing anything.**
2. The spec's "`MAX_INTERNAL_PAGES = 7`" is stale — it is 12 now.

## The real bottleneck (this reshapes Pillar 1)
- **The page CAP is NOT the lone binding constraint.** At ~11.5 s/page, the 150 s budget fits
  ~13 pages — i.e. the cap (12) and the time budget now bind at roughly the SAME point (~12).
  **Raising `MAX_INTERNAL_PAGES` to 30–50 alone is a NO-OP** until pages render faster, because
  the crawler hits the time budget first.
- To reach the spec's 30–50 pages you must fit more pages into a sane time → **per-page render
  SPEED is the key enabler.** 30 pages × 11.5 s = 345 s (~6 min) is impractical.
- **Selection is already reasonable:** `_select_subpages_to_fetch` (scraper/crawler.py:120)
  pulls from homepage links + the sitemap and orders by tier then `type_priority`. Within the
  HIGH tier, `CONTACT(0)` and `SERVICES(1)` rank ABOVE `PRODUCTS(2)` — so a store's scarce
  budget partly goes to contact/services before products (a minor reorder opportunity for
  stores; measured: only 19 product pages crawled across 15 stores).

## Recommended Pillar-1 sequence (each needs LIVE verification — do NOT change blind)
1. **Re-measure on fresh scrapes** with the current 150 s budget (the saved data is old-budget).
2. **Per-page render SPEED** (the enabler): on SUB-PAGE fetches, block heavy/non-essential
   resources (images / media / fonts / 3rd-party analytics & ads) and/or tune the wait
   condition. Sub-pages need text + links, not the homepage's full visual capture.
   RISK: JS-injected content (e.g. footer social links that load on scroll — see CLAUDE.md) —
   verify NO data loss on a fresh scrape. This is what makes adaptive depth feasible.
3. **Adaptive cap + budget for e-commerce** (universal detection by product-link density /
   sitemap product-URL share) — raise to 30–50 pages ONLY after (2) makes them fit in time.
4. **Selection reorder for stores** (products/categories before contact/services) — a modest,
   offline-verifiable win; captures offering breadth within the limited budget.
5. **Duplication early-termination** (`content_hash`) — stop crawling near-identical product
   pages to spend the budget on distinct content.

## Why no blind change was made (autonomous-mode discipline)
The high-impact fixes (render speed, adaptive budget) change crawl behaviour and can regress
JS-injected content — they REQUIRE a live re-scrape to measure, which can't be verified while
unattended. Per the project's standing rules ("Measure before changing", "be honest about
limitations", "one fix at a time"), a blind unverifiable scraper change would be wrong. This
measurement + diagnosis is the safe hand-off; the fixes are ready to implement + verify next.
