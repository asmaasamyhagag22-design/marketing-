# Autonomous decisions — Client-Deliverable 12-hour run

Every choice made without the owner present. Safest evidence-honest default, rationale, and a
FLAG where the owner should review. Newest first.

## Mission operating defaults (start of run)

- **D-0.1 — Never fabricate to pass the rubric.** Where the rubric demands a number the
  pipeline cannot source (a KPI target, a budget benchmark), the honest line
  "يُعاير بعد أول أسبوعين تشغيل / calibrated after the first two weeks" is used and an advisor
  gap is raised. No invented targets, ever. FLAG: none — this is the standing law.
- **D-0.2 — Dashboard failure policy.** Client-facing UI shows only achievements + the honest
  "what we don't know yet" panel. Every failure degrades gracefully → `logs/` + advisor gaps,
  with a discreet "التفاصيل في سجل التشغيل" link. No red errors / stack traces / FAIL banners
  client-side. Failures are relocated, never deleted.
- **D-0.3 — Owner-gated actions are PREPARED, never executed.** No reel/poster EXECUTE (HITL
  law). No spend beyond the ratified caps. Competitor-registry identity changes are queued for
  owner approval, never auto-applied.
- **D-0.4 — Suite-green invariant.** Every commit leaves the full suite green, count read from
  the run's own output (not a pipe). Self-contained commits so a 12-hour interruption loses
  nothing.
- **D-0.5 — Priority order** P0→P3→P1→P4→P2→P5→P6→P7; execution defaults to phase order but a
  blocked subtask (missing creds / 404 model / API refusal) is logged, ticketed, SKIPPED, and
  the queue continues.

<!-- new decisions appended below -->

## Phase 3 — dashboard rebuild

- **D-3.1 — Browser-preview visual check unavailable.** `preview_start` on the local
  file:// render timed out (300s) with the studio dev server already bound to :8770.
  Per never-halt, I verify the dashboard STRUCTURALLY (render succeeds + grep the composed
  copy in the HTML) instead of by screenshot, and rely on the deliberately-authored CSS for
  the design bar. FLAG: owner may want a screenshot pass in an interactive session; the
  rendered HTML files are in the scratchpad for direct opening.
