"""Language detection for the scraped pages.

Combines two signals:
- <html lang="..."> attribute(s) seen on pages
- langdetect probabilities on the concatenated body text

Outputs proportions per language code (ISO 639-1).
"""
from __future__ import annotations

from collections import Counter
from typing import Optional

# langdetect is non-deterministic by default; seed for reproducibility
try:
    from langdetect import DetectorFactory, detect_langs, LangDetectException
    DetectorFactory.seed = 42
    _LANGDETECT_OK = True
except Exception:
    _LANGDETECT_OK = False

from .schemas import LanguageEntry


def detect_languages(
    page_texts: list[str],
    html_lang_hints: Optional[list[str]] = None,
) -> list[LanguageEntry]:
    counter: Counter[str] = Counter()

    # html lang hints contribute as soft prior
    if html_lang_hints:
        for h in html_lang_hints:
            if not h:
                continue
            code = h.split("-")[0].lower()
            if 2 <= len(code) <= 3:
                counter[code] += 1

    if _LANGDETECT_OK:
        for text in page_texts:
            if not text or len(text.strip()) < 40:
                continue
            try:
                # Use a chunk of the text — full pages are slow
                sample = text[:4000]
                results = detect_langs(sample)
                for r in results[:2]:  # top-2 per page
                    code = str(r.lang).lower()
                    # weight by probability
                    counter[code] += float(r.prob)
            except LangDetectException:
                continue

    if not counter:
        return []

    total = sum(counter.values())
    entries = [
        LanguageEntry(code=code, proportion=count / total)
        for code, count in counter.most_common()
    ]
    return entries
