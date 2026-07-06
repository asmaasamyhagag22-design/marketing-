"""Vision QA for a GENERATED reel scene — rejects Veo image-to-video hallucinations.

The owner watched a real render and caught three failures the prompt alone can't stop
(Veo drifts away from the seed over a few seconds): the product is NOT faithful to the
real photo, it performs an IMPOSSIBLE action (pressing a sealed pump), and it "magically"
VANISHES mid-scene. A system prompt asks Veo not to do these; it does them anyway.

So we inspect the actual clip: extract a few frames, hand them (plus the REAL product photo
as the reference) to a vision model, and get a structured verdict. On fail the compositor
regenerates the scene once, then falls back to a FAITHFUL real-photo KenBurns pass — so the
worst case still shows the true product instead of a hallucinated one.

Degrades: no caller -> a permissive pass with checked=False (we can't gate without vision).
Never raises."""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class SceneQAVerdict(BaseModel):
    product_faithful: bool = True     # same product as the reference (shape / cap / colour / label)
    product_persists: bool = True     # present in every frame — does NOT vanish / melt / morph away
    action_plausible: bool = True     # no physically impossible action (a sealed pump pressed, etc.)
    overall_pass: bool = True
    reason: str = ""
    checked: bool = False             # True only when a vision model actually inspected the clip


class _QAResponse(BaseModel):
    product_faithful: bool
    product_persists: bool
    action_plausible: bool
    overall_pass: bool
    reason: str


def _extract_frames(clip_path: "str | Path", n: int = 3) -> list[bytes]:
    """Grab `n` evenly-spaced JPEG frames from the clip (start / middle / end) so the model
    can see the product's whole trajectory — a vanish shows as present-then-gone. [] on any
    failure (missing ffmpeg / unreadable clip)."""
    try:
        import imageio_ffmpeg
        ff = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return []
    p = Path(clip_path)
    if not p.is_file() or p.stat().st_size == 0:
        return []
    # probe duration; fall back to sampling by frame if unknown
    fracs = [0.1, 0.5, 0.9][:max(1, n)]
    out: list[bytes] = []
    import tempfile
    for frac in fracs:
        try:
            with tempfile.TemporaryDirectory() as td:
                dst = Path(td) / "f.jpg"
                # -ss before -i is fast; use a fraction of a nominal 4s clip if seek overshoots,
                # ffmpeg clamps to the last frame, which is exactly what we want for the tail.
                subprocess.run(
                    [ff, "-y", "-ss", f"{frac * 4.0:.2f}", "-i", str(p),
                     "-frames:v", "1", "-q:v", "4", str(dst)],
                    capture_output=True, timeout=30,
                )
                if dst.is_file() and dst.stat().st_size > 0:
                    out.append(dst.read_bytes())
        except Exception:
            continue
    return out


def check_scene(
    clip_path: "str | Path",
    *,
    product_hint: Optional[str] = None,
    reference_image: Optional[bytes] = None,
    caller: Any = None,
    frames: int = 3,
    log=logger.info,
) -> SceneQAVerdict:
    """Inspect a generated scene clip. Returns a verdict; checked=False (permissive pass) when
    no caller / no readable frames — never blocks a render on infrastructure gaps."""
    if caller is None:
        return SceneQAVerdict(reason="no vision caller: scene QA skipped", checked=False)
    imgs = _extract_frames(clip_path, n=frames)
    if not imgs:
        return SceneQAVerdict(reason="could not read clip frames", checked=False)

    images: list[tuple[bytes, str]] = []
    ref_note = ""
    if reference_image:
        images.append((reference_image, "image/jpeg"))
        ref_note = ("The FIRST image is the REAL product photo (the reference). The remaining "
                    "images are frames from the generated clip, in time order.\n")
    else:
        ref_note = "The images are frames from the generated clip, in time order.\n"
    images += [(f, "image/jpeg") for f in imgs]

    prod = (product_hint or "the brand's product").strip()
    system = (
        "You are a STRICT quality reviewer for a short product ad clip. " + ref_note +
        f"The product being advertised is: {prod}. Judge ONLY these, and be strict:\n"
        "- product_faithful: do the clip frames show the SAME product as the reference — same "
        "shape, cap/pump, colour and label? false if it is redrawn into a different product or a "
        "garbled//invented label replaces the real one.\n"
        "- product_persists: is the product clearly visible in EVERY clip frame and roughly the "
        "same object throughout? false if it disappears, dissolves, melts or morphs away by a "
        "later frame (the 'it magically vanishes' failure).\n"
        "- action_plausible: is every depicted action physically possible in reality? false for "
        "an IMPOSSIBLE action — a sealed/closed pump being pressed and spraying, pouring from a "
        "closed bottle, liquid appearing with no source, or the product changing state by magic.\n"
        "- overall_pass = product_faithful AND product_persists AND action_plausible.\n"
        "- reason = one short sentence naming the WORST problem (or 'clean')."
    )
    user = "Review the clip against the reference and return the structured verdict."
    try:
        resp, _u = caller(system, user, _QAResponse, group_name="reel_scene_qa", images=images)
    except Exception as exc:  # noqa: BLE001
        return SceneQAVerdict(reason=f"scene QA call failed ({type(exc).__name__})", checked=False)

    v = SceneQAVerdict(
        product_faithful=bool(resp.product_faithful),
        product_persists=bool(resp.product_persists),
        action_plausible=bool(resp.action_plausible),
        overall_pass=bool(resp.overall_pass),
        reason=str(resp.reason or "")[:200],
        checked=True,
    )
    return v
