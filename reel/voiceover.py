"""Voice-over track for the reel (OpenAI TTS).

Turns the creative director's per-scene narration lines into ONE audio track timed
to the scene durations: each line is synthesized, then padded with silence (or
trimmed) to fill its scene, and the segments are concatenated so the narration
lands in sync with the visuals. No key/SDK -> None (the reel just renders silent).
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Optional

from .ffmpeg_tools import run_ffmpeg

logger = logging.getLogger(__name__)

# OpenAI TTS. gpt-4o-mini-tts accepts an `instructions` param to STEER the
# delivery (accent/emotion/pace) — so we can ask for an Egyptian-Arabic read. The
# underlying voices are English-leaning, so this approximates the dialect, it is not
# a native ar-EG voice; for that, wire Azure ar-EG (Salma/Shakir) or ElevenLabs.
# Override via REEL_TTS_MODEL / REEL_TTS_VOICE / REEL_TTS_INSTRUCTIONS.
_DEFAULT_MODEL = "gpt-4o-mini-tts"
_DEFAULT_VOICE = "onyx"
_FALLBACK_MODEL = "tts-1"

# Arabic-presentation detection -> Egyptian-accent instruction.
_AR_RE = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")


def _instructions_for(lines: list[str]) -> str:
    env = os.environ.get("REEL_TTS_INSTRUCTIONS")
    if env:
        return env
    joined = " ".join(lines or [])
    if _AR_RE.search(joined):
        return (
            "Speak in authentic, natural EGYPTIAN ARABIC (Cairo dialect / اللهجة المصرية), "
            "NOT Modern Standard Arabic. Warm, confident, charismatic — like a premium "
            "Egyptian food-brand ad voice-over artist. Energetic but smooth, with natural "
            "Egyptian intonation and rhythm."
        )
    return ("Warm, confident, premium brand ad voice-over — energetic but smooth, natural.")


def _tts_segment(client, text: str, out: Path, *, model: str, voice: str,
                 instructions: str) -> bool:
    """Synthesize one line to mp3. Tries the steerable model with `instructions`,
    then falls back to the basic model. Returns False on failure."""
    import re as _re  # noqa: F401  (module-level re already imported)
    text = (text or "").strip()
    if not text:
        return False
    for mdl, kw in ((model, {"instructions": instructions}), (_FALLBACK_MODEL, {})):
        try:
            resp = client.audio.speech.create(model=mdl, voice=voice, input=text, **kw)
            resp.stream_to_file(str(out))
            if out.is_file() and out.stat().st_size > 0:
                return True
        except Exception as e:  # noqa: BLE001
            logger.warning("tts segment failed (model=%s): %s", mdl, e)
    return False


def synth_voiceover(
    lines: list[str],
    durations: list[float],
    out_path: str | Path,
    *,
    model: Optional[str] = None,
    voice: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Optional[Path]:
    """Build a single narration track aligned to `durations` (one entry per scene).
    Returns the audio path, or None if TTS is unavailable / nothing synthesized."""
    key = api_key or os.environ.get("OPENAI_API_KEY")
    if not key or not lines:
        return None
    try:
        from openai import OpenAI
    except ImportError:
        return None
    client = OpenAI(api_key=key)
    model = model or os.environ.get("REEL_TTS_MODEL") or _DEFAULT_MODEL
    voice = voice or os.environ.get("REEL_TTS_VOICE") or _DEFAULT_VOICE
    instructions = _instructions_for(lines)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    import tempfile
    with tempfile.TemporaryDirectory(prefix="vo_") as tmp:
        tmpd = Path(tmp)
        seg_paths: list[Path] = []
        for i, (line, dur) in enumerate(zip(lines, durations)):
            scene_aud = tmpd / f"scene{i}.wav"
            raw = tmpd / f"raw{i}.mp3"
            if _tts_segment(client, line, raw, model=model, voice=voice, instructions=instructions):
                # Pad with trailing silence (or trim) so the line exactly fills the
                # scene; a short lead-in delay keeps it off the hard cut.
                run_ffmpeg([
                    "-i", str(raw),
                    "-af", f"adelay=200|200,apad",
                    "-t", f"{max(0.5, dur):.2f}", "-ar", "44100", "-ac", "2",
                    str(scene_aud),
                ])
            else:
                # silent filler so the track stays aligned to the visuals
                run_ffmpeg([
                    "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                    "-t", f"{max(0.5, dur):.2f}", str(scene_aud),
                ])
            seg_paths.append(scene_aud)

        if not seg_paths:
            return None
        listfile = tmpd / "vo_concat.txt"
        listfile.write_text("".join(f"file '{p.as_posix()}'\n" for p in seg_paths), encoding="utf-8")
        run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(listfile),
                    "-c:a", "aac", "-b:a", "192k", str(out_path.resolve())])
    return out_path if out_path.is_file() else None
