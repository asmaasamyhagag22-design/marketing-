"""Unified poster pipeline — ONE path shared by the CLI and the web app.

Per the build brief (Step A): the CLI and the API used to run different branches, so the
web app shipped old behaviour. Everything now flows through `generate_poster()`:

  profile
    -> load-or-build BrandCreativeDNA (the brand's learned visual language)
    -> build_creative_concept            (ONE message; Arabic copy; chips = proof_points)
    -> build_poster_brief + override copy from the concept
    -> build_design_spec                 (free-form layout, DNA-steered)
    -> build_llm_concept_prompt          (image in the DNA language, scene = concept.visual_idea)
    -> ADAPTIVE brand-anchored background: OUTPAINT a real scraped photo -> STYLE on the
       brand's real creatives -> text-to-image (Ultra->4.0) fallback  [or stub when no_image]
    -> render_poster_html -> PNG
    -> Vision QA gate                    (reject + regenerate on fail; bounded retries)

Two truth domains: FACTS stay grounded (profile-derived; copy is brand-voice paraphrase of
real facts — the design domain). DESIGN (layout / scene / language) is the creative domain.
Never raises for ordinary failures; degrades to deterministic fallbacks.
"""
from __future__ import annotations

import base64
import json
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from poster.concept import CreativeConcept, brand_is_arabic, build_creative_concept
from poster.from_profile import build_poster_brief
from poster.schemas import PosterBrief, PosterDesignSpec
from poster.template import render_poster_html
from poster.render_playwright import render_html_to_png
from poster.variation import build_variation
from poster.vision_qa import PosterQAVerdict, poster_vision_qa

_FALLBACK_MODEL = "imagen-4.0-generate-001"


def _safe_log(msg: object) -> None:
    """Print pipeline progress WITHOUT ever crashing on a non-UTF-8 console (Windows cp1252
    raises on Arabic) — which previously surfaced as an HTTP 500 from the web app."""
    import sys
    try:
        print(msg)
    except Exception:
        try:
            sys.stdout.buffer.write((str(msg) + "\n").encode("utf-8", "replace"))
        except Exception:
            pass


@dataclass
class PosterGenResult:
    poster_path: str
    filename: str
    image_base64: str
    brief: PosterBrief
    spec: PosterDesignSpec
    concept: CreativeConcept
    brand_dna: Any
    background_path: str
    model_used: str
    prompt: str
    qa: PosterQAVerdict
    width: int = 1080
    height: int = 1350
    audit: Optional[dict] = None   # brand-safety trail (claim->source + gate remediation)


def _fv(profile: dict, key: str) -> str:
    v = (profile or {}).get(key)
    if isinstance(v, dict):
        v = v.get("value")
    return "" if v is None else str(v)


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (name or "brand").lower()).strip("_") or "brand"


def load_or_build_dna(profile: dict, caller: Any, *, cache_dir: str = "outputs/brandbooks") -> Any:
    """Build-or-load the BrandCreativeDNA: load the cached file for this brand, else build it
    once (Serper image search + Gemini vision) and cache. None on failure (pipeline proceeds
    with a generic — but still concept-driven, Arabic, safe — poster)."""
    try:
        from brand.creative_dna import build_creative_dna, load_creative_dna, save_creative_dna
    except Exception:
        return None
    path = Path(cache_dir) / f"{_slug(_fv(profile, 'name'))}_dna.json"
    if path.exists():
        try:
            return load_creative_dna(path)
        except Exception:
            pass
    if caller is None:
        return None
    try:
        dna = build_creative_dna(profile, caller=caller)
    except Exception:
        return None
    if getattr(dna, "used_vision", False):
        try:
            save_creative_dna(dna, path)
        except Exception:
            pass
    return dna


def _generate_imagen(prompt: str) -> tuple[str, str]:
    """Vertex Imagen Ultra -> lighter model on a capacity/quota (429). Returns (path, model)."""
    from poster.imagen_provider import VertexImagenProvider
    provider = VertexImagenProvider()
    try:
        return str(provider.generate(prompt)), provider.model
    except Exception:
        fb = VertexImagenProvider(model=_FALLBACK_MODEL)
        return str(fb.generate(prompt)), fb.model


def _maybe_upscale(path: str, *, log=_safe_log) -> str:
    """Upscale the generated background ~2x for crispness + sharper faces (owner: "الكوالتي
    محتاجة تتحسن"). Best-effort: returns the original path on any failure."""
    try:
        from poster.imagen_edit_provider import upscale_to_file
        out = upscale_to_file(path)
        if out and Path(out).exists():
            from PIL import Image
            log(f"[bg] upscaled -> {Image.open(out).size}")
        return out
    except Exception:
        return path


_LETTERBOX_LUM = 24      # MEASURED: the WE letterbox bars mean ~15 (max 17); real content >=31


def _trim_letterbox(path: str) -> str:
    """Crop near-black letterbox bars (top/bottom) from a generated background so it fills the
    poster canvas edge-to-edge. The STYLE / text-to-image model sometimes renders a LANDSCAPE
    scene centered in the portrait frame with dark bars (MEASURED on WE: a 896x1280 frame, bars
    mean~15 / max 17 — NOT pure black, so a per-pixel bbox at 16 missed them). Uses a ROW-MEAN
    detector (robust to stray bright pixels) at a calibrated threshold. Re-saves in place;
    no-op/safe on any failure. (Top/bottom only — letterbox in a portrait canvas; a legit dark
    edge on the sides is left alone to avoid over-cropping.)"""
    try:
        from PIL import Image
        im = Image.open(path).convert("RGB")
        W, H = im.size
        small = im.convert("L").resize((16, 320))      # 320-row vertical resolution, fast
        sw, sh = small.size
        px = small.load()
        def row_mean(y: int) -> float:
            return sum(px[x, y] for x in range(sw)) / sw
        top = 0
        while top < sh and row_mean(top) < _LETTERBOX_LUM:
            top += 1
        bot = sh - 1
        while bot > top and row_mean(bot) < _LETTERBOX_LUM:
            bot -= 1
        if top == 0 and bot == sh - 1:
            return path                                 # no bars
        y0, y1 = round(top / sh * H), round((bot + 1) / sh * H)
        if (y1 - y0) < 0.30 * H:                        # guard: don't gut a legitimately dark scene
            return path
        im.crop((0, y0, W, y1)).save(path)
    except Exception:
        pass
    return path


def _best_usable_photo(profile: dict, *, fetch=None) -> Optional[str]:
    """The brand's first TECHNICALLY-usable scraped photo (for OUTPAINT), or None. Reuses the
    REAL reel.image_quality gate (size/ratio/blankness); max_keep=1 stops at the first hit."""
    urls = ((profile or {}).get("visual") or {}).get("content_images") or []
    if not urls:
        return None
    try:
        from reel.image_quality import filter_usable_photos
        keep = filter_usable_photos(urls, fetch=fetch, max_keep=1)
    except Exception:
        return None
    return keep[0] if keep else None


def _brand_style_refs(profile: dict, brand_dna: Any, *, limit: int = 2) -> list[str]:
    """Real brand creatives to condition a STYLE generation on (the universal floor): the
    brand's harvested REAL ads first (BrandCreativeDNA.references_seen), then its own scraped
    site photos. Capped at `limit` (Vertex: non-square signatures accept at most 2 refs)."""
    refs: list[str] = []
    seen: set[str] = set()
    for src in (getattr(brand_dna, "references_seen", None) or []):
        if isinstance(src, str) and src.startswith(("http://", "https://")) and src not in seen:
            refs.append(src); seen.add(src)
    for src in (((profile or {}).get("visual") or {}).get("content_images") or []):
        if isinstance(src, str) and src.startswith(("http://", "https://")) and src not in seen:
            refs.append(src); seen.add(src)
    return refs[:limit]


def _generate_background(
    profile: dict, brand_dna: Any, prompt: str, *,
    log=_safe_log, fetch=None, edit_provider=None, t2i=None,
) -> tuple[str, str]:
    """ADAPTIVE brand-anchored background, with a safe cascade (never raises here):
      1) OUTPAINT a usable REAL scraped photo (max fidelity), else
      2) STYLE-condition on the brand's real creatives (universal floor), else
      3) plain text-to-image (the previous behaviour — last-resort fallback).
    Returns (background_path, model_label). `edit_provider`/`t2i`/`fetch` are injectable for tests."""
    t2i = t2i or _generate_imagen
    _prov = {"p": edit_provider}

    def _edit():
        if _prov["p"] is None:
            from poster.imagen_edit_provider import ImagenEditProvider
            _prov["p"] = ImagenEditProvider()
        return _prov["p"]

    photo = _best_usable_photo(profile, fetch=fetch)
    if photo:
        try:
            # Extend the REAL photo (keep the literal product/place); the guard handles the scene.
            p = _edit().outpaint(photo, "")
            log("[bg] mode=OUTPAINT (real scraped photo)")
            return str(p), "imagen-3.0-capability-001/outpaint"
        except Exception as e:  # noqa: BLE001 — fall through to the next mode, never crash
            log(f"[bg] outpaint failed ({type(e).__name__}: {e}); -> style")

    refs = _brand_style_refs(profile, brand_dna)
    if refs:
        try:
            p = _edit().style(prompt, refs)
            log(f"[bg] mode=STYLE ({len(refs)} real brand refs)")
            return str(p), "imagen-3.0-capability-001/style"
        except Exception as e:  # noqa: BLE001
            log(f"[bg] style failed ({type(e).__name__}: {e}); -> text-to-image")

    p, model = t2i(prompt)
    log("[bg] mode=text-to-image (fallback)")
    return str(p), model


def _dna_wants_lockup(brand_dna) -> bool:
    """True when the brand's learned typographic character is BOLD/GRAPHIC — i.e. its real ads
    treat the headline as a designed lockup (heavy weight / outline / gradient / 3D). Then the
    template renders a 'lockup' headline (the "real ad design, not photo+text" direction) rather
    than plain text. Read from the BrandCreativeDNA; harmless False when there's no DNA."""
    text = " ".join(str(getattr(brand_dna, f, "") or "")
                    for f in ("typographic_character", "signature_moves")).lower()
    return any(k in text for k in (
        "bold", "outline", "gradient", "lockup", "graphic art", "3d", "custom", "heavy", "extreme"))


def _qa_image_fixable(v: PosterQAVerdict) -> bool:
    """True when a QA failure is something REGENERATING THE IMAGE can fix (off-brand colour,
    candid look, baked Latin, a cluttered/competing-focal composition). A pure layout clip or
    a low-res logo is handled deterministically elsewhere — re-rolling the image won't change
    those, so we don't loop on them."""
    return (v.candid_violation or (not v.on_brand_color) or v.has_latin_text
            or (not v.single_focal))


def generate_poster(
    profile: dict[str, Any],
    *,
    caller: Any = None,
    qa_caller: Any = None,
    variation: Optional[dict] = None,
    brand_dna: Any = None,
    use_dna: bool = True,
    use_edit: bool = True,
    upscale: bool = True,
    no_image: bool = False,
    headline_override: Optional[str] = None,
    max_qa_retries: int = 2,
    out_dir: str = "outputs/posters",
    log=_safe_log,
) -> PosterGenResult:
    """The one pipeline. `caller` = a (multimodal) Gemini caller; `qa_caller` defaults to it."""
    qa_caller = qa_caller if qa_caller is not None else caller
    arabic = brand_is_arabic(profile)
    variation = variation or build_variation()

    # 1) Brand's learned visual language (cached per brand).
    if brand_dna is None and use_dna:
        brand_dna = load_or_build_dna(profile, caller)
    log(f"[concept] dna={'yes' if getattr(brand_dna,'used_vision',False) else 'no'} arabic={arabic}")

    # 2) ONE creative concept -> the copy is built FROM it (coherent, brand-language).
    #    enforce_grounding=True: the Evidence Ledger gate softens any falsifiable claim
    #    (number/year/certification/ranking) that isn't backed by the brand's real evidence.
    concept = build_creative_concept(profile, caller=caller, brand_dna=brand_dna,
                                     variation=variation, enforce_grounding=True)
    log(f"[concept] msg={concept.single_message!r} headline={concept.headline!r} "
        f"chips={concept.proof_points}")

    # 3) Brief, with copy OVERRIDDEN by the concept (headline/sub/cta/chips all one idea).
    headline = (headline_override or concept.headline or "").strip() or None
    brief = build_poster_brief(profile, headline_override=headline)
    updates: dict = {}
    if concept.subheadline:
        updates["subheadline"] = concept.subheadline
    if concept.cta:
        updates["cta_text"] = concept.cta
    if concept.proof_points:
        updates["offerings"] = concept.proof_points[:3]
    if updates:
        brief = brief.model_copy(update=updates)

    # 3b) Brand-safety audit trail (Step 3c): the (claim->source) proof of the SHIPPED copy +
    #     the gate's remediation log + explicit scoping. Built once (independent of the
    #     image/QA loop); written as a sidecar next to the poster that ships.
    try:
        from poster.audit import build_poster_audit
        audit = build_poster_audit(profile, concept, brief)
    except Exception:  # noqa: BLE001 — the trail must never break poster generation
        audit = None

    def _emit(r: PosterGenResult) -> PosterGenResult:
        if r.audit:
            try:
                Path(r.poster_path).with_suffix(".audit.json").write_text(
                    json.dumps(r.audit, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass
        return r

    # 4) Free-form, DNA-steered composition.
    from poster.art_director import build_design_spec, build_llm_concept_prompt
    spec = build_design_spec(brief, caller, profile=profile, variation=variation, brand_dna=brand_dna)
    # GUARANTEE the concept's elements render, but SCALE the count TO THE ARCHETYPE so each
    # looks like its kind of ad AND a side/upper editorial box doesn't overflow + clip the CTA
    # (MEASURED on WE: forcing headline+sub+3 chips+CTA into a top-anchored side third clipped
    # the CTA). An editorial lockup shows FEW elements; a B2B proof shows the evidence bullets.
    arche = getattr(spec, "marketing_archetype", None)
    must_show = ["logo", "headline"]
    if arche == "magazine_editorial":
        pass                                   # the massive lockup is the hero: logo+headline+cta
    elif arche in ("typographic_anchor", "product_hero"):
        if brief.subheadline:
            must_show.append("sub")            # one supporting line, no chips
    else:                                       # proof_and_trust / None: the evidence bullets ARE the point
        if brief.subheadline:
            must_show.append("sub")
        if brief.offerings:
            must_show.append("offerings")
    if brief.cta_text:
        must_show.append("cta")
    spec = spec.model_copy(update={"show": must_show})
    # DNA-driven TYPOGRAPHY: if the brand's real ads treat the headline as a bold designed
    # lockup, render it that way (gradient+outline) instead of plain text on the photo.
    if _dna_wants_lockup(brand_dna):
        spec = spec.model_copy(update={"headline_treatment": "lockup"})
        log("[concept] typography=lockup (DNA)")

    # 5) Generate image + render + VISION QA gate (regenerate the image on a fixable fail).
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    result: Optional[PosterGenResult] = None
    best: Optional[PosterGenResult] = None      # highest-scoring attempt seen
    for attempt in range(max_qa_retries + 1):
        run_var = variation if attempt == 0 else build_variation()
        if no_image:
            from poster.imagen_provider import StubImageProvider
            bg_path, model_used, prompt = str(StubImageProvider().generate("")), "stub", "(stub)"
        else:
            prompt = build_llm_concept_prompt(
                brief, caller, profile=profile, spec=spec, brand_dna=brand_dna,
                variation=run_var, scene_idea=concept.visual_idea,
            )
            # ADAPTIVE brand-anchored background (outpaint real photo -> style on real ads ->
            # text-to-image). `use_edit=False` forces the legacy pure text-to-image path.
            if use_edit:
                bg_path, model_used = _generate_background(profile, brand_dna, prompt, log=log)
            else:
                bg_path, model_used = _generate_imagen(prompt)
            # Deterministic letterbox safety net: crop any black bars so the background fills
            # the canvas edge-to-edge regardless of what the image model rendered.
            bg_path = _trim_letterbox(bg_path)
            # Quality: upscale ~2x for crispness + sharper, more believable faces.
            if upscale:
                bg_path = _maybe_upscale(bg_path, log=log)

        filename = f"poster_{uuid.uuid4().hex[:8]}.png"
        poster_path = str(render_html_to_png(render_poster_html(brief, bg_path, spec=spec), out / filename))
        verdict = poster_vision_qa(poster_path, caller=qa_caller, brand_dna=brand_dna, arabic=arabic)
        log(f"[qa] attempt={attempt} pass={verdict.overall_pass} checked={verdict.checked} "
            f"latin={verdict.has_latin_text} clip={verdict.cta_clipped} "
            f"color={verdict.on_brand_color} candid={verdict.candid_violation} :: {verdict.reason}")
        result = PosterGenResult(
            poster_path=poster_path, filename=filename,
            image_base64=base64.b64encode(Path(poster_path).read_bytes()).decode("ascii"),
            brief=brief, spec=spec, concept=concept, brand_dna=brand_dna,
            background_path=str(bg_path), model_used=model_used, prompt=prompt, qa=verdict,
            audit=audit,
        )
        if best is None or result.qa.score > best.qa.score:
            best = result
        if no_image or verdict.overall_pass or not verdict.checked:
            return _emit(result)                # passed (or can't gate) -> ship it
        if attempt < max_qa_retries and _qa_image_fixable(verdict):
            log("[qa] FAIL (image-fixable) -> regenerating...")
            continue
        break

    # No attempt fully passed the art bar -> return the BEST-scoring one (never a worse
    # later attempt), with its honest verdict attached so the caller can flag it.
    assert best is not None
    if not best.qa.overall_pass:
        log(f"[qa] no attempt passed; returning best (score={best.qa.score}): {best.qa.reason}")
    return _emit(best)
