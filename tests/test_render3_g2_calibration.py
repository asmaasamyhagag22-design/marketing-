# -*- coding: utf-8 -*-
"""§5/§10.5 — the MANDATORY G2 calibration: the gate must FAIL render #2's contact sheet
(a gate that passes render #2 is itself a failed build).

LIVE vision test — CI stays hermetic, so it runs only under RUN_LIVE_GATES=1. Verdict pinned
in process.md: FAIL, same_person=false with 4 identity offenders (blurred face / protagonist
absent / back turned / different woman, no hijab), same_world_grade=false, arc_readable=false.
C1 (owner, 2026-07-13): the glowing-UI frame (frame 5's cyan LED strips) MUST be caught in
junk_screens. Earlier (D-R3.5) the judge read that glow as architectural light -> junk_screens=[];
the G2 junk-screen prompt was strengthened to flag sci-fi glow even when it could pass as ambient
light, and now stably returns junk_screens=[5]. A gate that does NOT flag it is broken.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import pytest

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "render2_sheet.png"


def test_fixture_is_committed():
    assert _FIXTURE.is_file() and _FIXTURE.stat().st_size > 100_000


@pytest.mark.skipif(not os.environ.get("RUN_LIVE_GATES"),
                    reason="live Gemini vision — run with RUN_LIVE_GATES=1")
def test_g2_fails_render2_sheet_live():
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    from business_profile.llm import default_caller
    from reel.ffmpeg_tools import ffmpeg_exe
    from reel.render3.g2 import g2_check

    with tempfile.TemporaryDirectory() as td:
        ref_p = Path(td) / "ref.jpg"
        subprocess.run([ffmpeg_exe(), "-y", "-ss", "13.5", "-i",
                        "outputs/reels/nti_render2_generated.mp4", "-frames:v", "1",
                        "-vf", "scale=360:-2", "-q:v", "3", str(ref_p)],
                       capture_output=True, timeout=60)
        v = g2_check(_FIXTURE.read_bytes(), ref_p.read_bytes(), n=5,
                     caller=default_caller(strong=True))
    assert v.verdict == "FAIL"                 # the mandatory core
    assert v.same_person is False and v.identity_offenders
    assert 5 in v.junk_screens                 # C1: the glowing-cyan frame MUST be flagged
