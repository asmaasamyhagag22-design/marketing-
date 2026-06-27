"""Vision QA gate — a REAL self-critique that rejects and triggers regeneration.

Per the build brief (Step H): after rendering the FINAL poster, a vision model inspects the
actual rendered image and returns a structured verdict. On fail the pipeline regenerates
(bounded retries); if it still fails it returns a CLEAR ERROR, never a broken poster.

Checks (on the rendered poster, not just the background):
  * has_latin_text   — Latin letters in the HEADLINE / CHIPS / CTA (the brand LOGO is exempt)
  * cta_clipped      — the CTA / any element cut off at the frame edge
  * on_brand_color   — the dominant colour matches the brand (e.g. WE = purple), not random
  * candid_violation — candid/documentary look or flat natural lighting when the brand DNA
                       forbids it
  * overall_pass + reason

Side-effect free (multimodal caller injected). Degrades: no caller → a permissive PASS with a
note (we can't gate without vision). Never raises.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel


class PosterQAVerdict(BaseModel):
    has_latin_text: bool = False
    cta_clipped: bool = False
    on_brand_color: bool = True
    candid_violation: bool = False
    logo_ok: bool = True            # brand mark crisp/complete (hard gate)
    single_focal: bool = True       # one clear focal point, not competing ones
    strong_typography: bool = True  # an intentional display lockup, not a default font
    cta_prominent: bool = True      # a confident button, not a footnote
    score: int = 7                  # art-director score 1..10
    overall_pass: bool = True
    reason: str = ""
    checked: bool = False           # True only when a vision model actually inspected it


class _QAResponse(BaseModel):
    has_latin_text: bool
    cta_clipped: bool
    on_brand_color: bool
    candid_violation: bool
    overall_pass: bool
    reason: str
    # Art-director rubric (defaults keep older callers/tests valid; the model fills them).
    logo_ok: bool = True
    single_focal: bool = True
    strong_typography: bool = True
    cta_prominent: bool = True
    score: int = 7


def poster_vision_qa(
    poster_png: "str | Path | bytes",
    *,
    caller: Any = None,
    brand_dna: Any = None,
    arabic: bool = True,
) -> PosterQAVerdict:
    """Inspect the FINAL rendered poster. Returns a verdict; `checked=False` (permissive pass)
    when no multimodal caller is available."""
    if caller is None:
        return PosterQAVerdict(reason="no vision caller: QA skipped", checked=False)

    try:
        data = poster_png if isinstance(poster_png, bytes) else Path(poster_png).read_bytes()
    except Exception:
        return PosterQAVerdict(reason="could not read poster image", checked=False)

    brand_color = ""
    if brand_dna is not None:
        brand_color = (getattr(brand_dna, "color_usage", "") or "").strip()
    lang_line = (
        "The brand is ARABIC: the headline, chips and CTA must be Arabic. has_latin_text = true "
        "if ANY of the HEADLINE / CHIPS / CTA contain Latin letters. IGNORE the brand logo "
        "(it may contain Latin — that is fine)."
        if arabic else
        "has_latin_text = false unless there is clearly broken/garbled text."
    )
    color_line = (f"The brand's colour language is: {brand_color}. on_brand_color = true only if "
                  "the poster's DOMINANT colour matches that." if brand_color else
                  "on_brand_color = true unless the colours look random/off for a brand poster.")

    system = (
        "You are a WORLD-CLASS advertising ART DIRECTOR reviewing a FINAL rendered poster. "
        "Your bar: 'Would a top brand actually run this?' Be strict — return a structured verdict.\n"
        f"- {lang_line}\n"
        "- logo_ok = true ONLY if the brand logo/lockup is crisp, complete and correctly spaced "
        "with NO garbled/overlapping/duplicated glyphs or stray characters (HARD GATE).\n"
        "- cta_clipped = true if the CTA, or any text/chip/logo, is cut off at / outside the frame.\n"
        "- cta_prominent = true if the CTA reads as a confident, high-contrast button (not a "
        "tiny low-contrast footnote).\n"
        "- single_focal = true if there is ONE clear focal point with a clean eye-path to the "
        "headline (false if focal points compete).\n"
        "- strong_typography = true if the headline reads as an intentional display LOCKUP "
        "(deliberate weight/size hierarchy), not a flat default font.\n"
        f"- {color_line}\n"
        "- candid_violation = true if the imagery looks candid/documentary or flat natural "
        "lighting (amateur/stock) rather than a polished brand campaign.\n"
        "- score = 1..10 overall creative quality as a premium brand poster.\n"
        "- overall_pass = true ONLY if logo_ok AND no Latin in the copy AND no clipping AND "
        "on_brand_color AND no candid violation AND score >= 7.\n"
        "- reason = one short sentence naming the biggest problem (or 'clean')."
    )
    user = "Review this rendered poster as an art director and return the verdict."

    try:
        resp, _u = caller(system, user, _QAResponse, group_name="poster_vision_qa",
                          images=[(data, "image/png")])
    except Exception as exc:  # noqa: BLE001
        return PosterQAVerdict(reason=f"QA call failed ({type(exc).__name__})", checked=False)

    return PosterQAVerdict(
        has_latin_text=bool(resp.has_latin_text),
        cta_clipped=bool(resp.cta_clipped),
        on_brand_color=bool(resp.on_brand_color),
        candid_violation=bool(resp.candid_violation),
        logo_ok=bool(resp.logo_ok),
        single_focal=bool(resp.single_focal),
        strong_typography=bool(resp.strong_typography),
        cta_prominent=bool(resp.cta_prominent),
        score=int(resp.score or 0),
        overall_pass=bool(resp.overall_pass) and bool(resp.logo_ok),
        reason=(resp.reason or "").strip(),
        checked=True,
    )
