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

Model defaults to Veo 3 GA (`veo-3.0-generate-001`) — the model actually provisioned
on this project (MEASURED: `veo-3.1-*-preview`/`veo-3.1-generate-001` 404 NOT_FOUND on
project image-498715). Override with REEL_VIDEO_MODEL once a 3.1 model is provisioned.
"""
from __future__ import annotations

import os
import sys
import time
import uuid
from pathlib import Path
from typing import Optional, Protocol, runtime_checkable

from .ffmpeg_tools import hex_to_ffmpeg, run_ffmpeg

DEFAULT_ASPECT = "9:16"
# Veo 3.1 GA — GCP deprecated veo-3.0-generate-001 and recommends veo-3.1-generate-001.
# The earlier 404 was the `-preview` suffix; the GA `-generate-001` is the supported id.
# Override via REEL_VIDEO_MODEL. (Runs on Vertex via ADC + GOOGLE_CLOUD_PROJECT.)
DEFAULT_VEO_MODEL = "veo-3.1-generate-001"
# Veo accepts only these clip lengths (seconds).
_VEO_DURATIONS = (4, 6, 8)


@runtime_checkable
class VideoProvider(Protocol):
    """Generates a text-free scene clip and returns the saved mp4 path.

    `reference_image` (optional) is a scraped brand photo (local path or public
    http(s) URL) used to GROUND generation: real providers seed image-to-video
    from it so the clip resembles the brand's actual imagery. Providers that can't
    condition on an image MUST ignore it gracefully (never fail because of it).
    """
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
        reference_image: Optional[str] = None,
    ) -> Path:
        ...


def _new_clip_path(out_dir: str | Path) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    return out / f"clip_{uuid.uuid4().hex[:8]}.mp4"


def _mime_for(ctype: str, low_src: str) -> Optional[str]:
    """Pick a raster image MIME from a Content-Type header and/or the src suffix.
    Returns None for SVG / unknown (Veo needs a raster seed)."""
    if "svg" in ctype or low_src.endswith(".svg"):
        return None
    if "jpeg" in ctype or "jpg" in ctype or low_src.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if "webp" in ctype or low_src.endswith(".webp"):
        return "image/webp"
    if "gif" in ctype or low_src.endswith(".gif"):
        return "image/gif"
    if "png" in ctype or low_src.endswith(".png"):
        return "image/png"
    # Default to JPEG — the common case for a hero photo with no usable hint.
    return "image/jpeg"


def _to_vertical_seed(data: bytes, *, width: int = 768, height: int = 1366) -> tuple[bytes, str]:
    """Make a FULL-FRAME 9:16 seed so Veo i2v doesn't letterbox a landscape photo.

    Default 'cover' crops to fill (sharp, professional, the standard reel look).
    Set REEL_SEED_FILL=blur to instead CONTAIN the whole photo over a blurred copy
    (keeps every edge, slightly softer), or REEL_SEED_FILL=none to pass through.
    Returns (jpeg_bytes, 'image/jpeg'); falls back to the input on any error."""
    mode = (os.getenv("REEL_SEED_FILL") or "cover").lower()
    if mode == "none":
        return data, "image/jpeg"
    try:
        import io
        from PIL import Image, ImageEnhance, ImageFilter, ImageOps
        img = Image.open(io.BytesIO(data)).convert("RGB")
        if mode == "blur":
            bg = ImageOps.fit(img, (width, height), method=Image.LANCZOS)
            bg = ImageEnhance.Brightness(bg.filter(ImageFilter.GaussianBlur(40))).enhance(0.55)
            fg = img.copy()
            fg.thumbnail((width, height), Image.LANCZOS)
            bg.paste(fg, ((width - fg.width) // 2, (height - fg.height) // 2))
            canvas = bg
        else:  # cover
            canvas = ImageOps.fit(img, (width, height), method=Image.LANCZOS)
        buf = io.BytesIO()
        canvas.save(buf, format="JPEG", quality=88)
        return buf.getvalue(), "image/jpeg"
    except Exception:
        return data, "image/jpeg"


def _load_reference_image(src: str, *, timeout: int = 10) -> Optional[tuple[bytes, str]]:
    """Load a reference image as (bytes, mime). Accepts a local file path or a
    public http(s) URL (SSRF-guarded at fetch time — same discipline as the poster
    logo fetch: certifi first, unverified fallback ONLY on a cert-chain error, for
    a passive credential-free image GET). Returns None on any failure or for SVG."""
    if not src:
        return None
    s = str(src).strip()
    low = s.lower()

    local = Path(s)
    try:
        if local.is_file():
            data = local.read_bytes()
            mime = _mime_for("", low)
            return (data, mime) if (data and mime) else None
    except OSError:
        pass

    if not low.startswith(("http://", "https://")):
        return None
    try:
        from scraper.url_utils import is_safe_public_url
        if not is_safe_public_url(s):
            return None
        import ssl
        from urllib.request import Request, urlopen
        req = Request(s, headers={"User-Agent": "Mozilla/5.0 (ReelStudio)"})
        try:
            import certifi
            ctx = ssl.create_default_context(cafile=certifi.where())
        except Exception:
            ctx = ssl.create_default_context()
        try:
            resp = urlopen(req, timeout=timeout, context=ctx)
        except Exception as exc:                       # noqa: BLE001
            if "CERTIFICATE_VERIFY_FAILED" in str(exc):
                resp = urlopen(req, timeout=timeout, context=ssl._create_unverified_context())
            else:
                raise
        with resp as r:
            ctype = (r.headers.get("Content-Type") or "").lower()
            data = r.read(8_000_000)
        mime = _mime_for(ctype, low)
        return (data, mime) if (data and mime) else None
    except Exception:
        return None


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
        reference_image: Optional[str] = None,
    ) -> Path:
        from google.genai import types

        client = self._client()
        dur = min(_VEO_DURATIONS, key=lambda v: abs(v - duration_s))   # snap to 4/6/8

        def _submit(image_obj):
            kwargs = dict(
                model=self.model,
                prompt=prompt,
                config=types.GenerateVideosConfig(
                    aspect_ratio=DEFAULT_ASPECT,
                    number_of_videos=1,
                    duration_seconds=dur,
                ),
            )
            if image_obj is not None:
                kwargs["image"] = image_obj           # image-to-video seed
            return client.models.generate_videos(**kwargs)

        # GROUNDING (#4): seed from the brand's real scraped photo when available,
        # so the footage resembles the actual brand. Never let it break a render —
        # if loading or i2v submission fails, fall back to pure text-to-video.
        # The stderr notes make the i2v-vs-fallback path OBSERVABLE in the reel log
        # (so "the reel is grounded in the real image" is verifiable, not assumed).
        image_obj = None
        if reference_image:
            loaded = _load_reference_image(str(reference_image))
            if loaded:
                data, mime = loaded
                # Letterbox-free: reframe the seed to a full 9:16 canvas so Veo
                # outputs a full-frame vertical clip (no black bars on landscape photos).
                data, mime = _to_vertical_seed(data)
                try:
                    image_obj = types.Image(image_bytes=data, mime_type=mime)
                    print(f"[veo] image-to-video seed: {mime}, {len(data)} bytes "
                          f"from {str(reference_image)[:80]}", file=sys.stderr)
                except Exception:
                    image_obj = None
            else:
                print(f"[veo] reference image unusable ({str(reference_image)[:80]}); "
                      "text-to-video", file=sys.stderr)

        try:
            operation = _submit(image_obj)
        except Exception as exc:                      # noqa: BLE001
            if image_obj is None:
                raise
            print(f"[veo] image-to-video rejected ({type(exc).__name__}); "
                  "falling back to text-to-video", file=sys.stderr)
            operation = _submit(None)                 # i2v rejected -> text-to-video

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
        reference_image: Optional[str] = None,   # ignored: the stub has no model to seed
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


# Ken Burns motion presets (slow zoom toward a focal region) — varied so a SINGLE
# real photo still feels alive across scenes. Each entry is (x_expr, y_expr); all
# zoom in slowly toward that region. Expressions are ffmpeg zoompan exprs over the
# pre-upscaled image (iw/ih are the big intermediate's dims; zoom is the per-frame z).
_KENBURNS_MOVES = (
    ("iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),   # 0: zoom into center
    ("iw/2-(iw/zoom/2)", "0"),                   # 1: drift toward the top
    ("iw/2-(iw/zoom/2)", "ih-(ih/zoom)"),        # 2: drift toward the bottom
    ("0", "ih/2-(ih/zoom/2)"),                   # 3: drift toward the left
    ("iw-(iw/zoom)", "ih/2-(ih/zoom/2)"),        # 4: drift toward the right
)


class KenBurnsProvider:
    """FAITHFUL provider: animates the business's REAL scraped photo(s) with a slow
    Ken Burns pan/zoom (ffmpeg `zoompan`). No model, no invented scenes — the reel
    literally comes from the actual place (the user's "REEL جاي من المكان اصلا").

    Cycles through the provided real images; varies the motion by call index so even
    one photo stays alive across scenes. Landscape photos are cover-cropped to the
    vertical frame. If an image can't be loaded (or none were given) it falls back to
    a brand-palette gradient so a render never breaks — but it NEVER fabricates a scene.
    """
    name = "kenburns"

    def __init__(
        self,
        images: Optional[list[str]] = None,
        *,
        fallback_palette: Optional[list[str]] = None,
    ):
        # Dedup-preserving order; drop blanks. These are real http(s)/local images.
        seen: set[str] = set()
        self.images = []
        for s in (images or []):
            s = (s or "").strip()
            if s and s not in seen:
                seen.add(s)
                self.images.append(s)
        self.fallback_palette = fallback_palette or ["#15314F", "#2E6E9E", "#0A1622"]
        self._call = 0  # advances per scene -> cycles image + motion preset

    def _gradient_fallback(self, out_path: Path, duration_s: float, width: int,
                           height: int, palette: Optional[list[str]]) -> Path:
        StubVideoProvider(self.fallback_palette).generate(
            "", out_path=out_path, duration_s=duration_s, width=width,
            height=height, palette=palette,
        )
        return out_path

    def generate(
        self,
        prompt: str,                              # ignored — the real photo IS the scene
        *,
        out_path: Path,
        duration_s: float,
        width: int,
        height: int,
        palette: Optional[list[str]] = None,
        reference_image: Optional[str] = None,
    ) -> Path:
        idx = self._call
        self._call += 1
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # The scene's own seed (reference_image, a real CONTENT photo) wins; the
        # provider's pool is the fallback. Try several (cycling) so an INTERMITTENT
        # CDN fetch failure on one photo yields ANOTHER real photo, not a gradient.
        candidates: list[str] = []
        if reference_image:
            candidates.append(str(reference_image))
        if self.images:
            n = len(self.images)
            candidates += [self.images[(idx + k) % n] for k in range(min(n, 4))]
        loaded = None
        for src in candidates:
            loaded = _load_reference_image(str(src))
            if loaded:
                break
        if not loaded:
            return self._gradient_fallback(out_path, duration_s, width, height, palette)

        data, mime = loaded
        ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
               "image/gif": ".gif"}.get(mime, ".jpg")
        img_path = out_path.with_suffix(ext + ".src")
        img_path.write_bytes(data)

        frames = max(2, int(round(duration_s * 30)))
        xexpr, yexpr = _KENBURNS_MOVES[idx % len(_KENBURNS_MOVES)]
        # Cover-crop the photo to the vertical frame, upscale (zoompan is smoother on
        # a big intermediate), then a slow ~12% zoom toward the preset's focal region.
        # Single quotes inside the expr are ffmpeg's own quoting (protect the commas).
        vf = (
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},scale=4000:-2,"
            f"zoompan=z='min(zoom+0.0011,1.12)':d={frames}:"
            f"x='{xexpr}':y='{yexpr}':s={width}x{height}:fps=30,"
            f"format=yuv420p"
        )
        try:
            run_ffmpeg([
                "-loop", "1", "-i", str(img_path), "-t", f"{duration_s:.2f}",
                "-vf", vf, "-r", "30",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-profile:v", "high", "-preset", "medium", "-crf", "20",
                str(out_path),
            ])
        except Exception:
            return self._gradient_fallback(out_path, duration_s, width, height, palette)
        finally:
            try:
                img_path.unlink()
            except OSError:
                pass
        return out_path


class AimlVeoProvider:
    """Real provider via the AIML API gateway (https://aimlapi.com).

    Gives access to **Veo 3.1 image-to-video** (`google/veo-3.1-i2v`) WITHOUT Vertex
    provisioning (our project only has Veo 3.0 on Vertex), and Veo 3.1 renders NATIVE
    audio/voiceover straight from the prompt — so a voiceover line in the prompt is
    spoken in the clip (no separate TTS). Needs `AIML_API_KEY`. LIVE-ONLY (paid).

    Same `VideoProvider` contract as `VeoProvider`: one text-free scene clip per call.
    On ANY failure it RAISES, so the compositor's fallback (KenBurns over real photos ->
    gradient) takes over — a scene never silently degrades into a blank.
    """
    name = "aiml-veo"
    BASE_URL = "https://api.aimlapi.com/v2"
    DEFAULT_MODEL = "google/veo-3.1-i2v"

    def __init__(self, *, api_key: Optional[str] = None, model: Optional[str] = None,
                 aspect_ratio: str = "9:16", poll_interval: int = 20,
                 max_polls: int = 60, timeout: int = 60):
        self.api_key = api_key or os.getenv("AIML_API_KEY")
        self.model = model or os.getenv("REEL_AIML_MODEL") or self.DEFAULT_MODEL
        self.aspect_ratio = aspect_ratio
        self.poll_interval = poll_interval
        self.max_polls = max_polls
        self.timeout = timeout

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def _post_json(self, path: str, payload: dict) -> dict:
        import json
        import urllib.request
        req = urllib.request.Request(
            f"{self.BASE_URL}{path}", data=json.dumps(payload).encode("utf-8"),
            headers=self._headers(), method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    def _get_json(self, path: str, params: dict) -> dict:
        import json
        import urllib.parse
        import urllib.request
        req = urllib.request.Request(
            f"{self.BASE_URL}{path}?{urllib.parse.urlencode(params)}", headers=self._headers(),
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    def _submit(self, prompt: str, image_url: Optional[str]) -> str:
        payload = {"model": self.model, "prompt": prompt, "aspect_ratio": self.aspect_ratio}
        if image_url:
            payload["image_url"] = image_url           # image-to-video seed
        data = self._post_json("/video/generations", payload)
        gen_id = data.get("id") or data.get("generation_id")
        if not gen_id:
            raise RuntimeError(f"AIML submit returned no id: {str(data)[:160]}")
        return gen_id

    def _poll(self, gen_id: str) -> str:
        for _ in range(self.max_polls):
            time.sleep(self.poll_interval)
            data = self._get_json("/video/generations", {"generation_id": gen_id})
            status = str(data.get("status") or "")
            if status == "completed":
                # `video` may be a dict ({"url": ...}) OR a bare URL string, depending on
                # the gateway — handle both so a valid completed render isn't lost to an
                # AttributeError (which would silently degrade to the fallback).
                v = data.get("video")
                url = (v.get("url") if isinstance(v, dict) else v) or data.get("video_url")
                if not url:
                    raise RuntimeError("AIML completed but returned no video url")
                return url
            if status in ("failed", "error"):
                raise RuntimeError(f"AIML generation failed: {data.get('error')}")
        raise RuntimeError(
            f"AIML generation timed out after {self.max_polls * self.poll_interval}s"
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
        reference_image: Optional[str] = None,
    ) -> Path:
        if not self.api_key:
            raise RuntimeError("No AIML_API_KEY set for AimlVeoProvider.")
        import urllib.request
        # i2v needs a PUBLIC image URL; pass the seed only when it's http(s) (a scraped
        # photo). A local-file seed is skipped here -> text-to-video.
        ref = str(reference_image or "")
        image_url = ref if ref.startswith(("http://", "https://")) else None
        gen_id = self._submit(prompt, image_url)
        video_url = self._poll(gen_id)
        # The download URL comes from the third-party gateway response — guard it like
        # every other outbound fetch in this module: http(s) only (no file://), SSRF
        # gate, and a bounded read (a reel clip is a few MB; cap well above that).
        if not str(video_url).lower().startswith(("http://", "https://")):
            raise RuntimeError(f"AIML returned a non-http video url: {str(video_url)[:80]}")
        try:
            from scraper.url_utils import is_safe_public_url
            if not is_safe_public_url(video_url):
                raise RuntimeError("AIML video url failed the SSRF guard (private/loopback host)")
        except ImportError:
            pass
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(video_url, timeout=300) as r:
            out_path.write_bytes(r.read(200_000_000))   # ~200MB cap
        return out_path


class RunwayProvider:
    """Runway Gen-4/Gen-3 image-to-video (https://api.dev.runwayml.com). Animates a STILL (an
    Imagen scene) into a real cinematic clip — far better than a Ken-Burns zoom. Needs
    RUNWAY_API_KEY. The seed image may be a LOCAL file (sent as a base64 data URI) or an http(s)
    URL. Same VideoProvider contract; RAISES on any failure so the caller can fall back to Ken
    Burns — a scene never silently degrades into a blank."""
    name = "runway"
    BASE_URL = "https://api.dev.runwayml.com"
    RUNWAY_VERSION = "2024-11-06"
    DEFAULT_MODEL = "gen4_turbo"

    def __init__(self, *, api_key: Optional[str] = None, model: Optional[str] = None,
                 ratio: str = "720:1280", duration: int = 5,
                 poll_interval: int = 10, max_polls: int = 90, timeout: int = 60):
        self.api_key = api_key or os.getenv("RUNWAY_API_KEY")
        self.model = model or os.getenv("RUNWAY_MODEL") or self.DEFAULT_MODEL
        self.ratio = os.getenv("RUNWAY_RATIO") or ratio        # vertical 9:16-ish
        self.duration = int(duration)
        self.poll_interval = poll_interval
        self.max_polls = max_polls
        self.timeout = timeout

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json",
                "X-Runway-Version": self.RUNWAY_VERSION}

    def _image_uri(self, ref: str) -> str:
        if ref.startswith(("http://", "https://")):
            return ref
        import base64
        p = Path(ref)
        if not p.is_file():
            raise RuntimeError(f"Runway seed image not found: {ref}")
        mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
        return f"data:{mime};base64," + base64.b64encode(p.read_bytes()).decode("ascii")

    def _post_json(self, path: str, payload: dict) -> dict:
        import json
        import urllib.request
        req = urllib.request.Request(
            f"{self.BASE_URL}{path}", data=json.dumps(payload).encode("utf-8"),
            headers=self._headers(), method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    def _get_json(self, path: str) -> dict:
        import json
        import urllib.request
        req = urllib.request.Request(f"{self.BASE_URL}{path}", headers=self._headers())
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    def _submit(self, prompt: str, image_uri: str) -> str:
        payload = {"model": self.model, "promptImage": image_uri,
                   "ratio": self.ratio, "duration": self.duration}
        if prompt:
            payload["promptText"] = prompt[:980]
        data = self._post_json("/v1/image_to_video", payload)
        tid = data.get("id")
        if not tid:
            raise RuntimeError(f"Runway submit returned no id: {str(data)[:160]}")
        return tid

    def _poll(self, tid: str) -> str:
        for _ in range(self.max_polls):
            time.sleep(self.poll_interval)
            data = self._get_json(f"/v1/tasks/{tid}")
            status = str(data.get("status") or "").upper()
            if status == "SUCCEEDED":
                out = data.get("output")
                url = (out[0] if isinstance(out, list) and out
                       else out if isinstance(out, str) else None)
                if not url:
                    raise RuntimeError("Runway SUCCEEDED but returned no output url")
                return url
            if status in ("FAILED", "CANCELLED", "ERROR"):
                raise RuntimeError(f"Runway task {status}: {str(data.get('failure') or data)[:160]}")
        raise RuntimeError(f"Runway timed out after {self.max_polls * self.poll_interval}s")

    def generate(self, prompt: str, *, out_path: Path, duration_s: float, width: int,
                 height: int, palette: Optional[list[str]] = None,
                 reference_image: Optional[str] = None) -> Path:
        if not self.api_key:
            raise RuntimeError("No RUNWAY_API_KEY set for RunwayProvider.")
        ref = str(reference_image or "")
        if not ref:
            raise RuntimeError("RunwayProvider needs a reference image (the still to animate).")
        image_uri = self._image_uri(ref)
        video_url = self._poll(self._submit(prompt, image_uri))
        import urllib.request
        if not str(video_url).lower().startswith(("http://", "https://")):
            raise RuntimeError(f"Runway returned a non-http url: {str(video_url)[:80]}")
        try:
            from scraper.url_utils import is_safe_public_url
            if not is_safe_public_url(video_url):
                raise RuntimeError("Runway video url failed the SSRF guard (private/loopback)")
        except ImportError:
            pass
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(video_url, timeout=300) as r:
            out_path.write_bytes(r.read(200_000_000))
        return out_path


def default_video_provider() -> VideoProvider:
    """Pick a video provider from the environment:
      REEL_FORCE_STUB=1            -> offline stub (no creds, no cost)
      REEL_VIDEO_BACKEND=runway    -> Runway Gen-4 i2v (best animation)
      RUNWAY_API_KEY present        -> Runway (unless REEL_VIDEO_BACKEND says otherwise)
      REEL_VIDEO_BACKEND=aiml      -> AIML gateway (Veo 3.1 i2v + native voiceover)
      AIML_API_KEY present         -> AIML
      Gemini key / Vertex project  -> VeoProvider (Veo 3.0 on our Vertex)
      else                         -> offline stub
    """
    if os.getenv("REEL_FORCE_STUB") == "1":
        return StubVideoProvider()
    backend = (os.getenv("REEL_VIDEO_BACKEND") or "").lower()
    if backend == "runway" or (backend == "" and os.getenv("RUNWAY_API_KEY")):
        return RunwayProvider()
    if backend == "aiml" or (backend == "" and os.getenv("AIML_API_KEY")):
        return AimlVeoProvider()
    if backend == "vertex" or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") \
            or os.getenv("GOOGLE_CLOUD_PROJECT"):
        return VeoProvider()
    return StubVideoProvider()
