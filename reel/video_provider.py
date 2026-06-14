"""Video providers for the Reel Studio (mirrors the poster's ImageProvider).

A `VideoProvider` generates ONE text-free scene clip and returns its mp4 path.
Like the poster's image providers, NONE of them draw text — all words are overlaid
later by the compositor (so Arabic shapes correctly; Veo, like Imagen, garbles
baked text).

  VideoProvider        - the protocol
  VeoProvider          - real: Google Veo 3.1 (Gemini API key OR Vertex AI)
  StubVideoProvider    - offline: animated brand-palette gradient (ffmpeg, no creds)

Two ways to authenticate VeoProvider (it auto-detects):
  * EASY  - a Gemini API key from Google AI Studio: set GEMINI_API_KEY (or
            GOOGLE_API_KEY). No gcloud needed.
  * Vertex - GOOGLE_CLOUD_PROJECT + ADC (`gcloud auth application-default login`).

Model defaults to Veo 3.1; override with REEL_VIDEO_MODEL (e.g. the cheaper/faster
`veo-3.1-fast-generate-preview` or `veo-3.1-lite-generate-preview`).
"""
from __future__ import annotations

import os
import time
import uuid
from pathlib import Path
from typing import Optional, Protocol, runtime_checkable

from .ffmpeg_tools import hex_to_ffmpeg, run_ffmpeg

DEFAULT_ASPECT = "9:16"
# Veo 3.1 (best quality). Cheaper variants: veo-3.1-fast-generate-preview,
# veo-3.1-lite-generate-preview. Veo 3: veo-3.0-generate-001.
DEFAULT_VEO_MODEL = "veo-3.1-generate-preview"
# Veo accepts only these clip lengths (seconds).
_VEO_DURATIONS = (4, 6, 8)


@runtime_checkable
class VideoProvider(Protocol):
    """Generates a text-free scene clip and returns the saved mp4 path."""
    name: str

    def generate(
        self,
        prompt: str,
        *,
        out_path: Path,
        duration_s: float,
        width: int,
        height: int,
        palette: Optional[list[str]] = None,
    ) -> Path:
        ...


def _new_clip_path(out_dir: str | Path) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    return out / f"clip_{uuid.uuid4().hex[:8]}.mp4"


class VeoProvider:
    """Real provider: Google Veo (3.1 by default).

    Auth auto-detects: a Gemini API key (GEMINI_API_KEY / GOOGLE_API_KEY) uses the
    Gemini Developer API; otherwise GOOGLE_CLOUD_PROJECT + ADC uses Vertex AI. The
    SDK is imported lazily so offline stub use needs neither.

    LIVE-ONLY: needs credentials + a paid tier with Veo access; it cannot run in a
    sandbox. Generation is a long-running operation, so we submit then poll.
    """
    name = "veo"

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        project: Optional[str] = None,
        location: Optional[str] = None,
        model: Optional[str] = None,
        poll_seconds: int = 10,
        max_wait_seconds: int = 600,
    ):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.project = project or os.getenv("GOOGLE_CLOUD_PROJECT")
        self.location = location or os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
        self.model = model or os.getenv("REEL_VIDEO_MODEL") or DEFAULT_VEO_MODEL
        self.poll_seconds = poll_seconds
        self.max_wait_seconds = max_wait_seconds

    def _client(self):
        from google import genai
        if self.api_key:                                    # Gemini API (no gcloud)
            return genai.Client(api_key=self.api_key)
        if self.project:                                    # Vertex AI (ADC)
            return genai.Client(vertexai=True, project=self.project, location=self.location)
        raise RuntimeError(
            "No Veo credentials. Set GEMINI_API_KEY (from Google AI Studio) in .env, "
            "OR GOOGLE_CLOUD_PROJECT + run `gcloud auth application-default login`."
        )

    def generate(
        self,
        prompt: str,
        *,
        out_path: Path,
        duration_s: float,
        width: int,
        height: int,
        palette: Optional[list[str]] = None,
    ) -> Path:
        from google.genai import types

        client = self._client()
        dur = min(_VEO_DURATIONS, key=lambda v: abs(v - duration_s))   # snap to 4/6/8
        operation = client.models.generate_videos(
            model=self.model,
            prompt=prompt,
            config=types.GenerateVideosConfig(
                aspect_ratio=DEFAULT_ASPECT,
                number_of_videos=1,
                duration_seconds=dur,
            ),
        )

        waited = 0
        while not getattr(operation, "done", False):
            if waited >= self.max_wait_seconds:
                raise RuntimeError(f"Veo generation timed out after {waited}s.")
            time.sleep(self.poll_seconds)
            waited += self.poll_seconds
            operation = client.operations.get(operation)

        response = getattr(operation, "response", None) or getattr(operation, "result", None)
        vids = getattr(response, "generated_videos", None) or []
        if not vids:
            raise RuntimeError("Veo returned no video (safety filter, quota, or no access?).")

        out_path.parent.mkdir(parents=True, exist_ok=True)
        gv = vids[0]
        video = getattr(gv, "video", gv)
        # Current SDK: download the file handle, then save / read bytes.
        try:
            client.files.download(file=video)
        except Exception:
            pass
        data = getattr(video, "video_bytes", None)
        if data:
            out_path.write_bytes(data)
        elif hasattr(video, "save"):
            video.save(str(out_path))
        else:
            raise RuntimeError("Veo video had no bytes to write.")
        return out_path


class StubVideoProvider:
    """Offline provider: an animated gradient in the brand palette (ffmpeg only).

    No network, no credits, no Google creds — so the whole reel pipeline (and
    tests) runs locally. The prompt is ignored; the palette drives the colors.
    """
    name = "stub"

    def __init__(self, fallback_palette: Optional[list[str]] = None):
        self.fallback_palette = fallback_palette or ["#15314F", "#2E6E9E", "#0A1622"]

    def generate(
        self,
        prompt: str,
        *,
        out_path: Path,
        duration_s: float,
        width: int,
        height: int,
        palette: Optional[list[str]] = None,
    ) -> Path:
        colors = [c for c in (palette or self.fallback_palette) if c][:3] or self.fallback_palette
        cparts = [f"c{i}={hex_to_ffmpeg(c)}" for i, c in enumerate(colors)]
        src = (
            f"gradients=s={width}x{height}:{':'.join(cparts)}"
            f":nb_colors={len(colors)}:speed=0.006:duration={duration_s:.2f}:rate=30:type=radial"
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        run_ffmpeg([
            "-f", "lavfi", "-i", src,
            "-t", f"{duration_s:.2f}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-profile:v", "high", "-preset", "veryfast",
            str(out_path),
        ])
        return out_path


def default_video_provider() -> VideoProvider:
    """VeoProvider when credentials are configured (API key OR Vertex), else the
    offline stub. Set REEL_FORCE_STUB=1 to always stub."""
    if os.getenv("REEL_FORCE_STUB") == "1":
        return StubVideoProvider()
    if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
        return VeoProvider()
    # Vertex AI via ADC (`gcloud auth application-default login`) — ADC does NOT
    # set GOOGLE_APPLICATION_CREDENTIALS, so a configured project alone is enough.
    if os.getenv("GOOGLE_CLOUD_PROJECT"):
        return VeoProvider()
    return StubVideoProvider()
