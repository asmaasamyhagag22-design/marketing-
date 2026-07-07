"""Recover API-driven SPA content from same-site JSON (scraper.xhr_capture) — hermetic.

Reproduces the ITI case: the programme catalogue lives in a JSON API, not the HTML.
"""
from __future__ import annotations

import json

from scraper.xhr_capture import extract_json_text

# Shaped like ITI's ProgramCategory + Contacts + Partners API payloads (names + noise mixed).
_PROGRAMS = json.dumps({
    "totalCount": 5,
    "items": [
        {"id": "41c7ad70-a7cd-4af8-a3a1-e0000000000a", "name": "Post Graduates",
         "description": "Nine-month intensive diploma programs.",
         "image": "bbc5d683_8d94_4c1b_2d37_08de72b6c385.jpeg"},
        {"id": "41c7ad70-a7cd-4af8-a3a1-e0000000000b", "name": "Under Graduates",
         "description": "Summer training tracks."},
        {"id": "x", "name": "Tech-Business", "iconUrl": "https://cdn.iti.gov.eg/x.png"},
    ],
})
_PARTNERS = json.dumps({"items": [{"partnerName": "Vodafone _VOIS"},
                                  {"partnerName": "Etisalat Misr"}, {"partnerName": "Fawry"}]})


def test_extracts_program_names_and_descriptions():
    blob = extract_json_text([("https://pgateway.iti.gov.eg/OldApi/ProgramCategory/x", _PROGRAMS)])
    assert "Post Graduates" in blob and "Under Graduates" in blob and "Tech-Business" in blob
    assert "Nine-month intensive diploma programs." in blob


def test_drops_guids_urls_filenames_dates():
    blob = extract_json_text([("u", _PROGRAMS)])
    assert "41c7ad70" not in blob                      # guid dropped
    assert "https://cdn" not in blob and ".png" not in blob and ".jpeg" not in blob
    assert "bbc5d683" not in blob                      # underscored image-id token dropped


def test_merges_multiple_bodies_and_dedupes():
    dup = json.dumps({"a": "Fawry", "b": "Fawry"})
    blob = extract_json_text([("u1", _PARTNERS), ("u2", dup)])
    assert "Vodafone _VOIS" in blob and "Etisalat Misr" in blob
    assert blob.count("Fawry") == 1                    # de-duplicated across bodies


def test_non_json_and_empty_are_ignored():
    assert extract_json_text([("u", "<html>not json</html>"), ("u2", "")]) == ""
    assert extract_json_text([]) == ""


def test_respects_max_chars():
    big = json.dumps({"items": [{"name": f"Program Number {i} Long Name"} for i in range(500)]})
    blob = extract_json_text([("u", big)], max_chars=200)
    assert len(blob) <= 200 and "Program Number" in blob
