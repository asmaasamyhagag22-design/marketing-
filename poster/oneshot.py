"""ONE-SHOT designed poster — PILOT (step ب of the TrendPulse `media/` review, 2026-07-03).

TrendPulse's posters look "designed" because a Gemini IMAGE model composes the WHOLE creative —
layout + typography + graphics — in one shot, instead of our photo + HTML text overlay. Our
overlay architecture exists because Imagen garbles Arabic; the nano-banana-class Gemini image
models render text far better — but "better" is a claim to MEASURE, not assume.

This module is the pilot + its FIDELITY GATE. It is NOT wired into the poster pipeline:
`benchmark/measure_oneshot_poster.py` measures Arabic/English verbatim-text fidelity first
(rule 2), and only a measured pass earns it a pipeline mode.

GROUNDING: the text the model is asked to render is OUR already-Ledger-gated copy, passed
VERBATIM. The new risk is the model ALTERING/garbling that copy inside the image — so every
render is verified: a vision model reads the rendered image back and `text_fidelity` compares
what was rendered against what was requested (Arabic-aware normalization). A render that fails
the gate must never ship.

Vertex notes (probed live 2026-07-03 on project image-498715): `gemini-3-pro-image-preview` and
`gemini-3.1-flash-image-preview` resolve ONLY on location="global"; `gemini-2.5-flash-image`
also works on us-central1.
"""
from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path
from typing import Any, Optional

DEFAULT_ONESHOT_MODEL = os.getenv("ONESHOT_IMAGE_MODEL", "gemini-3.1-flash-image-preview")
DEFAULT_LOCATION = "global"

# tashkeel (064B-065F) + superscript alef (0670) + tatweel (0640) + Quranic marks (06D6-06ED)
_TASHKEEL_RE = re.compile("[ً-ٰٟـۖ-ۭ]")
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)


def _norm_text(s: str) -> str:
    """Arabic-aware normalization for verbatim comparison: strip tashkeel/tatweel, unify
    alef/ya/ta-marbuta glyph variants (a transcriber/renderer legitimately writes ة as ه),
    drop punctuation, collapse whitespace, casefold. Rendering that survives THIS normalization
    unchanged is 'verbatim' for the gate; any dropped/added/altered WORD is not."""
    s = unicodedata.normalize("NFKC", str(s or ""))
    s = _TASHKEEL_RE.sub("", s)
    s = (s.replace("أ", "ا").replace("إ", "ا")   # أ / إ -> ا
         .replace("آ", "ا").replace("ٱ", "ا")    # آ / ٱ -> ا
         .replace("ى", "ي").replace("ئ", "ي")    # ى / ئ -> ي
         .replace("ؤ", "و")                                 # ؤ -> و
         .replace("ة", "ه"))                                # ة -> ه
    s = _PUNCT_RE.sub(" ", s)
    return " ".join(s.casefold().split())


def build_oneshot_prompt(copy: dict, *, brand_name: str = "", palette_names: str = "",
                         dna_lines: str = "", rtl: bool = False, has_logo: bool = False,
                         heading_font: str = "", body_font: str = "",
                         single_message: str = "", visual_idea: str = "",
                         n_products: int = 0) -> str:
    """The one-shot design brief. The copy fields are OUR gated text and must be rendered
    EXACTLY — the prompt forbids inventing, translating or 'improving' any word, and forbids
    ANY other text in the image (the TrendPulse render lets the model add stray labels;
    zero-hallucination does not)."""
    headline = (copy.get("headline") or "").strip()
    sub = (copy.get("subheadline") or "").strip()
    cta = (copy.get("cta") or "").strip()
    parts = [
        "Design a COMPLETE, premium social-media advertising poster (portrait 4:5, 1080x1350):",
        "a professional ad an agency would ship — intentional layout, strong typographic",
        "hierarchy, a designed background scene, generous negative space. NOT a photo with",
        "text pasted on top.",
    ]
    if brand_name:
        parts.append(f"Brand: {brand_name}.")
    # ONE IDEA, not a collage (measured: without a concept the model crammed every
    # delivery trope — drone + robot + couch + floating products — into one frame).
    if single_message:
        parts.append(f"THE CONCEPT — the poster expresses exactly THIS ONE idea: {single_message}.")
    if visual_idea:
        parts.append(f"THE SCENE: {visual_idea}. Execute THIS scene only.")
    parts.append(
        "ART DIRECTION (mandatory): ONE clear focal subject; at most 2-3 supporting "
        "elements; generous calm negative space — 'less is more', never a cluttered "
        "collage. Choose a clear layout: the text lives in ONE calm, low-detail zone "
        "(e.g. the top or bottom third) and the subject in another. TEXT CONTRAST is "
        "non-negotiable: the copy must be instantly readable at a glance — light text "
        "on a dark calm area or dark text on a light calm area; if needed, design a "
        "soft panel or gradient behind the text; NEVER place text over busy detail."
    )
    if n_products:
        # The owner's radical fix: real assets composite correctly (proven by the
        # logo) — so the products in the scene are the brand's REAL product PHOTOS,
        # with their REAL labels, not model-invented packaging.
        parts.append(
            f"REAL PRODUCT PROPS: the {n_products} image(s) attached AFTER the logo are "
            "the brand's REAL products, photographed from its own store. Place one or "
            "two of them naturally in the scene as physical props — packaging shape, "
            "label text, colors and proportions EXACTLY as photographed; do NOT redraw, "
            "restyle, relabel, translate or 'improve' them. NO other products, boxes or "
            "packaging may appear in the scene."
        )
    parts.append(
        "BRAND INTEGRITY (mandatory): the brand's logo/name may appear ONLY as the "
        "attached real logo asset placed in a corner"
        + (" and on the attached real products exactly as photographed" if n_products else "")
        + ". NEVER paint or print the brand name onto other objects, devices, robots, "
        "vehicles, bags, screens or signage — do NOT invent branded objects or services "
        "the brand may not have."
        + ("" if n_products else " If generic products appear they must be COMPLETELY "
           "UNLABELED (no text, no pseudo-text, no gibberish lettering on any packaging).")
        + " Every object in the scene must belong to this business's real world — nothing "
        "that would look out of place in its actual category."
    )
    if palette_names:
        # A weak one-line palette hint was IGNORED by the model (measured: daturial's
        # scraped orange arrived in the brief and the render came out navy/teal). The
        # palette is a mandate with explicit roles, by NAME (raw hex in an image
        # prompt gets baked into the artwork as text — documented lesson).
        parts.append(
            f"COLOR SYSTEM — MANDATORY: build the entire design on the brand palette: "
            f"{palette_names}. The FIRST color is the brand's primary — make it "
            "unmistakably present (the CTA button, key accents, or a dominant color "
            "field). Neutrals (black/white/grey) may support but never replace the "
            "brand colors. Do NOT invent a different color scheme."
        )
    if dna_lines:
        parts.append(f"The brand's own visual language (match it): {dna_lines}")
    if heading_font or body_font:
        # The brand's REAL website typography — steer the poster's type character toward
        # it (identity signal that was captured but never reached any generation call).
        fonts = " / ".join(f for f in (heading_font, body_font) if f)
        parts.append(
            f"Brand typography: the website uses '{fonts}' — design the poster's type "
            "in the same typographic character (weight, feel), so it reads as this brand."
        )
    parts.append("RENDER THIS TEXT — EXACTLY, character for character, no word added, removed,")
    parts.append("translated or 'improved':")
    if headline:
        parts.append(f'HEADLINE (dominant, hero typography): "{headline}"')
    if sub:
        parts.append(f'SUBHEADLINE (smaller, supporting): "{sub}"')
    if cta:
        parts.append(f'CALL-TO-ACTION (on a pill button): "{cta}"')
    if rtl:
        parts.append(
            "The text is ARABIC: right-to-left, correctly SHAPED AND CONNECTED letters "
            "(never isolated/disconnected glyphs, never mirrored), professional modern Arabic "
            "typography."
        )
    if has_logo:
        parts.append(
            "The attached image is the brand's REAL logo: place it cleanly in a top corner, "
            "UNCHANGED — do not redraw, restyle, recolor or retype it."
        )
    parts.append(
        "ABSOLUTELY NO other text, words, letters, numbers, watermarks or invented labels "
        "anywhere in the image — ONLY the exact lines specified above."
    )
    return "\n".join(parts)


_CLIENTS: dict[str, Any] = {}   # retained — a temporary client gets GC'd mid-request (measured)


def _client(location: str):
    if location not in _CLIENTS:
        from google import genai
        _CLIENTS[location] = genai.Client(
            vertexai=True,
            project=os.environ["GOOGLE_CLOUD_PROJECT"],
            location=location,
        )
    return _CLIENTS[location]


def generate_oneshot_poster(prompt: str, out_path: str | Path, *,
                            model: str = DEFAULT_ONESHOT_MODEL,
                            location: str = DEFAULT_LOCATION,
                            logo_bytes: Optional[bytes] = None,
                            logo_mime: str = "image/png",
                            product_images: Optional[list[tuple[bytes, str]]] = None,
                            client: Any = None) -> Path:
    """ONE generate_content call -> the complete designed poster PNG. The real brand logo is
    passed as an INPUT IMAGE part when available (these models composite an attached image;
    a text description could never reproduce the real mark), and `product_images` — the
    brand's REAL product photos — follow it as scene props with their REAL labels. Raises on
    failure — the caller decides the fallback; nothing here ships unmeasured."""
    from google.genai import types

    cl = client or _client(location)
    contents: list[Any] = [prompt]
    if logo_bytes:
        contents.append(types.Part.from_bytes(data=logo_bytes, mime_type=logo_mime))
    for data, mime in (product_images or [])[:2]:
        if data:
            contents.append(types.Part.from_bytes(data=data, mime_type=mime or "image/jpeg"))
    resp = cl.models.generate_content(
        model=model,
        contents=contents,
        config=types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]),
    )
    for cand in (resp.candidates or []):
        for part in (cand.content.parts or []):
            inline = getattr(part, "inline_data", None)
            if inline and (inline.mime_type or "").startswith("image/"):
                out_path = Path(out_path)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                data = inline.data
                if isinstance(data, str):
                    import base64
                    data = base64.b64decode(data)
                out_path.write_bytes(data)
                return out_path
    raise RuntimeError(f"one-shot poster: {model} returned no image")


def read_rendered_text(image_path: "str | Path | bytes", caller: Any) -> list[str]:
    """Vision read-back: what text is ACTUALLY rendered in an image (the gate's evidence;
    also used to read the REAL label text off an attached product photo, so those lines
    become ALLOWED extras). Accepts a path or raw bytes. Returns the seen lines; [] on
    failure."""
    from pydantic import BaseModel

    class _SeenText(BaseModel):
        lines: list[str] = []

    try:
        data = image_path if isinstance(image_path, bytes) else Path(image_path).read_bytes()
        resp, _u = caller(
            "You are a CHARACTER-EXACT OCR reader. You copy text pixel-for-pixel; you NEVER "
            "correct spelling, dialect, or grammar.",
            "List EVERY piece of text visible in this poster image, one entry per distinct "
            "text element, top to bottom, copied EXACTLY letter-for-letter as printed. "
            "CRITICAL for Arabic: preserve DIALECTAL spellings exactly (if the poster prints "
            "أكتر with ت, write أكتر — do NOT 'fix' it to أكثر); count the dots — ت has 2 "
            "dots, ث has 3; ة vs ه as printed. Empty list if there is no text.",
            _SeenText,
            group_name="oneshot_ocr",
            images=[(data, "image/png")],
        )
        return [str(l).strip() for l in (getattr(resp, "lines", []) or []) if str(l).strip()]
    except Exception:
        return []


def text_fidelity(expected: dict, seen_lines: list[str]) -> dict:
    """The gate verdict: each requested copy field must appear VERBATIM (normalized) in the
    rendered image, and any rendered line that matches no expected field is flagged as EXTRA
    text (reported for the measurement; the logo's own fine print will show up here too).
    Returns {'fields': {name: bool}, 'rate': float, 'extra_lines': [...]}. rate=1.0 with no
    expected fields (nothing to verify)."""
    seen_norm = [_norm_text(l) for l in (seen_lines or [])]
    joined = " ".join(seen_norm)
    fields: dict[str, bool] = {}
    for name, text in (expected or {}).items():
        text = (text or "").strip()
        if not text:
            continue
        fields[name] = _norm_text(text) in joined
    expected_norms = [_norm_text(t) for t in (expected or {}).values() if (t or "").strip()]
    extra = [l for l, n in zip(seen_lines or [], seen_norm)
             if n and not any(n in e or e in n for e in expected_norms)]
    rate = (sum(fields.values()) / len(fields)) if fields else 1.0
    return {"fields": fields, "rate": round(rate, 3), "extra_lines": extra}
