"""Schema.org JSON-LD extraction.

Many business sites embed structured data via JSON-LD. When present,
these are the most reliable source for: name, category, address(es),
opening hours, geo coordinates.

Handles @graph arrays, nested @type, and the common schema.org types
we see on Egyptian business sites.
"""
from __future__ import annotations

from typing import Iterator, Optional

from scraper.schemas import ScrapeManifest

from ..schemas import (
    BusinessCategory,
    Confidence,
    EvidenceItem,
    EvidencedField,
    Location,
    OpeningHours,
    OpeningHoursEntry,
    SourceType,
)


# Map schema.org @type strings to our BusinessCategory enum.
# Order matters: more specific types should be checked first.
_TYPE_TO_CATEGORY: dict[str, BusinessCategory] = {
    # Food
    "Restaurant": BusinessCategory.RESTAURANT,
    "FastFoodRestaurant": BusinessCategory.RESTAURANT,
    "CafeOrCoffeeShop": BusinessCategory.CAFE,
    "BarOrPub": BusinessCategory.RESTAURANT,
    "Bakery": BusinessCategory.RESTAURANT,
    "FoodEstablishment": BusinessCategory.RESTAURANT,
    # Medical
    "MedicalClinic": BusinessCategory.CLINIC,
    "Dentist": BusinessCategory.CLINIC,
    "Physician": BusinessCategory.CLINIC,
    "Hospital": BusinessCategory.HOSPITAL,
    "MedicalBusiness": BusinessCategory.CLINIC,
    # Education
    "EducationalOrganization": BusinessCategory.EDUCATION,
    "School": BusinessCategory.EDUCATION,
    "CollegeOrUniversity": BusinessCategory.EDUCATION,
    "Preschool": BusinessCategory.EDUCATION,
    # Government
    "GovernmentOrganization": BusinessCategory.GOVERNMENT,
    "GovernmentOffice": BusinessCategory.GOVERNMENT,
    # Retail / e-commerce
    "Store": BusinessCategory.RETAIL,
    "ClothingStore": BusinessCategory.RETAIL,
    "ShoeStore": BusinessCategory.RETAIL,
    "ElectronicsStore": BusinessCategory.RETAIL,
    "DepartmentStore": BusinessCategory.RETAIL,
    "OnlineStore": BusinessCategory.ECOMMERCE,
    # Beauty / wellness
    "BeautySalon": BusinessCategory.BEAUTY,
    "HairSalon": BusinessCategory.BEAUTY,
    "DaySpa": BusinessCategory.BEAUTY,
    "HealthClub": BusinessCategory.FITNESS,
    "GymOrFitnessCenter": BusinessCategory.FITNESS,
    # Hospitality
    "Hotel": BusinessCategory.HOSPITALITY,
    "BedAndBreakfast": BusinessCategory.HOSPITALITY,
    "Resort": BusinessCategory.HOSPITALITY,
    "TravelAgency": BusinessCategory.HOSPITALITY,
    # Auto
    "AutomotiveBusiness": BusinessCategory.AUTOMOTIVE,
    "AutoRepair": BusinessCategory.AUTOMOTIVE,
    "AutoDealer": BusinessCategory.AUTOMOTIVE,
    # Professional services
    "Attorney": BusinessCategory.PROFESSIONAL_SERVICES,
    "AccountingService": BusinessCategory.PROFESSIONAL_SERVICES,
    "LegalService": BusinessCategory.PROFESSIONAL_SERVICES,
    "FinancialService": BusinessCategory.PROFESSIONAL_SERVICES,
    "InsuranceAgency": BusinessCategory.PROFESSIONAL_SERVICES,
    "RealEstateAgent": BusinessCategory.REAL_ESTATE,
    # Generic — lowest priority, but still useful
    "LocalBusiness": BusinessCategory.OTHER,
    "Organization": BusinessCategory.OTHER,
    "ProfessionalService": BusinessCategory.PROFESSIONAL_SERVICES,
    "NGO": BusinessCategory.NONPROFIT,
}


def _iter_schema_blocks(manifest: ScrapeManifest) -> Iterator[dict]:
    """Walk manifest.site_metadata.schema_org, handling @graph arrays."""
    for block in manifest.site_metadata.schema_org:
        data = block.data if hasattr(block, "data") else block
        if not isinstance(data, dict):
            continue
        graph = data.get("@graph")
        if isinstance(graph, list):
            for item in graph:
                if isinstance(item, dict):
                    yield item
            continue
        yield data


def _type_set(item: dict) -> set[str]:
    """@type can be a string or a list of strings."""
    t = item.get("@type")
    if isinstance(t, str):
        return {t}
    if isinstance(t, list):
        return {x for x in t if isinstance(x, str)}
    return set()


def extract_name_from_schema_org(manifest: ScrapeManifest) -> EvidencedField[str]:
    """Walk schema.org blocks and return the first name field found
    on a business-like type."""
    home_url = manifest.scrape_meta.final_url or manifest.scrape_meta.normalized_url

    # Prefer named business types over generic Organization
    business_match: Optional[tuple[str, str]] = None
    generic_match: Optional[tuple[str, str]] = None

    for item in _iter_schema_blocks(manifest):
        types = _type_set(item)
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        clean = name.strip()

        if types & set(_TYPE_TO_CATEGORY.keys()) - {"LocalBusiness", "Organization"}:
            business_match = (clean, next(iter(types)))
            break
        if "Organization" in types or "LocalBusiness" in types:
            generic_match = generic_match or (clean, next(iter(types)))

    match = business_match or generic_match
    if not match:
        return EvidencedField.missing()

    return EvidencedField(
        value=match[0],
        evidence=[EvidenceItem(
            block_id=None, page_url=home_url, quote=match[0],
            extractor=f"schema_org:{match[1]}.name",
        )],
        confidence=Confidence.HIGH,
        source_type=SourceType.EXTRACTED,
    )


def extract_category_from_schema_org(
    manifest: ScrapeManifest,
) -> EvidencedField[BusinessCategory]:
    home_url = manifest.scrape_meta.final_url or manifest.scrape_meta.normalized_url

    # Pick the most specific type we can map
    best: Optional[tuple[BusinessCategory, str]] = None
    for item in _iter_schema_blocks(manifest):
        for t in _type_set(item):
            cat = _TYPE_TO_CATEGORY.get(t)
            if cat is None:
                continue
            # Skip OTHER (from generic Organization/LocalBusiness) if we
            # already have something more specific
            if cat == BusinessCategory.OTHER and best is not None:
                continue
            if best is None or best[0] == BusinessCategory.OTHER:
                best = (cat, t)
            # Don't break — keep looking for something more specific

    if best is None:
        return EvidencedField.missing()

    return EvidencedField(
        value=best[0],
        evidence=[EvidenceItem(
            block_id=None, page_url=home_url, quote=None,
            extractor=f"schema_org:{best[1]}",
        )],
        confidence=Confidence.HIGH if best[0] != BusinessCategory.OTHER else Confidence.LOW,
        source_type=SourceType.EXTRACTED,
    )


def _parse_postal_address(addr: dict) -> Optional[Location]:
    """Build a Location from a schema.org PostalAddress dict."""
    if not isinstance(addr, dict):
        return None
    street = addr.get("streetAddress")
    city = addr.get("addressLocality")
    region = addr.get("addressRegion")
    country = addr.get("addressCountry")
    postal = addr.get("postalCode")
    if isinstance(country, dict):
        country = country.get("name") or country.get("@id")

    parts = [p for p in [street, city, region, postal, country]
             if isinstance(p, str) and p.strip()]
    if not parts:
        return None
    return Location(
        address_text=", ".join(parts),
        city=city if isinstance(city, str) else None,
        region=region if isinstance(region, str) else None,
        country=country if isinstance(country, str) else None,
        postal_code=postal if isinstance(postal, str) else None,
    )


def extract_locations_from_schema_org(manifest: ScrapeManifest) -> list[Location]:
    home_url = manifest.scrape_meta.final_url or manifest.scrape_meta.normalized_url
    out: list[Location] = []
    seen: set[str] = set()

    for item in _iter_schema_blocks(manifest):
        addr = item.get("address")
        if not addr:
            continue
        addrs = addr if isinstance(addr, list) else [addr]
        for a in addrs:
            loc = _parse_postal_address(a) if isinstance(a, dict) else None
            if loc is None:
                continue
            key = (loc.address_text or "").lower()
            if key in seen:
                continue
            seen.add(key)

            # Geo coordinates if present on the parent item
            geo = item.get("geo")
            if isinstance(geo, dict):
                try:
                    loc.latitude = float(geo.get("latitude", 0)) or None
                    loc.longitude = float(geo.get("longitude", 0)) or None
                except (TypeError, ValueError):
                    pass

            loc.evidence = [EvidenceItem(
                block_id=None, page_url=home_url,
                quote=loc.address_text[:200] if loc.address_text else None,
                extractor="schema_org:PostalAddress",
            )]
            out.append(loc)
    return out


def _parse_opening_hours_spec(spec: dict) -> Optional[OpeningHoursEntry]:
    """schema.org OpeningHoursSpecification."""
    days_field = spec.get("dayOfWeek")
    if isinstance(days_field, list):
        days_list = [d for d in days_field if isinstance(d, str)]
    elif isinstance(days_field, str):
        days_list = [days_field]
    else:
        days_list = []
    # Strip the schema.org URL prefix
    days_clean = [d.rsplit("/", 1)[-1] for d in days_list]
    days_str = ", ".join(days_clean) if days_clean else "?"

    opens = spec.get("opens") if isinstance(spec.get("opens"), str) else None
    closes = spec.get("closes") if isinstance(spec.get("closes"), str) else None
    if not opens and not closes:
        return None
    return OpeningHoursEntry(days=days_str, opens=opens, closes=closes)


def _parse_opening_hours_string(s: str) -> Optional[OpeningHoursEntry]:
    """schema.org openingHours as 'Mo-Fr 09:00-17:00' format."""
    parts = s.strip().split(" ", 1)
    if len(parts) != 2:
        return None
    days, hrs = parts
    if "-" not in hrs:
        return None
    opens, closes = hrs.split("-", 1)
    return OpeningHoursEntry(days=days, opens=opens.strip(), closes=closes.strip())


def extract_hours_from_schema_org(manifest: ScrapeManifest) -> Optional[OpeningHours]:
    home_url = manifest.scrape_meta.final_url or manifest.scrape_meta.normalized_url
    entries: list[OpeningHoursEntry] = []

    for item in _iter_schema_blocks(manifest):
        # openingHoursSpecification (richer form)
        spec = item.get("openingHoursSpecification")
        if spec:
            specs = spec if isinstance(spec, list) else [spec]
            for s in specs:
                if isinstance(s, dict):
                    entry = _parse_opening_hours_spec(s)
                    if entry:
                        entries.append(entry)

        # openingHours (simpler string form)
        oh = item.get("openingHours")
        if oh:
            oh_list = oh if isinstance(oh, list) else [oh]
            for s in oh_list:
                if isinstance(s, str):
                    entry = _parse_opening_hours_string(s)
                    if entry:
                        entries.append(entry)

    if not entries:
        return None
    return OpeningHours(
        entries=entries,
        evidence=[EvidenceItem(
            block_id=None, page_url=home_url, quote=None,
            extractor="schema_org:openingHours",
        )],
    )
