"""Recover the content of an API-driven SPA from its own JSON responses.

The owner hit this on ITI (iti.gov.eg): a full Angular single-page app whose homepage exposes
only 4 static <a href> links, while ALL the real content — the programme catalogue (Post
Graduates / Under Graduates / Tech-Business …), the contacts (phones, socials), the partners —
is loaded at runtime from same-site JSON APIs (`pgateway.iti.gov.eg/OldApi/ProgramCategory/…`).
A link-following crawler sees a news-heavy shell and extracts 0 offerings.

`extract_json_text(bodies)` flattens those captured JSON bodies and pulls out the human-readable
strings (names, titles, descriptions), dropping the machine noise (guids, urls, filenames, dates,
hashes). The fetcher appends the result to the page's rendered text, so the SAME extraction that
reads a normal page's text now also sees the SPA's API content. Universal (any same-site JSON
API); pure + hermetic; never raises."""
from __future__ import annotations

import json
import re
from typing import Any, Iterable

_GUID = re.compile(r"^[0-9a-f]{8}[-_][0-9a-f]{4}[-_][0-9a-f]{4}[-_][0-9a-f]{4}[-_][0-9a-f]{12}$", re.I)
_FILE = re.compile(r"\.(jpe?g|png|gif|svg|webp|bmp|ico|pdf|mp4|mp3|css|js|woff2?|ttf)$", re.I)
_ISODATE = re.compile(r"^\d{4}-\d{2}-\d{2}([tT ]\d{2}:\d{2})?")
_HEXTOKEN = re.compile(r"^[0-9a-f_]{16,}$", re.I)          # long hex / underscored-guid image ids
_LETTER = re.compile(r"[A-Za-z؀-ۿ]")            # Latin OR Arabic letter


def _walk_strings(obj: Any) -> Iterable[str]:
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _walk_strings(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _walk_strings(v)


def _is_content(s: str) -> bool:
    """A human-readable content string (a name/title/description), not machine noise."""
    s = s.strip()
    if len(s) < 2 or len(s) > 400:
        return False
    if not _LETTER.search(s):                             # must contain a real letter
        return False
    low = s.lower()
    if low.startswith(("http://", "https://", "www.", "/", "data:", "#", "{", "<")):
        return False
    if _GUID.match(s) or _FILE.search(low) or _ISODATE.match(s) or _HEXTOKEN.match(s):
        return False
    return True


def extract_json_text(bodies: Iterable[tuple[str, str]], *, max_chars: int = 40000) -> str:
    """From captured (url, json_text) bodies, return a de-duplicated blob of the human-readable
    content strings, capped at `max_chars`. '' when there is nothing useful. Never raises."""
    seen: set[str] = set()
    out: list[str] = []
    total = 0
    for _url, text in bodies or []:
        if not text:
            continue
        try:
            obj = json.loads(text)
        except Exception:  # noqa: BLE001 — not JSON / truncated
            continue
        for s in _walk_strings(obj):
            v = " ".join(s.split())                       # collapse whitespace
            if not _is_content(v):
                continue
            k = v.lower()
            if k in seen:
                continue
            seen.add(k)
            out.append(v)
            total += len(v) + 3
            if total >= max_chars:
                return " · ".join(out)[:max_chars]
    return " · ".join(out)[:max_chars]
