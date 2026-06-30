"""Procedural SOUND DESIGN for the reel (the owner's #6 — "sound is half the feel").

The web reel was SILENT and there is NO royalty-free music bundled (and we can't license
one). So this synthesizes a tasteful, free sound bed ENTIRELY with the bundled ffmpeg's
audio-synthesis filters (sine / anoisesrc / aevalsrc — VERIFIED present in imageio-ffmpeg):
  * a quiet low ambient PAD (a detuned two-note drone) so the reel never feels dead,
  * a WHOOSH on every cut (timed to the transition offsets) — the classic transition sweep,
  * an opening IMPACT (a soft low boom) under the hero word — the "hit".
This is sound DESIGN, not music: when a real `music_path` is supplied the compositor/motion
engine muxes THAT instead (and the cuts beat-sync to its bpm). Never raises — on any failure
the caller just gets a silent reel (today's behavior), so it can't break a render.
"""
from __future__ import annotations

import math
import struct
import wave
from pathlib import Path
from typing import Optional

from reel.ffmpeg_tools import run_ffmpeg


def _wave_impact_fallback(out_path: str | Path, total_s: float) -> Optional[Path]:
    """stdlib-ONLY fallback (the owner's #ج): if ffmpeg's audio-synth filters are ever missing
    from the build, write a short low IMPACT then silence as a real WAV via the `wave` module —
    so the CTA/opening still gets a hit and the reel is never dead-silent. No external library."""
    try:
        sr = 44100
        n = max(sr, int(float(total_s) * sr))
        path = Path(out_path).with_suffix(".wav")
        impact_n = int(0.5 * sr)
        frames = bytearray()
        for i in range(impact_n):                       # a 62Hz boom decaying over ~0.4s
            t = i / sr
            s = math.exp(-t * 8.0) * math.sin(2 * math.pi * 62 * t) * 0.7
            frames += struct.pack("<h", int(max(-1.0, min(1.0, s)) * 32767))
        with wave.open(str(path), "w") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sr)
            w.writeframes(bytes(frames))
            w.writeframes(b"\x00\x00" * (n - impact_n))  # silence to length (bulk, fast)
        return path if path.exists() else None
    except Exception:
        return None


def synth_sound_bed(
    out_path: str | Path,
    total_s: float,
    cut_times: Optional[list[float]] = None,
    *,
    impact: bool = True,
) -> Optional[Path]:
    """Synthesize a sound bed (pad + whooshes at `cut_times` + opening impact) into an .m4a.
    Returns the path, or None on failure (caller falls back to silence). Pure ffmpeg synth —
    no external assets, no network."""
    out_path = Path(out_path)
    total = max(1.0, float(total_s))
    cuts = [c for c in (cut_times or []) if 0.2 < c < total - 0.1]

    inputs: list[str] = []
    filters: list[str] = []
    mix_labels: list[str] = []
    idx = 0

    # 0) ambient PAD — two quiet detuned low sines (A2 + a soft fifth), lowpassed = a warm drone.
    inputs += ["-f", "lavfi", "-i",
               f"aevalsrc=0.05*sin(2*PI*110*t)+0.035*sin(2*PI*164.81*t):d={total:.2f}:s=44100"]
    filters.append(f"[{idx}:a]lowpass=f=520,volume=0.55,"
                   f"afade=t=in:d=0.6,afade=t=out:st={max(0.0, total - 1.2):.2f}:d=1.2[pad]")
    mix_labels.append("[pad]")
    idx += 1

    # 1) opening IMPACT — a soft low boom under the hero word.
    if impact:
        inputs += ["-f", "lavfi", "-i", "sine=frequency=62:duration=0.5:sample_rate=44100"]
        filters.append(f"[{idx}:a]afade=t=out:st=0.06:d=0.42,lowpass=f=180,volume=0.85[imp]")
        mix_labels.append("[imp]")
        idx += 1

    # 2..) a WHOOSH per cut — pink-noise sweep, band-limited, delayed to just before the cut.
    for c in cuts:
        inputs += ["-f", "lavfi", "-i", "anoisesrc=d=0.6:c=pink:a=0.7:r=44100"]
        ms = int(max(0.0, c - 0.3) * 1000)
        filters.append(
            f"[{idx}:a]highpass=f=320,lowpass=f=5200,"
            f"afade=t=in:d=0.3,afade=t=out:st=0.3:d=0.3,volume=0.5,"
            f"adelay={ms}|{ms}[w{idx}]"
        )
        mix_labels.append(f"[w{idx}]")
        idx += 1

    n = len(mix_labels)
    filters.append(
        "".join(mix_labels)
        + f"amix=inputs={n}:normalize=0,atrim=0:{total:.2f},"
        + "alimiter=limit=0.95,aresample=44100[out]"
    )
    graph = ";".join(filters)

    try:
        run_ffmpeg(inputs + [
            "-filter_complex", graph, "-map", "[out]",
            "-c:a", "aac", "-b:a", "160k", str(out_path),
        ])
    except Exception:
        return _wave_impact_fallback(out_path, total)   # owner's #ج — never dead-silent
    return out_path if out_path.exists() else _wave_impact_fallback(out_path, total)
