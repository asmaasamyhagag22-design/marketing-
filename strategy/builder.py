"""Strategy builder — turn a BusinessProfile into a concrete N-day CONTENT CALENDAR.

An LLM (the same `Caller` the poster uses) plans a scheduled mix of posts/reels across
platforms, grounded in the brand's real persona + offerings and, optionally, CURRENT
trends (from `trends.top_trends`). A content PLAN is DESIGN/strategy, not a factual
claim, so paraphrase is fine (the two-truth-domains rule); the poster/reel still validate
any hard fact at render time.

Degrades gracefully: with no caller (or on error) it emits a deterministic plan that
cycles the brand's real offerings across the calendar — never empty, never fabricated.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel

_DEFAULT_PLATFORMS = ["instagram", "tiktok", "linkedin"]
_CONTENT_TYPES = ["reel", "post", "story", "carousel"]


# ---- structured LLM output -------------------------------------------------
class _PlanItem(BaseModel):
    day_offset: int                # 0 .. days-1
    platform: str
    content_type: str              # reel | post | story | carousel
    topic: str
    angle: str = ""
    hook: str = ""


class _PlanResponse(BaseModel):
    items: list[_PlanItem]


# ---- public calendar types -------------------------------------------------
@dataclass
class ContentItem:
    date: str                      # ISO YYYY-MM-DD
    platform: str
    content_type: str
    topic: str
    angle: str = ""
    hook: str = ""
    # Recording ONLY (additive): what the grounding gate blanked on THIS item — so the
    # audit trail shows the item's hook/angle was fabricated and remediated (the item then
    # runs on its sourced `topic`), not that it silently vanished. Empty when nothing blanked.
    remediation: list[dict] = field(default_factory=list)


@dataclass
class ContentCalendar:
    business_name: str
    start_date: str
    days: int
    items: list[ContentItem] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {**{k: v for k, v in asdict(self).items() if k != "items"},
                "items": [asdict(i) for i in self.items]}

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return path


def _val(x):
    return x.get("value") if isinstance(x, dict) and "value" in x else x


def _profile_name(profile: dict[str, Any]) -> str:
    n = _val(profile.get("name")) or _val(profile.get("business_name"))
    return str(n) if n else "The brand"


_AR_RE = re.compile(r"[؀-ۿ]")
# Language-matched generic themes for the LAST-RESORT fallback — an Arabic brand must not get
# hardcoded ENGLISH topics that then render as English poster headlines (the language lock).
_FILLER_EN = ["Brand highlight", "Customer story", "Behind the scenes", "Offer spotlight"]
_FILLER_AR = ["أبرز ما نقدّمه", "قصة عميل", "من وراء الكواليس", "عرض مميز"]


def _brand_is_arabic(profile: dict[str, Any]) -> bool:
    """True when the brand's REAL text is Arabic — so the calendar's copy and its last-resort
    filler match the brand's language instead of defaulting to English."""
    blob = " ".join(str(_val(profile.get(k)) or "") for k in ("name", "description", "tagline"))
    for o in (profile.get("offerings") or [])[:6]:
        blob += " " + str(_val(o.get("name") if isinstance(o, dict) else o) or "")
    return len(_AR_RE.findall(blob)) >= 3


def _profile_topics(profile: dict[str, Any]) -> list[str]:
    topics: list[str] = []
    for o in (profile.get("offerings") or []):
        name = _val(o.get("name") if isinstance(o, dict) else o)
        if isinstance(name, str) and name.strip():
            topics.append(name.strip())
    for vp in (profile.get("value_propositions") or [])[:4]:
        # A value_proposition is an EvidencedField -> text under 'value' (NOT 'text').
        v = _val(vp)
        if isinstance(v, str) and v.strip():
            topics.append(v.strip())
    tag = _val(profile.get("tagline"))          # real brand copy — one more grounded topic
    if isinstance(tag, str) and tag.strip():
        topics.append(tag.strip())
    # Dedup, order-preserving.
    seen: set[str] = set()
    uniq = [t for t in topics if not (t in seen or seen.add(t))]
    if uniq:
        return uniq
    return _FILLER_AR if _brand_is_arabic(profile) else _FILLER_EN


def _coerce_date(value) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value).date()
        except Exception:
            pass
    return date.today()


def _persona_block(profile: dict[str, Any]) -> str:
    lines = [f"Brand: {_profile_name(profile)}"]
    for key, label in [("category", "Category"), ("tagline", "Tagline"),
                       ("audience_type", "Audience"), ("tone_of_voice", "Tone")]:
        v = _val(profile.get(key))
        if isinstance(v, str) and v.strip():
            lines.append(f"{label}: {v.strip()}")
    offs = _profile_topics(profile)[:8]
    if offs:
        lines.append("Offerings / themes: " + "; ".join(offs))
    return "\n".join(lines)


def _llm_plan(profile, caller, *, days, platforms, trends, target) -> list[_PlanItem]:
    persona = _persona_block(profile)
    trend_block = ""
    if trends:
        titles = [getattr(t, "title", None) or (t.get("title") if isinstance(t, dict) else None) for t in trends]
        titles = [t for t in titles if t][:6]
        if titles:
            trend_block = ("\nRIDE THESE CURRENT TRENDS where they fit the brand "
                           "(tie an item to one, don't force it):\n- " + "\n- ".join(titles))
    lang = ("Egyptian Arabic — write EVERY topic, angle and hook in Arabic, no Latin letters"
            if _brand_is_arabic(profile) else "English")
    system = (
        "You are a senior social-media strategist. Produce a concrete, varied content "
        "calendar for the brand below — a realistic mix of formats, angles, and platforms. "
        "Ground every item in the brand's real persona/offerings; do NOT invent facts, "
        "prices, or claims. Vary content_type and angle so the feed isn't repetitive. "
        f"LANGUAGE: {lang}."
    )
    user = (
        f"{persona}\n{trend_block}\n\n"
        f"Plan {target} items EVENLY spread across a {days}-day window (use the FULL range of "
        f"day_offset 0..{days-1}, not just the first days). "
        f"Platforms to use: {', '.join(platforms)}. "
        f"content_type ∈ {{reel, post, story, carousel}}. "
        f"Each item: day_offset, platform, content_type, topic, a one-line angle, and a "
        f"scroll-stopping hook. Write the topic/angle/hook in {lang}."
    )
    resp, _usage = caller(system, user, _PlanResponse, group_name="content_strategy")
    return list(resp.items)


def _fallback_plan(profile, *, days, platforms, target) -> list[_PlanItem]:
    topics = _profile_topics(profile)
    items: list[_PlanItem] = []
    for i in range(target):
        # Spread items EVENLY across the whole window. The old `i * (days // target)` floored
        # the spacing to 1 whenever target > days/2, front-loading every item into the first
        # third and leaving the tail empty (MEASURED: a 30-day/17-item plan filled only days
        # 0-16). Interpolating over [0, days-1] uses the full window.
        off = round(i * (days - 1) / (target - 1)) if target > 1 else 0
        items.append(_PlanItem(
            day_offset=max(0, min(days - 1, off)),
            platform=platforms[i % len(platforms)],
            content_type=_CONTENT_TYPES[i % len(_CONTENT_TYPES)],
            topic=topics[i % len(topics)],
            angle="",
            hook="",
        ))
    return items


def _hook_is_grounded(text: str, ledger: Any) -> bool:
    """Evidence-Ledger predicate for one generated copy line (a calendar hook/angle).

    True iff `text` carries NO unsourced falsifiable claim — a number/year, a
    superlative/ranking, a credential (award/certification/guarantee), or a free-offer
    claim that the brand's real evidence doesn't support. Pure paraphrase (no hard claim)
    always passes, so the gate is strict on fabrication without freezing creative copy.

    The strategy ledger is profile-only (every entry is brand-tier), so there is no
    web-snippet reputability dimension here — unlike `pick_angle`, which also ingests live
    research facts. OPT-IN: `build_strategy` only consults this when a ledger is supplied
    (the gate is wired in a separate step, after the gray-case FP/FN measurement).
    """
    return not any(not v.sourced for v in ledger.audit_text(text or ""))


def _blank_record(field_name: str, text: str, ledger: Any) -> dict:
    """RECORDING ONLY — describe a hook/angle the gate blanked (it does NOT decide the
    blank; the caller already did). Captures the original text + the unsourced claim kinds
    so the per-item audit shows the fabrication was caught and handled."""
    uns = sorted({v.claim.kind for v in ledger.audit_text(text or "") if not v.sourced})
    return {"field": field_name, "original_text": text, "unsourced_claims": uns,
            "action": "blanked",
            "note": f"fabricated {field_name} removed; item runs on its sourced topic"}


def build_strategy(
    profile: dict[str, Any],
    caller: Optional[Any] = None,
    *,
    days: int = 30,
    platforms: Optional[list[str]] = None,
    trends: Optional[list] = None,
    start_date=None,
    cadence_per_week: int = 4,
    ledger: Any = None,
) -> ContentCalendar:
    """Build an N-day `ContentCalendar`. Uses the LLM when `caller` is given; otherwise
    (or on error) a deterministic plan over the brand's real offerings.

    When an Evidence `ledger` is supplied (opt-in; the live CLI builds it from the profile),
    each generated `hook`/`angle` passes the grounding gate: a line carrying an UNSOURCED
    falsifiable claim is blanked (drop-to-grounded — the item keeps its real `topic`, which
    the creative's headline falls back to). Pure paraphrase passes untouched. Without a
    ledger the behaviour is exactly as before."""
    platforms = platforms or _DEFAULT_PLATFORMS
    start = _coerce_date(start_date)
    target = max(1, round(days / 7 * cadence_per_week))

    plan: Optional[list[_PlanItem]] = None
    if caller is not None:
        try:
            plan = _llm_plan(profile, caller, days=days, platforms=platforms,
                             trends=trends, target=target)
        except Exception:
            plan = None
    if not plan:
        plan = _fallback_plan(profile, days=days, platforms=platforms, target=target)

    items: list[ContentItem] = []
    for it in plan:
        off = max(0, min(days - 1, int(getattr(it, "day_offset", 0))))
        hook, angle = str(it.hook or ""), str(it.angle or "")
        rem: list[dict] = []
        if ledger is not None:
            # Drop-to-grounded: a hook/angle carrying an UNSOURCED falsifiable claim is
            # blanked. The item keeps its real `topic` (the creative's headline falls back
            # hook->topic), so the headline stays a grounded value consistent with the
            # item's own topic — an empty hook beats a fabricated or topic-contradicting
            # one. We never synthesize a replacement (that would re-introduce fabrication)
            # nor substitute an unrelated offering.
            # (The `rem.append(...)` lines are RECORDING ONLY — the blank conditions and
            # their results are byte-for-byte unchanged; they only make the catch visible.)
            if hook and not _hook_is_grounded(hook, ledger):
                rem.append(_blank_record("hook", hook, ledger))
                hook = ""
            if angle and not _hook_is_grounded(angle, ledger):
                rem.append(_blank_record("angle", angle, ledger))
                angle = ""
        items.append(ContentItem(
            date=(start + timedelta(days=off)).isoformat(),
            platform=str(it.platform), content_type=str(it.content_type),
            topic=str(it.topic), angle=angle, hook=hook, remediation=rem,
        ))
    items.sort(key=lambda c: (c.date, c.platform))
    return ContentCalendar(business_name=_profile_name(profile),
                           start_date=start.isoformat(), days=days, items=items)
