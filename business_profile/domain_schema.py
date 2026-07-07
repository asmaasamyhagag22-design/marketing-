"""Domain-adaptive profile schema (Anthropic / Claude).

The base BusinessProfile is UNIVERSAL by design — the same fields for every
business. But "not all restaurants are the same, nor all educational places"
(user, 2026-06-14): a charcoal grill, a patisserie, and a fine-dining cafe deserve
DIFFERENT marketing attributes, and so do a coding bootcamp vs a university.

This module asks Claude to read the (already grounded) scrape result and generate
a schema TAILORED to this specific business's vertical + website: the 5-8 attributes
that actually matter for marketing IT, each filled FROM the evidence with a verbatim
supporting quote. It is ADDITIVE — it sits beside the base BusinessProfile, never
replaces it, so every downstream consumer keeps working.

Grounding is enforced by THIS CODE (same discipline as competitor/themes.py): a
field is kept only if its quote is actually found in the evidence we sent. No key /
SDK / network -> returns None (honest-degrade), never raises.
"""
from __future__ import annotations

import json
import logging
import os
import re
import unicodedata
from typing import Any, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "claude-sonnet-4-6"


class DomainField(BaseModel):
    """One domain-specific attribute Claude judged important for THIS business."""
    key: str                       # snake_case machine name, e.g. "cuisine_style"
    label: str                     # human label, e.g. "Cuisine style"
    value: str                     # the extracted value
    evidence_quote: str            # verbatim snippet from the scrape backing it
    grounded: bool = True          # code-verified: the quote was found in the evidence


class DomainProfile(BaseModel):
    """A schema Claude built for this specific business + the values it filled."""
    vertical: str                  # specific vertical (finer than the base category)
    rationale: str                 # one line: why these attributes for this business
    fields: list[DomainField] = Field(default_factory=list)
    model: str = _DEFAULT_MODEL


# ---------------------------------------------------------------------
# Evidence assembly (only already-grounded profile fields)
# ---------------------------------------------------------------------

def _v(profile: dict, key: str) -> str:
    f = profile.get(key)
    if isinstance(f, dict):
        f = f.get("value")
    return str(f).strip() if f else ""


def _evidence_text(profile: dict) -> str:
    """Concatenate the profile's REAL extracted text — the only thing Claude may
    draw from. Everything here is already evidence-backed by the base pipeline."""
    parts: list[str] = []
    name = _v(profile, "name")
    if name:
        parts.append(f"Business name: {name}")
    for k, label in (("category", "Category"), ("tagline", "Tagline"),
                     ("description", "Description"), ("audience_type", "Audience type"),
                     ("tone_of_voice", "Tone"), ("pricing_posture", "Pricing posture")):
        val = _v(profile, k)
        if val:
            parts.append(f"{label}: {val}")
    offerings = [o.get("name") for o in (profile.get("offerings") or []) if isinstance(o, dict) and o.get("name")]
    if offerings:
        parts.append("Offerings: " + "; ".join(offerings))
    for k, label in (("value_propositions", "Value propositions"),
                     ("trust_signals", "Trust signals"),
                     ("service_areas", "Service areas")):
        items = [(x.get("value") if isinstance(x, dict) else x) for x in (profile.get(k) or [])]
        items = [str(i).strip() for i in items if i]
        if items:
            parts.append(f"{label}: " + "; ".join(items))
    langs = profile.get("languages") or []
    if langs:
        parts.append("Languages: " + ", ".join(map(str, langs)))
    return "\n".join(parts)


# ---------------------------------------------------------------------
# Grounding check
# ---------------------------------------------------------------------

def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").lower()
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip()


def _is_grounded(quote: str, evidence: str) -> bool:
    """True if the quote is really in the evidence (verbatim or high token overlap)
    — so Claude can't invent an attribute that the scrape doesn't support."""
    q, e = _norm(quote), _norm(evidence)
    if not q:
        return False
    if q in e:
        return True
    qt = [w for w in q.split() if len(w) > 2]
    if not qt:
        return False
    hits = sum(1 for w in qt if w in e)
    return hits / len(qt) >= 0.6


_PROMPT = """You are designing a MARKETING-INTELLIGENCE schema for one specific business, then filling it.

Here is everything we scraped about it (this is your ONLY source of truth):
---
{evidence}
---

Do TWO things:
1. Identify its SPECIFIC vertical — finer than a generic category. Not "restaurant" but e.g. "traditional Egyptian charcoal grill"; not "education" but e.g. "professional tech-skills training institute". Base it strictly on the evidence.
2. Propose the 5-8 domain-specific ATTRIBUTES that matter MOST for marketing THIS business, and fill each from the evidence. Two businesses in the same broad category should get DIFFERENT attributes when their evidence differs (a grill vs a patisserie; a bootcamp vs a university). For each attribute give:
   - key: snake_case machine name
   - label: short human label
   - value: the value, drawn ONLY from the evidence
   - evidence_quote: a VERBATIM snippet from the evidence above that supports the value

Rules:
- Use ONLY the evidence. If an attribute can't be supported by a quote, OMIT it.
- Do not invent dishes, programs, certifications, audiences, or claims not in the evidence.
- Prefer attributes that distinguish this business from generic peers in its field.
- Each attribute must be one a marketer could ACT on — a targeting axis, a message angle, or a proof point — not a trivia field. If it wouldn't change a campaign decision, omit it.

Return ONLY a JSON object, no prose, no markdown fences:
{{"vertical": "...", "rationale": "one line: why these attributes for this business", "fields": [{{"key": "...", "label": "...", "value": "...", "evidence_quote": "..."}}]}}"""


def build_domain_profile(
    profile: dict,
    *,
    api_key: Optional[str] = None,
    model: str = _DEFAULT_MODEL,
    max_tokens: int = 1500,
) -> Optional[DomainProfile]:
    """Generate + fill a domain-tailored schema for this business. None on any
    failure (no key / SDK / parse / nothing grounded). Never raises."""
    evidence = _evidence_text(profile)
    if len(evidence) < 40:
        logger.info("domain_schema: too little evidence (%d chars); skipping", len(evidence))
        return None
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        logger.info("domain_schema: ANTHROPIC_API_KEY not set; skipping")
        return None
    try:
        import anthropic
    except ImportError:
        logger.warning("domain_schema: anthropic SDK not installed")
        return None
    try:
        client = anthropic.Anthropic(api_key=key)
        resp = client.messages.create(
            model=model, max_tokens=max_tokens,
            messages=[{"role": "user", "content": _PROMPT.format(evidence=evidence)}],
        )
        raw = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
    except Exception as e:  # noqa: BLE001
        logger.warning("domain_schema: Anthropic call failed: %s", e)
        return None

    data = _safe_json_object(raw)
    if not data:
        return None
    fields: list[DomainField] = []
    for item in (data.get("fields") or []):
        if not isinstance(item, dict):
            continue
        k = str(item.get("key", "")).strip()
        val = str(item.get("value", "")).strip()
        quote = str(item.get("evidence_quote", "")).strip()
        if not (k and val):
            continue
        grounded = _is_grounded(quote, evidence)
        if not grounded:                       # code-enforced: drop unsupported attributes
            logger.info("domain_schema: dropped ungrounded field %r (quote not in evidence)", k)
            continue
        fields.append(DomainField(
            key=k, label=str(item.get("label", k)).strip() or k,
            value=val, evidence_quote=quote, grounded=True,
        ))
    if not fields:
        return None
    return DomainProfile(
        vertical=str(data.get("vertical", "")).strip() or "unknown",
        rationale=str(data.get("rationale", "")).strip(),
        fields=fields, model=model,
    )


def _safe_json_object(raw: str) -> Optional[dict[str, Any]]:
    if not raw:
        return None
    s = re.sub(r"```(?:json)?", "", raw).strip().strip("`").strip()
    start, end = s.find("{"), s.rfind("}")
    if start != -1 and end > start:
        s = s[start:end + 1]
    try:
        out = json.loads(s)
        return out if isinstance(out, dict) else None
    except json.JSONDecodeError:
        return None
