"""Visual identity projection from scrape manifest to business profile.

v0.2 preserves old fields while projecting the new structured visual data:
logo candidates, co-branding, raw palette vs brand palette, and warnings.
"""
from __future__ import annotations

from typing import Optional

from scraper.schemas import LogoCandidate, ScrapeManifest

from ..schemas import LogoCandidateSummary, VisualIdentitySummary


def _hex_to_rgb(hex_color: str) -> Optional[tuple[int, int, int]]:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return None
    try:
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return None


def _is_weak_neutral(hex_color: str) -> bool:
    """Neutral for legacy fallback only.

    Unlike v0.1, near-black is NOT automatically discarded because
    black/gold restaurant identities are valid brand systems when the
    scraper has supporting header/logo/CTA evidence.
    """
    rgb = _hex_to_rgb(hex_color)
    if rgb is None:
        return True
    r, g, b = rgb
    if min(r, g, b) >= 225:  # near white
        return True
    if max(r, g, b) - min(r, g, b) < 18 and max(r, g, b) > 45:  # gray, not black
        return True
    return False

def _is_background_like(hex_color: str) -> bool:
    rgb = _hex_to_rgb(hex_color)
    if rgb is None:
        return True

    r, g, b = rgb

    if min(r, g, b) >= 225:
        return True

    if max(r, g, b) <= 38:
        return False

    if max(r, g, b) - min(r, g, b) < 18:
        return True

    saturation = (max(r, g, b) - min(r, g, b)) / max(max(r, g, b), 1)

    # Beige/taupe page backgrounds like #aca297 should not become primary.
    return saturation < 0.16


def _safe_primary_color(
    primary: Optional[str],
    palette_hex: list[str],
    accent_colors: list[str],
    background_colors: list[str],
    warnings: list[str],
) -> Optional[str]:
    if primary and primary not in background_colors and not _is_background_like(primary):
        return primary

    # If backend warns that the screenshot is background-dominated, prefer
    # explicit accents over the legacy primary.
    if "palette_dominated_by_background" in warnings or primary in background_colors:
        for hx in accent_colors + palette_hex:
            if hx not in background_colors and not _is_background_like(hx):
                return hx

    for hx in palette_hex:
        if hx not in background_colors and not _is_weak_neutral(hx):
            return hx

    return primary


def _candidate(c: LogoCandidate) -> LogoCandidateSummary:
    return LogoCandidateSummary(
        src=c.src,
        alt=c.alt,
        text_wordmark=c.text_wordmark,
        source_type=c.source_type,
        classification=c.classification,
        confidence=c.confidence,
        score=c.score,
        reasons=c.reasons,
        width=c.width,
        height=c.height,
        aspect_ratio=c.aspect_ratio,
    )


def extract_visual(manifest: ScrapeManifest) -> VisualIdentitySummary:
    v = manifest.visual

    raw_palette = v.raw_palette or v.color_palette
    brand_palette = v.brand_palette or v.color_palette

    palette_hex = [c.hex for c in brand_palette]
    palette_dom = [c.dominance for c in brand_palette]
    raw_hex = [c.hex for c in raw_palette]
    raw_dom = [c.dominance for c in raw_palette]

    primary = _safe_primary_color(
        v.primary_brand_color,
        palette_hex,
        v.accent_colors,
        v.background_colors,
        v.visual_warnings,
    )

    primary_logo = _candidate(v.primary_logo) if v.primary_logo else None
    logo_url = None
    if primary_logo and primary_logo.source_type != "text_wordmark":
        logo_url = primary_logo.src
    elif v.logo:
        logo_url = v.logo.src

    return VisualIdentitySummary(
        # Legacy fields.
        palette_hex=palette_hex,
        palette_dominance=palette_dom,
        primary_color=primary,
        body_font=(v.fonts or {}).get("body"),
        heading_font=(v.fonts or {}).get("headings"),
        logo_url=logo_url,

        # v0.2 logo fields.
        primary_logo=primary_logo,
        logo_candidates=[_candidate(c) for c in v.logo_candidates],
        partner_logos=[_candidate(c) for c in v.partner_logos],
        authority_logos=[_candidate(c) for c in v.authority_logos],
        co_branding_detected=v.co_branding_detected,
        visual_extraction_note=v.visual_extraction_note,

        # v0.2 palette fields.
        raw_palette=raw_hex,
        raw_palette_dominance=raw_dom,
        brand_palette=palette_hex,
        brand_palette_confidence=palette_dom,
        primary_brand_color=primary,
        accent_colors=v.accent_colors,
        neutral_colors=v.neutral_colors,
        background_colors=v.background_colors,
        text_colors=v.text_colors,
        palette_extraction_note=v.palette_extraction_note,
        visual_warnings=v.visual_warnings,
    )
