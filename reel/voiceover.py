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
# Default to gpt-audio-1.5 — OpenAI's newest CONVERSATIONAL audio model. It sounds
# noticeably more HUMAN than the gpt-4o-mini-tts speech endpoint and is steered with
# a full system prompt (so we can push hard for a natural Egyptian read). It runs via
# chat.completions (modalities=audio), not /audio/speech. 'marin' is the newest voice.
# Honest ceiling: still not a NATIVE ar-EG human — for that wire ElevenLabs / Azure
# (Salma/Shakir). Override via REEL_TTS_MODEL / REEL_TTS_VOICE / REEL_TTS_INSTRUCTIONS.
_DEFAULT_MODEL = "gpt-audio-1.5"
_DEFAULT_VOICE = "marin"
_SPEECH_VOICE = "onyx"          # valid /audio/speech voice for the fallback path

# Arabic-presentation detection -> Egyptian-accent instruction.
_AR_RE = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")


def _instructions_for(lines: list[str], delivery: str = "") -> str:
    """Performance brief for one line. Pushes hard for EMOTION (the default read came
    out flat) and optionally folds in a per-line delivery note from the director."""
    env = os.environ.get("REEL_TTS_INSTRUCTIONS")
    base = env if env else (
        _AR_RE.search(" ".join(lines or [])) and (
            "You are a passionate, EXPRESSIVE human voice-over artist performing a premium "
            "food-brand ad. Perform with REAL EMOTION and energy — sound genuinely excited, "
            "proud and warm; let your pitch rise and fall, lean into the appetizing words, "
            "add a smile you can hear and natural enthusiasm. Authentic EGYPTIAN ARABIC "
            "(Cairo dialect / اللهجة المصرية) — NOT flat, NOT a news reader, NOT robotic. "
            "Vary your pace and build energy."
        ) or (
            "You are a passionate, EXPRESSIVE human voice-over artist for a premium brand ad. "
            "Perform with real emotion and energy — excited, warm, dynamic; vary pace and pitch, "
            "lean into the key words. Sound human and alive, never flat or robotic."
        )
    )
    if delivery:
        base += f" For THIS line, the emotion/delivery is: {delivery}."
    return base + " Speak ONLY the line you are given, no extra words."


def _synth_one(client, text: str, out: Path, *, model: str, voice: str,
               instructions: str) -> bool:
    """One line -> mp3. gpt-audio* models go through chat.completions (audio
    modality, steered by a system prompt); tts/* models go through /audio/speech."""
    if model.startswith("gpt-audio"):
        import base64
        r = client.chat.completions.create(
            model=model, modalities=["text", "audio"],
            audio={"voice": voice, "format": "mp3"},
            messages=[{"role": "system", "content": instructions},
                      {"role": "user", "content": text}],
        )
        data = base64.b64decode(r.choices[0].message.audio.data)
        out.write_bytes(data)
    else:
        kw = {"instructions": instructions} if model == "gpt-4o-mini-tts" else {}
        client.audio.speech.create(model=model, voice=voice, input=text, **kw).stream_to_file(str(out))
    return out.is_file() and out.stat().st_size > 0


def _tts_segment(client, text: str, out: Path, *, model: str, voice: str,
                 instructions: str) -> bool:
    """Synthesize one line, trying the chosen (human) model first, then degrading to
    the steerable speech model, then plain tts-1. Returns False only if all fail."""
    text = (text or "").strip()
    if not text:
        return False
    chain = [(model, voice)]
    if not model.startswith("gpt-4o-mini-tts"):
        chain.append(("gpt-4o-mini-tts", _SPEECH_VOICE))
    chain.append(("tts-1", _SPEECH_VOICE))
    for mdl, vc in chain:
        try:
            if _synth_one(client, text, out, model=mdl, voice=vc, instructions=instructions):
                return True
        except Exception as e:  # noqa: BLE001
            logger.warning("tts segment failed (model=%s): %s", mdl, e)
    return False


# ---------------------------------------------------------------------
# Gemini TTS (runs on the SAME GCP/Vertex credits as Imagen/Veo — no OpenAI key
# needed). gemini-2.5-flash-preview-tts returns raw PCM (L16, mono); we wrap it in a
# WAV so the shared ffmpeg pad/trim path below handles it identically to OpenAI mp3s.
# ---------------------------------------------------------------------
_GEMINI_TTS_MODEL = "gemini-2.5-flash-preview-tts"
_GEMINI_VOICE = "Kore"          # a clear, warm prebuilt voice; multilingual (auto-detects Arabic)


def _gemini_client():
    """Vertex (GCP credits, ADC) or a Gemini API key. None if neither is available."""
    try:
        from google import genai
    except Exception:
        return None
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if api_key:
        return genai.Client(api_key=api_key)
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if project:
        return genai.Client(vertexai=True, project=project,
                            location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"))
    return None


def _gemini_segment(client, text: str, out_wav: Path, *, voice: str, model: str,
                    instructions: str) -> bool:
    """One narration line -> WAV via Gemini TTS. The style brief is prepended to the
    text (Gemini TTS is steered by a natural-language directive in the content)."""
    text = (text or "").strip()
    if not text:
        return False
    from google.genai import types
    import re as _re
    import wave
    prompt = f"{instructions}\n\nLine to say: {text}" if instructions else text
    try:
        r = client.models.generate_content(
            model=model, contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice))),
            ),
        )
        parts = r.candidates[0].content.parts
        blob = next((p.inline_data for p in parts if getattr(p, "inline_data", None)), None)
        if not blob or not blob.data:
            return False
        rate = 24000
        m = _re.search(r"rate=(\d+)", getattr(blob, "mime_type", "") or "")
        if m:
            rate = int(m.group(1))
        with wave.open(str(out_wav), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(blob.data)
        return out_wav.is_file() and out_wav.stat().st_size > 44
    except Exception as e:  # noqa: BLE001
        logger.warning("gemini tts segment failed: %s", e)
        return False


# ---------------------------------------------------------------------
# edge-tts — FREE, keyless TTS (Microsoft Edge read-aloud). For Arabic it provides a
# NATIVE Egyptian voice (ar-EG-SalmaNeural / -ShakirNeural), which is both cheaper
# (zero cost) and more authentic for ar-EG reels than the English-leaning OpenAI
# voices. Online (Microsoft endpoint), no API key, outputs mp3. Pace/pitch can be
# steered (rate/pitch); there is no free-form 'instructions' prompt, so the emotional
# brief is not applied here — the native dialect carries the read.
# Override the voice via REEL_TTS_VOICE.
# ---------------------------------------------------------------------
_EDGE_VOICE_AR = "ar-EG-SalmaNeural"     # Egyptian Arabic, female (warm)
_EDGE_VOICE_EN = "en-US-AriaNeural"      # default English voice
_EDGE_RATE = os.environ.get("REEL_TTS_EDGE_RATE", "+0%")
_EDGE_PITCH = os.environ.get("REEL_TTS_EDGE_PITCH", "+0Hz")


def _edge_voice_for(text: str, override: Optional[str]) -> str:
    """Pick a native Egyptian voice for Arabic copy, else an English voice."""
    if override:
        return override
    return _EDGE_VOICE_AR if _AR_RE.search(text or "") else _EDGE_VOICE_EN


def _edge_segment(text: str, out_mp3: Path, *, voice: str) -> bool:
    """One narration line -> mp3 via edge-tts (free). The lib is async, so we drive it
    with asyncio.run (the reel pipeline is synchronous). Never raises -> False on any
    failure (offline / endpoint error) so the caller degrades to silent filler."""
    text = (text or "").strip()
    if not text:
        return False
    try:
        import asyncio
        import edge_tts

        async def _run() -> None:
            await edge_tts.Communicate(
                text, voice, rate=_EDGE_RATE, pitch=_EDGE_PITCH
            ).save(str(out_mp3))

        asyncio.run(_run())
        return out_mp3.is_file() and out_mp3.stat().st_size > 0
    except Exception as e:  # noqa: BLE001
        logger.warning("edge tts segment failed: %s", e)
        return False


def narration_lines(storyboard) -> list[str]:
    """One grounded narration line PER scene — the verbatim text already shown on that
    scene (headline -> first subline -> CTA). Empty for scenes with no text (silent)."""
    out: list[str] = []
    for s in storyboard.scenes:
        txt = (s.headline or (s.sublines[0] if s.sublines else "") or s.cta_text or "")
        out.append(str(txt).strip())
    return out


def _resolve_backend(backend: Optional[str]) -> str:
    """gemini | openai | edge. Explicit > REEL_TTS_BACKEND > auto.

    Auto prefers a configured PAID backend (Gemini on GCP credits, else OpenAI by key),
    and falls back to FREE, keyless `edge` when no paid backend is configured — so a
    reel always gets a voice instead of going silent. Set REEL_TTS_BACKEND=edge to force
    the free native-Egyptian voice and skip the paid TTS spend entirely."""
    b = (backend or os.environ.get("REEL_TTS_BACKEND") or "").lower()
    if b in ("gemini", "openai", "edge"):
        return b
    if os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    return "edge"


def synth_voiceover(
    lines: list[str],
    durations: list[float],
    out_path: str | Path,
    *,
    model: Optional[str] = None,
    voice: Optional[str] = None,
    deliveries: Optional[list[str]] = None,
    api_key: Optional[str] = None,
    backend: Optional[str] = None,
) -> Optional[Path]:
    """Build a single narration track aligned to `durations` (one entry per scene).
    `deliveries` (optional, one per line) is a per-line emotion/performance note from
    the director, folded into that line's instruction so each scene is performed with
    its own feeling. `backend` selects the TTS engine (gemini | openai; default auto).
    Returns the audio path, or None if TTS is unavailable."""
    if not lines:
        return None
    chosen = _resolve_backend(backend)

    gem_client = _gemini_client() if chosen == "gemini" else None
    if chosen == "gemini" and gem_client is None:        # Gemini unavailable -> OpenAI
        chosen = "openai"

    oa_client = None
    if chosen == "openai":                               # OpenAI path needs a key
        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            return None
        try:
            from openai import OpenAI
        except ImportError:
            return None
        oa_client = OpenAI(api_key=key)
    # chosen == "edge" needs no client/key (free, keyless).

    model = model or os.environ.get("REEL_TTS_MODEL") or (
        _GEMINI_TTS_MODEL if chosen == "gemini" else _DEFAULT_MODEL)
    if chosen == "edge":
        default_voice = _edge_voice_for(" ".join(lines), None)
    elif chosen == "gemini":
        default_voice = _GEMINI_VOICE
    else:
        default_voice = _DEFAULT_VOICE
    voice = voice or os.environ.get("REEL_TTS_VOICE") or default_voice
    deliveries = deliveries or []
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    import tempfile
    with tempfile.TemporaryDirectory(prefix="vo_") as tmp:
        tmpd = Path(tmp)
        seg_paths: list[Path] = []
        for i, (line, dur) in enumerate(zip(lines, durations)):
            scene_aud = tmpd / f"scene{i}.wav"
            ext = "wav" if chosen == "gemini" else "mp3"
            raw = tmpd / f"raw{i}.{ext}"
            instructions = _instructions_for(lines, deliveries[i] if i < len(deliveries) else "")
            if chosen == "gemini":
                ok = _gemini_segment(gem_client, line, raw, voice=voice, model=model,
                                     instructions=instructions)
            elif chosen == "edge":
                ok = _edge_segment(line, raw, voice=voice)
            else:
                ok = _tts_segment(oa_client, line, raw, model=model, voice=voice,
                                  instructions=instructions)
            if ok:
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
