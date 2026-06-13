"""Regression tests for the universal-channel fixes (2026-05).

Three fixes ship together:

  1. Internal code reads `phones` (not deprecated `phones_e164`) so
     short-code hotlines count as a contact channel. Surfaces in:
     - business_profile.quality.compute_quality (has_contact)
     - business_profile.readiness.compute_readiness (no_reachable_contact_channel blocker)
     - business_profile.rules.orchestrator (contact:manifest_passthrough trace)
     - business_profile.__main__ (CLI summary)

  2. RDFa extraction filters out OpenGraph, AppLinks, and XHTML accessibility
     blocks that don't carry schema.org data. The bug surfaced on Buffalo
     Burger where extruct returned 25 RDFa blocks, ALL with type=None,
     because the site emits OpenGraph + Next.js accessibility metadata
     but no actual schema.org RDFa.

  3. (Docs-only) Clarified that the `phones_e164` property is deprecated
     and does NOT serialize via Pydantic v2. No test needed for docs.

These fixes are universal: hotlines affect every business with a short
code (restaurants, hospitals, food delivery, customer service); RDFa
noise affects every site that emits OpenGraph or React accessibility
roles, which is essentially every modern site.
"""
from __future__ import annotations

import sys
import types
from datetime import datetime, timezone

_fake = types.ModuleType("playwright")
_fake_sync = types.ModuleType("playwright.sync_api")
class _Stub: ...
for _n in ("Browser", "BrowserContext", "Page", "sync_playwright"):
    setattr(_fake_sync, _n, _Stub)
_fake_sync.TimeoutError = type("TimeoutError", (Exception,), {})
_fake_sync.Error = type("Error", (Exception,), {})
sys.modules.setdefault("playwright", _fake)
sys.modules.setdefault("playwright.sync_api", _fake_sync)


def _now():
    return datetime.now(timezone.utc)


# =====================================================================
# Fix 1: short-code hotlines count as a contact channel
# =====================================================================

def _profile_with_only_hotline():
    """Build a minimal profile whose ONLY contact is a short-code hotline.
    Before this fix, has_contact was False because `phones_e164` filtered
    out short codes."""
    from business_profile.schemas import (
        BusinessProfile, ContactChannels, ExtractionMeta, PhoneChannel,
        ProfileQuality,
    )
    return BusinessProfile(
        source_url="https://buffaloburger.com/",
        extraction_meta=ExtractionMeta(manifest_path="x.json", extracted_at=_now()),
        quality=ProfileQuality(
            has_name=False, has_category=False, has_offerings=False,
            has_audience=False, has_value_propositions=False, has_tone=False,
            has_contact=False, has_visual=False,
            fields_extracted=0, fields_inferred=0, fields_missing=0,
            ready_for_strategy=False,
        ),
        contact_channels=ContactChannels(phones=[
            PhoneChannel(e164=None, raw="19914", is_short_code=True),
        ]),
    )


def test_hotline_only_profile_counts_as_having_contact():
    """The compute_quality `has_contact` flag must be True when the only
    phone is a short-code hotline. Before this fix it was False."""
    from business_profile.quality import compute_quality

    p = _profile_with_only_hotline()
    q = compute_quality(p)
    assert q.has_contact is True


def test_hotline_only_profile_does_not_block_readiness_on_contact():
    """The Stage F-readiness layer's `no_reachable_contact_channel`
    blocker must NOT fire when the only phone is a hotline."""
    from business_profile.readiness import compute_readiness

    p = _profile_with_only_hotline()
    r = compute_readiness(p)
    # The campaign-gate blocker for contact channels must not fire here.
    assert "no_reachable_contact_channel" not in r.campaign_blockers, (
        f"hotline-only profile incorrectly blocked: {r.campaign_blockers}"
    )


def test_no_phones_at_all_still_blocks_readiness():
    """Regression guard: a profile with NO phones, no emails, no whatsapp,
    no form, no addresses should still trigger the no-contact blocker."""
    from business_profile.readiness import compute_readiness
    from business_profile.schemas import (
        BusinessProfile, ContactChannels, ExtractionMeta, ProfileQuality,
    )
    p = BusinessProfile(
        source_url="https://x.com/",
        extraction_meta=ExtractionMeta(manifest_path="x.json", extracted_at=_now()),
        quality=ProfileQuality(
            has_name=False, has_category=False, has_offerings=False,
            has_audience=False, has_value_propositions=False, has_tone=False,
            has_contact=False, has_visual=False,
            fields_extracted=0, fields_inferred=0, fields_missing=0,
            ready_for_strategy=False,
        ),
        contact_channels=ContactChannels(),  # nothing at all
    )
    r = compute_readiness(p)
    assert "no_reachable_contact_channel" in r.campaign_blockers


def test_phones_e164_property_still_filters_to_e164_only():
    """Deprecated property contract: even though internal code no longer
    uses `phones_e164`, the property must still return ONLY E.164 strings
    for any external caller relying on the old contract."""
    from business_profile.schemas import ContactChannels, PhoneChannel

    channels = ContactChannels(phones=[
        PhoneChannel(e164="+201001234567", raw="+20 100 123 4567", is_short_code=False),
        PhoneChannel(e164=None, raw="19914", is_short_code=True),
        PhoneChannel(e164="+201007654321", raw="+20 100 765 4321", is_short_code=False),
    ])
    # The deprecated property excludes the hotline (correct legacy contract)
    assert channels.phones_e164 == ["+201001234567", "+201007654321"]
    # The new canonical field includes everyone
    assert len(channels.phones) == 3


# =====================================================================
# Fix 2: RDFa filter — schema.org-only, drop OpenGraph + AppLinks + a11y
# =====================================================================

def test_rdfa_opengraph_only_html_produces_no_schema_blocks():
    """Buffalo Burger's actual pattern: a page that uses OpenGraph meta
    tags but emits no schema.org markup. extruct's RDFa parser will see
    the OpenGraph tags (because they use RDFa-shaped <meta property=...>);
    we must NOT pass those through as schema_org blocks."""
    from scraper.extractors.structured_data import extract_structured_data

    html = """
    <html><head>
      <meta property="og:title" content="Menu Page" />
      <meta property="og:description" content="Our menu" />
      <meta property="og:image" content="https://x.com/seo.png" />
      <meta property="og:site_name" content="Buffalo Burger | online ordering" />
      <meta property="og:type" content="website" />
      <meta property="al:android:app_name" content="Buffalo Burger" />
      <meta property="al:ios:app_store_id" content="1476031336" />
    </head><body></body></html>
    """
    blocks = extract_structured_data(html, "https://buffaloburger.com/")
    assert blocks == [], (
        f"OpenGraph-only page must produce zero schema_org blocks; got: {blocks}"
    )


def test_rdfa_xhtml_accessibility_roles_filtered_out():
    """Modern React apps emit XHTML accessibility roles
    (`<div role="combobox">`) which extruct parses as RDFa. These have no
    schema.org content and must not pollute schema_org."""
    from scraper.extractors.structured_data import extract_structured_data

    html = """
    <html><body>
      <div role="combobox" id="react-select-long-value-select-input"></div>
      <div role="alert" id="__next-route-announcer__"></div>
    </body></html>
    """
    blocks = extract_structured_data(html, "https://x.example/")
    # No schema.org content; expect empty.
    assert blocks == []


def test_rdfa_real_schema_org_still_extracted():
    """Critical regression guard: a site with REAL schema.org RDFa
    (WordPress-themed restaurant, clinic, etc.) must still produce
    blocks after Fix 2. The filter only drops blocks with no
    schema.org signal at all."""
    from scraper.extractors.structured_data import extract_structured_data

    html = """
    <html><body vocab="https://schema.org/" typeof="Restaurant">
      <h1 property="name">Andrea Restaurant</h1>
      <span property="telephone">+201001234567</span>
    </body></html>
    """
    blocks = extract_structured_data(html, "https://andrea.example/")
    rdfa = [b for b in blocks if b.source == "rdfa"]
    assert len(rdfa) == 1, (
        f"Real schema.org RDFa must still be extracted; got {len(rdfa)} blocks"
    )
    assert rdfa[0].type == "Restaurant"
    assert rdfa[0].data.get("name") == "Andrea Restaurant"


def test_rdfa_mixed_schema_org_and_opengraph_keeps_only_schema_org():
    """A site that uses BOTH OpenGraph (for social previews) AND schema.org
    RDFa (for SEO). The OpenGraph block must be filtered out; the
    schema.org block must come through."""
    from scraper.extractors.structured_data import extract_structured_data

    html = """
    <html>
      <head>
        <meta property="og:title" content="Smile Clinic" />
        <meta property="og:type" content="website" />
      </head>
      <body vocab="https://schema.org/" typeof="Dentist">
        <h1 property="name">Smile Clinic</h1>
      </body>
    </html>
    """
    blocks = extract_structured_data(html, "https://smile.example/")
    rdfa = [b for b in blocks if b.source == "rdfa"]
    # We keep exactly the Dentist block, drop the OpenGraph one.
    types = {b.type for b in rdfa}
    assert "Dentist" in types, (
        f"Real schema.org Dentist must be extracted; got types={types}"
    )
    # And we must not have produced an "og:" block (no such type would
    # exist anyway, but we double-check by ensuring no block carries a
    # data dict with ogp.me keys after normalization).
    for b in rdfa:
        for k in b.data.keys():
            assert "ogp.me" not in k, (
                f"OpenGraph data leaked into schema_org block: {k!r}"
            )


def test_buffalo_burger_style_full_page_produces_zero_schema_blocks():
    """End-to-end fixture matching Buffalo Burger's actual shape: a
    Next.js page with OpenGraph + AppLinks + accessibility roles, but no
    real schema.org RDFa. Before Fix 2, this produced 25 noise blocks
    with type=None. After Fix 2, zero."""
    from scraper.extractors.structured_data import extract_structured_data

    html = """
    <html><head>
      <meta property="og:title" content="Menu Page" />
      <meta property="og:image" content="https://x.com/seo.png" />
      <meta property="og:image:width" content="1200" />
      <meta property="og:image:height" content="630" />
      <meta property="og:site_name" content="Buffalo Burger | online ordering" />
      <meta property="al:android:app_name" content="Buffalo Burger" />
      <meta property="al:android:package" content="com.thebuffaloburger" />
      <meta property="al:android:url" content="https://buffaloburger.com/" />
      <meta property="al:ios:app_name" content="Buffalo Burger" />
      <meta property="al:ios:app_store_id" content="1476031336" />
    </head><body>
      <div role="combobox" id="react-select-long-value-select-input"></div>
      <div role="alert" id="__next-route-announcer__"></div>
      <main>
        <h1>Welcome</h1>
        <p>Order online for delivery.</p>
      </main>
    </body></html>
    """
    blocks = extract_structured_data(html, "https://buffaloburger.com/")
    # Zero is the honest answer: this page has no schema.org markup.
    assert blocks == [], (
        f"expected 0 schema_org blocks from OpenGraph+a11y-only page; "
        f"got {len(blocks)}: {[(b.source, b.type) for b in blocks]}"
    )