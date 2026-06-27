# Project Reference — AI Marketing Campaign Strategist

> Status legend:  **[BUILT]** = working & tested today · **[PARTIAL]** = working, being
> deepened · **[PLANNED]** = agreed design, next to build.

---

## 0. What the product delivers (the MARKETING outcome)

The user runs a brand's marketing. She publishes **posts** (an image **+ a caption /
description + hashtags**) and **reels**, on a schedule. This product turns **one business
URL** into a ready‑to‑publish **campaign**:

```
ONE URL  ──▶  a Brand Book (deep understanding)  ──▶  a CAMPAIGN:
   • multiple POSTS   = on‑brand image  +  ad caption/description  +  hashtags
   • REELS            = vertical video (from the brand's real footage/photos)
   • a CONTENT CALENDAR that schedules them over time
```

**Core principle — two truth domains:**
- **FACTS** (claims, numbers, offerings, contacts, the logo) must trace to a real source.
- **DESIGN + COPY** are free — the model is the art director & copywriter.
The system keeps facts grounded while creativity is unbounded. *Zero hallucination on facts.*

---

## 1. End‑to‑end pipeline

```
URL
 ▼  [1] SCRAPER            Playwright + trafilatura            → ScrapeManifest      [BUILT]
 ▼  [2] BUSINESS PROFILE   rules + LLM, evidence‑validated     → BusinessProfile     [BUILT]
 ├─▶ [3] COMPETITORS       Places / web SERP                  → cited SWOT          [BUILT]
 ▼  [4] BRAND BOOK ★       multimodal: UNDERSTAND the brand    → BrandBook (file)    [BUILT]
 ▼  [5] CAMPAIGN GENERATOR reads the Brand Book                → posts + reels       [PARTIAL]
 │      ├─ POSTER image   design spec → on‑brand GENERATED visual                    [BUILT]
 │      ├─ CAPTION/desc   ad copy + hashtags, grounded + sourced                     [PLANNED]
 │      └─ REEL           storyboard → Veo / real‑photo motion → mp4                 [BUILT]
 ▼  [6] CALENDAR / PUBLISH schedule N posts; (later) push to APIs                    [PLANNED]
 ▼  WEB APP                FastAPI + Next.js                                          [BUILT]
```

---

## 2. The Brand Book — **UNDERSTAND, then CREATE** (not copy)  ★

The point of "look at the brand's images" is **NOT** to reuse the website's own photo as
the output — that adds zero value (the client could do that). It is to **UNDERSTAND** the
business from its real images and then **CREATE fresh, on‑brand work**:

- **Done once per brand.** A **multimodal** model (Gemini 2.5 Pro — already vision‑capable)
  SEES the brand's real photos + reads the profile + deep web research, and writes a
  structured **`BrandBook`** file: visual identity (aesthetic, mood, color story, typography
  character, **photography style** — the look of its real people/places), brand **voice**,
  **audience**, **positioning**, and **sourced facts** (each with a URL).
- **Then generation USES that understanding.** The poster/reel/caption are produced *in the
  brand's understood style* — e.g. "real young Egyptian trainees in a modern Cairo tech lab,
  the brand's cool‑blue lighting" — a **newly generated** on‑brand visual. Real photos are a
  **reference for understanding / image‑to‑video conditioning**, not the literal background.
  *(Correction in progress: the first wiring reused the site photo directly; the value is
  understand → generate, so that is being changed to drive generation from the BrandBook.)* [PARTIAL]

---

## 3. Per‑asset pipelines (what goes IN / what comes OUT)

### Post image (poster)  `poster/`
| Step | INPUT (from) | OUTPUT |
|---|---|---|
| `build_poster_brief` | BusinessProfile | `PosterBrief` (facts, logo, palette) |
| `research_brand` → `pick_angle` | brand + web (Serper) + Gemini | a **fresh, sourced** headline angle |
| `build_design_spec` | brief + BrandBook + Gemini | `PosterDesignSpec` (layout, accent, what to show) |
| background | BrandBook understanding → **generated** on‑brand scene (Imagen), real photo as reference | background image (calm zone where text lands) |
| `render_poster_html` → Playwright | brief (facts + real logo) + bg + spec | **Poster PNG 1080×1350** (no URL on image) |

### Caption / description  `[PLANNED]`
| Step | INPUT | OUTPUT |
|---|---|---|
| caption generator | BrandBook (voice) + chosen angle + sourced facts | **publish‑ready caption + hashtags**, grounded (every hard claim has a source) |

### Reel  `reel/`
| Step | INPUT (from) | OUTPUT |
|---|---|---|
| `build_reel_brief` | BusinessProfile | `ReelBrief` |
| `select_brand_photos` (vision) | content_images + identity | curated real on‑brand photos |
| `build_storyboard` | brief + photos + caller | `Storyboard` (timed, RTL‑aware scenes) |
| per‑scene video | each scene + VideoProvider | a clip per scene (Veo motion / Ken‑Burns on real photos) |
| text + logo overlay (Playwright) | scene text + logo | Arabic‑correct overlay PNGs |
| `render_reel` (ffmpeg) | clips + overlays + music | **Reel MP4 1080×1920** |

---

## 4. Open creative gaps (agreed, being worked)  [PARTIAL/PLANNED]
1. **Copy is still repetitive** — `research` gives fresh sourced angles, but it must be ON by
   default and feed every asset so the same line doesn't repeat. **Typography needs life**
   (varied fonts, angled / curved / kinetic treatments) — not one fixed block. [PARTIAL]
2. **Brand Book drives GENERATION** (understand → create), not literal photo reuse. [PARTIAL]
3. **Caption/description + hashtags** per post (the actual thing she publishes). [PLANNED]
4. **Content calendar** (N posts over time) + later **publish via official APIs**. [PLANNED]

---

## 5. Model & infrastructure
- **LLM:** Gemini 2.5 Pro via **Vertex** (GCP credits) — research, brand understanding,
  design, copy. OpenAI is fallback. Token‑heavy extraction → cheaper Gemini Flash. [BUILT]
- **Images:** Vertex **Imagen** · **Video:** Vertex **Veo** / real‑photo Ken Burns. [BUILT]
- **Render:** Playwright (Arabic‑correct overlays) · **ffmpeg** (reel). [BUILT]

## 6. Quality & honesty
- **580 automated tests pass** (LLM/network mocked).
- Verified **live** on Vodafone · WE/Telecom Egypt · Digilians · Qasr Elkbabgi; every change
  measured before/after. **No social‑media scraping** — real social data via official
  marketing APIs (ToS/GDPR‑clean). Sites behind hardened WAFs yield secondary evidence only.
