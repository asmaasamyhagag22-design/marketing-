"""profile -> reel content brief.

The reel's text content is EXACTLY the poster's: the same verbatim, evidence-only
selection (headline / offerings / CTA / contact / palette / logo / social / fonts).
Rather than fork ~700 lines of selection logic, we REUSE `build_poster_brief` as
the single source of truth for zero-hallucination selection — so any improvement
to the poster's selectors (e.g. smarter headline pick) benefits the reel too.

The reel-specific structure (timed scenes, RTL direction, length cap) is added by
`reel.storyboard.build_storyboard`, which consumes the brief this returns.
"""
from __future__ import annotations

import re
from typing import Any

from poster.from_profile import build_poster_brief
from poster.schemas import PosterBrief

# Arabic / Hebrew / Arabic-presentation-forms ranges — enough to detect an RTL
# script in scraped text so libass aligns the reel right-to-left.
_RTL_RE = re.compile(r"[֐-׿؀-ۿݐ-ݿࢠ-ࣿיִ-﷿ﹰ-﻿]")


def is_rtl(text: str | None) -> bool:
    """True if the text contains a right-to-left script (Arabic/Hebrew/...)."""
    return bool(_RTL_RE.search(text or ""))


def build_reel_brief(profile: dict[str, Any]) -> PosterBrief:
    """Build the reel's verbatim content brief from a (serialized) BusinessProfile.

    Returns a `PosterBrief` — the shared content contract. Reusing the poster
    builder keeps the zero-hallucination guarantee identical across both outputs.
    """
    return build_poster_brief(profile)
