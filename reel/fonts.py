"""Font resolution for the libass overlay.

libass needs a real font FILE that covers the reel's scripts. For an Arabic reel
that means an Arabic-capable family. We resolve a single family that covers BOTH
Latin and Arabic (so a mixed RTL/LTR reel shapes from one family) and hand libass
the directory to scan plus the family NAME to match.

Windows ships several Arabic-capable families (Segoe UI / Tahoma / Arial); we pick
the first present. The bold weight for headings is a libass style flag, so one
family serves both heading and body. A custom font can be dropped into
`reel/assets/fonts/` and will be preferred.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

_ASSETS = Path(__file__).resolve().parent / "assets" / "fonts"

# (family name, a filename that proves the family is installed). All cover Arabic.
_WINDOWS_FAMILIES = [
    ("Segoe UI", "segoeui.ttf"),
    ("Tahoma", "tahoma.ttf"),
    ("Arial", "arial.ttf"),
]


@lru_cache(maxsize=1)
def resolve_fonts() -> dict:
    """Return {'family', 'fontsdir', 'arabic_ok'} for the libass overlay.

    `family` is the libass FontName; `fontsdir` is the directory libass scans to
    find it. Prefers a bundled font in reel/assets/fonts, else a Windows
    Arabic-capable family, else a best-effort generic.
    """
    # 1) Bundled font shipped with the repo (deterministic, cross-platform).
    if _ASSETS.is_dir():
        for f in sorted(_ASSETS.glob("*.ttf")) + sorted(_ASSETS.glob("*.otf")):
            return {"family": f.stem, "fontsdir": str(_ASSETS),
                    "font_file": str(f), "arabic_ok": True}

    # 2) Windows system family that covers Arabic + Latin.
    win_fonts = Path(os.environ.get("SystemRoot", "C:/Windows")) / "Fonts"
    if win_fonts.is_dir():
        for family, probe in _WINDOWS_FAMILIES:
            if (win_fonts / probe).is_file():
                return {"family": family, "fontsdir": str(win_fonts),
                        "font_file": str(win_fonts / probe), "arabic_ok": True}

    # 3) Best-effort generic (Latin only — Arabic may not shape). Surfaced so the
    #    compositor can warn rather than silently render boxes.
    for d in ("/usr/share/fonts", "/Library/Fonts"):
        if Path(d).is_dir():
            return {"family": "DejaVu Sans", "fontsdir": d, "font_file": None, "arabic_ok": False}
    return {"family": "Sans", "fontsdir": str(Path.cwd()), "font_file": None, "arabic_ok": False}
