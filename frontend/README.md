# Marketing Strategist — Frontend (Day 2)

Next.js 14 + TypeScript + Tailwind + shadcn primitives.

## Setup

```bash
cd frontend
npm install
cp .env.local.example .env.local
# Edit .env.local if your backend isn't on http://localhost:8000
npm run dev
# → http://localhost:3000
```

The backend must be running separately:

```bash
# In another terminal, from the repo root
uvicorn api.main:app --reload --port 8000
```

## Fixture mode (no backend needed)

```
http://localhost:3000/?demo=sp-clinic
```

Loads `fixtures/sp-clinic.json` as if the live pipeline had returned
it. The timeline renders as fully complete with synthesized events.
**Replace `fixtures/sp-clinic.json` with your real `business_profile.json`
output for the most accurate demo.**

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Backend base URL |
| `NEXT_PUBLIC_ENABLE_POSTER_TAB` | `true` | Show the Poster Studio placeholder tab |

## Architecture

```
app/
├── layout.tsx          # root layout + fonts
├── page.tsx            # the one MVP page (URL → timeline → tabs)
└── globals.css         # Tailwind + shadcn tokens

components/
├── ui/                 # shadcn primitives (button, input, card, tabs, dialog, badge, skeleton)
├── url-bar.tsx
├── pipeline-timeline.tsx   # accepts arbitrary stage list, no hard-coded length
├── tabs-shell.tsx          # 3 MVP tabs + optional Poster Studio
├── profile-card.tsx
├── offerings-list.tsx
├── visual-identity-card.tsx
├── value-props-and-trust.tsx
├── diagnostics-panel.tsx
├── evidenced-field.tsx     # the killer demo primitive: every claim → its source
└── evidence-dialog.tsx     # the modal that displays block_id + page_url + quote

lib/
├── types.ts            # TS mirrors of Pydantic schemas
├── api-client.ts       # typed fetch wrappers
├── fixtures.ts         # ?demo= loader + synthesized events
└── utils.ts            # cn(), formatters

hooks/
└── use-job-stream.ts   # SSE subscription

fixtures/
└── sp-clinic.json      # static profile JSON for demo mode
```

## Future tabs (not in MVP)

The architecture is intentionally structured so the following can be
added without refactoring existing components:

- **PosterStudio** — top-level tab (placeholder shown when
  `NEXT_PUBLIC_ENABLE_POSTER_TAB=true`)
- **PosterBriefPanel** — grounded poster brief with evidence
- **ImagePromptPanel** — the prompt sent to the image model + provenance
- **GeneratedBackgroundPreview** — text-free background image
- **FinalPosterPreview** — Pillow-composed final PNG
- **PromptSourcesPanel** — evidence chain for the poster brief

The pipeline timeline already accepts the future stages
(`poster_brief`, `image_gen`, `compose`) via the `Stage` type union;
filtering happens by stage list, not by enum membership. Adding the
new stages will be additive: extend `MVP_STAGES` or pass a different
list to `<PipelineTimeline />`.

The `<EvidencedField />` + `<EvidenceDialog />` primitives are
intentionally generic and will be reused for poster brief claims (which
will cite the same `block_id`s as the profile).

## Verification checklist

After `npm run dev`:

- [ ] `http://localhost:3000` shows the URL input and empty state
- [ ] `http://localhost:3000/?demo=sp-clinic` shows the full SP Clinic profile with timeline fully done
- [ ] Clicking "view evidence" on any claim opens the dialog with block_id, page_url, and quote
- [ ] Tabs switch cleanly between Profile, Evidence, Diagnostics
- [ ] Poster Studio tab is visible (default) and shows the "Coming next" placeholder
- [ ] Submit a real URL → timeline streams events live → profile appears when done

## What's NOT in Day 2

- No tests (UI will change daily for a week)
- No mobile-perfect layout (responsive enough, not designed)
- No authentication / multi-user
- No actual Poster Studio generation
- No history / past runs page
- No frontend build in CI

These are Day 6 polish or post-MVP.
