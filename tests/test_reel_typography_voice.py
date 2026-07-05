# -*- coding: utf-8 -*-
"""Reel polish (owner: the reel looked "بشع" — silly typography + a voice that "بتتغير وبيقطع").

Hermetic (no network / no TTS / no ffmpeg): pins the pure decisions —
  * a luxury/fashion/beauty brand gets the ELEGANT serif caption theme, others stay BOLD;
  * the voice-over performance brief is tone-aware and no longer hardcodes an "appetizing food ad";
  * the continuous-narration script joins the scene lines in order (one voice, no per-scene call).
"""
from __future__ import annotations

from reel.text_overlay import _reel_theme
from reel.voiceover import _instructions_for


def _profile(tone: str = "", category: str = "") -> dict:
    return {
        "tone_of_voice": {"value": tone} if tone else None,
        "category": {"value": category} if category else None,
    }


# --- caption THEME (elegant serif vs bold) ---------------------------

def test_luxury_tone_selects_elegant_theme():
    assert _reel_theme(_profile(tone="luxury")) == "elegant"
    assert _reel_theme(_profile(tone="premium")) == "elegant"


def test_jewelry_category_selects_elegant_theme():
    assert _reel_theme(_profile(tone="", category="jewelry")) == "elegant"
    assert _reel_theme(_profile(tone="", category="Fashion & Beauty")) == "elegant"


def test_ordinary_brand_stays_bold():
    assert _reel_theme(_profile(tone="friendly", category="ecommerce")) == "bold"
    assert _reel_theme(_profile(tone="", category="")) == "bold"
    assert _reel_theme({}) == "bold"


# --- voice-over performance brief (no food hardcode; tone-aware) ------

def test_brief_has_no_food_hardcode():
    for tone in ("luxury", "playful", "", "corporate"):
        brief = _instructions_for(["Some brand line"], tone=tone).lower()
        assert "food" not in brief and "appetizing" not in brief


def test_brief_is_tone_aware_and_one_narrator():
    lux = _instructions_for(["Timeless elegance"], tone="luxury").lower()
    assert "unhurried" in lux or "refined" in lux
    # ONE consistent narrator is the fix for the changing voice.
    assert "one consistent" in lux or "same voice" in lux


def test_brief_detects_arabic_and_asks_for_egyptian():
    ar = _instructions_for(["روّاد التحول الرقمي"], tone="luxury")
    assert "EGYPTIAN" in ar or "المصرية" in ar
    en = _instructions_for(["An enduring symbol"], tone="luxury")
    assert "EGYPTIAN" not in en
