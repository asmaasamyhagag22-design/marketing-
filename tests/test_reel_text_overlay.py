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


def test_plan_beats_story_captions_sit_between_hook_and_outro():
    caps = [("لحظة قرب", 0.5, 4.0),      # early scene -> the hook SHORTENS to make room for it
            ("شبكة أقوى", 6.0, 9.5),     # mid-reel -> kept, clipped before the outro
            ("خلينا أقرب", 12.0, 15.5)]  # inside the outro window -> dropped
    beats = plan_beats("المسافات بينا", "WE", "اعرف أكتر", 16.0, captions=caps)
    kinds = [s.kind for s, _, _ in beats]
    assert kinds[0] == "intro" and kinds[-1] == "outro"
    assert kinds.count("value_prop") == 2                    # the two pre-outro captions survive
    assert beats[0][2] == 2.4                                # hook shortened before the 1st caption
    texts = [s.headline for s, _, _ in beats if s.kind == "value_prop"]
    assert texts == ["لحظة قرب", "شبكة أقوى"]                 # caption text untouched, in order
    # windows are time-ordered and never overlap
    for (_, _, out1), (_, in2, _) in zip(beats, beats[1:]):
        assert in2 >= out1


def test_plan_beats_include_outro_false_drops_the_cta_beat():
    beats = plan_beats("Stay Close", "WE", "Learn more", 12.0, include_outro=False)
    assert [s.kind for s, _, _ in beats] == ["intro"]        # end-card carries the pay-off
    # and a late caption may then use the freed tail
    beats = plan_beats("Stay Close", "WE", "Learn more", 12.0, include_outro=False,
                       captions=[("real moments", 7.0, 11.0)])
    assert [s.kind for s, _, _ in beats] == ["intro", "value_prop"]


def test_timeline_html_fades_persistent_logo_at_logo_until():
    sb = Storyboard(business_name="WE", primary_dir="ltr",
                    palette_hex=["#512283"], primary_color="#512283")
    beats = plan_beats("Stay Close", "WE", "Learn more", 12.0)
    html = _timeline_html(beats, sb, 1080, 1920, None, logo_until=14.9)
    assert "var LOGO_UNTIL=14.90;" in html                   # the fade deadline reaches the driver
    assert "toplogo" in html                                 # ... which targets the persistent logo
    html_default = _timeline_html(beats, sb, 1080, 1920, None)
    assert "var LOGO_UNTIL=-1;" in html_default              # no end-card -> logo never fades
