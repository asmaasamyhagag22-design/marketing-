"""Review-theme extractor (Gemini 2.5 Pro).

Reads the REAL competitor reviews (from Places, <=5 per place) and asks the model to
surface recurring praise/complaint themes. The themes feed synthesize_swot() as
Opportunities / Threats.

Grounding is enforced by THIS CODE, not by trusting the model:
  - the model must cite, for each theme, the exact review IDs that support it;
  - a theme is kept only if those citations resolve to >= min_support_reviews
    real reviews OR span >= min_support_peers distinct competitors;
  - the model's own "confidence" is never used (it is not calibrated).

Honest limit: Places returns at most ~5 reviews per place, so with 4 peers you
have ~20 reviews. Themes are DIRECTIONAL — say so in the defense.

Injectable, like scrape_fn:

    from competitor.themes import ReviewThemeExtractor
    extractor = ReviewThemeExtractor()             # uses the shared Gemini caller
    themes = extractor(result.competitors)          # list[ReviewTheme]
    swot = synthesize_swot(matrix, themes=themes)

If no Gemini caller is available, the extractor returns [] (and records why in
.last_error), so the SWOT still builds without themes.
"""

from __future__ import annotations

import json
import os
import re
from typing import Dict, List, Optional

from pydantic import BaseModel

from .models import CompetitorProfile
from .swot import ReviewTheme

_REVIEW_TEXT_CAP = 400        # chars per review sent to the model (token control)
_DEFAULT_MODEL = "gemini-2.5-pro"


class _ThemeItem(BaseModel):
    """One raw theme the model returns (before code-enforced citation grounding)."""
    text: str = ""
    polarity: str = ""
    review_ids: List[str] = []
    is_unmet_need: bool = False


class _ThemesResponse(BaseModel):
    """Top-level structured response (Gemini response_schema needs a BaseModel, not a bare list)."""
    themes: List[_ThemeItem] = []


_PROMPT_TEMPLATE = """You are analyzing real Google reviews of competing local businesses to find recurring customer themes.

Below are numbered reviews. Each line is: [ID] (PEER, rating) text

{reviews_block}

Identify recurring THEMES in what customers say. Rules:
- Only themes expressed in AT LEAST TWO reviews. Ignore one-off remarks.
- For each theme, list the exact review IDs (e.g. R3, R7) whose text actually expresses it. Do not cite a review that does not clearly express the theme.
- Classify each theme as "praise" (customers are happy) or "complaint" (customers are unhappy).
- Mark is_unmet_need=true ONLY for a complaint that represents a service gap a competitor could win on (e.g. long waits, poor booking, rude staff).
- Base everything ONLY on the reviews above. Do not invent themes, businesses, or details.
- Write each theme as a short phrase (<= 8 words), in the language most of its supporting reviews use.

Return the recurring themes. Each theme has: text (<= 8 words), polarity ("praise" or "complaint"), review_ids (the exact IDs above whose text expresses it), is_unmet_need (bool).
If there are no themes with >= 2 supporting reviews, return an empty list.
"""


class ReviewThemeExtractor:
    def __init__(
        self,
        *,
        caller=None,
        model: str = _DEFAULT_MODEL,
        max_themes: int = 8,
        min_reviews_total: int = 4,
        min_support_reviews: int = 3,
        min_support_peers: int = 2,
    ):
        self.caller = caller            # injectable; defaults to the shared Gemini caller
        self.model = model
        self.max_themes = max_themes
        self.min_reviews_total = min_reviews_total
        self.min_support_reviews = min_support_reviews
        self.min_support_peers = min_support_peers
        self.last_error: Optional[str] = None

    # ----- public API: call like a function -----
    def __call__(self, competitors: List[CompetitorProfile]) -> List[ReviewTheme]:
        self.last_error = None
        index = self._collect_reviews(competitors)
        if len(index) < self.min_reviews_total:
            self.last_error = (f"only {len(index)} reviews available "
                               f"(need >= {self.min_reviews_total}); skipping theming")
            return []
        caller = self.caller
        if caller is None:
            from business_profile.llm import default_caller
            caller = default_caller(strong=True)      # Gemini 2.5 Pro
        if caller is None:
            self.last_error = "no Gemini caller (creds/SDK missing); skipping theming"
            return []

        items = self._call_llm(caller, self._build_prompt(index))
        if items is None:
            return []   # last_error already set
        return self._parse_and_validate(items, index)

    # ----- steps -----
    def _collect_reviews(self, competitors) -> Dict[str, Dict]:
        """Build {ID: {peer, rating, text}} across all competitors."""
        index: Dict[str, Dict] = {}
        i = 1
        for comp in competitors:
            peer = comp.candidate.name
            for r in (comp.reviews or []):
                text = (r.text or "").strip()
                if not text:
                    continue
                index[f"R{i}"] = {
                    "peer": peer,
                    "rating": r.rating,
                    "text": text[:_REVIEW_TEXT_CAP],
                }
                i += 1
        return index

    def _build_prompt(self, index: Dict[str, Dict]) -> str:
        lines = []
        for rid, r in index.items():
            rating = f"{r['rating']}\u2605" if r["rating"] is not None else "?"
            peer = r["peer"][:40]
            text = r["text"].replace("\n", " ")
            lines.append(f"[{rid}] ({peer}, {rating}) {text}")
        return _PROMPT_TEMPLATE.format(reviews_block="\n".join(lines))

    def _call_llm(self, caller, prompt: str) -> Optional[List[dict]]:
        """Run the shared Gemini caller with a structured response. Returns the raw theme dicts
        (one per _ThemeItem) for _parse_and_validate, or None on failure (last_error set)."""
        try:
            resp, _usage = caller(
                "You are a review-theme analyst. Obey the rules and return only the requested themes.",
                prompt, _ThemesResponse, group_name="review_themes",
            )
            return [t.model_dump() for t in (getattr(resp, "themes", None) or [])]
        except Exception as e:  # noqa: BLE001
            self.last_error = f"Gemini API call failed: {type(e).__name__}: {e}"
            return None

    def _parse_and_validate(self, data: List[dict], index: Dict[str, Dict]) -> List[ReviewTheme]:
        valid_ids = set(index.keys())
        kept: List[ReviewTheme] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text", "")).strip()
            polarity = str(item.get("polarity", "")).strip().lower()
            if not text or polarity not in ("praise", "complaint"):
                continue

            cited = [rid for rid in (item.get("review_ids") or []) if rid in valid_ids]
            if not cited:
                continue
            peers = {index[rid]["peer"] for rid in cited}

            # CODE-ENFORCED grounding: enough real reviews OR enough distinct peers
            if len(cited) < self.min_support_reviews and len(peers) < self.min_support_peers:
                continue

            support = [f"{len(cited)} reviews across {len(peers)} peer(s): "
                       + ", ".join(sorted(peers)[:3])
                       + (" +more" if len(peers) > 3 else "")]
            kept.append(ReviewTheme(
                polarity=polarity,
                text=text,
                support=support,
                is_unmet_need=bool(item.get("is_unmet_need", False)) and polarity == "complaint",
            ))

        # most-supported first, capped
        kept.sort(key=lambda t: _support_count(t), reverse=True)
        return kept[: self.max_themes]


# ---------------------------------------------------------------------------
def extract_review_themes(competitors: List[CompetitorProfile], **kwargs) -> List[ReviewTheme]:
    """Convenience wrapper: build an extractor and run it."""
    return ReviewThemeExtractor(**kwargs)(competitors)


# ---------------------------------------------------------------------------
def _safe_json_array(raw: str):
    if not raw:
        return None
    s = raw.strip()
    s = re.sub(r"^```(?:json)?", "", s).strip()
    s = re.sub(r"```$", "", s).strip()
    # grab the outermost [...] if the model added stray text
    start, end = s.find("["), s.rfind("]")
    if start != -1 and end != -1 and end > start:
        s = s[start:end + 1]
    try:
        out = json.loads(s)
        return out if isinstance(out, list) else None
    except json.JSONDecodeError:
        return None


def _support_count(theme: ReviewTheme) -> int:
    if not theme.support:
        return 0
    m = re.match(r"\s*(\d+)", theme.support[0])
    return int(m.group(1)) if m else 0