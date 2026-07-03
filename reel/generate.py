"""Generate a brand reel: UNDERSTAND the brand -> INVENT fresh footage -> REAL motion.

Owner's direction: don't dump the website's product photos; UNDERSTAND the brand and INVENT
on-brand footage that tells its STORY. Pipeline:
  BrandCreativeDNA (the brand's real ads via search — used as LEARNED TEXT: themes/mood,
      never the ad pixels, which baked garbled text/colour)
   -> an LLM director writes a brand-grounded STORY (narrative arc + ONE recurring protagonist
      + a short on-screen CAPTION per beat, gated by the Evidence Ledger: drop-to-grounded)
   -> text-to-image stills (Imagen; region + natural-skin + hard no-text guards)
   -> Veo 3.1 image-to-video animates EACH still (Ken Burns is the per-scene fallback)
   -> xfade assembly on the clips' ACTUAL durations.
Returns the reel + the captions timed on its timeline (for the kinetic overlay layer). Never
fabricates the FACTS (footage is text-free; captions are gated); raises if nothing generates.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, NamedTuple, Optional


class GeneratedReel(NamedTuple):
    """The assembled footage + the story captions timed on ITS timeline (for the overlay layer)."""
    path: Path
    caption_beats: list  # (text, t_in, t_out) tuples, in footage seconds


_AR_RE = re.compile(r"[؀-ۿ]")


def _voiceover_clause(text: str, profile: dict) -> str:
    """The spoken-audio instruction for one Veo 3.1 scene (the TrendPulse insight — Veo renders
    NATIVE speech from the prompt, so the reel talks at no extra cost). The dialect is derived
    UNIVERSALLY from the copy language + the brand's ccTLD (no vertical/market hardcoding):
    Arabic + .eg -> Egyptian Arabic; Arabic elsewhere -> natural conversational Arabic. Empty
    text -> ambience only."""
    text = (text or "").strip()
    if not text:
        return "Natural ambient sound only, no speech."
    if _AR_RE.search(text):
        url = ""
        try:
            url = str(profile.get("source_url") or "").lower() if isinstance(profile, dict) else ""
        except Exception:
            url = ""
        dialect = ("natural Egyptian Arabic (Masri)" if ".eg" in url
                   else "natural, warm conversational Arabic")
        return f'Voiceover: a warm, confident voice speaking in {dialect}: "{text}".'
    return f'Voiceover: a warm, confident voice speaking in English: "{text}".'


def _caption_windows(durs: list[float], transition_s: float = 0.5) -> list[tuple[float, float]]:
    """Pure: each clip's fully-visible window on the assembled xfade timeline (mirrors
    `build_animated_reel`'s math — clip i starts at sum(durs[:i]) - i*t). The window opens just
    after the incoming transition settles and closes before the outgoing one starts."""
    if not durs:
        return []
    t = min(transition_s, min(durs) * 0.5)
    wins: list[tuple[float, float]] = []
    for i, d in enumerate(durs):
        start = sum(durs[:i]) - i * t
        t_in = start + (0.3 if i else 0.2)
        t_out = start + d - t - 0.15
        wins.append((round(t_in, 2), round(max(t_in, t_out), 2)))
    return wins


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
) -> GeneratedReel:
    """Generate fresh, on-brand, TEXT-FREE scenes (text-to-image) then motion-animate them.
    NOTE: STYLE-conditioning on the brand's real ADS was DROPPED — Imagen reproduced the ads'
    text-heavy look as GARBLED baked text (the owner's "الكلام معكوس / عبث"). Brand fidelity now
    comes from the PROMPT (region + the brand's real offerings), and the image stays text-free.
    Returns GeneratedReel(path, caption_beats) — the caption beats are the story's GROUNDED
    on-screen lines timed on the footage timeline, for the kinetic overlay layer; raises only
    if no scene could be generated."""
    from poster.from_profile import build_poster_brief
    from poster.imagen_provider import VertexImagenProvider
    from reel.art_director import build_brand_story
    from reel.motion import _clip_duration, _grid_durations, _make_clip, build_animated_reel
    from reel.video_provider import VeoProvider

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
    # GROUND THE STORY IN THE BRAND'S REAL CREATIVE (owner: "اعتمد ع الريلز القديمة بالسيرش"): the
    # BrandCreativeDNA searches the brand's actual ads and vision-UNDERSTANDS their visual language
    # (themes/mood/imagery — as TEXT), so the story reflects the real brand world. We feed only the
    # learned DESCRIPTION into the prompt, never the ad pixels (which baked garbled text/colour).
    if brand_dna is None and caller is not None:
        try:
            from poster.pipeline import load_or_build_dna
            brand_dna = load_or_build_dna(profile, caller)
            if brand_dna is not None:
                log(f"[gen] brand DNA loaded ({len(getattr(brand_dna, 'references_seen', []) or [])} real ads)")
        except Exception:
            brand_dna = None
    character, story, captions, voiceovers = build_brand_story(brief, profile, caller, n=n_scenes,
                                                               brand_dna=brand_dna)
    # Captions AND voiceovers are LLM copy on CUSTOMER-FACING surfaces (displayed / SPOKEN) ->
    # gate both (drop-to-grounded): a line carrying an unsourced falsifiable claim is BLANKED
    # (that scene shows no caption / gets ambience instead of speech).
    from reel.grounding import grounded_captions
    for label, lines in (("caption", captions), ("voiceover", voiceovers)):
        if any(lines):
            kept = grounded_captions(profile, lines)
            blanked = sum(1 for a, b in zip(lines, kept) if a and not b)
            if blanked:
                log(f"[gen] {blanked} {label}(s) blanked (unsourced hard claim)")
            lines[:] = kept
    cont = f" The SAME recurring person appears in this scene: {character}." if character else ""
    if story:
        scene_prompts = [f"{s}{cont}" for s in story][:n_scenes]
        captions = (captions + [""] * len(scene_prompts))[: len(scene_prompts)]
        voiceovers = (voiceovers + [""] * len(scene_prompts))[: len(scene_prompts)]
        log(f"[gen] brand STORY: {len(scene_prompts)} scenes"
            + (" + recurring character" if character else "")
            + (f" + {sum(1 for c in captions if c)} captions" if any(captions) else "")
            + (f" + {sum(1 for v in voiceovers if v)} voiceover lines" if any(voiceovers) else ""))
    else:
        scene_prompts = _scene_prompts(brief, n_scenes)
        captions = [""] * len(scene_prompts)
        voiceovers = [""] * len(scene_prompts)
        log(f"[gen] no LLM story -> {len(scene_prompts)} deterministic varied scenes")

    out_path = Path(out_path)
    work = out_path.parent / "_genscenes"
    work.mkdir(parents=True, exist_ok=True)
    provider = VertexImagenProvider()
    ctx = _onbrand_context(profile, brief)
    stills: list[tuple[int, str]] = []       # (scene index, still path) — a failed scene must not
    for i, prompt in enumerate(scene_prompts):  # shift the later scenes off their story/caption
        try:
            p = provider.generate(f"{prompt}\n{ctx}", out_dir=str(work), aspect_ratio="9:16")
            stills.append((i, str(p)))
            log(f"[gen] scene {i + 1}/{n_scenes} ok")
        except Exception as exc:  # noqa: BLE001 — skip a failed scene, keep the rest
            log(f"[gen] scene {i + 1} failed: {type(exc).__name__}: {exc}")
    if not stills:
        raise RuntimeError("build_brand_generated_reel: no scene could be generated")

    # PRIMARY PATH: animate each Imagen still into REAL video with Veo 3.1 (image-to-video), so the
    # reel MOVES (a real short film, not a slideshow). Ken Burns (static zoom) is ONLY the per-scene
    # fallback when Veo fails. The still is passed as the i2v reference so the motion is anchored to
    # the exact on-brand scene; the story action steers the motion.
    veo = VeoProvider()
    durs = _grid_durations(len(stills))
    clips: list[str] = []
    veo_ok = 0
    for j, (si, still) in enumerate(stills):
        clip = work / f"_scene_clip{j}.mp4"
        d = durs[j] if j < len(durs) else 5.0
        veo_prompt = ((story[si] + " " if (story and si < len(story)) else "")
                      + "Gentle, natural cinematic motion — the person and scene move naturally, "
                      "subtle camera move; photoreal, absolutely NO text, letters or logos. "
                      + _voiceover_clause(voiceovers[si] if si < len(voiceovers) else "", profile))
        try:
            veo.generate(veo_prompt, out_path=clip, duration_s=d, width=width, height=height,
                         reference_image=still)
            veo_ok += 1
            log(f"[veo] scene {si + 1}/{n_scenes} -> REAL video")
        except Exception as exc:  # noqa: BLE001 — Veo failed this scene: Ken Burns fallback only
            log(f"[veo] scene {si + 1} FAILED ({type(exc).__name__}: {str(exc)[:90]}) -> Ken Burns")
            _make_clip(Path(still), clip, move="in" if j % 2 == 0 else "out",
                       duration_s=d, width=width, height=height)
        clips.append(str(clip))
    log(f"[gen] Veo real video: {veo_ok}/{len(stills)} scenes; assembling reel")
    # Time each scene's caption on the ASSEMBLED footage timeline (actual clip durations, same
    # xfade math as build_animated_reel) BEFORE the per-scene clips are deleted.
    actual = [_clip_duration(Path(c)) for c in clips]
    wins = _caption_windows(actual)
    caption_beats: list[tuple[str, float, float]] = []
    for j, (si, _still) in enumerate(stills):
        text = captions[si] if si < len(captions) else ""
        if text and j < len(wins):
            caption_beats.append((text, wins[j][0], wins[j][1]))
    # keep_audio: Veo 3.1's NATIVE audio (the gated spoken voiceover + ambience) survives the
    # assembly — the reel TALKS; silent fallback clips are padded so the audio chain holds.
    reel = build_animated_reel(clips, out_path, width=width, height=height, keep_audio=True)
    for c in clips:                                    # tidy the per-scene clips
        try:
            Path(c).unlink()
        except OSError:
            pass
    return GeneratedReel(reel, caption_beats)
