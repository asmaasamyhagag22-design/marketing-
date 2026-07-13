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

- **D-3.2 — RTL applied without screenshot verification.** Set `<html lang="ar" dir="rtl">` on
  the standalone deliverable (Arabic-primary content) + an Arabic-capable font stack (Segoe UI /
  Sakkal Majalla). New sections use logical CSS props so they mirror cleanly; older flex/grid
  sections reflow via bidi. Structural verify passed (dir attr + cleaned citations + 0 raw
  leaks); a pixel-level RTL check needs the owner's interactive screenshot pass (browser preview
  was unavailable, D-3.1). FLAG: if any older section shows mixed-direction breakage on screen,
  it's cheap to pin with a logical-property fix — noted as the one visual risk in this pass.

- **D-3.3 — test_api_run.py flakes under full-suite contention.** Two API-run tests
  (returns_job_id, rejects_when_llm_required) failed once during a full-suite run while a heavy
  render/other work contended for the port/timing, then passed 9/9 in isolation. Not caused by
  the dashboard changes. Treating as a load flake; re-running the full suite clean before each
  commit. FLAG: worth a port-isolation/retry hardening pass on those tests (ticket T-APIFLAKE).

- **D-3.4 — Tier-mismatch cap is conservative to protect the U1 gate.** The decisive cap in
  peer_match._aggregate only fires on EXTREME mismatch (size score <0.20 ≈ 100x reviews, or the
  opposite price tier), so genuine near-tier peers the U1 objective-deduction gate selects are
  untouched (verified by test_genuine_near_tier_peer_is_untouched). A full U1 re-gate on live
  data is the owner-side confirmation that discovery quality didn't regress — ticket T-TIER-GATE
  (needs network + is measurement-sensitive; not run inside this offline mission).

## Render #3 — reel consistency prompt pack

- **D-R3.1 — Resolved image model ids (pack 🌐 verify-at-decision-time).** Probed live on
  radiant-octane: `gemini-3.1-flash-image-preview` (Nano Banana 2, fast lane) and
  `gemini-3-pro-image-preview` (Pro lane, legible text) both LIVE at Vertex
  `location="global"`; 404 at us-central1. Legacy `gemini-2.5-flash-image` live at
  us-central1 as fallback. Seed generator switches Imagen → Nano Banana per §10; resolved
  model id logged per request.
- **D-R3.2 — Calibration fixture built from render #2.** tests/fixtures/render2_sheet.png
  (5 frames — the 6th timestamp fell past the last keyframe; 5 are sufficient and visibly
  carry the diseases: ≥4 different protagonists, the banned smile-at-laptop beat, a glowing
  sci-fi UI panel). G2 MUST fail this sheet or the gate itself is broken (§5).
- **D-R3.3 — Temperature 0 for G2 not directly controllable** through the caller protocol
  (temp lives inside the caller implementation). The BINDING part is preserved in code: the
  PASS conjunction is computed from the boolean fields in code (the model never self-passes),
  matching the pack's code-level invariant. FLAG: if G2 verdicts prove noisy, expose a
  temperature override on the Gemini caller.
- **D-R3.4 — VO↔EVIDENCE check upgraded from "cheap LLM check" to the Ledger.** G1's VO trace
  uses ledger.audit_text (deterministic, the actual moat) instead of an LLM opinion — stronger
  than the pack's minimum, same intent.
