"""Tests for rule-based extractors.

Built around two fixture manifests:
- minimal: bare-bones (just enough to keep schemas valid)
- rich: a mock of an Egyptian medical clinic site with schema.org,
        contact info, bilingual content, CTAs, and currency text
"""
from __future__ import annotations

import sys
import types
from datetime import datetime, timezone

# Stub playwright so scraper.schemas imports cleanly in this env.
# On the user's machine playwright is installed and this stub is a no-op.
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

from business_profile.rules.from_contact import extract_contact
from business_profile.rules.from_links import (
    extract_existing_ctas, extract_social_presence,
)
from business_profile.rules.from_metadata import extract_name_from_metadata
from business_profile.rules.from_pricing import extract_pricing_visible
from business_profile.rules.from_schema_org import (
    extract_category_from_schema_org,
    extract_hours_from_schema_org,
    extract_locations_from_schema_org,
    extract_name_from_schema_org,
)
from business_profile.rules.from_visual import extract_visual
from business_profile.rules.orchestrator import apply_rules
from business_profile.schemas import (
    BusinessCategory, Confidence, SourceType,
)


# ---------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------

def _now():
    return datetime.now(timezone.utc)


def _make_block(block_id: str, page_url: str, tag: str, text: str,
                section: Section = Section.MAIN, above_fold: bool = False,
                is_link: bool = False, href: str | None = None) -> TextBlock:
    return TextBlock(
        block_id=block_id, page_url=page_url, tag=tag, text=text,
        section=section, selector=f"{tag}#{block_id}",
        bbox=BoundingBox(x=10, y=100, width=200, height=20),
        above_fold=above_fold, is_link=is_link, href=href,
    )


def _empty_readiness() -> ReadinessReport:
    return ReadinessReport(
        has_homepage=True, has_internal_pages=True,
        has_contact_signals=True, has_visual_signals=True,
        has_cta_candidates=True, has_metadata=True,
        ready_for_extraction=True,
    )


def _rich_manifest() -> ScrapeManifest:
    home_url = "https://sp-clinic-test.com/"
    contact_url = "https://sp-clinic-test.com/contact-us/"

    home_page = PageRecord(
        url=home_url, final_url=home_url, http_status=200,
        fetched_at=_now(), fetch_duration_ms=1500,
        page_type=PageType.HOMEPAGE, tier=PageTier.HIGH,
        viewport_width=1366, viewport_height=800,
        text_blocks=[
            _make_block("home_h1_0001", home_url, "h1",
                        "Premium Foot Care in Cairo", above_fold=True),
            _make_block("home_p_0002", home_url, "p",
                        "Our consultations start from EGP 500."),
            _make_block("home_a_0003", home_url, "a", "Book Now",
                        is_link=True, href="/book-now/"),
        ],
    )

    contact_page = PageRecord(
        url=contact_url, final_url=contact_url, http_status=200,
        fetched_at=_now(), fetch_duration_ms=1200,
        page_type=PageType.CONTACT, tier=PageTier.HIGH,
        viewport_width=1366, viewport_height=800,
        text_blocks=[
            _make_block("contact_h2_0001", contact_url, "h2", "Contact Us"),
            _make_block("contact_p_0002", contact_url, "p",
                        "Call us at +20 100 123 4567"),
        ],
    )

    schema_block = SchemaOrgBlock(
        type="MedicalClinic",
        data={
            "@type": "MedicalClinic",
            "name": "SP Clinic",
            "address": {
                "@type": "PostalAddress",
                "streetAddress": "12 Tahrir Square",
                "addressLocality": "Cairo",
                "addressCountry": "EG",
            },
            "openingHoursSpecification": [{
                "@type": "OpeningHoursSpecification",
                "dayOfWeek": ["https://schema.org/Monday",
                              "https://schema.org/Tuesday"],
                "opens": "09:00",
                "closes": "17:00",
            }],
            "openingHours": "Sa 10:00-14:00",
        },
    )

    return ScrapeManifest(
        scrape_meta=ScrapeMeta(
            input_url=home_url,
            normalized_url=home_url,
            final_url=home_url,
            scraped_at=_now(),
            duration_ms=15000,
            pages_attempted=2,
            pages_succeeded=2,
        ),
        robots=RobotsRecord(checked=True, allowed=True,
                            robots_url=home_url + "robots.txt"),
        readiness=_empty_readiness(),
        languages=[LanguageEntry(code="en", proportion=0.9),
                   LanguageEntry(code="ar", proportion=0.1)],
        pages=[home_page, contact_page],
        site_metadata=SiteMetadata(
            title="SP Clinic | Premium Foot Care",
            og_site_name="SP Clinic",
            description="Premium foot care in Cairo.",
            schema_org=[schema_block],
            html_lang="en",
        ),
        visual=VisualIdentity(
            color_palette=[
                ColorEntry(hex="#ffffff", dominance=0.5),  # neutral
                ColorEntry(hex="#0a3d62", dominance=0.3),  # brand
                ColorEntry(hex="#e0e0e0", dominance=0.2),  # neutral
            ],
            body_bg="#ffffff",
            primary_button_color="#0a3d62",
            fonts={"body": "Inter", "headings": "Poppins", "buttons": "Inter"},
            logo=LogoRecord(src=home_url + "logo.svg", alt="SP Clinic Logo",
                            page_url=home_url),
        ),
        contact=ContactInfo(
            phones=[PhoneRecord(
                e164="+201001234567", raw="+20 100 123 4567",
                evidence_block_id="contact_p_0002", page_url=contact_url,
            )],
            emails=[EmailRecord(
                address="info@sp-clinic-test.com",
                evidence_block_id=None, page_url=contact_url,
            )],
            whatsapp=[WhatsAppRecord(
                number="201001234567", raw_url="https://wa.me/201001234567",
                page_url=contact_url,
            )],
            map_embeds=[MapEmbed(provider="google_maps",
                                 src="https://google.com/maps/...",
                                 page_url=contact_url)],
        ),
        links=LinkInventory(
            internal=[],
            social=[LinkRecord(
                href="https://instagram.com/spclinic",
                anchor_text="Instagram",
                page_url=home_url,
                block_id=None,
                category=LinkCategory.SOCIAL,
                platform="instagram",
            )],
            cta_candidates=[LinkRecord(
                href=home_url + "book-now/",
                anchor_text="Book Now",
                page_url=home_url,
                block_id="home_a_0003",
                category=LinkCategory.CTA,
            )],
        ),
    )


# ---------------------------------------------------------------------
# Visual
# ---------------------------------------------------------------------

def test_visual_picks_brand_color_not_white():
    m = _rich_manifest()
    v = extract_visual(m)
    assert v.primary_color == "#0a3d62"  # not the white or gray
    assert v.body_font == "Inter"
    assert v.heading_font == "Poppins"
    assert v.logo_url and v.logo_url.endswith("logo.svg")


def test_visual_neutral_only_palette_returns_none_primary():
    m = _rich_manifest()
    m.visual.color_palette = [
        ColorEntry(hex="#ffffff", dominance=0.6),
        ColorEntry(hex="#e0e0e0", dominance=0.4),
    ]
    v = extract_visual(m)
    assert v.primary_color is None
    assert v.palette_hex == ["#ffffff", "#e0e0e0"]


# ---------------------------------------------------------------------
# Contact
# ---------------------------------------------------------------------

def test_contact_passthrough_with_evidence():
    m = _rich_manifest()
    c = extract_contact(m)
    assert c.phones_e164 == ["+201001234567"]
    assert c.emails == ["info@sp-clinic-test.com"]
    assert c.whatsapp_numbers == ["+201001234567"]
    assert c.map_embed_present is True
    assert c.has_contact_form is False  # no forms in fixture
    # Every channel has at least one evidence item with a non-empty extractor
    assert all(e.extractor.startswith("rule:") for e in c.evidence)
    # Phone evidence should carry the block_id from the manifest
    phone_ev = [e for e in c.evidence if e.extractor == "rule:phone"]
    assert phone_ev and phone_ev[0].block_id == "contact_p_0002"


# ---------------------------------------------------------------------
# Links: social + CTAs
# ---------------------------------------------------------------------

def test_social_dedup_and_evidence():
    m = _rich_manifest()
    socials = extract_social_presence(m)
    assert len(socials) == 1
    assert socials[0].platform == "instagram"
    assert socials[0].evidence[0].extractor == "rule:social_link"


def test_ctas_extracted_with_block_id():
    m = _rich_manifest()
    ctas = extract_existing_ctas(m)
    assert len(ctas) == 1
    assert ctas[0].value == "Book Now"
    assert ctas[0].source_type == SourceType.EXTRACTED
    assert ctas[0].confidence == Confidence.HIGH
    assert ctas[0].evidence[0].block_id == "home_a_0003"


# ---------------------------------------------------------------------
# Metadata: name from og:site_name / title / h1
# ---------------------------------------------------------------------

def test_name_from_og_site_name():
    m = _rich_manifest()
    n = extract_name_from_metadata(m)
    assert n.value == "SP Clinic"
    assert n.evidence[0].extractor == "rule:og:site_name"
    assert n.confidence == Confidence.HIGH


def test_name_from_title_cleaned():
    m = _rich_manifest()
    m.site_metadata.og_site_name = None
    n = extract_name_from_metadata(m)
    # "SP Clinic | Premium Foot Care" -> shortest non-generic segment
    assert n.value == "SP Clinic"
    assert n.evidence[0].extractor == "rule:title"
    assert n.confidence == Confidence.MEDIUM


def test_name_falls_back_to_h1():
    m = _rich_manifest()
    m.site_metadata.og_site_name = None
    m.site_metadata.title = None
    n = extract_name_from_metadata(m)
    assert n.value == "Premium Foot Care in Cairo"
    assert n.evidence[0].extractor == "rule:homepage_h1"
    assert n.confidence == Confidence.LOW


def test_name_missing_when_no_signals():
    m = _rich_manifest()
    m.site_metadata.og_site_name = None
    m.site_metadata.title = None
    m.pages[0].text_blocks = [
        b for b in m.pages[0].text_blocks if b.tag != "h1"
    ]
    n = extract_name_from_metadata(m)
    assert n.value is None
    assert n.source_type == SourceType.MISSING


def test_name_strips_chrome_from_og_site_name():
    """og:site_name = 'Qasr Elkbabgi Website' must yield the clean brand at the
    SOURCE (measured: the only chrome-bearing name across 59 saved manifests)."""
    m = _rich_manifest()
    m.site_metadata.og_site_name = "Qasr Elkbabgi Website"
    n = extract_name_from_metadata(m)
    assert n.value == "Qasr Elkbabgi"
    # The verbatim source is still the cited quote (provenance preserved).
    assert n.evidence[0].quote == "Qasr Elkbabgi Website"
    assert n.evidence[0].extractor == "rule:og:site_name"


def test_strip_chrome_is_conservative():
    """Whole-word, fixed-point, never empties; leaves legitimate brand words."""
    from business_profile.rules.from_metadata import _strip_chrome
    assert _strip_chrome("Acme - Official Website") == "Acme"
    assert _strip_chrome("Welcome to Zooba") == "Zooba"
    assert _strip_chrome("Nike Official") == "Nike"
    # E-commerce SECTION designators are chrome (MEASURED: Vodafone's e-shop sub-site).
    assert _strip_chrome("Vodafone Egypt E-Shop") == "Vodafone Egypt"
    assert _strip_chrome("Foo Online Store") == "Foo"
    # Not chrome — must be left intact (no false positives).
    assert _strip_chrome("Home Depot") == "Home Depot"
    assert _strip_chrome("AOL Online") == "AOL Online"
    assert _strip_chrome("Microsoft") == "Microsoft"
    # Bare "shop"/"store" stay legitimate brand words (only e-shop/online-shop strip).
    assert _strip_chrome("EVA Shop") == "EVA Shop"
    assert _strip_chrome("The Body Shop") == "The Body Shop"
    # A name that is ONLY chrome is kept verbatim rather than emptied.
    assert _strip_chrome("Website") == "Website"


def test_name_drops_glued_tagline_from_og_site_name():
    """og:site_name is often a whole marketing sentence — 'Brand - Tagline'. Taking it verbatim
    made the brand NAME a sentence (MEASURED: rawafrican.net =
    "Raw African's Beauty Hub - Get the Raw Experience!"). The name is the identity anchor on the
    poster/reel/dashboard/SWOT, so it must be the BRAND, picked by the segment that echoes the
    domain. The verbatim og:site_name stays the cited quote."""
    m = _rich_manifest()
    m.scrape_meta.final_url = "https://rawafrican.net/"
    m.scrape_meta.normalized_url = "https://rawafrican.net/"
    raw = "Raw African's Beauty Hub - Get the Raw Experience!"
    m.site_metadata.og_site_name = raw
    n = extract_name_from_metadata(m)
    assert n.value == "Raw African"
    assert n.evidence[0].quote == raw            # provenance: the full string is still cited
    assert n.evidence[0].extractor == "rule:og:site_name"


def test_brand_segment_is_domain_aware_and_possessive_safe():
    """The segment picker: brand echoes the domain; a glued tagline/qualifier is dropped; a
    possessive brand whose name ENDS at the "'s" (Levi's, McDonald's) is never trimmed."""
    from business_profile.rules.from_metadata import _pick_brand_segment, _registrable_label

    def og(raw, url):
        return _pick_brand_segment(raw, _registrable_label(url), legacy_shortest=False)

    def title(raw, url):
        return _pick_brand_segment(raw, _registrable_label(url), legacy_shortest=True)

    # Brand + tagline: keep the domain-echoing segment, strip a possessive descriptor.
    assert og("Raw African's Beauty Hub - Get the Raw Experience!", "https://rawafrican.net/") == "Raw African"
    # Title 'Brand | categories...' keeps the brand (domain hit beats the category list).
    assert title("Orange Egypt | Mobiles, Internet, DSL, Offers.", "https://www.orange.eg/en/") == "Orange Egypt"
    # No separator -> untouched (a qualifier like 'Egypt' is NOT a tagline).
    assert og("Vodafone Egypt", "https://web.vodafone.com.eg/") == "Vodafone Egypt"
    assert og("As-Salam International Hospital", "https://as-salamhospital.com/") == "As-Salam International Hospital"
    # Possessive brands that end at "'s" are preserved (nothing trails the possessive).
    assert og("Levi's", "https://levi.com/") == "Levi's"
    assert og("McDonald's", "https://mcdonalds.com/") == "McDonald's"
    # No domain signal -> brand-first for og (first segment), then chrome/possessive rules.
    assert og("Acme - Your Trusted Partner", "https://xyzholdings.com/") == "Acme"


# ---------------------------------------------------------------------
# Schema.org
# ---------------------------------------------------------------------

def test_schema_org_name_prefers_specific_type():
    m = _rich_manifest()
    n = extract_name_from_schema_org(m)
    assert n.value == "SP Clinic"
    assert "MedicalClinic" in n.evidence[0].extractor


def test_schema_org_category_mapping():
    m = _rich_manifest()
    c = extract_category_from_schema_org(m)
    assert c.value == BusinessCategory.CLINIC
    assert c.confidence == Confidence.HIGH


def test_schema_org_locations_parsing():
    m = _rich_manifest()
    locs = extract_locations_from_schema_org(m)
    assert len(locs) == 1
    assert "Tahrir Square" in (locs[0].address_text or "")
    assert locs[0].city == "Cairo"
    assert locs[0].country == "EG"


def test_schema_org_hours_both_forms():
    m = _rich_manifest()
    h = extract_hours_from_schema_org(m)
    assert h is not None
    # 1 from openingHoursSpecification (Mon-Tue) + 1 from openingHours (Sa)
    assert len(h.entries) == 2
    spec_entry = next((e for e in h.entries if "Monday" in e.days), None)
    assert spec_entry and spec_entry.opens == "09:00"
    sa_entry = next((e for e in h.entries if e.days == "Sa"), None)
    assert sa_entry and sa_entry.opens == "10:00"


def test_schema_org_graph_array_handled():
    """Some sites wrap multiple entities in @graph."""
    m = _rich_manifest()
    m.site_metadata.schema_org = [SchemaOrgBlock(
        type=None,
        data={"@graph": [
            {"@type": "WebPage", "name": "Homepage"},
            {"@type": "Restaurant", "name": "Pasta Place"},
        ]},
    )]
    c = extract_category_from_schema_org(m)
    n = extract_name_from_schema_org(m)
    assert c.value == BusinessCategory.RESTAURANT
    assert n.value == "Pasta Place"


def test_schema_org_generic_organization_lower_confidence():
    m = _rich_manifest()
    m.site_metadata.schema_org = [SchemaOrgBlock(
        type="Organization",
        data={"@type": "Organization", "name": "Generic Co"},
    )]
    c = extract_category_from_schema_org(m)
    assert c.value == BusinessCategory.OTHER
    assert c.confidence == Confidence.LOW


# ---------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------

def test_pricing_detected_on_relevant_page():
    m = _rich_manifest()
    p = extract_pricing_visible(m)
    assert p.value is True
    assert p.source_type == SourceType.EXTRACTED
    assert p.evidence[0].block_id == "home_p_0002"


def test_pricing_arabic_currency():
    m = _rich_manifest()
    m.pages[0].text_blocks = [
        _make_block("home_p_0001", "https://sp-clinic-test.com/", "p",
                    "السعر يبدأ من 500 جنيه"),
        _make_block("home_p_0002", "https://sp-clinic-test.com/", "p",
                    "خدمة ممتازة بأفضل سعر"),
    ]
    p = extract_pricing_visible(m)
    assert p.value is True


def test_pricing_missing_with_few_blocks():
    m = _rich_manifest()
    # Strip the currency mention and most blocks
    for page in m.pages:
        page.text_blocks = [b for b in page.text_blocks if "EGP" not in b.text]
    p = extract_pricing_visible(m)
    # Under the 50-block confidence threshold -> missing
    assert p.value is None
    assert p.source_type == SourceType.MISSING


# ---------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------

def test_orchestrator_full_run():
    m = _rich_manifest()
    profile = apply_rules(m, manifest_path="test/fixture.json")

    # Identity
    assert profile.name.value == "SP Clinic"
    assert profile.category.value == BusinessCategory.CLINIC

    # Pricing
    assert profile.pricing_visible.value is True

    # Geography
    assert len(profile.locations) == 1
    assert profile.hours is not None and len(profile.hours.entries) == 2

    # Contact
    assert profile.contact_channels.phones_e164 == ["+201001234567"]
    assert profile.contact_channels.map_embed_present

    # Links
    assert len(profile.social_presence) == 1
    assert len(profile.existing_ctas) == 1

    # Visual
    assert profile.visual.primary_color == "#0a3d62"

    # Languages passthrough
    assert profile.languages == ["en", "ar"]

    # LLM fields still missing
    assert profile.tagline.source_type == SourceType.MISSING
    assert profile.tone_of_voice.source_type == SourceType.MISSING
    assert profile.offerings == []

    # Audit trail
    assert any("name:schema_org" in u for u in profile.extraction_meta.rule_extractors_used)
    assert any("category:schema_org" in u for u in profile.extraction_meta.rule_extractors_used)


def test_orchestrator_schema_org_name_beats_metadata():
    m = _rich_manifest()
    # Both have a name; schema.org should win
    profile = apply_rules(m)
    assert "MedicalClinic" in profile.name.evidence[0].extractor


def test_orchestrator_fallback_to_metadata_name():
    m = _rich_manifest()
    m.site_metadata.schema_org = []  # remove schema.org
    profile = apply_rules(m)
    assert profile.name.value == "SP Clinic"  # from og:site_name
    assert profile.name.evidence[0].extractor == "rule:og:site_name"
