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
    base = f"A premium, photorealistic commercial scene for {brief.business_name}"
    # VARIED human + city moments (not every shot a person staring at a blank phone). The brand
    # vibe comes from the people + city energy + the persistent logo overlay, NOT a literal screen.
    prompts = [
        f"{base}: a confident hero portrait of a real person, genuine expression, natural light.",
        f"{base}: friends or family together, authentically connected and happy, a warm real moment.",
        f"{base}: a person out in a vibrant modern Egyptian city street, dynamic urban energy.",
        f"{base}: a relaxed aspirational lifestyle moment at home or a cafe, real and unposed.",
        f"{base}: a cinematic wide establishing shot of a modern city skyline at golden hour.",
    ]
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


def _onbrand_context(profile: dict, brief: Any) -> str:
    """On-brand, TEXT-FREE context for text-to-image: brand region (from the ccTLD) + the brand
    palette + a HARD no-text clause. With no ad references there is no text to copy, so the scene
    stays clean while the prompt keeps it on-brand."""
    url = ""
    try:
        url = str(profile.get("source_url") or "").lower() if isinstance(profile, dict) else ""
    except Exception:
        url = ""
    region = ""
    if ".eg" in url:
        region = ("Set in EGYPT with authentic local Egyptian people and real Egyptian "
                  "surroundings — NOT Western, NOT Gulf/Khaleeji. ")
    # DELIBERATELY no brand-palette instruction: telling the model to use the (purple) brand
    # colour produced a monochromatic purple DYE over people + scene ("purple-people"). Brand
    # identity comes from the persistent LOGO overlay, NOT from tinting the footage.
    return (
        "Natural, vibrant, TRUE-TO-LIFE colour like a real professional photograph: WARM realistic "
        "human SKIN TONES, full natural colour contrast and depth, clean soft daylight. CRITICAL — "
        "do NOT apply ANY single-colour tint, duotone, monochrome wash, colour grade or coloured-gel "
        "lighting to the people or the scene; NO purple, green or neon cast on skin or environment; "
        "every person and object keeps its OWN natural colour. " + region +
        "If a phone or screen appears it is incidental, held naturally, with only a soft natural "
        "glow — never a blank white screen. ABSOLUTELY NO text, words, letters, numbers, logos, "
        "signage, watermarks or typography anywhere — a clean, text-free photograph."
    )


def build_brand_generated_reel(
    profile: dict, *, caller: Any = None, out_path: str | Path, brand_dna: Any = None,
    n_scenes: int = 5, music_path: Optional[str] = None, width: int = 1080, height: int = 1920,
    log=print,
) -> Path:
    """Generate fresh, on-brand, TEXT-FREE scenes (text-to-image) then motion-animate them.
    NOTE: STYLE-conditioning on the brand's real ADS was DROPPED — Imagen reproduced the ads'
    text-heavy look as GARBLED baked text (the owner's "الكلام معكوس / عبث"). Brand fidelity now
    comes from the PROMPT (region + palette + the brand's real offerings), and the image stays
    text-free. Returns out_path; raises only if no scene could be generated."""
    from poster.from_profile import build_poster_brief
    from poster.imagen_provider import VertexImagenProvider
    from reel.art_director import build_brand_story
    from reel.motion import build_motion_reel

    brief = build_poster_brief(profile)
    # The reel must EXPRESS the brand (the owner: "هو حكاية بتعبّر عن البراند، مش صور ورا بعض").
    # An LLM director crafts a brand-grounded STORY (narrative arc + recurring character) from the
    # real persona — like the poster understands the brand. Resolve a default caller so the web
    # reel gets it too; fall back to deterministic varied scenes when no LLM is available.
    if caller is None:
        try:
            from business_profile.llm.caller import default_caller
            caller = default_caller(strong=True)
        except Exception:
            caller = None
    character, story = build_brand_story(brief, profile, caller, n=n_scenes, brand_dna=brand_dna)
    cont = f" The SAME recurring person appears in this scene: {character}." if character else ""
    if story:
        scene_prompts = [f"{s}{cont}" for s in story][:n_scenes]
        log(f"[gen] brand STORY: {len(scene_prompts)} scenes"
            + (" + recurring character" if character else ""))
    else:
        scene_prompts = _scene_prompts(brief, n_scenes)
        log(f"[gen] no LLM story -> {len(scene_prompts)} deterministic varied scenes")

    out_path = Path(out_path)
    work = out_path.parent / "_genscenes"
    work.mkdir(parents=True, exist_ok=True)
    provider = VertexImagenProvider()
    ctx = _onbrand_context(profile, brief)
    stills: list[str] = []
    for i, prompt in enumerate(scene_prompts):
        try:
            p = provider.generate(f"{prompt}\n{ctx}", out_dir=str(work), aspect_ratio="9:16")
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
