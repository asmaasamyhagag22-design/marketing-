"""Motion/Music engine — turn the brand's REAL photos into a CINEMATIC reel, not a slideshow.

The Ken Burns path animated each photo with a slow zoom and HARD-CUT them side by side, which
reads as a PowerPoint. This engine adds the "polish" layer that makes a reel feel like an ad:
  * RHYTHM   — durations on a musical (beat) grid, a short punchy HOOK first, varied pacing.
  * MOTION   — eased push-IN / pull-OUT alternating across cuts (dynamic, not one slow zoom).
  * TRANSITIONS — real `xfade` dissolves/slides between shots (no hard seams).
  * MUSIC    — an optional track muxed + trimmed to length; the beat grid is BPM-aligned so the
               cuts land on the beat when a track is supplied.
NO text here by design (the kinetic-caption layer is separate). Pure helpers (grid + xfade graph)
are unit-tested; the ffmpeg render is verified live. Never fabricates footage — real photos only,
with a brand-palette gradient as the last-resort fallback for a missing photo.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from reel.ffmpeg_tools import run_ffmpeg

# A small, tasteful transition vocabulary (cycled). All are stock ffmpeg `xfade` transitions.
_TRANSITIONS = ("fade", "smoothleft", "fadeblack", "smoothup", "dissolve", "smoothright")
# Alternating camera moves so consecutive shots contrast (push-in vs pull-out) = dynamic.
_MOVES = ("in", "out")


def _grid_durations(n: int, *, bpm: float = 100.0, hook_beats: int = 2,
                    cycle_beats=(4, 3, 4)) -> list[float]:
    """Per-shot durations on a BEAT grid (so cuts feel rhythmic and align to music at `bpm`).
    The FIRST shot is a short HOOK; the rest cycle a varied pattern. Returns n durations."""
    beat = 60.0 / max(40.0, bpm)
    if n <= 0:
        return []
    durs = [round(max(1, hook_beats) * beat, 3)]
    for i in range(1, n):
        durs.append(round(cycle_beats[(i - 1) % len(cycle_beats)] * beat, 3))
    return durs


def _xfade_offsets(durs: list[float], t: float) -> list[float]:
    """Offset (start time) for each xfade join. With N clips overlapping by `t` each, the i-th
    join starts at sum(durs[:i]) - i*t. Returns n-1 offsets."""
    return [round(sum(durs[:i]) - i * t, 3) for i in range(1, len(durs))]


def _xfade_filtergraph(n: int, durs: list[float], t: float, transitions=_TRANSITIONS) -> tuple[str, str]:
    """Build the xfade chain filtergraph + the final video label. n==1 -> no xfade."""
    if n <= 1:
        return "", "[0:v]"
    offs = _xfade_offsets(durs, t)
    parts, prev = [], "[0:v]"
    for i in range(1, n):
        tr = transitions[(i - 1) % len(transitions)]
        out = "[vout]" if i == n - 1 else f"[vx{i}]"
        parts.append(f"{prev}[{i}:v]xfade=transition={tr}:duration={t}:offset={offs[i - 1]}{out}")
        prev = out
    return ";".join(parts), "[vout]"


def total_duration(durs: list[float], t: float) -> float:
    """Final reel length after the xfade overlaps."""
    return round(sum(durs) - max(0, len(durs) - 1) * t, 3) if durs else 0.0


def _make_clip(img_path: Path, out_path: Path, *, move: str, duration_s: float,
               width: int, height: int) -> None:
    """One cinematic shot: cover-crop the photo to the vertical frame, then an EASED push-in
    (`in`) or pull-out (`out`), centered. (zoompan `on` = output frame index.)"""
    frames = max(2, int(round(duration_s * 30)))
    if move == "out":
        zexpr = f"1.18-0.16*on/{frames}"        # start zoomed, pull out
    else:
        zexpr = f"1.0+0.16*on/{frames}"         # push in
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},"
        f"scale=3000:-2,"
        f"zoompan=z='{zexpr}':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"s={width}x{height}:fps=30,format=yuv420p"
    )
    run_ffmpeg([
        "-loop", "1", "-i", str(img_path), "-t", f"{duration_s:.2f}", "-vf", vf, "-r", "30",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium", "-crf", "20",
        str(out_path),
    ])


def build_motion_reel(
    images: list[str],
    out_path: Path,
    *,
    width: int = 1080,
    height: int = 1920,
    palette: Optional[list[str]] = None,
    music_path: Optional[str] = None,
    bpm: float = 100.0,
    transition_s: float = 0.45,
    max_clips: int = 8,
    fetch: Optional[Callable[[str], Optional[tuple[bytes, str]]]] = None,
) -> Path:
    """Render a cinematic motion reel from real photos. Returns out_path. Raises if no photo
    can be loaded (the caller decides the fallback — never fabricates footage here)."""
    from reel.video_provider import _load_reference_image
    fetch = fetch or _load_reference_image
    out_path.parent.mkdir(parents=True, exist_ok=True)
    work = out_path.parent

    # Load real photos (cap), keep order, skip the unfetchable.
    loaded: list[Path] = []
    for i, src in enumerate(images or []):
        if len(loaded) >= max_clips:
            break
        got = fetch(str(src))
        if not got:
            continue
        data, mime = got
        ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}.get(mime, ".jpg")
        p = work / f"_motion_src{i}{ext}"
        p.write_bytes(data)
        loaded.append(p)
    if not loaded:
        raise RuntimeError("build_motion_reel: no usable photo could be loaded")

    n = len(loaded)
    durs = _grid_durations(n, bpm=bpm)
    t = min(transition_s, min(durs) * 0.5)                 # transition must fit the shortest shot
    clips: list[Path] = []
    for i, src in enumerate(loaded):
        clip = work / f"_motion_clip{i}.mp4"
        _make_clip(src, clip, move=_MOVES[i % len(_MOVES)], duration_s=durs[i],
                   width=width, height=height)
        clips.append(clip)

    graph, vlabel = _xfade_filtergraph(n, durs, t)
    args: list[str] = []
    for c in clips:
        args += ["-i", str(c)]
    has_music = bool(music_path) and Path(music_path).exists()
    if has_music:
        args += ["-i", str(music_path)]

    if graph:
        args += ["-filter_complex", graph, "-map", vlabel]
    else:
        args += ["-map", "0:v"]
    if has_music:
        args += ["-map", f"{n}:a", "-c:a", "aac", "-b:a", "192k", "-shortest"]
    args += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30",
             "-profile:v", "high", "-preset", "medium", "-crf", "20", str(out_path)]
    run_ffmpeg(args)

    for p in clips + loaded:                                # tidy temp files
        try:
            p.unlink()
        except OSError:
            pass
    return out_path
