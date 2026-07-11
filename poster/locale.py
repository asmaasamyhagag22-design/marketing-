"""Evidence-derived brand locale — ONE shared primer for every image-prompt builder.

FIX-C3/D (2026-07-11, owner: "لازم البلد والثقافة تأثر"): an Egyptian government brand got
visibly non-Egyptian generic-Western people because the culture anchor lived ONLY on the
poster's classic path — the oneshot engine, the concept builder and the reel had zero locale.
This module derives the brand's country from PROFILE EVIDENCE (never hardcoded):
    ccTLD  ->  service_areas (an evidenced field)  ->  phone e164 prefix  ->  languages cue
and renders the proven `_region_line` wording parameterized by that country. Unknown locale ->
("", "") — an HONEST fallback: no cultural claim is injected when the evidence doesn't carry one.
Universal by construction: works for any country; nothing Egypt-specific.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

# ccTLD -> country. The MENA core (the pilot market) + the major world markets. A static
# lookup, no deps; extend freely — every entry is evidence-driven (the brand's own domain).
CCTLD_COUNTRY = {
    # MENA
    "eg": "Egypt", "sa": "Saudi Arabia", "ae": "the UAE", "ma": "Morocco", "jo": "Jordan",
    "kw": "Kuwait", "qa": "Qatar", "lb": "Lebanon", "dz": "Algeria", "tn": "Tunisia",
    "iq": "Iraq", "om": "Oman", "bh": "Bahrain", "ly": "Libya", "sy": "Syria",
    "ye": "Yemen", "sd": "Sudan", "ps": "Palestine", "tr": "Turkey", "ir": "Iran",
    # Africa
    "ng": "Nigeria", "ke": "Kenya", "za": "South Africa", "gh": "Ghana", "et": "Ethiopia",
    # Europe
    "uk": "the UK", "de": "Germany", "fr": "France", "es": "Spain", "it": "Italy",
    "nl": "the Netherlands", "pt": "Portugal", "gr": "Greece", "pl": "Poland",
    "se": "Sweden", "ch": "Switzerland", "at": "Austria", "be": "Belgium", "ie": "Ireland",
    # Asia-Pacific
    "in": "India", "pk": "Pakistan", "bd": "Bangladesh", "id": "Indonesia", "my": "Malaysia",
    "sg": "Singapore", "th": "Thailand", "vn": "Vietnam", "ph": "the Philippines",
    "jp": "Japan", "kr": "South Korea", "cn": "China", "hk": "Hong Kong", "tw": "Taiwan",
    "au": "Australia", "nz": "New Zealand",
    # Americas
    "us": "the USA", "ca": "Canada", "mx": "Mexico", "br": "Brazil", "ar": "Argentina",
    "cl": "Chile", "co": "Colombia", "pe": "Peru",
}

# e164 dial prefix -> country (longest-prefix match). Compact, common markets.
_E164_COUNTRY = {
    "+20": "Egypt", "+966": "Saudi Arabia", "+971": "the UAE", "+212": "Morocco",
    "+962": "Jordan", "+965": "Kuwait", "+974": "Qatar", "+961": "Lebanon",
    "+213": "Algeria", "+216": "Tunisia", "+964": "Iraq", "+968": "Oman",
    "+973": "Bahrain", "+218": "Libya", "+249": "Sudan", "+970": "Palestine",
    "+90": "Turkey", "+234": "Nigeria", "+254": "Kenya", "+27": "South Africa",
    "+44": "the UK", "+49": "Germany", "+33": "France", "+34": "Spain", "+39": "Italy",
    "+91": "India", "+92": "Pakistan", "+62": "Indonesia", "+60": "Malaysia",
    "+65": "Singapore", "+81": "Japan", "+82": "South Korea", "+86": "China",
    "+61": "Australia", "+1": "the USA/Canada", "+52": "Mexico", "+55": "Brazil",
}


def _get(obj: Any, key: str, default: Any = None) -> Any:
    val = obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)
    return default if val is None else val


def _fv(obj: Any, key: str) -> str:
    v = _get(obj, key)
    if isinstance(v, dict) and "value" in v:
        v = v.get("value")
    v = getattr(v, "value", v)
    return str(v).strip() if v else ""


def country_of(profile: Any) -> str:
    """The brand's country from profile evidence, strongest signal first. '' when unknown."""
    p = profile or {}
    if isinstance(p, dict) and isinstance(p.get("profile"), dict):
        p = p["profile"]

    # 1. ccTLD of the brand's own domain (the most reliable signal)
    url = _fv(p, "source_url") or _fv(p, "url") or _fv(p, "website")
    try:
        host = urlparse(url if "://" in url else "https://" + url).netloc.lower()
    except Exception:
        host = ""
    if host:
        tld = host.rsplit(".", 1)[-1]
        if tld in CCTLD_COUNTRY:
            return CCTLD_COUNTRY[tld]

    # 2. service_areas — an evidenced profile field ("Egypt", "Cairo, Egypt", ...)
    for area in (_get(p, "service_areas") or []):
        a = area.get("value") if isinstance(area, dict) else getattr(area, "value", area)
        a = str(a or "").strip()
        for country in set(CCTLD_COUNTRY.values()):
            plain = country.replace("the ", "")
            if plain and plain.lower() in a.lower():
                return country

    # 3. phone e164 prefix (longest match wins)
    cc = _get(p, "contact_channels") or {}
    for ph in (_get(cc, "phones") or []):
        e164 = ph.get("e164") if isinstance(ph, dict) else getattr(ph, "e164", None)
        e164 = str(e164 or "")
        if e164.startswith("+"):
            for pref in sorted(_E164_COUNTRY, key=len, reverse=True):
                if e164.startswith(pref):
                    return _E164_COUNTRY[pref]
    return ""


def brand_locale(profile: Any) -> tuple[str, str]:
    """(country, primer_line) for image prompts. The primer is the proven anti-drift wording
    (no clichés: 'their own everyday style', never named dress items). When only the LANGUAGE
    is known (Arabic content, no country evidence), an honest regional cue is returned; when
    nothing is known, ('', '') — inject no cultural claim."""
    p = profile or {}
    if isinstance(p, dict) and isinstance(p.get("profile"), dict):
        p = p["profile"]
    country = country_of(p)
    if country:
        return country, (
            f"PEOPLE & SETTING — every person and environment is authentically from {country}: "
            f"real local people in their own everyday style and dress (NOT a generic 'Arab' or "
            f"Gulf/Khaleeji look, NOT Western/European casting); architecture, streets, interiors "
            f"and signage that belong in {country}."
        )
    langs = [str(getattr(x, "code", None) or (x.get("code") if isinstance(x, dict) else x) or "").lower()
             for x in (_get(p, "languages") or [])]
    if any(str(l).startswith("ar") for l in langs):
        return "", ("PEOPLE & SETTING — an authentic Arabic-speaking-region environment with real "
                    "local people; NOT Western or European architecture, streets, signage, or people.")
    return "", ""
