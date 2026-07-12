# STEP 0 — Inventory: what the pipeline computes vs what the deliverable tells

Census of 79 intelligence items across 5 domains (raw data: `logs/_census_raw.json`). Verdict
matches the owner's: the kitchen cooks far more than the plate serves. **52 of 79 items are
hidden or shown as raw enums/jargon.** Categorised for the mission's two-column honest report.

## The headline: the moat is computed, the moat is hidden

The product's whole promise is "grounded — here's the receipt". Today the receipt is a green
tick. Every one of these is COMPUTED and dropped:
- **MediaPlan evidence quotes** → collapsed to `مؤكد بالأدلة ✓`; the actual proof line (a real
  price, the contact-form finding) never shows.
- **`alternatives`** (objectives considered-and-rejected) → the single richest "why this, not
  that" story, discarded.
- **`channel_weights`** (category-tuned FB/IG/YT budget split) → real "where do I put my money"
  answer, never attached to the plan.
- **`confidence`** (high/…) → thrown away; a paid deliverable that says "highly confident"
  vs "tentative" changes trust.
- **SWOT evidence quotes** → not on hover/expand (the census's central question: NO).
- **TOWS anchors** (S1+O2 → this strategy) → the grounding promise of TOWS, never shown.
- **Comparative Gap Matrix** (11-dim you-vs-peer table) → the core competitive artifact,
  persisted only as derived SWOT; the owner never sees the table.
- **Content-calendar audit + remediation** (a fabricated hook BLANKED by the Ledger) → the moat
  in action, never surfaced.
- **Compliance sheets** (verdict=PASS proof) → the page headlines "Provable Brand Safety" and
  never renders the proof.
- **Per-run telemetry cost** (~$0.11/run, tokens, model) → tracked, never shown.

## Two-column split (the mission's honest report, seeded here)

### Column 1 — HIDDEN, now surfaceable (surfacing beats building)
Media plan: channel_weights split · alternatives · evidence quotes · confidence · KPI honest
"calibrate after 2 weeks" + unit/window · learning-floor "don't panic day 1" · persona axes as
human sentences · full objectives[] funnel. Competitor: Comparative Gap Matrix · MarketDefinition
· PeerFitBreakdown (why matched) · SWOT evidence quotes · TOWS anchors · discovery_notes.
Voice: standalone "what we don't know" notes · peer praise themes · ad-availability gap message.
Trends: trend ranking/recency · calendar per-item trend attribution (needs a ContentItem field —
tiny build) · remediation record. Telemetry: per-run cost + stage latency. Profile: 7 offerings ·
5 value props · 8 trust signals · 5 audience segments · pricing posture · service areas · CTAs.
Dashboard: executive summary (A) · creative→strategy labels (D) · honesty surface (F) · ordered
5-min read (H) · RTL + real fonts (G+).

### Column 2 — TRULY THIN, needs a named unit (no fabrication)
- **Egyptian-season window** (Ramadan/Eid/back-to-school) — *genuinely not computed*. Rubric
  allows new computation where data is absent → small deterministic season calendar (Round-2 A).
  Ticket: T-SEASON.
- **KPI target value** — honestly null until launch data exists → honest "calibrate after first
  ~2 weeks" line, never a fabricated number. Ticket: T-KPI (filled by real campaign data, not us).
- **Competitor tier signals as criteria** — price-band/distance/size ARE extracted but NOT wired
  into discovery scoring (Round-2 C). Real wiring, not new data. Ticket: T-TIER.
- **Competitor determinism / registry** — the set rebuilds per run (Round-2 B). The one real
  build: schema + persistence + diff + approval UI. Ticket: T-REGISTRY.
- **advisor-gap object** — referenced in comments but never constructed/rendered. Needs a real
  gap type the honesty surface reads. Ticket: T-ADVISOR.
- **ad-presence** (ads_intel) — built but wired nowhere + blocked on Meta identity confirmation.
  Surface as an availability gap. Ticket: T-ADS.
- **live customer voice on real brands** — ABSA only renders when a saved review file matches the
  slug; real deliverables need a review pull first (P2/P5 wiring). Ticket: T-VOICE-LIVE.

## Rubric baseline (before any fix) — scorecard v0
| § | Section | Score | Worst failure |
|---|---------|-------|---------------|
| A | First-screen story | 1 | No executive summary; first screen is a product pitch |
| B | Plan not enum | 2 | Export decodes enums; studio prints BOFO/100%/cost_per_lead raw; no budget split, no evidence quote |
| C | Strategy narrative | 2 | SO/ST badges unexplained; no evidence on hover; posture a bare enum word |
| D | Creative tied to strategy | 1 | Poster/reel orphaned — no strategy/audience/funnel label |
| E | Voice of customer | 1 | Does not render for real artifacts (no matched review file) |
| F | Honesty surface | 1 | No "what we don't know" panel; standalone notes + remediation dropped |
| G | Zero raw internals | 2 | `readiness.swot_quality_signals.tagline=false`, `↳ value_propositions`, raw enums leak |
| H | Five-minute ordered read | 2 | No arc, no numbers, no "start here" |
| I | Explained plan (non-marketer can explain back) | 1 | "cards I don't even understand" — owner's own verdict |

Pass = every section ≥4. **Current: 0/9 sections pass.** Build order (lowest first, but all fail
→ reading order): A → I/B → C → D → E → F → Market Pulse → Registry/tier → RTL+design → capability
census. Commit per section with before/after.
