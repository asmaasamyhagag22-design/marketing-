"""Generate a reel from the brand's REAL ADS (understand -> generate), NOT website photos.

Owner's direction: don't dump the website's product photos; UNDERSTAND the brand from its real
ads (found via search) and INVENT fresh on-brand footage. Pipeline:
  BrandCreativeDNA (the brand's real ads from search, attribution-filtered)  -- the references
   -> STYLE-generate N fresh, text-free, on-brand STILL scenes (Imagen edit, conditioned on those
      real ads, via the poster's ImagenEditProvider)                          -- the "invent"
   -> the Motion/Music engine animates them cinematically (eased motion + xfade + optional music).
No literal website-photo reuse. Stills are brand-world scenes, varied per shot. Never fabricates
the FACTS (this is footage only — no text is rendered here); raises if nothing can be generated.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional


def _scene_prompts(brief: Any, n: int) -> list[str]:
    """N brand-grounded, TEXT-FREE scene briefs for the generated stills — a hero moment, the real
    offerings, and an aspirational lifestyle beat. The STYLE reference carries the brand look; the
    image stays text-free (ImagenEditProvider appends the no-text contract)."""
    base = f"A premium, photorealistic on-brand marketing scene for {brief.business_name}"
    offers = [o for o in (brief.offerings or []) if o][:3]
    prompts = [f"{base}: a striking HERO moment that captures the brand's world and energy."]
    for o in offers:
        prompts.append(f"{base}: a real, candid moment that shows {o}.")
    prompts.append(f"{base}: an aspirational lifestyle moment with the brand's real audience.")
    # cycle to fill n, keep at least 2
    out: list[str] = []
    i = 0
    while len(out) < max(2, n):
        out.append(prompts[i % len(prompts)])
        i += 1
    return out


def _dna_refs(profile: dict, caller: Any, brand_dna: Any) -> list[str]:
    """The brand's REAL ad references (from BrandCreativeDNA). Uses a supplied/cached DNA, else
    builds with caller=None (harvest + the tiered attribution filter — no vision cost needed just
    to get the reference URLs)."""
    refs = list(getattr(brand_dna, "references_seen", []) or []) if brand_dna is not None else []
    if refs:
        return refs
    try:
        from brand.creative_dna import build_creative_dna
        dna = build_creative_dna(profile, caller=None)   # refs only -> no Gemini-vision spend
        return list(getattr(dna, "references_seen", []) or [])
    except Exception:
        return []


def build_brand_generated_reel(
    profile: dict, *, caller: Any = None, out_path: str | Path, brand_dna: Any = None,
    n_scenes: int = 4, music_path: Optional[str] = None, width: int = 1080, height: int = 1920,
    log=print,
) -> Path:
    """STYLE-generate fresh on-brand stills from the brand's real ads, then motion-animate them.
    Returns out_path. Raises if no ad references exist or no scene could be generated."""
    from poster.from_profile import build_poster_brief
    from poster.imagen_edit_provider import ImagenEditProvider
    from reel.motion import build_motion_reel

    brief = build_poster_brief(profile)
    refs = _dna_refs(profile, caller, brand_dna)
    if not refs:
        raise RuntimeError("build_brand_generated_reel: no brand-ad references to generate from "
                           "(search returned nothing brand-owned)")
    log(f"[gen] {len(refs)} real brand-ad references -> generating {n_scenes} on-brand scenes")

    out_path = Path(out_path)
    work = out_path.parent / "_genscenes"
    work.mkdir(parents=True, exist_ok=True)
    provider = ImagenEditProvider()
    stills: list[str] = []
    for i, prompt in enumerate(_scene_prompts(brief, n_scenes)):
        try:
            p = provider.style(prompt, refs, out_dir=str(work), aspect_ratio="9:16")  # vertical reel
            stills.append(str(p))
            log(f"[gen] scene {i + 1}/{n_scenes} ok")
        except Exception as exc:  # noqa: BLE001 — skip a failed scene, keep the rest
            log(f"[gen] scene {i + 1} failed: {type(exc).__name__}: {exc}")
    if not stills:
        raise RuntimeError("build_brand_generated_reel: no scene could be generated")

    def _local_fetch(u: str):
        pth = Path(u)
        return (pth.read_bytes(), "image/png") if pth.exists() else None

    log(f"[gen] {len(stills)} scenes generated -> motion engine")
    return build_motion_reel(stills, out_path, width=width, height=height,
                             palette=list(brief.palette_hex or []), music_path=music_path,
                             fetch=_local_fetch)
