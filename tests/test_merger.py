"""Tests for the profile merger and the full pipeline."""
from __future__ import annotations

import sys
import types
from datetime import datetime, timezone

# Stub playwright
_fake = types.ModuleType("playwright")
_fake_sync = types.ModuleType("playwright.sync_api")
class _Stub: ...
for n in ("Browser", "BrowserContext", "Page", "sync_playwright"):
    setattr(_fake_sync, n, _Stub)
_fake_sync.TimeoutError = type("TimeoutError", (Exception,), {})
_fake_sync.Error = type("Error", (Exception,), {})
sys.modules.setdefault("playwright", _fake)
sys.modules.setdefault("playwright.sync_api", _fake_sync)

from scraper.schemas import (  # noqa: E402
    BoundingBox, ColorEntry, ContactInfo, EmailRecord, LanguageEntry,
    LinkCategory, LinkInventory, LinkRecord, LogoRecord, MapEmbed,
    PageRecord, PageTier, PageType, PhoneRecord, ReadinessReport,
    RobotsRecord, SchemaOrgBlock, Section, ScrapeManifest, ScrapeMeta,
    SiteMetadata, TextBlock, VisualIdentity, WhatsAppRecord,
)

from business_profile.build import (
    build_profile, build_profile_no_llm, write_profile,
)
from business_profile.llm.caller import MockCaller
from business_profile.llm.evidence_pack import build_evidence_pack
from business_profile.llm.extractor import (
    GroupResult, LLMExtractionResult, run_llm_extraction,
)
from business_profile.llm.responses import (
    IdentityResponse, OfferingItem, OfferingsResponse,
    PositioningResponse, StringListItem, TrustResponse,
)
from business_profile.llm.validator import (
    ValidatedScalarField, ValidationDiagnostics, validate_llm_extraction,
)
from business_profile.merger import merge_profile
from business_profile.rules.orchestrator import apply_rules
from business_profile.schemas import (
    AudienceType, BusinessCategory, BusinessProfile, Confidence,
    ContactChannels, EvidenceItem, EvidencedField, ExtractionMeta,
    LLMEvidenceRef, Offering, PricingPosture, ProfileQuality,
    SocialAccount, SourceType, ToneOfVoice, VisualIdentitySummary,
)


# ---------------------------------------------------------------------
# Fixtures (reused from earlier tests, replicated here for isolation)
# ---------------------------------------------------------------------

def _now():
    return datetime.now(timezone.utc)


def _block(bid: str, page_url: str, tag: str, text: str,
           section: Section = Section.MAIN, above_fold: bool = False,
           is_link: bool = False, href: str | None = None) -> TextBlock:
    return TextBlock(
        block_id=bid, page_url=page_url, tag=tag, text=text, section=section,
        selector=f"{tag}#{bid}",
        bbox=BoundingBox(x=10, y=100, width=200, height=20),
        above_fold=above_fold, is_link=is_link, href=href,
    )


def _rich_manifest() -> ScrapeManifest:
    """Manifest with schema.org MedicalClinic + bilingual EN/AR copy."""
    home = "https://sp-clinic-test.com/"
    contact = "https://sp-clinic-test.com/contact-us/"
    return ScrapeManifest(
        scrape_meta=ScrapeMeta(
            input_url=home, normalized_url=home, final_url=home,
            scraped_at=_now(), duration_ms=15000,
            pages_attempted=2, pages_succeeded=2,
        ),
        robots=RobotsRecord(checked=True, allowed=True,
                             robots_url=home + "robots.txt"),
        readiness=ReadinessReport(
            has_homepage=True, has_internal_pages=True,
            has_contact_signals=True, has_visual_signals=True,
            has_cta_candidates=True, has_metadata=True,
            ready_for_extraction=True,
        ),
        languages=[LanguageEntry(code="en", proportion=0.9),
                   LanguageEntry(code="ar", proportion=0.1)],
        pages=[
            PageRecord(
                url=home, final_url=home, http_status=200,
                fetched_at=_now(), fetch_duration_ms=1000,
                page_type=PageType.HOMEPAGE, tier=PageTier.HIGH,
                viewport_width=1366, viewport_height=800,
                text_blocks=[
                    _block("home_h1_0001", home, "h1",
                           "Premium Foot Care in Cairo", above_fold=True),
                    _block("home_p_0002", home, "p",
                           "Our consultations start from EGP 500."),
                    _block("home_a_0003", home, "a", "Book Now",
                           is_link=True, href="/book-now/"),
                ],
            ),
            PageRecord(
                url=contact, final_url=contact, http_status=200,
                fetched_at=_now(), fetch_duration_ms=1000,
                page_type=PageType.CONTACT, tier=PageTier.HIGH,
                viewport_width=1366, viewport_height=800,
                text_blocks=[
                    _block("contact_p_0001", contact, "p",
                           "Call +20 100 123 4567"),
                ],
            ),
        ],
        site_metadata=SiteMetadata(
            title="SP Clinic | Premium Foot Care",
            og_site_name="SP Clinic",
            schema_org=[SchemaOrgBlock(
                type="MedicalClinic",
                data={
                    "@type": "MedicalClinic", "name": "SP Clinic",
                    "address": {
                        "@type": "PostalAddress",
                        "streetAddress": "12 Tahrir Sq",
                        "addressLocality": "Cairo",
                        "addressCountry": "EG",
                    },
                },
            )],
            html_lang="en",
        ),
        visual=VisualIdentity(
            color_palette=[
                ColorEntry(hex="#0a3d62", dominance=0.5),
                ColorEntry(hex="#ffffff", dominance=0.5),
            ],
            primary_button_color="#0a3d62",
            fonts={"body": "Inter", "headings": "Poppins", "buttons": "Inter"},
            logo=LogoRecord(src=home + "logo.svg", alt="SP Clinic Logo",
                             page_url=home),
        ),
        contact=ContactInfo(
            phones=[PhoneRecord(
                e164="+201001234567", raw="+20 100 123 4567",
                evidence_block_id="contact_p_0001", page_url=contact,
            )],
            emails=[EmailRecord(
                address="info@sp-clinic-test.com",
                evidence_block_id=None, page_url=contact,
            )],
            whatsapp=[WhatsAppRecord(
                number="201001234567",
                raw_url="https://wa.me/201001234567",
                page_url=contact,
            )],
            map_embeds=[MapEmbed(
                provider="google_maps",
                src="https://google.com/maps/...",
                page_url=contact,
            )],
        ),
        links=LinkInventory(
            internal=[],
            social=[LinkRecord(
                href="https://instagram.com/spclinic",
                anchor_text="Instagram", page_url=home, block_id=None,
                category=LinkCategory.SOCIAL, platform="instagram",
            )],
            cta_candidates=[LinkRecord(
                href=home + "book-now/", anchor_text="Book Now",
                page_url=home, block_id="home_a_0003",
                category=LinkCategory.CTA,
            )],
        ),
    )


def _full_staged_responses():
    return {
        "identity": IdentityResponse(
            tagline_value="Premium Foot Care in Cairo",
            tagline_evidence=[LLMEvidenceRef(
                block_id="home_h1_0001",
                quote="Premium Foot Care in Cairo",
            )],
            tagline_confidence=Confidence.HIGH,
            description_value="A foot care clinic in Cairo offering consultations.",
            description_evidence=[LLMEvidenceRef(
                block_id="home_h1_0001",
                quote="Premium Foot Care in Cairo",
            )],
            description_confidence=Confidence.MEDIUM,
            category_value="restaurant",  # WRONG — schema.org says clinic
            category_evidence=[LLMEvidenceRef(
                block_id="home_h1_0001",
                quote="Premium Foot Care",
            )],
            category_confidence=Confidence.LOW,
        ),
        "offerings": OfferingsResponse(
            offerings=[OfferingItem(
                name="Consultation", price_text="EGP 500",
                evidence=[LLMEvidenceRef(
                    block_id="home_p_0002",
                    quote="Our consultations start from EGP 500.",
                )],
                confidence=Confidence.HIGH,
            )],
            pricing_posture_value="mid",
            pricing_posture_evidence=[LLMEvidenceRef(
                block_id="home_p_0002", quote="EGP 500",
            )],
            pricing_posture_confidence=Confidence.MEDIUM,
        ),
        "positioning": PositioningResponse(
            audience_type_value="B2C",
            audience_type_evidence=[LLMEvidenceRef(
                block_id="home_p_0002", quote="Our consultations",
            )],
            audience_type_confidence=Confidence.MEDIUM,
            audience_signals=[StringListItem(
                value="individuals seeking foot care",
                evidence=[LLMEvidenceRef(
                    block_id="home_h1_0001", quote="Foot Care",
                )],
            )],
            value_propositions=[StringListItem(
                value="Premium positioning",
                evidence=[LLMEvidenceRef(
                    block_id="home_h1_0001", quote="Premium",
                )],
            )],
            tone_of_voice_value="professional",
            tone_of_voice_evidence=[LLMEvidenceRef(
                block_id="home_h1_0001",
                quote="Premium Foot Care in Cairo",
            )],
            tone_of_voice_confidence=Confidence.MEDIUM,
        ),
        "trust": TrustResponse(
            trust_signals=[],
            service_areas=[StringListItem(
                value="Cairo",
                evidence=[LLMEvidenceRef(
                    block_id="home_h1_0001", quote="Cairo",
                )],
            )],
        ),
    }


# ---------------------------------------------------------------------
# Priority: rules-only fields beat LLM
# ---------------------------------------------------------------------

def test_schema_org_category_beats_llm_category():
    """schema.org MedicalClinic stays even when LLM says 'restaurant'."""
    m = _rich_manifest()
    rules_profile = apply_rules(m, "test/m.json")
    assert rules_profile.category.value == BusinessCategory.CLINIC

    pack = build_evidence_pack(m, rules_profile)
    mock = MockCaller(_full_staged_responses(), model="gpt-4o-mini")
    llm_result = run_llm_extraction(pack, mock)
    payload = validate_llm_extraction(llm_result, pack)

    final = merge_profile(rules_profile, payload, llm_result)
    # schema.org wins
    assert final.category.value == BusinessCategory.CLINIC
    assert any(ev.extractor.startswith("schema_org")
               for ev in final.category.evidence)
    assert final.category.source_type == SourceType.EXTRACTED


def test_rules_name_beats_llm_anything():
    """Names are never overridden by the LLM, even if the LLM suggests one."""
    m = _rich_manifest()
    rules_profile = apply_rules(m, "test/m.json")
    rules_name = rules_profile.name.value
    assert rules_name == "SP Clinic"  # from schema.org

    pack = build_evidence_pack(m, rules_profile)
    mock = MockCaller(_full_staged_responses(), model="gpt-4o-mini")
    llm_result = run_llm_extraction(pack, mock)
    payload = validate_llm_extraction(llm_result, pack)

    final = merge_profile(rules_profile, payload, llm_result)
    # Unchanged
    assert final.name.value == "SP Clinic"


def test_pricing_visible_rule_field_unchanged_by_merge():
    """Rules-only pricing_visible boolean is independent of LLM pricing_posture."""
    m = _rich_manifest()
    rules_profile = apply_rules(m, "test/m.json")
    # Rule extractor for SP-Clinic-like fixture finds EGP 500 in a relevant page
    initial = rules_profile.pricing_visible

    pack = build_evidence_pack(m, rules_profile)
    mock = MockCaller(_full_staged_responses(), model="gpt-4o-mini")
    llm_result = run_llm_extraction(pack, mock)
    payload = validate_llm_extraction(llm_result, pack)

    final = merge_profile(rules_profile, payload, llm_result)
    assert final.pricing_visible == initial


# ---------------------------------------------------------------------
# Missing-field filling
# ---------------------------------------------------------------------

def test_llm_fills_tagline_when_rules_had_none():
    m = _rich_manifest()
    rules_profile = apply_rules(m, "test/m.json")
    assert rules_profile.tagline.value is None  # rules don't produce one

    pack = build_evidence_pack(m, rules_profile)
    llm_result = run_llm_extraction(
        pack, MockCaller(_full_staged_responses(), model="gpt-4o-mini"),
    )
    payload = validate_llm_extraction(llm_result, pack)
    final = merge_profile(rules_profile, payload, llm_result)
    assert final.tagline.value == "Premium Foot Care in Cairo"
    assert final.tagline.source_type == SourceType.EXTRACTED
    assert final.tagline.evidence[0].extractor == "llm"


def test_llm_fills_tone_audience_value_props_when_rules_had_none():
    m = _rich_manifest()
    rules_profile = apply_rules(m, "test/m.json")
    assert rules_profile.audience_type.value is None
    assert rules_profile.tone_of_voice.value is None
    assert rules_profile.value_propositions == []

    pack = build_evidence_pack(m, rules_profile)
    llm_result = run_llm_extraction(
        pack, MockCaller(_full_staged_responses(), model="gpt-4o-mini"),
    )
    payload = validate_llm_extraction(llm_result, pack)
    final = merge_profile(rules_profile, payload, llm_result)

    assert final.audience_type.value == AudienceType.B2C
    assert final.audience_type.source_type == SourceType.INFERRED
    assert final.tone_of_voice.value == ToneOfVoice.PROFESSIONAL
    assert final.tone_of_voice.source_type == SourceType.INFERRED
    assert len(final.value_propositions) == 1
    assert final.value_propositions[0].value == "Premium positioning"
    assert final.value_propositions[0].source_type == SourceType.INFERRED


def test_offerings_populated_from_llm():
    m = _rich_manifest()
    rules_profile = apply_rules(m, "test/m.json")
    assert rules_profile.offerings == []

    pack = build_evidence_pack(m, rules_profile)
    llm_result = run_llm_extraction(
        pack, MockCaller(_full_staged_responses(), model="gpt-4o-mini"),
    )
    payload = validate_llm_extraction(llm_result, pack)
    final = merge_profile(rules_profile, payload, llm_result)

    assert len(final.offerings) == 1
    o = final.offerings[0]
    assert o.name == "Consultation"
    assert o.price_text == "EGP 500"
    assert o.evidence[0].block_id == "home_p_0002"
    assert o.page_url == "https://sp-clinic-test.com/"


# ---------------------------------------------------------------------
# Lists from rules + LLM coexist
# ---------------------------------------------------------------------

def test_rules_lists_preserved_alongside_llm_lists():
    m = _rich_manifest()
    rules_profile = apply_rules(m, "test/m.json")
    # Rules produced: existing_ctas, social_presence
    assert len(rules_profile.existing_ctas) > 0
    assert len(rules_profile.social_presence) > 0

    pack = build_evidence_pack(m, rules_profile)
    llm_result = run_llm_extraction(
        pack, MockCaller(_full_staged_responses(), model="gpt-4o-mini"),
    )
    payload = validate_llm_extraction(llm_result, pack)
    final = merge_profile(rules_profile, payload, llm_result)

    # Rules-derived lists kept exactly
    assert len(final.existing_ctas) == len(rules_profile.existing_ctas)
    assert final.existing_ctas[0].value == "Book Now"
    assert len(final.social_presence) == 1
    assert final.social_presence[0].platform == "instagram"

    # LLM-derived lists added
    assert len(final.value_propositions) == 1
    assert len(final.audience_signals) == 1
    assert len(final.service_areas) == 1


def test_contact_channels_and_visual_unchanged_by_llm():
    """Rules own these completely. LLM never touches them."""
    m = _rich_manifest()
    rules_profile = apply_rules(m, "test/m.json")
    rules_contact = rules_profile.contact_channels
    rules_visual = rules_profile.visual

    pack = build_evidence_pack(m, rules_profile)
    llm_result = run_llm_extraction(
        pack, MockCaller(_full_staged_responses(), model="gpt-4o-mini"),
    )
    payload = validate_llm_extraction(llm_result, pack)
    final = merge_profile(rules_profile, payload, llm_result)

    assert final.contact_channels.phones_e164 == rules_contact.phones_e164
    assert final.contact_channels.emails == rules_contact.emails
    assert final.contact_channels.whatsapp_numbers == rules_contact.whatsapp_numbers
    assert final.visual.logo_url == rules_visual.logo_url
    assert final.visual.palette_hex == rules_visual.palette_hex


# ---------------------------------------------------------------------
# Diagnostics propagation into ExtractionMeta
# ---------------------------------------------------------------------

def test_extraction_meta_records_llm_usage_and_diagnostics():
    m = _rich_manifest()
    rules_profile = apply_rules(m, "test/m.json")
    pack = build_evidence_pack(m, rules_profile)
    mock = MockCaller(_full_staged_responses(),
                       input_tokens=500, output_tokens=200,
                       model="gpt-4o-mini")
    llm_result = run_llm_extraction(pack, mock)
    payload = validate_llm_extraction(llm_result, pack)

    final = merge_profile(rules_profile, payload, llm_result)
    meta = final.extraction_meta

    assert meta.llm_calls == 4
    assert meta.llm_tokens_input == 4 * 500
    assert meta.llm_tokens_output == 4 * 200
    assert meta.llm_cost_usd is not None and meta.llm_cost_usd > 0
    assert meta.llm_model == "gpt-4o-mini"
    # Diagnostics summary appears in the audit trail
    assert any("merger:" in s for s in meta.rule_extractors_used)


def test_failed_llm_group_does_not_break_merge():
    m = _rich_manifest()
    rules_profile = apply_rules(m, "test/m.json")
    pack = build_evidence_pack(m, rules_profile)
    # Simulate offerings call failing
    mock = MockCaller(_full_staged_responses(),
                       raise_on_group={"offerings"},
                       model="gpt-4o-mini")
    llm_result = run_llm_extraction(pack, mock)
    payload = validate_llm_extraction(llm_result, pack)

    final = merge_profile(rules_profile, payload, llm_result)
    # Identity / positioning / trust still made it through
    assert final.tagline.value == "Premium Foot Care in Cairo"
    assert final.tone_of_voice.value == ToneOfVoice.PROFESSIONAL
    # Offerings stay empty
    assert final.offerings == []
    # Pricing posture stays missing
    assert final.pricing_posture.value is None
    # ExtractionMeta reports 3 successful calls
    assert final.extraction_meta.llm_calls == 3


def test_no_llm_call_keeps_meta_zeros():
    """When llm_result is None, the meta llm_* fields stay at their defaults."""
    m = _rich_manifest()
    rules_profile = apply_rules(m, "test/m.json")
    # Empty validated payload (no LLM run at all)
    empty_payload = validate_llm_extraction(
        LLMExtractionResult(
            identity=GroupResult(group="identity", error="not_run"),
            offerings=GroupResult(group="offerings", error="not_run"),
            positioning=GroupResult(group="positioning", error="not_run"),
            trust=GroupResult(group="trust", error="not_run"),
        ),
        build_evidence_pack(m, rules_profile),
    )
    final = merge_profile(rules_profile, empty_payload, llm_result=None)
    assert final.extraction_meta.llm_calls == 0
    assert final.extraction_meta.llm_tokens_input == 0
    assert final.extraction_meta.llm_cost_usd is None


# ---------------------------------------------------------------------
# ready_for_strategy gating after merge
# ---------------------------------------------------------------------

def test_ready_for_strategy_true_after_full_merge():
    """With rules + LLM both contributing, the SP-Clinic-like fixture
    should clear the ready_for_strategy bar."""
    m = _rich_manifest()
    rules_profile = apply_rules(m, "test/m.json")
    pack = build_evidence_pack(m, rules_profile)
    llm_result = run_llm_extraction(
        pack, MockCaller(_full_staged_responses(), model="gpt-4o-mini"),
    )
    payload = validate_llm_extraction(llm_result, pack)
    final = merge_profile(rules_profile, payload, llm_result)

    # ready_for_strategy needs: name + category + offerings + contact + visual
    q = final.quality
    assert q.has_name is True
    assert q.has_category is True
    assert q.has_offerings is True
    assert q.has_contact is True
    assert q.has_visual is True
    assert q.ready_for_strategy is True


def test_ready_for_strategy_false_if_llm_fails_on_offerings():
    m = _rich_manifest()
    rules_profile = apply_rules(m, "test/m.json")
    pack = build_evidence_pack(m, rules_profile)
    # Block offerings group only
    mock = MockCaller(_full_staged_responses(),
                       raise_on_group={"offerings"}, model="gpt-4o-mini")
    llm_result = run_llm_extraction(pack, mock)
    payload = validate_llm_extraction(llm_result, pack)
    final = merge_profile(rules_profile, payload, llm_result)

    # No offerings means not ready
    assert final.quality.has_offerings is False
    assert final.quality.ready_for_strategy is False
    assert "offerings" in final.quality.major_missing


def test_quality_counts_recomputed_after_merge():
    """After merging, fields_extracted + fields_inferred + fields_missing == 20."""
    m = _rich_manifest()
    rules_profile = apply_rules(m, "test/m.json")
    pack = build_evidence_pack(m, rules_profile)
    llm_result = run_llm_extraction(
        pack, MockCaller(_full_staged_responses(), model="gpt-4o-mini"),
    )
    payload = validate_llm_extraction(llm_result, pack)
    final = merge_profile(rules_profile, payload, llm_result)
    q = final.quality
    assert q.fields_extracted + q.fields_inferred + q.fields_missing == 20
    # We expect MORE inferred fields than rules-only (LLM contributed several)
    rules_q = rules_profile.quality
    assert q.fields_inferred > rules_q.fields_inferred


# ---------------------------------------------------------------------
# Rules-only profile unchanged by merge call
# ---------------------------------------------------------------------

def test_merge_does_not_mutate_input_profile():
    m = _rich_manifest()
    rules_profile = apply_rules(m, "test/m.json")
    snapshot = rules_profile.model_dump_json()

    pack = build_evidence_pack(m, rules_profile)
    llm_result = run_llm_extraction(
        pack, MockCaller(_full_staged_responses(), model="gpt-4o-mini"),
    )
    payload = validate_llm_extraction(llm_result, pack)

    _ = merge_profile(rules_profile, payload, llm_result)
    # Input should be byte-identical after merge
    assert rules_profile.model_dump_json() == snapshot


# ---------------------------------------------------------------------
# Full pipeline: build.py
# ---------------------------------------------------------------------

def test_build_profile_no_llm_round_trip(tmp_path):
    m = _rich_manifest()
    # Write manifest to disk so we exercise the file path branch
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(m.model_dump_json(indent=2), encoding="utf-8")

    profile = build_profile_no_llm(manifest_path)
    assert profile.name.value == "SP Clinic"
    assert profile.category.value == BusinessCategory.CLINIC
    assert profile.extraction_meta.manifest_hash is not None
    assert len(profile.extraction_meta.manifest_hash) == 64


def test_build_profile_full_pipeline(tmp_path):
    m = _rich_manifest()
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(m.model_dump_json(indent=2), encoding="utf-8")

    mock = MockCaller(_full_staged_responses(),
                       input_tokens=500, output_tokens=200,
                       model="gpt-4o-mini")
    profile = build_profile(manifest_path, caller=mock)

    # Rules + LLM both contributed
    assert profile.name.value == "SP Clinic"             # rules
    assert profile.tagline.value == "Premium Foot Care in Cairo"  # LLM
    assert profile.category.value == BusinessCategory.CLINIC      # rules
    assert profile.tone_of_voice.value == ToneOfVoice.PROFESSIONAL  # LLM
    assert profile.quality.ready_for_strategy is True
    assert profile.extraction_meta.llm_calls == 4
    assert profile.extraction_meta.manifest_hash is not None


def test_build_profile_return_details(tmp_path):
    m = _rich_manifest()
    mock = MockCaller(_full_staged_responses(), model="gpt-4o-mini")
    result = build_profile(m, caller=mock, return_details=True)
    # In-memory manifest -> no hash
    assert result.profile.extraction_meta.manifest_hash == "" or \
           result.profile.extraction_meta.manifest_hash is None
    # All intermediates populated
    assert result.pack.block_count > 0
    assert result.llm_result.total_calls == 4
    assert result.payload.identity is not None


def test_write_profile_round_trip(tmp_path):
    m = _rich_manifest()
    mock = MockCaller(_full_staged_responses(), model="gpt-4o-mini")
    profile = build_profile(m, caller=mock)
    out_path = tmp_path / "business_profile.json"
    written = write_profile(profile, out_path)
    assert written.exists()
    # Round-trip
    reloaded = BusinessProfile.model_validate_json(written.read_text())
    assert reloaded.name.value == profile.name.value
    assert reloaded.category.value == profile.category.value
    assert reloaded.quality.ready_for_strategy == profile.quality.ready_for_strategy
