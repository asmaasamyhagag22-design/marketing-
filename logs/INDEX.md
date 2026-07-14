# Run index

Every pipeline run, newest first. `run · brand · date · outcome · link`.

Auto-maintained by `telemetry/run_log.py` (renders human-readable step lines on top of the U7
telemetry JSONL — no duplicate instrumentation).

| run_id | brand | date (UTC) | outcome | log |
|--------|-------|-----------|---------|-----|
| _(populated as runs complete)_ | | | | |

## FRONT 1 — REEL FINALIZED (2026-07-14)
- Deliverable: outputs/reels/nti_render3_final.mp4 (34s) + _contactsheet.png. NTI «من مجهول لحارس»
  testimonial: Karim to-camera (real VEED lip-sync) + B-roll, grounded in the REAL NTI Smart Village
  building + blue tunnel, blue-logo chip watermark, creative end-card A, clean audio, anti-cliché VO.
- Gates: G2 seed-set PASS (same_person=T, same_world_grade=T, junk_screens=[], arc_readable=T,
  zero regens). render#2 calibration pinned (FAIL, junk_screens=[5]).
- Veo: the authorized render (used this session). Lip-sync WaveSpeed VEED ~$0.90.
- BLOCKED→PREPARED: Egyptian voice — needs owner to upgrade ElevenLabs to Creator (free tier can't
  use library voices via API). Swap is one-command-away (scratchpad: add_egyptian_voices + assemble_v4).
- FLAG: owner's 3-question verdict on return; then upgrade ElevenLabs → swap voice → re-lipsync.
