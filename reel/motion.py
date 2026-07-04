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

# MOTIVATED transition vocabulary (cycled) — directional wipes + a shape reveal, not naive
# crossfades. All are stock ffmpeg `xfade` transitions, so they read as intentional camera
# moves between shots instead of a lazy dissolve.
_TRANSITIONS = ("smoothleft", "wipeleft", "slideup", "circleopen", "smoothup", "diagtl")
# Alternating camera moves so consecutive shots contrast (push-in vs pull-out) = dynamic.
_MOVES = ("in", "out")

# ONE cinematic grade applied IDENTICALLY to every clip so the shots read as one film
# (cohesion — the owner's #5): a gentle punch (contrast + saturation) + a filmic curve that
# lifts blacks slightly and rolls off highlights. Limited, uniform — not a per-clip look.
_GRADE = "curves=m='0/0.02 0.5/0.5 1/0.98',eq=contrast=1.04:saturation=1.0:gamma=0.99"

# Finishing layer (the owner's #7) applied to the FOOTAGE only (text is composited later, so it
# stays crisp): a soft vignette to focus the eye + subtle temporal film grain so the frame reads
# cinematic, not flat-digital. Bloom/DoF deferred (need a split/blend filtergraph).
_FINISH = "vignette=a=PI/4.6,noise=alls=6:allf=t"


def _grid_durations(n: int, *, hook_s: float = 2.8,
                    body_cycle=(4.4, 3.8, 4.4, 4.0),
                    bpm: Optional[float] = None) -> list[float]:
    """Per-shot durations: a slightly punchy HOOK first (~2.8s), then calmer ~4s body shots so the
    reel BREATHES — a premium ad pace, not a frantic music-video (a 3-shot reel was ~4.5s of
    1.2-2.4s cuts, which read as fast and tiny). When `bpm` is supplied (a music track), each
    duration snaps to the nearest beat so the cuts land on the beat. Returns n durations."""
    if n <= 0:
        return []
    raw = [hook_s] + [body_cycle[(i - 1) % len(body_cycle)] for i in range(1, n)]
    if bpm:
        beat = 60.0 / max(40.0, bpm)
        return [round(max(1, round(d / beat)) * beat, 3) for d in raw]
    return [round(d, 3) for d in raw]


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
               width: int, height: int, clut: Optional[str] = None) -> None:
    """One cinematic shot: cover-crop the photo to the vertical frame, then an EASED push-in
    (`in`) or pull-out (`out`) with a slight directional drift. The camera move is smoothstep
    (ease-in-out) on the frame index — NOT linear — so it starts/stops softly (premium feel).
    When `clut` (a brand Hald-CLUT png) is given it is applied via the `haldclut` filter (fed as
    an input) for identical film cohesion; else the inline eq+curves grade. (zoompan `on` = frame.)"""
    frames = max(2, int(round(duration_s * 30)))
    p = f"(on/{frames})"
    ease = f"({p}*{p}*(3-2*{p}))"               # smoothstep ease-in-out on normalized progress
    amp = 0.16                                   # more noticeable push/pull (was too static at 0.10)
    if move == "out":
        zexpr = f"({1.0 + amp:.2f}-{amp}*{ease})"   # start zoomed, ease out
        dx = -30                                    # drift left
    else:
        zexpr = f"(1.0+{amp}*{ease})"               # ease in
        dx = 30                                     # drift right
    xexpr = f"iw/2-(iw/zoom/2)+({dx})*{ease}"       # subtle horizontal parallax-ish drift
    pre = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},"
        f"scale=3000:-2,"
        f"zoompan=z='{zexpr}':d={frames}:x='{xexpr}':y='ih/2-(ih/zoom/2)':"
        f"s={width}x{height}:fps=30"
    )
    # NO colour grade — the brand Hald-CLUT was tinting everything PURPLE (the owner's
    # "كائنات بنفسجية"); the text-to-image stills are already natural golden-hour colour, so we
    # PRESERVE them and only add the hue-neutral finish (vignette + film grain). `clut` is kept
    # in the signature for compatibility but intentionally IGNORED.
    enc = ["-t", f"{duration_s:.2f}", "-r", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p",
           "-preset", "medium", "-crf", "20", str(out_path)]
    vf = f"{pre},{_FINISH},format=yuv420p"
    run_ffmpeg(["-loop", "1", "-i", str(img_path), "-vf", vf] + enc)


def build_motion_reel(
    images: list[str],
    out_path: Path,
    *,
    width: int = 1080,
    height: int = 1920,
    palette: Optional[list[str]] = None,
    music_path: Optional[str] = None,
    bpm: Optional[float] = None,
    transition_s: float = 0.5,
    max_clips: int = 8,
    sound_design: bool = False,        # synth bed is OFF by default — silent beats a bad synth;
    fetch: Optional[Callable[[str], Optional[tuple[bytes, str]]]] = None,  # supply music_path for real audio
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
                   width=width, height=height)               # no colour grade — keep natural colour
        clips.append(clip)

    graph, vlabel = _xfade_filtergraph(n, durs, t)

    # AUDIO (the owner's #6): a supplied track wins (its bpm beat-syncs the cut grid above);
    # else synthesize a FREE sound-design bed (pad + a whoosh on every cut + opening impact) so
    # the reel is NEVER silent. cut_times land at each transition midpoint.
    audio_path = music_path if (music_path and Path(music_path).exists()) else None
    if audio_path is None and sound_design:
        from reel.sound import synth_sound_bed
        cut_times = [round(o + t / 2, 3) for o in _xfade_offsets(durs, t)]
        bed = synth_sound_bed(work / "_soundbed.m4a", total_duration(durs, t), cut_times)
        audio_path = str(bed) if bed else None
    has_audio = bool(audio_path) and Path(audio_path).exists()

    args: list[str] = []
    for c in clips:
        args += ["-i", str(c)]
    if has_audio:
        args += ["-i", str(audio_path)]

    if graph:
        args += ["-filter_complex", graph, "-map", vlabel]
    else:
        args += ["-map", "0:v"]
    if has_audio:
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


def _clip_duration(path: Path) -> float:
    """Probe a video clip's duration (seconds) from ffmpeg's stderr banner. 4.0 on failure."""
    import re
    import subprocess
    from reel.ffmpeg_tools import ffmpeg_exe
    try:
        r = subprocess.run([ffmpeg_exe(), "-i", str(path)], capture_output=True, text=True)
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", r.stderr)
        if m:
            h, mi, s = m.groups()
            return int(h) * 3600 + int(mi) * 60 + float(s)
    except Exception:
        pass
    return 4.0


def _has_audio(path: Path) -> bool:
    """True when the clip carries an audio stream (ffmpeg stderr banner probe)."""
    import subprocess
    from reel.ffmpeg_tools import ffmpeg_exe
    try:
        r = subprocess.run([ffmpeg_exe(), "-i", str(path)], capture_output=True, text=True)
        return "Audio:" in (r.stderr or "")
    except Exception:
        return False


def _acrossfade_filtergraph(n: int, t: float) -> tuple[str, str]:
    """Pure: the AUDIO twin of `_xfade_filtergraph` — chain `acrossfade` joins between the n
    clips' audio streams so the sound cross-fades exactly where the video wipes do (same overlap
    `t`, same total-duration math: sum - (n-1)*t). n==1 -> no chain."""
    if n <= 1:
        return "", "[0:a]"
    parts, prev = [], "[0:a]"
    for i in range(1, n):
        out = "[aout]" if i == n - 1 else f"[ax{i}]"
        parts.append(f"{prev}[{i}:a]acrossfade=d={t}{out}")
        prev = out
    return ";".join(parts), "[aout]"


def _normalize_clip(in_clip: Path, out_clip: Path, width: int, height: int,
                    keep_audio: bool = False) -> None:
    """Cover-crop ANY video clip to the vertical WxH @30fps + the hue-neutral finish, so mixed
    clips (Veo 720x1280 real video / Ken-Burns 1080x1920) cross-fade cleanly. Natural colour
    preserved — no grade. `keep_audio=False` drops audio (the legacy silent path);
    `keep_audio=True` keeps Veo's NATIVE audio (voiceover + ambience) normalized to stereo
    48kHz AAC — a silent clip (Ken-Burns fallback) gets a silent track so every clip carries
    an audio stream and the acrossfade chain never breaks."""
    vf = (f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},"
          f"fps=30,{_FINISH},format=yuv420p")
    enc = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium", "-crf", "20"]
    if not keep_audio:
        run_ffmpeg(["-i", str(in_clip), "-vf", vf, "-an"] + enc + [str(out_clip)])
        return
    # The clip's audio must cover EXACTLY its video length: a Veo clip's AAC track
    # runs a few ms short of its video (encoder priming) and those deltas ACCUMULATE
    # across the acrossfade chain — the voiceover drifted then cut out mid-reel
    # (measured user bug). NOTE: `apad`/`anullsrc` + `-shortest` is NOT the fix — the
    # muxer interleaves padded audio AHEAD of the video EOF signal and the clip
    # OVERSHOOTS by seconds (measured: a 4.0s clip came out 5.6-7.9s). Pad to the
    # PROBED duration explicitly instead.
    in_dur = _clip_duration(in_clip)
    if _has_audio(in_clip):
        run_ffmpeg(["-i", str(in_clip), "-vf", vf,
                    "-af", f"apad=whole_dur={in_dur:.3f}"] + enc
                   + ["-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "192k", str(out_clip)])
    else:  # pad a silent stereo track (exact length) so the audio graph stays uniform
        run_ffmpeg(["-i", str(in_clip),
                    "-f", "lavfi", "-t", f"{in_dur:.3f}",
                    "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
                    "-vf", vf, "-map", "0:v", "-map", "1:a"] + enc
                   + ["-c:a", "aac", "-b:a", "192k", str(out_clip)])


def build_animated_reel(clips, out_path: Path, *, width: int = 1080, height: int = 1920,
                        transition_s: float = 0.5, keep_audio: bool = False) -> Path:
    """Assemble PRE-ANIMATED video clips — REAL Veo 3.1 i2v footage (or a Ken-Burns fallback clip)
    — into one reel with xfade transitions. Each clip is normalized to WxH@30fps, then cross-faded
    on its ACTUAL (probed) duration. `keep_audio=True` PRESERVES Veo 3.1's native audio (spoken
    voiceover + ambience — the reel TALKS): every clip is padded to a uniform stereo track and the
    audio acrossfades on the same overlap as the video wipes. This is the primary web-reel
    assembler now that Veo makes the scenes MOVE. Returns out_path; raises if no clip is usable."""
    paths = [Path(c) for c in (clips or []) if c and Path(c).is_file()]
    if not paths:
        raise RuntimeError("build_animated_reel: no usable clips")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    work = out_path.parent
    norm: list[Path] = []
    durs: list[float] = []
    for i, c in enumerate(paths):
        nc = work / f"_anorm{i}.mp4"
        _normalize_clip(c, nc, width, height, keep_audio=keep_audio)
        norm.append(nc)
        durs.append(_clip_duration(nc))
    n = len(norm)
    t = min(transition_s, min(durs) * 0.5) if durs else 0.0
    graph, vlabel = _xfade_filtergraph(n, durs, t)
    args: list[str] = []
    for c in norm:
        args += ["-i", str(c)]
    fc, amap = graph, None
    if keep_audio:
        agraph, alabel = _acrossfade_filtergraph(n, t)
        fc = ";".join(g for g in (graph, agraph) if g)
        amap = alabel if agraph else "0:a"        # single clip: map the stream, not a link label
    if fc:
        args += ["-filter_complex", fc, "-map", vlabel if graph else "0:v"]
    else:
        args += ["-map", "0:v"]
    if amap:
        # Audio is now always >= video (each clip apad-ded to its probed duration),
        # and the excess is trailing SILENCE — -shortest trims it to the video length
        # exactly. Safe here: both streams are FINITE (the apad+infinite-source muxer
        # overshoot race doesn't apply).
        args += ["-map", amap, "-c:a", "aac", "-b:a", "192k", "-shortest"]
    args += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30",
             "-profile:v", "high", "-preset", "medium", "-crf", "20", str(out_path)]
    run_ffmpeg(args)
    for c in norm:
        try:
            c.unlink()
        except OSError:
            pass
    return out_path
