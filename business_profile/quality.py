"""Profile quality computation.

Inspects a (partial or complete) BusinessProfile and produces a
ProfileQuality readiness report. Called both:
- after the rule-based stage (to show what rules covered)
- after the LLM stage + merge (final readiness for downstream)

Counting taxonomy (1 "field" = 1 logical category, not 1 item):
- 8 scalar EvidencedFields:
    name, tagline, description, category,
    pricing_visible, pricing_posture, audience_type, tone_of_voice
- 5 list-of-EvidencedField sections (extracted if non-empty):
    audience_signals, value_propositions, trust_signals,
    existing_ctas, service_areas
- 3 list-of-structures sections (extracted if non-empty):
    offerings, locations, social_presence
- 2 structured sections (extracted if any sub-field populated):
    contact_channels, visual
- 1 optional struct:
    hours
- 1 list of strings:
    languages
Total = 20 fields. extracted + inferred + missing always sums to 20.

has_* booleans use specific rules (see compute_quality docstring).
"""
from __future__ import annotations

from .schemas import (
    BusinessProfile,
    EvidencedField,
    ProfileQuality,
    SourceType,
)


# Fields whose absence blocks the downstream strategy stage.
_STRATEGY_REQUIRED = ("name", "category", "offerings", "contact", "visual")

# Fields tracked in `major_missing` when still missing.
_MAJOR_FIELDS = (
    "category", "offerings", "audience_type",
    "value_propositions", "tone_of_voice",
)


def _ef_state(f: EvidencedField) -> SourceType:
    """Return the effective state of an EvidencedField.

    A field with value=None is always MISSING regardless of source_type.
    A field with value set and source_type=MISSING is treated as
    EXTRACTED (graceful migration from older profile files).
    """
    if f.value is None:
        return SourceType.MISSING
    if f.source_type == SourceType.MISSING:
        # Has a value but source_type wasn't set; treat as extracted.
        return SourceType.EXTRACTED
    return f.source_type


def _contact_has_data(profile: BusinessProfile) -> bool:
    c = profile.contact_channels
    return bool(
        c.phones or c.emails or c.whatsapp_numbers
        or c.has_contact_form or c.physical_addresses or c.map_embed_present
    )


def _visual_has_data(profile: BusinessProfile) -> bool:
    v = profile.visual
    return bool(
        v.logo_url
        or v.primary_logo
        or v.primary_brand_color
        or v.brand_palette
        or v.palette_hex  # legacy fallback
    )


def compute_quality(profile: BusinessProfile) -> ProfileQuality:
    """Compute the readiness/quality report for a BusinessProfile.

    has_name: name.value not null AND source_type == EXTRACTED
        (we don't accept LLM-inferred names; the business name should
         always have a hard source)
    has_category: category.value not null AND source_type != MISSING
        (allows schema.org=EXTRACTED or LLM=INFERRED)
    has_offerings: at least one offering
    has_audience: audience_type.value not null
    has_value_propositions: at least one value prop
    has_tone: tone_of_voice.value not null
    has_contact: any contact channel populated
    has_visual: logo or palette present

    ready_for_strategy = has_name AND has_category AND has_offerings
                        AND has_contact AND has_visual
    """
    extracted = 0
    inferred = 0
    missing = 0

    def _tally(state: SourceType) -> None:
        nonlocal extracted, inferred, missing
        if state == SourceType.EXTRACTED:
            extracted += 1
        elif state == SourceType.INFERRED:
            inferred += 1
        else:
            missing += 1

    # ---- 8 scalar EvidencedFields ----
    scalar_fields = (
        profile.name, profile.tagline, profile.description, profile.category,
        profile.pricing_visible, profile.pricing_posture,
        profile.audience_type, profile.tone_of_voice,
    )
    for f in scalar_fields:
        _tally(_ef_state(f))

    # ---- 5 list-of-EvidencedField sections ----
    def _list_state(items: list) -> SourceType:
        if not items:
            return SourceType.MISSING
        # If any item is inferred and none extracted, the list is inferred.
        # Otherwise extracted.
        if any(_ef_state(i) == SourceType.EXTRACTED for i in items
               if isinstance(i, EvidencedField)):
            return SourceType.EXTRACTED
        if any(_ef_state(i) == SourceType.INFERRED for i in items
               if isinstance(i, EvidencedField)):
            return SourceType.INFERRED
        return SourceType.EXTRACTED  # non-EvidencedField items (rare)

    ef_lists = (
        profile.audience_signals, profile.value_propositions,
        profile.trust_signals, profile.existing_ctas, profile.service_areas,
    )
    for lst in ef_lists:
        _tally(_list_state(lst))

    # ---- 3 list-of-structures sections ----
    # offerings, locations, social_presence — extracted if non-empty
    for items in (profile.offerings, profile.locations, profile.social_presence):
        _tally(SourceType.EXTRACTED if items else SourceType.MISSING)

    # ---- 2 structured sections ----
    _tally(SourceType.EXTRACTED if _contact_has_data(profile) else SourceType.MISSING)
    _tally(SourceType.EXTRACTED if _visual_has_data(profile) else SourceType.MISSING)

    # ---- hours ----
    _tally(SourceType.EXTRACTED if profile.hours and profile.hours.entries
           else SourceType.MISSING)

    # ---- languages ----
    _tally(SourceType.EXTRACTED if profile.languages else SourceType.MISSING)

    # Sanity: 8 + 5 + 3 + 2 + 1 + 1 = 20 total
    assert extracted + inferred + missing == 20, \
        f"counts mismatch: {extracted}+{inferred}+{missing} != 20"

    # ---- has_* booleans ----
    has_name = (
        profile.name.value is not None
        and _ef_state(profile.name) == SourceType.EXTRACTED
    )
    has_category = (
        profile.category.value is not None
        and _ef_state(profile.category) != SourceType.MISSING
    )
    has_offerings = len(profile.offerings) > 0
    has_audience = (
        profile.audience_type.value is not None
        and _ef_state(profile.audience_type) != SourceType.MISSING
    )
    has_value_props = len(profile.value_propositions) > 0
    has_tone = (
        profile.tone_of_voice.value is not None
        and _ef_state(profile.tone_of_voice) != SourceType.MISSING
    )
    has_contact = _contact_has_data(profile)
    has_visual = _visual_has_data(profile)

    # ---- major_missing ----
    major_missing: list[str] = []
    if not has_category:
        major_missing.append("category")
    if not has_offerings:
        major_missing.append("offerings")
    if not has_audience:
        major_missing.append("audience_type")
    if not has_value_props:
        major_missing.append("value_propositions")
    if not has_tone:
        major_missing.append("tone_of_voice")

    # ---- ready_for_strategy ----
    ready_for_strategy = all((
        has_name, has_category, has_offerings, has_contact, has_visual
    ))

    # ---- ready_for_poster (v0.2-b1) ----
    # The poster gate is more permissive on offerings than ready_for_strategy.
    # We allow generating a poster when:
    #   - name + category are present
    #   - the brand has SOMETHING to say:
    #         description OR value_propositions OR tagline
    #   - the brand has SOMETHING to offer to the audience:
    #         offerings OR (value_propositions AND audience)
    #   - the brand has visual identity to drive the poster aesthetic:
    #         palette OR logo
    # Pricing is NOT required.
    #
    # When ready_for_poster is False, poster_blockers enumerates which
    # of those gates failed. Frontend renders human-readable reasons.
    has_description = (
        profile.description.value is not None
        and _ef_state(profile.description) != SourceType.MISSING
    )
    has_tagline = (
        profile.tagline.value is not None
        and _ef_state(profile.tagline) != SourceType.MISSING
    )

    poster_blockers: list[str] = []
    if not has_name:
        poster_blockers.append("no_name")
    if not has_category:
        poster_blockers.append("no_category")
    if not (has_description or has_value_props or has_tagline):
        poster_blockers.append("no_brand_statement")
    if not (has_offerings or (has_value_props and has_audience)):
        poster_blockers.append("no_offer_or_strong_positioning")
    visual_warnings = list(dict.fromkeys(profile.visual.visual_warnings or []))
    strong_brand_palette = bool(profile.visual.brand_palette or profile.visual.primary_brand_color)
    confident_primary_logo = bool(
        profile.visual.primary_logo
        and profile.visual.primary_logo.confidence >= 0.55
    )
    legacy_visual = bool(profile.visual.logo_url or profile.visual.palette_hex)

    if not (strong_brand_palette or confident_primary_logo or legacy_visual):
        poster_blockers.append("no_visual_signals")
    if (
        not strong_brand_palette
        and not confident_primary_logo
        and legacy_visual
        and "weak_brand_palette_confidence" not in visual_warnings
    ):
        visual_warnings.append("weak_brand_palette_confidence")
    # llm_silent_failure is set on the profile by the merger; if present,
    # block poster generation even if individual fields look populated.
    if getattr(profile, "llm_silent_failure", False):
        poster_blockers.append("llm_silent_failure")

    ready_for_poster = len(poster_blockers) == 0

    return ProfileQuality(
        has_name=has_name,
        has_category=has_category,
        has_offerings=has_offerings,
        has_audience=has_audience,
        has_value_propositions=has_value_props,
        has_tone=has_tone,
        has_contact=has_contact,
        has_visual=has_visual,
        fields_extracted=extracted,
        fields_inferred=inferred,
        fields_missing=missing,
        major_missing=major_missing,
        ready_for_strategy=ready_for_strategy,
        ready_for_poster=ready_for_poster,
        poster_blockers=poster_blockers,
        poster_warnings=visual_warnings,
    )