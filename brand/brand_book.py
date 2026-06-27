"""BrandBook — a one-time, multimodal understanding of a brand.

The creative studio used to re-derive the brand from text fields on every poster/reel.
That is shallow (hex codes + font names) and repetitive. Instead, ONCE per brand, a
multimodal model (Gemini 2.5 Pro, vision) actually LOOKS at the brand's REAL images,
reads its scraped profile, and folds in deep web research, then emits a single
structured **brand reference** that every later generation reads from — cheaper,
more consistent, and far deeper.

HONESTY / GROUNDING (unchanged premise):
  * Facts come only from the scraped profile + sourced web research (each fact keeps a
    URL). The model never invents facts.
  * The VISUAL read (mood, photography style, which real image is the best background)
    is design judgement over what the model actually SEES — not a factual claim.
  * Degrades gracefully: no caller -> a profile-only book; no images -> text-only read;
    no provider -> no research facts. Never raises for ordinary failures.

Side-effect free: never loads .env / mutates os.environ (entry points inject the
caller + provider), same discipline as scraper/deep_search.py and poster/brand_research.py.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from poster.brand_research import BrandFact, research_brand


# ---------------------------------------------------------------------
# Public schema (the reference file)
# ---------------------------------------------------------------------

class BrandVisualIdentity(BaseModel):
    aesthetic: str = ""              # overall visual character in a sentence
    mood: str = ""
    color_story: str = ""            # how the palette is actually used
    typography_character: str = ""
    photography_style: str = ""      # what the brand's real photos look like
    best_background_image_url: Optional[str] = None   # the strongest real bg, or None
    best_background_reason: str = ""
    recommended_text_color: str = "light"             # 'light' or 'dark' over that bg


class BrandBook(BaseModel):
    business_name: str
    used_vision: bool = False        # True when a model actually SAW the images
    images_seen: list[str] = Field(default_factory=list)
    palette_hex: list[str] = Field(default_factory=list)
    primary_color: Optional[str] = None
    visual_identity: BrandVisualIdentity = Field(default_factory=BrandVisualIdentity)
    voice: str = ""
    audience: str = ""
    positioning: str = ""
    sourced_facts: list[BrandFact] = Field(default_factory=list)
    note: Optional[str] = None


# ---------------------------------------------------------------------
# LLM structured-output model (no numeric/range constraints -> strict-mode safe)
# ---------------------------------------------------------------------

class _BrandBookResponse(BaseModel):
    aesthetic: str
    mood: str
    color_story: str
    typography_character: str
    photography_style: str
    best_background_index: int       # index into the shown images, or -1 to generate
    best_background_reason: str
    recommended_text_color: str      # "light" or "dark"
    voice: str
    audience: str
    positioning: str


# ---------------------------------------------------------------------
# Profile helpers
# ---------------------------------------------------------------------

def _fv(profile: dict, key: str) -> str:
    v = (profile or {}).get(key)
    if isinstance(v, dict):
        v = v.get("value")
    return "" if v is None else str(v)


def _brand_image_urls(profile: dict, max_images: int) -> list[str]:
    """Real on-page PHOTOS only (logos are identity, not a background)."""
    vis = (profile or {}).get("visual") or {}
    urls: list[str] = []
    for c in (vis.get("content_images") or []):
        src = c.get("src") if isinstance(c, dict) else c
        if src and src not in urls:
            urls.append(src)
    return urls[:max_images]


def _fetch_images(urls: list[str], *, timeout: int = 8, max_bytes: int = 4_000_000) -> list[tuple]:
    """(url, bytes, mime) for each fetchable raster image. SSRF-guarded; skips SVG."""
    from scraper.url_utils import is_safe_public_url
    from poster.template import _open_image_url

    out: list[tuple] = []
    for u in urls:
        if not is_safe_public_url(u):
            continue
        try:
            with _open_image_url(u, timeout) as r:
                ctype = (r.headers.get("Content-Type") or "").lower()
                data = r.read(max_bytes)
        except Exception:
            continue
        if not data or "svg" in ctype or u.lower().endswith(".svg"):
            continue
        low = u.lower()
        if "png" in ctype or low.endswith(".png"):
            mime = "image/png"
        elif "webp" in ctype or low.endswith(".webp"):
            mime = "image/webp"
        else:
            mime = "image/jpeg"
        out.append((u, data, mime))
    return out


# ---------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------

def build_brand_book(
    profile: dict[str, Any],
    *,
    caller: Any = None,
    search_provider: Any = None,
    max_images: int = 6,
    with_research: bool = True,
    _image_fetcher=_fetch_images,   # injectable for tests (no network)
) -> BrandBook:
    """Build the BrandBook for one business profile.

    `caller` should be a multimodal Caller (Gemini). `search_provider` is a
    competitor.search_providers provider (resolved by default when None inside
    research_brand). Returns a BrandBook; never raises for ordinary failures.
    """
    name = _fv(profile, "name") or "the brand"
    vis = (profile or {}).get("visual") or {}
    palette = [h for h in (vis.get("palette_hex") or []) if h][:6]
    primary = vis.get("primary_color") or (palette[0] if palette else None)

    # Persona block (verbatim scraped lines).
    try:
        from poster.art_director import _persona_lines
        persona = _persona_lines(profile)
    except Exception:
        persona = ""

    # 1) Sourced facts via deep research (real, each with a URL).
    facts: list[BrandFact] = []
    if with_research and caller is not None:
        try:
            research = research_brand(name, persona=persona, provider=search_provider, caller=caller)
            facts = list(research.facts)
        except Exception:
            facts = []

    # 2) Real brand images for the model to SEE.
    image_urls = _brand_image_urls(profile, max_images)
    images = _image_fetcher(image_urls) if image_urls else []

    # 3) No caller -> a profile-only book (honest, shallow). No images -> text-only read.
    if caller is None:
        return BrandBook(
            business_name=name, used_vision=False, palette_hex=palette, primary_color=primary,
            sourced_facts=facts,
            visual_identity=BrandVisualIdentity(
                color_story=("palette: " + ", ".join(palette)) if palette else "",
                typography_character=_fv(profile, "tone_of_voice"),
            ),
            voice=_fv(profile, "tone_of_voice"),
            audience=_fv(profile, "audience_type"),
            positioning=_fv(profile, "tagline"),
            note="no caller: profile-only brand book (no vision)",
        )

    facts_block = "\n".join(f"- {f.text}  (source: {f.source_url})" for f in facts[:8]) or "(none)"
    seen_urls = [u for (u, _b, _m) in images]
    img_block = "\n".join(f"[{i}] {u}" for i, u in enumerate(seen_urls)) or "(no images available)"

    system = (
        "You are a brand strategist AND art director. You are shown the brand's REAL "
        "images (in order, index 0..N) and given its scraped profile + sourced facts. "
        "Analyze the brand and produce a structured brand reference.\n"
        "- Describe the VISUAL identity from what you actually SEE: aesthetic, mood, how "
        "the palette is used (color_story), typography character, and photography_style.\n"
        "- best_background_index: pick the index of the SINGLE image that would make the "
        "strongest poster/reel background — a real photo of the place/people/product. "
        "NEVER pick a logo, icon, QR code, or flat graphic. Use -1 if none is suitable.\n"
        "- recommended_text_color: 'light' or 'dark' for legibility over that image.\n"
        "- voice / audience / positioning: ground these in the profile + facts; write them "
        "in the brand's own language (Arabic stays Arabic). Never invent facts."
    )
    user = (
        f"Brand: {name}\n"
        + (f"Profile (verbatim):\n{persona}\n" if persona else "")
        + f"\nSourced facts:\n{facts_block}\n"
        + f"\nImages shown to you (by index):\n{img_block}\n"
    )

    visual = BrandVisualIdentity(
        color_story=("palette: " + ", ".join(palette)) if palette else "",
    )
    used_vision = False
    note: Optional[str] = None

    if images:
        try:
            resp, _u = caller(
                system, user, _BrandBookResponse, group_name="brand_book",
                images=[(b, m) for (_u2, b, m) in images],
            )
            idx = resp.best_background_index
            bg_url = seen_urls[idx] if isinstance(idx, int) and 0 <= idx < len(seen_urls) else None
            visual = BrandVisualIdentity(
                aesthetic=resp.aesthetic.strip(),
                mood=resp.mood.strip(),
                color_story=resp.color_story.strip() or visual.color_story,
                typography_character=resp.typography_character.strip(),
                photography_style=resp.photography_style.strip(),
                best_background_image_url=bg_url,
                best_background_reason=resp.best_background_reason.strip(),
                recommended_text_color=("dark" if resp.recommended_text_color.strip().lower() == "dark" else "light"),
            )
            used_vision = True
            return BrandBook(
                business_name=name, used_vision=True, images_seen=seen_urls,
                palette_hex=palette, primary_color=primary, visual_identity=visual,
                voice=resp.voice.strip(), audience=resp.audience.strip(),
                positioning=resp.positioning.strip(), sourced_facts=facts,
            )
        except Exception as exc:
            note = f"vision call failed ({type(exc).__name__}); text-only read"

    # Text-only read (no images, or vision failed): still useful + honest.
    return BrandBook(
        business_name=name, used_vision=used_vision, images_seen=seen_urls,
        palette_hex=palette, primary_color=primary, visual_identity=visual,
        voice=_fv(profile, "tone_of_voice"), audience=_fv(profile, "audience_type"),
        positioning=_fv(profile, "tagline"), sourced_facts=facts,
        note=note or "no fetchable images: text-only brand book",
    )


# ---------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------

def save_brand_book(book: BrandBook, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(book.model_dump_json(indent=2), encoding="utf-8")
    return p


def load_brand_book(path: str | Path) -> BrandBook:
    return BrandBook.model_validate_json(Path(path).read_text(encoding="utf-8"))
