# Reel Studio v2 — Brand-DNA-Driven, LLM-Designed (kill the templates)

> Status: PLAN (awaiting owner approval). No code yet. Author: this session, 2026-06-27.

## Why (the owner's point — verbatim intent)
A content-creator product **can't be canned templates**. Today the reel is template-based:
- **TEXT** = ONE fixed HTML/CSS caption (`reel/textlayer._scene_html`) — the *same* design for
  every brand (only the words/colours change). I recently made it prettier, but it is still ONE
  template. That's the "بروميت/قالب جاهز" the owner rejected.
- **SCENE** = canned templates (`_VERTICAL_SCENE` + `_identity_scene` slot-filling).
- **STRUCTURE** = a fixed storyboard order (intro/offering/contact/outro).

Meanwhile the **POSTER already evolved past this**: it LEARNS the brand's real visual language
(`BrandCreativeDNA`, via a multimodal LLM over the brand's actual ads) and an LLM **AUTHORS a
unique composition + copy per brand**. The reel never got that leap. v2 closes the gap: every
brand's reel — caption design, scene, motion feel — is **authored from its OWN creative language**,
not stamped from a template.

**Governing principle (unchanged): two truth domains.** FACTS (the on-screen words, offerings,
contact) stay VERBATIM/grounded (+ the Evidence-Ledger reel gate, separate workstream). DESIGN
(caption composition, scene, motion) is LLM-authored creative, in the brand's language.

## Reuse — the poster engine already solves most of this (do NOT re-implement)
- `brand/creative_dna.py` → `BrandCreativeDNA` (fields: `layout_philosophy`, `composition_patterns`,
  `typographic_character`, `color_usage`, `imagery_style`, `mood`, `motifs`, `text_density`,
  `signature_moves`, `do_list`, `dont_list`). Built ONCE per brand, cached to
  `outputs/brandbooks/<name>_dna.json`. The SAME cache file the poster uses.
- `poster/pipeline.load_or_build_dna(profile, caller)` → build-or-load the cached DNA (reuse as-is).
- `poster/art_director.build_design_spec(brief, caller, profile, variation, brand_dna)` → an LLM
  authors a `PosterDesignSpec` (pure design; FREE-FORM `text_box`/`logo_xy` continuous coords;
  `accent_hex` validated to EXACTLY match a scraped brand colour; deterministic
  `default_design_spec` fallback; per-run `variation_seed`). The reel MIRRORS this for captions.

## New architecture

### A. Veo 403 unblock (Step 0, prerequisite)
`reel/video_provider.AimlVeoProvider._headers()` sends only `Authorization` + `Content-Type` — NO
`User-Agent` → Cloudflare blocks every Veo 3.1 call with **403** → the reel silently falls back to
KenBurns (and, post quality-gate, to a gradient for image-less brands). **Until this lands, NO Veo
output is possible**, so none of the scene/DNA work can be visually judged. Fix = add a browser UA.

### B. `ReelCaptionSpec` — LLM-authored caption design per brand (replaces the fixed `_scene_html`)
A new pure-DESIGN spec (mirrors `PosterDesignSpec`), carrying ZERO facts:
- `typography` — display/body font character from `DNA.typographic_character` (weight, case, scale).
- `text_box` / `caption_anchor` — WHERE the caption sits (free-form continuous coords, like the
  poster), driven by `DNA.layout_philosophy`/`composition_patterns`.
- `emphasis` — how a word is highlighted (accent word / knockout / chip), accent colour validated to
  the REAL palette (same rule as poster `accent_hex`).
- `scrim_style` — legibility treatment (soft/strong/panel/none) — KEEPS the legibility win from the
  v1 redesign so it still reads on any footage.
- `density` — one line vs short stack, from `DNA.text_density` (kills the "list dump").
- `motion_feel` — entrance/emphasis motion cue → drives the compositor's overlay animation.

`build_caption_spec(brief, caller, profile, variation, brand_dna)` authors it (LLM, strict structured
output); `default_caption_spec(brief, variation_seed)` is the deterministic per-brand fallback (the
current v1 look — so no-caller/no-DNA never regresses). `reel/textlayer._scene_html` is rewritten to
render FROM the spec (parameterised HTML/CSS) — so two brands render DIFFERENT captions. The WORDS
stay verbatim from the storyboard. Per-run `variation_seed` varies typography/treatment between runs.

### C. DNA-aware scene generation (demote the templates to last-resort)
`reel/art_director.build_brand_scene` already LLM-generates the scene; feed it the BrandCreativeDNA
(`imagery_style`/`mood`/`signature_moves`) so the b-roll is in the brand's visual world (like the
poster's concept prompt). The deterministic `_VERTICAL_SCENE`/`_identity_scene` become a LAST-RESORT
fallback only (no caller) — kept, not primary.

### D. One pipeline (mirror `poster.pipeline.generate_poster`)
`reel/pipeline.generate_reel(...)`: load-or-build DNA → caption spec → storyboard (DNA-aware scenes)
→ provider (Veo/KenBurns) → spec-driven text layer → compose. Same shape + graceful fallbacks as the
poster pipeline; `__main__` and the API both call it (one path, like the poster).

## Sequence (one step at a time, measured — standing rule 1)
- **Step 0 — Veo 403 fix** (browser UA). Tiny; unblocks the generative path so everything downstream
  can be SEEN. Verify: a live Veo call no longer 403s (owner's run).
- **Step 1 — reel builds-or-loads BrandCreativeDNA** (reuse `load_or_build_dna`). Verify: DNA cached
  for a test brand; degrades to current look without it.
- **Step 2 — `ReelCaptionSpec` + spec-driven renderer** (the big "kill the template" win for TEXT).
  Verify OFFLINE (zero Veo cost): render captions for 2–3 brands → they look genuinely DIFFERENT
  (before/after grid), legibility preserved. ← highest value, fully offline.
- **Step 3 — DNA-aware scene** (feed DNA into `build_brand_scene`; demote templates). Verify: scene
  prompt inspection (offline) + a Veo run (owner) shows on-brand b-roll.
- **Step 4 — unify into `reel/pipeline`** + variation + wire `__main__`/API. Verify end-to-end; suite
  green.

Each step lands + is measured (before/after) + CLAUDE.md updated before the next.

## Files
- `reel/video_provider.py` (Step 0 — UA).
- `reel/caption_design.py` (NEW — `build_caption_spec` / `default_caption_spec`; mirrors
  `poster/art_director.build_design_spec`).
- `reel/schemas.py` (add `ReelCaptionSpec`).
- `reel/textlayer.py` (render FROM the spec, not a fixed template).
- `reel/art_director.py` (DNA-aware scene; demote `_VERTICAL_SCENE`/`_identity_scene`).
- `reel/storyboard.py` + NEW `reel/pipeline.py` (load-or-build DNA, thread the spec).
- REUSE unchanged: `brand/creative_dna.py`, `poster/pipeline.load_or_build_dna`, the
  `poster/art_director.build_design_spec` pattern, `poster/template` free-form/colour helpers.

## Verification
- OFFLINE per-brand caption renders (before/after; 2–3 brands showing DIFFERENT designs) — the key
  proof, zero Veo cost (same harness style as the v1 text redesign).
- Veo run (owner) for scenes (after Step 0).
- Hermetic tests per step (MockCaller; spec mapping/validation/fallback; renderer coordinate clamps).
- Full suite stays green at each step.

## Honesty / risks / open questions
- DNA needs a vision LLM (Gemini, on GCP credits) + the brand's real ads (Serper image search).
  Degrades: no DNA → the current deterministic look (no regression). Cost: ONE DNA call per brand,
  cached and shared with the poster.
- The LLM-authored caption spec MUST be validated/CLAMPED (like the poster's coord clamping) so a bad
  spec can never break the render — the renderer never trusts raw LLM coordinates.
- Veo 3.1 visual quality is the owner's to judge on a live run; the offline proof is the caption
  design + the scene prompt text.
- The reel grounding gate (separate Evidence-Ledger workstream) still governs the WORDS — design
  freedom never touches facts.
- OPEN: confirm the reel should reuse the SAME cached DNA file as the poster (recommended: yes —
  same brand, same `<name>_dna.json`).
- This is a multi-step build; **Step 2 is the one that actually kills the "templated" feel for text**
  and is fully offline — so it is the highest-value early milestone after the 403 unblock.
