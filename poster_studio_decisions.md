# Poster Studio — Design Decisions

> **Status of this document:** compiled from our past conversations (the
> "creative authenticity" / Poster Studio audit thread and the related
> project summaries). Items I have clear evidence for are stated plainly.
> Items that were *not* fully locked are marked **⚠ TO CONFIRM** — don't
> treat those as settled.
>
> **Project rule that governs everything here:** zero LLM hallucination.
> Every piece of text on the poster must be backed by evidence from the
> scrape (an `EvidenceItem` with `block_id` + `page_url` + `quote`). A
> field with no surviving evidence does not get invented — it stays empty
> or the layout adapts around its absence.

---

## 1. The problem we are replacing (current state)

The current poster generator is **template-driven and not "creative."**
Concretely, what's wrong with it today:

- **Same 9 elements, always in the same order.** Every poster is the
  identical skeleton regardless of the business.
- **"Layouts" are just x/y offsets.** Switching layout only nudges element
  coordinates; it doesn't change the composition in any meaningful way.
- **The OpenAI image is used only as a dimmed BACKGROUND.** It's literally
  coded as a passive `BACKGROUND` layer behind everything, darkened so text
  is readable on top. The image does no creative work.
- **Everything is UPPERCASE.**
- **The headline is duplicated twice** on the poster.
- **There is no LLM anywhere in the creative pipeline.** Nothing is making
  layout or composition decisions; it's all fixed code.

The verdict from the audit: this produces generic, template-looking output,
not designed campaign posters.

---

## 2. The agreed redesign — core direction

Four decisions form the spine of the new Poster Studio:

1. **`CreativePlan` replaces the fixed layouts.** Instead of one hardcoded
   skeleton with x/y offsets, a `CreativePlan` describes the composition for
   *this specific* poster (see §3).

2. **The image becomes a real campaign scene with defined empty composition
   zones** — **not** a passive dimmed background. The image is generated
   *with intentional negative space* (e.g. a clean area on the left, or top
   third) where text will later be placed. The image carries the creative
   weight; the text sits in the zones the image left open.

3. **No Pillow.** Pillow is explicitly ruled out going forward (rejected as
   ugly / not good enough for the visual quality we want). This applies to
   the whole project, not just the poster.

4. **Zero hallucination on all poster text fields.** Every text field on the
   poster (headline, offer, contact, etc.) must trace to scraped evidence.
   No invented copy. (This is the project's core philosophy applied to the
   poster specifically.)

---

## 3. Architecture — `CreativePlan`

`CreativePlan` is the object that replaces the old fixed layout. It describes,
per poster:

- which text fields are present (driven by what survived evidence validation),
- where they go relative to the image's composition zones,
- the visual treatment.

**⚠ TO CONFIRM — the exact field list of `CreativePlan`.** The decision that
it *exists* and *replaces fixed layouts* is firm. The precise schema (field
names, the full set of composition-zone descriptors) was not nailed down in
the conversations I could recover. Define this when implementation starts,
and keep it evidence-driven (fields appear only when their evidence exists).

---

## 4. Rendering — HTML/CSS via Playwright

- **Renderer = HTML/CSS rendered to an image via a Playwright screenshot.**
  This was set as the **default** approach. **SVG was the considered
  alternative.**
  - **⚠ TO CONFIRM:** HTML/CSS-via-Playwright was chosen as default but I am
    not 100% certain it was *finally locked* over SVG. Confirm before building
    the renderer. (Leaning HTML/CSS+Playwright.)

- **Text lives in a separate HTML/CSS layer on top of the AI image.** The
  image is one layer; the text is composited over it via HTML/CSS. This is
  what makes Arabic text render correctly (see §5 for why this separation is
  non-negotiable).

- **No Pillow** anywhere in the rendering path (restating §2.3 because it's a
  rendering-path decision too).

---

## 5. Image generation — `ImageProvider` + Vertex AI

- **The AI image is generated with NO text in the prompt.** All diffusion
  image models fail at rendering legible text, and they fail *especially* hard
  at Arabic. So the generated image is **purely the visual scene/background**
  with composition zones — and **all text is added afterward** in the HTML/CSS
  layer (§4). This is the reason text and image are separate layers.

- **Image model: Imagen / Gemini via Vertex AI.** Chosen target. There is a
  **$300 free credit** available on Vertex AI. **This is deferred** — not the
  immediate step.

- **Build an `ImageProvider` protocol** that mirrors the existing `Caller`
  protocol pattern in the codebase. Same idea as how the LLM caller is
  abstracted: a clean protocol so the image backend (Vertex/Imagen, or a stub
  for offline testing) is swappable. This keeps offline/mock testing possible
  without burning credits.

---

## 6. Zero-hallucination contract for poster text

Restating the binding rule, because it's the whole point of the project:

- Every text field on the poster must come from a validated `EvidenceItem`
  (`block_id` + `page_url` + `quote`) produced by the scrape → BusinessProfile
  pipeline.
- If a field has no surviving evidence, it is **not** invented. The
  `CreativePlan` adapts to its absence (the composition works without it).
- The poster is downstream of the same evidence chain as everything else; it
  does not get a hallucination exception for the sake of "looking finished."

---

## 7. Known bug to fix in the poster code

- **`phones_e164` serialization bug in `poster/from_profile.py`.**
  The poster must read the **`phones` list of `PhoneChannel` dicts** and
  prefer each entry's **`.e164`**, falling back to **`.raw`** — it must **not**
  read the unserialized `phones_e164` `@property` (which doesn't survive
  serialization and comes back wrong/empty). This was flagged in an external
  code review and confirmed as a real bug.

---

## 8. Related files / references

- **`poster_studio_senior_audit.md`** — the full audit that produced these
  decisions. It should live in the repo so Claude Code can read it directly.
  **⚠** I'm not certain this file is actually present in the repo right now —
  verify. If it's missing, this document carries the substance.
- **`poster/from_profile.py`** — where the `phones_e164` bug lives (§7).
- **`CLAUDE.md`** (repo root) — architecture, standing rules, backlog.

---

## 9. Open / to-confirm items (collected)

1. **⚠ Renderer final choice:** HTML/CSS-via-Playwright (default) vs SVG. Lean
   HTML/CSS+Playwright; confirm before building.
2. **⚠ `CreativePlan` exact schema:** existence + role are decided; precise
   field list is not. Define at implementation, evidence-driven.
3. **⚠ Presence of `poster_studio_senior_audit.md` in the repo:** verify.
4. **Vertex AI / Imagen integration:** deferred (the $300 credit is available
   when you pick it up).

---

*If anything above contradicts what you remember deciding, your memory of the
live decision wins — flag it and I'll correct this doc.*
