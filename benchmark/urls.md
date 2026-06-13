# Benchmark URL Grid

**Locked:** 2026-05-27
**Grid:** 13 URLs, asymmetric — 6 clean / 3 typical / 4 messy
**Goal:** universal extraction quality across diverse website patterns (not Egyptian-only, not vertical-specific)

## Thresholds for SWOT-unlock

The scraper + business_profile pipeline graduates to SWOT generation when **both** hold:

1. **At least 10 of 13 URLs (76.9%) reach `ready_for_strategy = True`** after extraction.
2. **Average SWOT-critical sub-score ≥ 0.85** across all 13 URLs, where the
   sub-score is the mean correctness of the 7 SWOT-critical fields:
   `business_name, category, offerings, audience, value_propositions,
   tone_of_voice, contact_channels`.

Per-vertical gate: **no single vertical may average below 0.70** on the
SWOT-critical sub-score. A passing overall average can still hide a
broken vertical; we surface that explicitly.

Per-tier expectation: messy-tier failures are expected (we're testing
how far the scraper degrades, not whether it doesn't). A messy-tier URL
graded at 0.50 is not a defect; a clean-tier URL graded at 0.50 is.

## Field-correctness rubric

Per field, per URL: `1.0` (correct), `0.5` (partial), `0.0`
(wrong or missing). A field is "partial" when it's directionally
correct but missing structure (e.g. `business_name` returns the right
brand but with a tagline appended, or `offerings` returns 3 of 8 actual
products).

## The grid

| Vertical | Tier | Brand | URL | Platform | Notable signals |
|---|---|---|---|---|---|
| Restaurant | typical | McDonald's Egypt | https://www.mcdonalds.eg | custom | Microdata=2, bilingual (HTML lang missing, body has Arabic), no robots, no sitemap, body=1.5K chars |
| Restaurant | typical | Buffalo Burger | https://buffaloburger.com/ | Next.js | hotline 19914, `__NEXT_DATA__` on every page (16KB–700KB), redirects to `/branches/all/home`, 8 pages crawlable |
| Restaurant | messy | Zooba | https://zoobaeats.com | Nuxt | SPA-empty-body (302 chars), zero structured data, no robots, no sitemap |
| Clinic | clean | Alameda Healthcare Group (was Dar Al Fouad) | https://alameda-hc.com | WordPress | JSON-LD=1, robots+sitemap, 2.8K chars body, redirects from `daralfouad.org` |
| Clinic | clean | As-Salam International Hospital | https://www.assih.com | Squarespace | JSON-LD=1, robots+sitemap, bilingual (en-US + Arabic body), 3.7K chars |
| Clinic | messy | Andalusia Hospitals Egypt | https://andalusiaegypt.com | Nuxt | `lang='ar'` (Arabic-primary), JSON-LD=3 despite SPA-thin body (343 chars), robots+sitemap |
| Skincare/Ecom | clean | EVA Cosmetics (shop) | https://shop.eva-cosmetics.com | Shopify | JSON-LD=2, 13K chars body, bilingual, redirects to `www.shop.eva-cosmetics.com` |
| Skincare/Ecom | clean | The Hair Addict | https://thehairaddict.net | WordPress | JSON-LD=1, robots+sitemap (default `/sitemap.xml`), 15.9K chars body, bilingual |
| Skincare/Ecom | clean | Raw African | https://rawafrican.net | Shopify | JSON-LD=1, robots+sitemap, 10.9K chars body, bilingual |
| Skincare/Ecom | clean | Norshek | https://norshek.com | WordPress | Microdata=22 (highest in set), JSON-LD=0, robots+sitemap, 6.6K chars body |
| Skincare/Ecom | messy | Glamira | https://www.glamira.com | unknown (WAF-protected) | International luxury jewelry. Returns 403 to non-browser HTTP clients. Loads in real browsers. Tests Playwright resilience against bot-detection. |
| Education | typical | Almentor | https://www.almentor.net | custom | Bilingual EG education, Arabic-primary title but `lang='en'` (mismatch), zero structured markup, robots+sitemap, 12K chars body |
| Education | typical | AUC SCE | https://sce.aucegypt.edu | custom | Zero structured markup, robots+sitemap, 6.9K chars body, institutional EN-only |
| Education | messy | Mumm | https://mumm.io | unknown | Empty body (0 visible chars), no title, but robots+sitemap exist. Pure JS-rendered SPA. |

## Per-URL evaluation checklist (filled at scrape time)

For each URL the benchmark harness records:

- `final_url` after any redirects
- `page_count` (homepage + crawled subpages)
- `text_blocks_total` (DOM text blocks across all pages)
- `next_data_found_pages` (count of pages where `__NEXT_DATA__` was harvested)
- `schema_org_blocks_by_source` (count by `json_ld / microdata / rdfa / next_data`)
- `contact_channels.phones_count` (full list including hotlines)
- `cta_candidates_count`
- `ready_for_strategy` (T/F)
- 14 field-correctness grades (one per BusinessProfile.field, 0.0–1.0)

## Coverage of must-haves

The grid was selected to cover these patterns at least once each:

| Pattern | Covered by |
|---|---|
| Shopify-hosted brand | Eva-shop, Raw African (2 data points) |
| WordPress site | Alameda, The Hair Addict, Norshek (3 data points) |
| Squarespace site | As-Salam |
| Next.js with `__NEXT_DATA__` | Buffalo Burger |
| Nuxt SPA-empty-body | Zooba, Andalusia (2 data points) |
| Arabic-primary HTML `lang='ar'` | Andalusia |
| Bilingual content (en HTML + ar body) | McDonald's, As-Salam, Eva-shop, The Hair Addict, Raw African, Almentor (6 data points) |
| `lang` declaration mismatch with body | Almentor (`lang='en'` but Arabic-primary title) |
| Microdata-heavy markup | Norshek (22 blocks), McDonald's (2 blocks) |
| JSON-LD only, no Microdata | Alameda, As-Salam, Andalusia, Eva-shop, Raw African |
| Zero structured markup with real content | Almentor, AUC SCE |
| SPA with literal 0 chars in body | Mumm |
| WAF-protected / 403-to-script | Glamira |
| Site that redirects across canonical hosts | Alameda (from daralfouad.org), Andalusia (www→bare), As-Salam (bare→www) |
| Multi-team / multi-doctor clinic | Alameda, As-Salam, Andalusia (3 data points) |

## Patterns NOT covered (acknowledged blind spots)

- **Image-only or PDF menu**: no candidate flagged for this. McDonald's
  partial markup (1.5K chars body) is the closest watch-list candidate;
  we'll discover image-menu behavior when we scrape and grade it.
- **B2B services site**: no candidate. Almentor and AUC SCE are
  consumer-facing education, not B2B SaaS.
- **Heavy infinite-scroll catalog**: Glamira may exhibit this; we'll
  see when Playwright renders it.
- **Government / municipal site**: not in scope.
- **Blog-only content site**: not in scope.

If the benchmark reveals weak performance on these patterns, the right
move is to add candidates and re-validate — not to widen the rubric.

## Replacements log

Candidates that were on the original shortlist but dropped during validation:

| Original | Reason dropped | Replaced with |
|---|---|---|
| Cilantro Café (`cilantrocafe.com`) | Parked domain (hugedomains.com) | — |
| TBS Bakery (`tbsbakery.com`) | DNS resolution failure | — |
| Change Me Clinic (`changemeclinic.com`) | JS redirect to nowhere (14-char body) | — |
| Tabibi 24/7 (`tabibi247.com`) | HTTP timeout (uncertain reachability) | — |
| Eva Cosmetics (`evacosmetics.com`) | Connection refused | `shop.eva-cosmetics.com` (more representative for ecom benchmark) |
| Glamera Shop (`glamera.com`) | DNS resolution failure | Glamira (`glamira.com`) — different brand, but adds international luxury-jewelry diversity |
| Espresso Lab Egypt (`espressolab.com`) | Resolved to global TR site, not EG operation | — |
| Career 180 (`career180.com`) | SSL certificate hostname mismatch | — |
| Russian Cultural Center (`rcegypt.com`) | DNS resolution failure | — |
| Dar Al Fouad (`daralfouad.org`) | Redirects to Alameda — ownership change | Alameda Healthcare Group (`alameda-hc.com`) |

## How to re-validate

```bash
# From repo root
python tools/check_candidates.py > candidate_check.txt 2>&1
```

The script in `tools/check_candidates.py` makes one HTTP request per
candidate, checks for structured markup, fingerprints the platform, and
prints a per-URL summary. It does NOT replace the scraper — it's a
lightweight validation pass to confirm candidates are reachable and
roughly match the tier we assigned.

## Future moves

- After the harness runs the full grid, append `benchmark/results.md`
  per-run with timestamp, version, and per-URL grades.
- If a candidate breaks (site redesign, ownership change, takedown),
  document the replacement here with the same level of validation.
- Grid lock changes require updating the date at the top of this file.