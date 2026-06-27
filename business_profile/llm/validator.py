"""Evidence validator.

Takes raw LLMExtractionResult + the EvidencePack used to produce it,
and returns a ValidatedPayload — same data shape minus any evidence
that doesn't survive validation.

Validation rules (applied to every LLMEvidenceRef):
1. block_id must be a non-empty string.
2. block_id must exist in pack.block_ids (otherwise: hallucinated).
3. quote must be a non-empty string.
4. quote (after normalization) must appear in the cited block's text
   (after normalization). If the quote is >200 chars, we truncate and
   try a substring match — the prompt told the LLM to keep quotes short.

Field-level rules applied after item-level validation:
- Scalar fields lose their value if all their evidence is invalid.
- Enum fields' string values are matched against the target enum;
  bad values become null.
- List items (offerings, audience_signals, etc.) are dropped
  individually when they have no valid evidence left.

The validator NEVER fabricates evidence. The only thing it adds to
an EvidenceItem that wasn't in the LLMEvidenceRef is `page_url`,
which it looks up from the pack — that field is *structural*, not
content; the LLM has no business knowing or inventing it.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from ..schemas import (
    AudienceType,
    BusinessCategory,
    Confidence,
    EvidenceItem,
    LLMEvidenceRef,
    PricingPosture,
    ToneOfVoice,
)
from .evidence_pack import EvidencePack
from .extractor import GroupResult, LLMExtractionResult
from .prompts import UNSUBSTANTIATED_CLAIM_TOKENS
from .responses import (
    IdentityResponse,
    OfferingItem,
    OfferingsResponse,
    PositioningResponse,
    StringListItem,
    TrustResponse,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# Validation primitives
# ---------------------------------------------------------------------

MAX_QUOTE_LEN = 200
_WS_RE = re.compile(r"\s+")
# Unify quote glyphs for matching. The evidence pack shows the LLM a TRANSFORMED block
# (`as_llm_text` replaces `"`->`'` and newlines->spaces so its `"..."` wrapper stays
# unambiguous), so a verbatim quote of a mid-text double-quote arrives as `'` and would
# never match the original `"`. Folding all quote glyphs to one char (here + on the block)
# closes that false-reject without loosening the substring check.
_QUOTE_RE = re.compile("[\"“”«»‘’`´]")


def _normalize(text: str) -> str:
    """Whitespace-collapse + lowercase + quote-glyph fold, for substring matching only.

    Returns "" for None or empty input.
    """
    if not text:
        return ""
    return _QUOTE_RE.sub("'", _WS_RE.sub(" ", text).strip().lower())


@dataclass
class _BlockLookup:
    """Cached lookups from the pack."""
    text_by_id: dict[str, str]
    page_url_by_id: dict[str, str]
    normalized_text_by_id: dict[str, str]


def _build_lookup(pack: EvidencePack) -> _BlockLookup:
    text_by_id: dict[str, str] = {}
    page_url_by_id: dict[str, str] = {}
    normalized_text_by_id: dict[str, str] = {}
    for b in pack.blocks:
        text_by_id[b.block_id] = b.text
        page_url_by_id[b.block_id] = b.page_url
        normalized_text_by_id[b.block_id] = _normalize(b.text)
    return _BlockLookup(text_by_id, page_url_by_id, normalized_text_by_id)


# ---------------------------------------------------------------------
# Rejection codes (for diagnostics)
# ---------------------------------------------------------------------

class RejectionCode:
    NULL_BLOCK_ID = "null_block_id"
    EMPTY_BLOCK_ID = "empty_block_id"
    HALLUCINATED_BLOCK_ID = "hallucinated_block_id"
    NULL_QUOTE = "null_quote"
    EMPTY_QUOTE = "empty_quote"
    QUOTE_NOT_IN_BLOCK = "quote_not_in_block"


@dataclass
class RejectionRecord:
    code: str
    block_id: Optional[str]
    quote: Optional[str]
    note: str = ""


# ---------------------------------------------------------------------
# Per-item validation
# ---------------------------------------------------------------------

def _validate_evidence_item(
    ref: LLMEvidenceRef,
    lookup: _BlockLookup,
    extractor_tag: str = "llm",
) -> tuple[Optional[EvidenceItem], Optional[RejectionRecord]]:
    """Validate one LLMEvidenceRef.

    Returns (EvidenceItem, None) on success, or (None, RejectionRecord)
    on failure. We never return both.
    """
    # block_id checks
    if ref.block_id is None:
        return None, RejectionRecord(
            code=RejectionCode.NULL_BLOCK_ID,
            block_id=None,
            quote=ref.quote,
        )
    if not isinstance(ref.block_id, str) or not ref.block_id.strip():
        return None, RejectionRecord(
            code=RejectionCode.EMPTY_BLOCK_ID,
            block_id=ref.block_id,
            quote=ref.quote,
        )
    if ref.block_id not in lookup.text_by_id:
        return None, RejectionRecord(
            code=RejectionCode.HALLUCINATED_BLOCK_ID,
            block_id=ref.block_id,
            quote=ref.quote,
            note="block_id not in evidence pack",
        )

    # quote checks
    if ref.quote is None:
        return None, RejectionRecord(
            code=RejectionCode.NULL_QUOTE,
            block_id=ref.block_id,
            quote=None,
        )
    if not isinstance(ref.quote, str) or not ref.quote.strip():
        return None, RejectionRecord(
            code=RejectionCode.EMPTY_QUOTE,
            block_id=ref.block_id,
            quote=ref.quote,
        )

    # Truncate long quotes — the prompt rule was <=200 chars. We try the
    # first 200 chars as a substring match before rejecting.
    candidate = ref.quote
    if len(candidate) > MAX_QUOTE_LEN:
        candidate = candidate[:MAX_QUOTE_LEN]

    norm_quote = _normalize(candidate)
    norm_block = lookup.normalized_text_by_id[ref.block_id]
    if norm_quote not in norm_block:
        # One more chance: the LLM occasionally wraps the quote in
        # punctuation/quotes. Strip leading/trailing non-alphanumerics
        # and retry.
        stripped = candidate.strip(" \t\n\r\"'“”‘’«».,;:!?(){}[]<>—–-")
        if stripped and stripped != candidate:
            if _normalize(stripped) in norm_block:
                # Accept — store the cleaner version
                page_url = lookup.page_url_by_id[ref.block_id]
                return EvidenceItem(
                    block_id=ref.block_id,
                    page_url=page_url,
                    quote=stripped[:MAX_QUOTE_LEN],
                    extractor=extractor_tag,
                ), None
        return None, RejectionRecord(
            code=RejectionCode.QUOTE_NOT_IN_BLOCK,
            block_id=ref.block_id,
            quote=ref.quote[:200],
            note=f"quote not found in block text after normalization",
        )

    page_url = lookup.page_url_by_id[ref.block_id]
    return EvidenceItem(
        block_id=ref.block_id,
        page_url=page_url,
        quote=candidate[:MAX_QUOTE_LEN],
        extractor=extractor_tag,
    ), None


def _validate_evidence_list(
    refs: list[LLMEvidenceRef],
    lookup: _BlockLookup,
    extractor_tag: str,
) -> tuple[list[EvidenceItem], list[RejectionRecord]]:
    accepted: list[EvidenceItem] = []
    rejected: list[RejectionRecord] = []
    for ref in refs:
        item, rej = _validate_evidence_item(ref, lookup, extractor_tag)
        if item is not None:
            accepted.append(item)
        elif rej is not None:
            rejected.append(rej)
    return accepted, rejected


# ---------------------------------------------------------------------
# Enum coercion
# ---------------------------------------------------------------------

def _coerce_enum(value: Optional[str], enum_cls):
    """Map a string to an enum member. Returns None on miss."""
    if value is None:
        return None
    v = str(value).strip()
    if not v:
        return None
    # Try direct match first
    for member in enum_cls:
        if member.value == v:
            return member
    # Case-insensitive fallback
    v_low = v.lower()
    for member in enum_cls:
        if member.value.lower() == v_low:
            return member
    return None


# ---------------------------------------------------------------------
# Validated payload shapes
# ---------------------------------------------------------------------

@dataclass
class ValidatedScalarField:
    """A validated scalar field's pieces, ready for the merger."""
    value: object  # final value (str | enum member | None)
    evidence: list[EvidenceItem]
    confidence: Confidence
    inferred: bool  # True if the LLM's signal was inferential


@dataclass
class ValidatedListItem:
    """A validated list item with its surviving evidence."""
    value: object  # str, OfferingItem-like dict, etc.
    evidence: list[EvidenceItem]
    confidence: Confidence


@dataclass
class ValidatedIdentity:
    tagline: ValidatedScalarField
    description: ValidatedScalarField
    category: ValidatedScalarField  # value is BusinessCategory or None


@dataclass
class ValidatedOffering:
    name: str
    short_description: Optional[str]
    price_text: Optional[str]
    evidence: list[EvidenceItem]
    confidence: Confidence


@dataclass
class ValidatedOfferings:
    offerings: list[ValidatedOffering]
    pricing_posture: ValidatedScalarField  # value is PricingPosture or None


@dataclass
class ValidatedPositioning:
    audience_type: ValidatedScalarField  # AudienceType or None
    audience_signals: list[ValidatedListItem]  # values are str
    value_propositions: list[ValidatedListItem]  # values are str
    tone_of_voice: ValidatedScalarField  # ToneOfVoice or None
    other_unique_insights: list[ValidatedListItem] = field(default_factory=list)


@dataclass
class ValidatedTrust:
    trust_signals: list[ValidatedListItem]
    service_areas: list[ValidatedListItem]


@dataclass
class ValidationDiagnostics:
    """Per-group rejection counts and records, for debugging."""
    rejections_by_group: dict[str, list[RejectionRecord]] = field(
        default_factory=lambda: {"identity": [], "offerings": [],
                                  "positioning": [], "trust": []}
    )
    fields_dropped: list[str] = field(default_factory=list)
    items_dropped: dict[str, int] = field(default_factory=dict)
    # --- v0.2-b1 ---
    # How many candidate items each group emitted (the denominator
    # for items_dropped). Useful for distinguishing "LLM returned nothing"
    # from "LLM returned 10 items, all rejected by validator."
    candidates_seen: dict[str, int] = field(default_factory=dict)
    # Items rejected specifically because they contained a blacklisted
    # claim token (halal, organic, ISO, etc.) that wasn't in the cited
    # quote. Separate counter so we can surface this distinctly in
    # diagnostics. Subset of items_dropped.
    blacklist_rejections: dict[str, list[str]] = field(default_factory=dict)

    @property
    def total_rejections(self) -> int:
        return sum(len(v) for v in self.rejections_by_group.values())

    @property
    def total_items_dropped(self) -> int:
        return sum(self.items_dropped.values())

    @property
    def total_blacklist_rejections(self) -> int:
        return sum(len(v) for v in self.blacklist_rejections.values())


@dataclass
class ValidatedPayload:
    """Everything from the LLM, after validation. Ready for the merger."""
    identity: Optional[ValidatedIdentity]
    offerings: Optional[ValidatedOfferings]
    positioning: Optional[ValidatedPositioning]
    trust: Optional[ValidatedTrust]
    diagnostics: ValidationDiagnostics


# ---------------------------------------------------------------------
# Group validators
# ---------------------------------------------------------------------

def _validate_scalar(
    refs: list[LLMEvidenceRef],
    value: object,
    confidence: Confidence,
    lookup: _BlockLookup,
    diag_bucket: list[RejectionRecord],
    *,
    inferred: bool = False,
    require_evidence: bool = True,
) -> ValidatedScalarField:
    """Validate a scalar field's evidence and decide whether to keep value.

    If value is None or all evidence is invalid, the field is missing.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return ValidatedScalarField(value=None, evidence=[], confidence=Confidence.NONE,
                            inferred=False)

    accepted, rejected = _validate_evidence_list(refs, lookup, "llm")
    diag_bucket.extend(rejected)

    if require_evidence and not accepted:
        return ValidatedScalarField(value=None, evidence=[], confidence=Confidence.NONE,
                            inferred=False)

    return ValidatedScalarField(value=value, evidence=accepted, confidence=confidence,
                        inferred=inferred)


def _validate_identity(
    resp: IdentityResponse, lookup: _BlockLookup,
    diag: ValidationDiagnostics,
) -> ValidatedIdentity:
    bucket = diag.rejections_by_group["identity"]

    # tagline: direct quote from a block; inferred=False
    tagline = _validate_scalar(
        resp.tagline_evidence, resp.tagline_value,
        resp.tagline_confidence, lookup, bucket,
        inferred=False,
    )

    # description: synthesized from multiple blocks; inferred=True
    description = _validate_scalar(
        resp.description_evidence, resp.description_value,
        resp.description_confidence, lookup, bucket,
        inferred=True,
    )

    # category: enum-coerced; LLM-inferred but high-confidence on schema match
    coerced_cat = _coerce_enum(resp.category_value, BusinessCategory)
    category = _validate_scalar(
        resp.category_evidence, coerced_cat,
        resp.category_confidence, lookup, bucket,
        inferred=True,
    )

    if tagline.value is None:
        diag.fields_dropped.append("tagline")
    if description.value is None:
        diag.fields_dropped.append("description")
    if category.value is None:
        diag.fields_dropped.append("category")

    return ValidatedIdentity(tagline=tagline, description=description,
                              category=category)


# ---------------------------------------------------------------------
# Unsubstantiated-claim blacklist (v0.2-b1)
# ---------------------------------------------------------------------

def _contains_blacklisted_claim(
    text: str, evidence_items: list[EvidenceItem],
) -> Optional[str]:
    """Check if `text` (a candidate offering name/description or list
    value) contains a blacklisted claim token NOT supported by any
    cited evidence quote. Returns the offending token, or None.

    Rule:
    - If the candidate text contains any blacklist token T, AND
    - No cited evidence quote contains T (case-insensitive),
    - THEN reject.
    """
    text_lc = (text or "").lower()
    quotes_lc = " ||| ".join(
        (e.quote or "").lower() for e in evidence_items if e.quote
    )
    for token in UNSUBSTANTIATED_CLAIM_TOKENS:
        if token in text_lc and token not in quotes_lc:
            return token
    return None


def _validate_offerings(
    resp: OfferingsResponse, lookup: _BlockLookup,
    diag: ValidationDiagnostics,
) -> ValidatedOfferings:
    bucket = diag.rejections_by_group["offerings"]
    diag.candidates_seen["offerings"] = len(resp.offerings)
    blacklist_hits: list[str] = []

    # Each offering item gets validated; drop items with no valid evidence
    kept_offerings: list[ValidatedOffering] = []
    dropped = 0
    for item in resp.offerings:
        if not item.name or not item.name.strip():
            dropped += 1
            continue
        accepted, rejected = _validate_evidence_list(item.evidence, lookup, "llm")
        bucket.extend(rejected)
        if not accepted:
            dropped += 1
            continue
        # v0.2-b1: universal blacklist — reject offerings whose name or
        # short_description mentions an unsupported claim (halal, organic,
        # ISO, etc.) when the cited quote doesn't literally contain it.
        candidate_text = " ".join(filter(None, [
            item.name, item.short_description or "",
        ]))
        offending = _contains_blacklisted_claim(candidate_text, accepted)
        if offending:
            blacklist_hits.append(
                f"{item.name!r}: '{offending}' not in cited quotes"
            )
            dropped += 1
            continue
        kept_offerings.append(ValidatedOffering(
            name=item.name.strip(),
            short_description=(item.short_description or None),
            price_text=(item.price_text or None),
            evidence=accepted,
            confidence=item.confidence,
        ))
    if dropped:
        diag.items_dropped["offerings"] = dropped
    if blacklist_hits:
        diag.blacklist_rejections["offerings"] = blacklist_hits

    # pricing_posture: enum-coerced scalar
    coerced_posture = _coerce_enum(resp.pricing_posture_value, PricingPosture)
    pricing_posture = _validate_scalar(
        resp.pricing_posture_evidence, coerced_posture,
        resp.pricing_posture_confidence, lookup, bucket,
        inferred=True,
    )
    if pricing_posture.value is None:
        diag.fields_dropped.append("pricing_posture")

    return ValidatedOfferings(offerings=kept_offerings,
                                pricing_posture=pricing_posture)


def _validate_string_list(
    items: list[StringListItem],
    lookup: _BlockLookup,
    diag_bucket: list[RejectionRecord],
    diag: ValidationDiagnostics,
    item_label: str,
) -> list[ValidatedListItem]:
    # Track candidates_seen by item type (trust_signals, value_propositions,
    # audience_signals, service_areas) so diagnostics show the denominator.
    diag.candidates_seen[item_label] = (
        diag.candidates_seen.get(item_label, 0) + len(items)
    )
    blacklist_hits: list[str] = []
    kept: list[ValidatedListItem] = []
    dropped = 0
    for item in items:
        if not item.value or not item.value.strip():
            dropped += 1
            continue
        accepted, rejected = _validate_evidence_list(item.evidence, lookup, "llm")
        diag_bucket.extend(rejected)
        if not accepted:
            dropped += 1
            continue
        # v0.2-b1: universal blacklist — reject list items mentioning
        # unsupported claims (e.g., a "value proposition" claiming "halal"
        # when no quote contains the word).
        offending = _contains_blacklisted_claim(item.value, accepted)
        if offending:
            blacklist_hits.append(
                f"{item.value!r}: '{offending}' not in cited quotes"
            )
            dropped += 1
            continue
        kept.append(ValidatedListItem(
            value=item.value.strip(),
            evidence=accepted,
            confidence=item.confidence,
        ))
    if dropped:
        diag.items_dropped[item_label] = (
            diag.items_dropped.get(item_label, 0) + dropped
        )
    if blacklist_hits:
        diag.blacklist_rejections[item_label] = (
            diag.blacklist_rejections.get(item_label, []) + blacklist_hits
        )
    return kept


def _validate_positioning(
    resp: PositioningResponse, lookup: _BlockLookup,
    diag: ValidationDiagnostics,
) -> ValidatedPositioning:
    bucket = diag.rejections_by_group["positioning"]

    coerced_audience = _coerce_enum(resp.audience_type_value, AudienceType)
    audience_type = _validate_scalar(
        resp.audience_type_evidence, coerced_audience,
        resp.audience_type_confidence, lookup, bucket,
        inferred=True,
    )

    coerced_tone = _coerce_enum(resp.tone_of_voice_value, ToneOfVoice)
    tone_of_voice = _validate_scalar(
        resp.tone_of_voice_evidence, coerced_tone,
        resp.tone_of_voice_confidence, lookup, bucket,
        inferred=True,
    )

    audience_signals = _validate_string_list(
        resp.audience_signals, lookup, bucket, diag, "audience_signals",
    )
    value_propositions = _validate_string_list(
        resp.value_propositions, lookup, bucket, diag, "value_propositions",
    )
    other_unique_insights = _validate_string_list(
        resp.other_unique_insights, lookup, bucket, diag, "other_unique_insights",
    )

    if audience_type.value is None:
        diag.fields_dropped.append("audience_type")
    if tone_of_voice.value is None:
        diag.fields_dropped.append("tone_of_voice")

    return ValidatedPositioning(
        audience_type=audience_type,
        audience_signals=audience_signals,
        value_propositions=value_propositions,
        tone_of_voice=tone_of_voice,
        other_unique_insights=other_unique_insights,
    )


def _validate_trust(
    resp: TrustResponse, lookup: _BlockLookup,
    diag: ValidationDiagnostics,
) -> ValidatedTrust:
    bucket = diag.rejections_by_group["trust"]
    trust_signals = _validate_string_list(
        resp.trust_signals, lookup, bucket, diag, "trust_signals",
    )
    service_areas = _validate_string_list(
        resp.service_areas, lookup, bucket, diag, "service_areas",
    )
    return ValidatedTrust(trust_signals=trust_signals,
                           service_areas=service_areas)


# ---------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------

def validate_llm_extraction(
    result: LLMExtractionResult,
    pack: EvidencePack,
) -> ValidatedPayload:
    """Validate every piece of LLM output against the evidence pack.

    Returns a ValidatedPayload with:
    - field values dropped to None when evidence is invalid
    - list items dropped when evidence is invalid
    - every surviving EvidenceItem fully populated (block_id, page_url,
      quote, extractor='llm')
    - diagnostics listing every rejection for auditing
    """
    lookup = _build_lookup(pack)
    diag = ValidationDiagnostics()

    identity: Optional[ValidatedIdentity] = None
    offerings: Optional[ValidatedOfferings] = None
    positioning: Optional[ValidatedPositioning] = None
    trust: Optional[ValidatedTrust] = None

    if _is_group_ok(result.identity, IdentityResponse):
        identity = _validate_identity(result.identity.response, lookup, diag)  # type: ignore[arg-type]

    if _is_group_ok(result.offerings, OfferingsResponse):
        offerings = _validate_offerings(result.offerings.response, lookup, diag)  # type: ignore[arg-type]

    if _is_group_ok(result.positioning, PositioningResponse):
        positioning = _validate_positioning(result.positioning.response, lookup, diag)  # type: ignore[arg-type]

    if _is_group_ok(result.trust, TrustResponse):
        trust = _validate_trust(result.trust.response, lookup, diag)  # type: ignore[arg-type]

    logger.info(
        "Validator finished: rejections=%d, fields_dropped=%s, items_dropped=%s",
        diag.total_rejections, diag.fields_dropped, dict(diag.items_dropped),
    )
    return ValidatedPayload(
        identity=identity,
        offerings=offerings,
        positioning=positioning,
        trust=trust,
        diagnostics=diag,
    )


def _is_group_ok(gr: GroupResult, expected_type: type) -> bool:
    return gr.ok and isinstance(gr.response, expected_type)
