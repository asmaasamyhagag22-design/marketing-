# Prompt Audit — the 53-prompt catalog, resolved

A full-catalog adversarial audit of every LLM / image / vision prompt in the system (the catalog
itself is [PROMPTS.md](PROMPTS.md)). Ran in five batches, each prompt scored on a **pentagonal
matrix** — ① grounding integrity · ② semantic precision · ③ cliché / convergence · ④ structural
robustness · ⑤ universality (process.md rule 5) — with an objective verdict per prompt (keep /
refine / restructure / measurement-locked / discard).

**The thesis it proved:** the catalog was never *broken*. Its grounding core is strong (the strategy
subsystem is grounded-by-construction; the gates are real; the variation engine is sound). It drifted
through **duplication** and **priming**, not bad instruction. The audit's product is not 53 rewrites —
it is **6 shared contracts + 1 config map** that turn 53 independently-drifting prompts into one
coherent system: grounding stated once, universality structural, creativity free *because facts are
gated*.

---

## The 6 shared contracts — ~30 duplicated rule-statements retired

Each contract states, once, a rule that was previously re-litigated (and drifting) across many prompts.

| Contract | Replaces | Born in | Lives in | Status |
|---|---|---|---|---|
| `GROUNDING_CONTRACT` | ~9 re-stated evidence rules | Batch 1 | `business_profile/llm/prompts.py` | **shipped** |
| `CRAFT_CONTRACT` | ~7 "senior / premium / world-class" primers | Batch 2 | `poster/contracts.py` | **shipped** |
| `VERBATIM_RENDER_CONTRACT` | 3 copy-integrity restatements | Batch 2 | `poster/contracts.py` | **shipped** |
| `IMAGE_NEGATIVE_CONTRACT` / `_TERMS` | ~9 "no text/logo/typography" stacks | Batch 3 | `poster/contracts.py` | **shipped** |
| `COMPLIANCE_CONTRACT` (`compliance_for`) | ad-safety buried in 5 aesthetic prompts | Batch 3 | `poster/contracts.py` | **shipped** |
| `MOTION_CONTRACT` | product-identity across 2 reel prompts | Batch 4 | (`_MOTION_TAIL` today) | **deferred** (promote) |

`CRAFT_CONTRACT` now opens the poster concept prompt AND the reel director (persona stripped).
`COMPLIANCE_CONTRACT` is the highest-leverage: real ad-safety relocated out of five aesthetic strings
into ONE category-keyed source that also covers the LLM image path and the reel (which had **none**),
and feeds the future Meta Policy Linter (U4) — one compliance truth across the system.

---

## The spine fix — ONE config map retires THREE rule-5 violations

The same vertical-hardcoding recurred three times: `_OFFERINGS_GUIDANCE` (18 keys), `build_art_direction`
(5 category prompts), `_MOTION_GUIDANCE` (4 keys). The fix is one **category → shape** config map with a
real `default` fallback, keyed by a universal signal — this is D-8 from INTERFACES.md, applied to prompts.

- `business_profile/llm/prompts._CATEGORY_TO_SHAPE` / `_shape_for()` — **shipped** (Batch 1: 18 → 4 catalog shapes; importable cross-module).
- `build_art_direction` 5 → ~3 scene shapes (`atmosphere` / `environment_of_practice` / `hero_surface` / `default`) — **deferred**.
- `_MOTION_GUIDANCE` 4 → motion shapes (`human_product_interaction` / `ambient_reveal` / `sensory_process` / `default`) — **deferred**.

One map, three consumers (offerings + art + motion). `domain_schema` (Batch 1) sits above it as the
*generative* universality template — it designs a per-business schema instead of switching on a vertical.

---

## Batch-by-batch

### Batch 1 — Business Profile (extraction) · SHIPPED
`GROUNDING_CONTRACT` (5 rules + coverage + specificity, injected into the shared `SYSTEM_PROMPT`);
identity split (tagline COPIES / description COMPOSES-but-cited); offerings dropped the prose
FORBIDDEN-CLAIMS (contract + validator cover it); `_OFFERINGS_GUIDANCE` 18 keys → 4 catalog shapes +
`_CATEGORY_TO_SHAPE`; trust dropped "self-praise"; the same-subject `judge` truncation windowed on the
token. **Tally:** 1 promoted · 5 refine · 3 keep · 1 restructure · 0 discard.

### Batch 2 — Poster concept / copy / fidelity · SHIPPED
`CRAFT_CONTRACT` (a bar, not a brag; bans the empty primers) replaced the "senior creative director"
persona in the concept prompt; the STRANGER TEST kept as the positive engine; `VERBATIM_RENDER_CONTRACT`
shared by the one-shot renderer + the OCR reader; **`script_wellformed`** added to the vision-QA gate — a
no-Latin-but-garbled-Arabic poster now FAILS (composes with the separate OCR character-fidelity gate).
**Tally:** 6 refine · 5 keep · 2 new contracts · 0 discard.

### Batch 3 — Poster image generation · CORE SHIPPED, restructure deferred
`COMPLIANCE_CONTRACT` (`compliance_for`) — the batch's #1 fix, wired into the LLM image path + the reel
(both had no compliance); `IMAGE_NEGATIVE_CONTRACT` / `_TERMS` promoted from the per-call negative. The
best image prompt (the grounded 'lead' assembly + the anti-gel-lighting rule) and the archetype enum in
`build_design_spec` are kept. **Deferred:** collapse the 5 vertical prompts → 3 scene shapes; strip the
"award-winning" primers. **Ticket:** `bake_text` reachability (it bakes Latin the OCR gate rejects).

### Batch 4 — Reel · KEYSTONE SHIPPED, restructure deferred
The reel director's "SENIOR CREATIVE DIRECTOR with 15 years TikTok" persona — the most homogenizing
primer in the catalog — replaced by `CRAFT_CONTRACT` + a **brand-derived register** (luxury=unhurried,
youth=fast, clinic=calm; no default hype pacing). The ad-spine, the SUBJECT+STYLE+CAMERA+LIGHTING+MOTION
formula, BANNED WORDS, FRAMING, and "OBSESSED with realism" are kept. **Deferred:** `_MOTION_GUIDANCE` →
motion shapes; `_MOTION_TAIL` → `MOTION_CONTRACT`; re-key `_DELIVERY_EG`. **Measurement-locked (protected):**
`check_scene` scene-QA — the live D-9 gate; only additive/benchmarked changes.

### Batch 5 — Competitor & Strategy · CLEANEST (1 refine)
Grounded-by-construction, nothing to strip — the proof the canonical-block approach works (these prompts
independently practice `GROUNDING_CONTRACT` without having been told to). The review-theme extractor
(evidence floor + review-ID citation), the TOWS anchor-id auditability, the reject-only competitor judge
("when unsure DROP, never add" = the no-hallucination invariant as a rule) are all reference-grade **keeps**.
**One refine (shipped):** the content-calendar prompt now weights trend vs evergreen explicitly (trends
shape timing/angle of grounded content, never invent).

---

## Two cross-subsystem contradictions surfaced (only a full-catalog audit catches these)

1. **`bake_text` vs the OCR gate** — the static art-direction fallback can bake Latin text into an image
   that Batch 2's OCR fidelity gate exists to *reject*. Two parts of the codebase working against each
   other. **Ticketed** (confirm `bake_text=True` is still reachable now that oneshot is primary; if not, retire it).
2. **malformed-Arabic-but-no-Latin poster passing QA** — the QA gate only checked "no Latin". **Fixed**
   (Batch 2 `script_wellformed`).

---

## Deliberately NOT touched — measurement-locked gates

- `grounding/subject_judge._SYSTEM` (same-subject judge, 98% live-verified) — Batch 1. Only the truncation
  was improved (short claims byte-identical).
- `reel/scene_qa.check_scene` (the live product-fidelity gate) — Batch 4.

Tuned, validated wording is not refactored on aesthetic grounds. Any change is additive + benchmarked.

---

## Measure-first tickets (rule 6 — four measurements before four locks)

| Ticket | From | What to measure | Blocker |
|---|---|---|---|
| oneshot negative → positive reframe | B2 | OCR pass-rate on the benchmark before locking | Gemini billing |
| scene-QA `compliant` criterion | B4 | pass-rate delta on the live gate | Gemini billing |
| `bake_text` reachability | B3 | is `bake_text=True` still reachable in production | code trace |
| cross-lingual RAG recall | B1 | `_GROUP_QUERIES` top-K recall on Arabic-dominant sites | Gemini billing |

The three billing-blocked tickets are pending Gemini billing (dunning-deny on project 106225033713).

---

## Implementation status (2026-07-07)

**Shipped & tested (suite 1175):** all of Batch 1, Batch 2, Batch 5; Batch 3 `COMPLIANCE_CONTRACT` +
image-negative consolidation; Batch 4 reel persona strip.

**Deferred to a post-U1 cleanup unit** (billing now makes the 50+-assertion rewrite safe to verify against
the live pipeline): the two vertical→shape restructures (art, motion), `MOTION_CONTRACT`, the remaining
"award-winning" primer strips, and `build_creative_prompt`'s surreal-default alignment.
