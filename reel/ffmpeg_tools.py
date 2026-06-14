"""ffmpeg plumbing for the reel compositor.

We use the static ffmpeg bundled by `imageio-ffmpeg` (gyan.dev build on Windows,
johnvansickle on Linux) — both ship `--enable-libass --enable-libharfbuzz
--enable-libfribidi` (Arabic RTL shaping), `libx264` (H.264), and `libmp3lame`
(audio mux). No system ffmpeg or browser is required.
"""
from __future__ import annotations

import subprocess
from functools import lru_cache


@lru_cache(maxsize=1)
def ffmpeg_exe() -> str:
    """Absolute path to the bundled ffmpeg binary."""
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


@lru_cache(maxsize=1)
def has_libass() -> bool:
    """True if the bundled ffmpeg was built with libass (Arabic shaping). The
    compositor needs this; the stub clip generation does not."""
    try:
        out = subprocess.run(
            [ffmpeg_exe(), "-hide_banner", "-version"],
            capture_output=True, text=True, timeout=30,
        ).stdout or ""
    except Exception:
        return False
    return "--enable-libass" in out


def run_ffmpeg(args: list[str], *, timeout: int = 600, cwd: str | None = None) -> subprocess.CompletedProcess:
    """Run ffmpeg with `-y` (overwrite). Raises RuntimeError with the stderr tail
    on failure so graph errors are legible. `cwd` lets the caller reference
    filtergraph paths (e.g. a libass .ass) RELATIVELY, sidestepping the Windows
    drive-colon escaping problem in filter descriptions."""
    cmd = [ffmpeg_exe(), "-hide_banner", "-y", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)
    if proc.returncode != 0:
        tail = (proc.stderr or "")[-2000:]
        raise RuntimeError(f"ffmpeg failed (exit {proc.returncode}):\n{tail}")
    return proc


def hex_to_ffmpeg(color: str | None, fallback: str = "0x101820") -> str:
    """'#0B1F3A' -> '0x0B1F3A' (ffmpeg color syntax)."""
    c = (color or "").strip().lstrip("#")
    if len(c) == 6 and all(ch in "0123456789abcdefABCDEF" for ch in c):
        return "0x" + c.upper()
    return fallback
