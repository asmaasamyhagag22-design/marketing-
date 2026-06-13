"""Review-theme extractor (Anthropic SDK).

Reads the REAL competitor reviews (from Places, <=5 per place) and asks Claude to
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

    from competitor.themes import AnthropicThemeExtractor
    extractor = AnthropicThemeExtractor()          # reads ANTHROPIC_API_KEY
    themes = extractor(result.competitors)          # list[ReviewTheme]
    swot = synthesize_swot(matrix, themes=themes)

If the SDK or key is missing, the extractor returns [] (and records why in
.last_error), so the SWOT still builds without themes.

Requires: anthropic  (pip install anthropic) + ANTHROPIC_API_KEY in the env.
"""

from __future__ import annotations

import json
import os
import re
from typing import Dict, List, Optional

from .models import CompetitorProfile
from .swot import ReviewTheme

_REVIEW_TEXT_CAP = 400        # chars per review sent to the model (token control)
_DEFAULT_MODEL = "claude-sonnet-4-6"   # override to claude-haiku-4-5 for lower cost


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

Return ONLY a JSON array, no prose, no markdown fences. Schema:
[{{"text": "...", "polarity": "praise|complaint", "review_ids": ["R1","R2"], "is_unmet_need": false}}]
If there are no themes with >=2 supporting reviews, return [].
"""


class AnthropicThemeExtractor:
    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        model: str = _DEFAULT_MODEL,
        max_themes: int = 8,
        min_reviews_total: int = 4,
        min_support_reviews: int = 3,
        min_support_peers: int = 2,
        max_tokens: int = 1500,
    ):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.model = model
        self.max_themes = max_themes
        self.min_reviews_total = min_reviews_total
        self.min_support_reviews = min_support_reviews
        self.min_support_peers = min_support_peers
        self.max_tokens = max_tokens
        self.last_error: Optional[str] = None

    # ----- public API: call like a function -----
    def __call__(self, competitors: List[CompetitorProfile]) -> List[ReviewTheme]:
        self.last_error = None
        index = self._collect_reviews(competitors)
        if len(index) < self.min_reviews_total:
            self.last_error = (f"only {len(index)} reviews available "
                               f"(need >= {self.min_reviews_total}); skipping theming")
            return []
        if not self.api_key:
            self.last_error = "ANTHROPIC_API_KEY not set; skipping theming"
            return []

        raw = self._call_llm(self._build_prompt(index))
        if raw is None:
            return []   # last_error already set
        return self._parse_and_validate(raw, index)

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

    def _call_llm(self, prompt: str) -> Optional[str]:
        try:
            import anthropic
        except ImportError:
            self.last_error = "anthropic SDK not installed (pip install anthropic)"
            return None
        try:
            client = anthropic.Anthropic(api_key=self.api_key)
            resp = client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
        except Exception as e:
            self.last_error = f"Anthropic API call failed: {type(e).__name__}: {e}"
            return None

    def _parse_and_validate(self, raw: str, index: Dict[str, Dict]) -> List[ReviewTheme]:
        data = _safe_json_array(raw)
        if data is None:
            self.last_error = "could not parse model output as JSON"
            return []

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
    return AnthropicThemeExtractor(**kwargs)(competitors)


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