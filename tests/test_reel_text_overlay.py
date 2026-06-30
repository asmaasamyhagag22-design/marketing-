"""Web-app reel kinetic caption layer — the pure beat-planning + timeline-HTML logic.
The Chromium render + ffmpeg overlay are heavy/live (verified offline, out of CI)."""
from __future__ import annotations

from reel.schemas import Storyboard
from reel.text_overlay import plan_beats, _timeline_html


def test_plan_beats_hook_then_cta_ordered_within_bounds():
    beats = plan_beats("Stay Connected", "WE", "Shop Now", 10.0)
    kinds = [s.kind for s, _, _ in beats]
    assert kinds == ["intro", "outro"]                       # HOOK then OUTRO
    (h, hi, ho), (c, ci, co) = beats
    assert 0 <= hi < ho <= ci < co == 10.0                   # ordered, non-overlapping, CTA holds to end
    assert all(0 <= tin < tout <= 10.0 for _, tin, tout in beats)
    assert h.headline == "Stay Connected"                    # verbatim hook
    assert c.headline == "WE" and c.cta_text == "Shop Now"   # outro = brand + CTA


def test_plan_beats_handles_partial_and_empty_content():
    assert [s.kind for s, _, _ in plan_beats("Hi there", "N", "", 8.0)] == ["intro"]
    assert [s.kind for s, _, _ in plan_beats("", "N", "Go", 8.0)] == ["outro"]
    assert plan_beats("", "", "", 8.0) == []                 # nothing to show


def test_timeline_html_is_kinetic_rtl_pill():
    sb = Storyboard(business_name="قصر", primary_dir="rtl",
                    palette_hex=["#512283", "#6449cd", "#ff7900"], primary_color="#1b1340")
    beats = plan_beats("المسافات بينا", "قصر الكبابجي", "اعرف أكتر", 10.0)
    html = _timeline_html(beats, sb, 1080, 1920, None)
    assert 'class="beat"' in html and "data-tin=" in html and "data-tout=" in html
    assert "window.__seektl" in html and "data-anim" in html          # kinetic driver
    assert "border-radius:999px" in html                              # CTA pill
    assert "linear-gradient(to top" in html                           # legibility scrim
    assert "letter-spacing:0;" in html                                # Arabic-safe (RTL) tracking
    assert "headline lockup" in html and 'class="lw"' in html         # minimal clean white hero lockup
