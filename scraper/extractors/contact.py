"""Contact extraction.

Rules:
- Phones via the `phonenumbers` library, parsed against EG as default
  region and US as fallback. Stored in E.164 form.
- Emails via regex.
- WhatsApp via wa.me / api.whatsapp.com links.
- Addresses: not auto-detected reliably; we leave a placeholder for
  schema.org PostalAddress blocks to feed in later.
- Map embeds: <iframe src> matching Google Maps.

Every record carries an `evidence_block_id` linking back to the
text block (or `None` if surfaced from an attribute like href).
"""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urlparse, unquote

import phonenumbers
from bs4 import BeautifulSoup

from ..config import EMAIL_REGEX
from ..url_utils import region_from_site
from ..schemas import (
    AddressRecord,
    ContactInfo,
    EmailRecord,
    MapEmbed,
    PhoneRecord,
    TextBlock,
    WhatsAppRecord,
)


_EMAIL_RE = re.compile(EMAIL_REGEX)

# Home-market fallback region for phone parsing when a site gives NO reliable country
# signal (no /xx-yy locale path, generic TLD). The product is Egypt-first (its whole
# corpus + the business_profile phone layer default to EG), so a signal-less national
# number is most likely Egyptian. Reliable per-site signals ALWAYS override this (see
# region_from_site), which is what stops the wrong-country fabrication that a blanket
# "EG" caused on the Saudi site nahdionline.com (/ar-sa -> SA, not EG). LIMITATION: a
# non-Egyptian site on a generic TLD with no locale path can still get EG here — the
# honest edge of what a universal signal can prove (tracked in process.md §6).
_HOME_MARKET_REGION = "EG"


def _e164(raw: str, region: str = "EG") -> Optional[str]:
    try:
        num = phonenumbers.parse(raw, region)
        if phonenumbers.is_possible_number(num) and phonenumbers.is_valid_number(num):
            return phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        pass
    return None


def _extract_phones_from_text(text: str, region: str = "EG") -> list[str]:
    """Find phone-number-shaped substrings in free text."""
    found = []
    seen = set()
    for match in phonenumbers.PhoneNumberMatcher(text, region):
        e164 = phonenumbers.format_number(match.number, phonenumbers.PhoneNumberFormat.E164)
        if e164 not in seen:
            seen.add(e164)
            found.append(e164)
    return found


def _extract_whatsapp(href: str) -> Optional[str]:
    """Extract the phone number from a wa.me / whatsapp.com URL."""
    try:
        p = urlparse(href)
        host = p.netloc.lower()
        if "wa.me" in host:
            return p.path.strip("/").split("/")[0] or None
        if "whatsapp.com" in host:
            # /send?phone=XXX or /send/?phone=XXX
            from urllib.parse import parse_qs
            q = parse_qs(p.query)
            ph = q.get("phone", [None])[0]
            return ph
    except Exception:
        return None
    return None


def extract_contact(
    html_by_page: dict[str, str],
    text_blocks_by_page: dict[str, list[TextBlock]],
    default_region: Optional[str] = None,
    *,
    site_url: Optional[str] = None,
) -> ContactInfo:
    """Extract phones/emails/whatsapp/maps/addresses from crawled pages.

    Phone region: numbers WITHOUT an international ``+`` prefix are ambiguous — the same
    digits are a different real number in every country. We parse them against the
    SITE's own region, derived from a RELIABLE universal signal (URL locale path /
    ccTLD) via ``region_from_site``; only when the site gives no such signal do we fall
    back to the home market (``_HOME_MARKET_REGION``). This is what stopped the blanket
    "EG" from turning the Saudi hotline 920024673 into a valid-looking WRONG
    +20920024673 (its /ar-sa locale now resolves to SA -> +966...). An explicit
    ``default_region`` overrides everything (used by tests); ``+``-prefixed and
    short-code numbers are region-independent.
    """
    info = ContactInfo()
    region = default_region or region_from_site(site_url) or _HOME_MARKET_REGION

    seen_phones: set[str] = set()
    seen_emails: set[str] = set()
    seen_wa: set[str] = set()
    seen_map_srcs: set[str] = set()

    # ---- Phones / emails from text blocks (with evidence) ----------
    for page_url, blocks in text_blocks_by_page.items():
        for b in blocks:
            # Emails in text
            for m in _EMAIL_RE.findall(b.text):
                key = m.lower()
                if key not in seen_emails:
                    seen_emails.add(key)
                    info.emails.append(EmailRecord(
                        address=m, evidence_block_id=b.block_id, page_url=page_url
                    ))
            # Phones in text
            for e164 in _extract_phones_from_text(b.text, region):
                if e164 not in seen_phones:
                    seen_phones.add(e164)
                    info.phones.append(PhoneRecord(
                        e164=e164, raw=b.text[:120], evidence_block_id=b.block_id,
                        page_url=page_url,
                    ))

    # ---- Protocol links and iframes from HTML ----------------------
    for page_url, html in html_by_page.items():
        if not html:
            continue
        soup = BeautifulSoup(html, "lxml")

        # tel: / mailto: / wa.me
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            lower = href.lower()

            if lower.startswith("tel:"):
                raw = unquote(href[4:])
                e164 = _e164(raw, region)
                if e164 and e164 not in seen_phones:
                    seen_phones.add(e164)
                    info.phones.append(PhoneRecord(
                        e164=e164, raw=raw, evidence_block_id=None, page_url=page_url,
                    ))
                elif not e164:
                    # 2026-05: hotline / short-code support (e.g. tel:19914).
                    # If E.164 validation failed but the body is short-and-numeric,
                    # store as a short-code PhoneRecord. Numeric junk
                    # ("tel:abc123" or "tel:1") is still dropped.
                    digits = re.sub(r"\D", "", raw)
                    if 3 <= len(digits) <= 7 and digits not in seen_phones:
                        seen_phones.add(digits)
                        info.phones.append(PhoneRecord(
                            e164=None,
                            raw=digits,
                            is_short_code=True,
                            evidence_block_id=None,
                            page_url=page_url,
                        ))
            elif lower.startswith("mailto:"):
                addr = unquote(href[7:]).split("?", 1)[0].strip()
                key = addr.lower()
                if addr and key not in seen_emails:
                    seen_emails.add(key)
                    info.emails.append(EmailRecord(
                        address=addr, evidence_block_id=None, page_url=page_url
                    ))
            elif "wa.me" in lower or "whatsapp.com" in lower:
                num = _extract_whatsapp(href)
                key = num or href
                if key not in seen_wa:
                    seen_wa.add(key)
                    info.whatsapp.append(WhatsAppRecord(
                        number=num, raw_url=href, page_url=page_url
                    ))

        # iframes -> map embeds
        for iframe in soup.find_all("iframe", src=True):
            src = iframe["src"]
            if src in seen_map_srcs:
                continue
            lower = src.lower()
            if "google.com/maps" in lower or "maps.google" in lower:
                seen_map_srcs.add(src)
                info.map_embeds.append(MapEmbed(
                    provider="google_maps", src=src, page_url=page_url
                ))
            elif "openstreetmap" in lower:
                seen_map_srcs.add(src)
                info.map_embeds.append(MapEmbed(
                    provider="openstreetmap", src=src, page_url=page_url
                ))

    # ---- Addresses from schema.org PostalAddress (handled in metadata
    # extractor; we leave info.addresses_raw empty for v0.1 unless the
    # caller injects them). Future: surface PostalAddress and <address>
    # tag content here.

    return info


def fill_addresses_from_schema_org(info: ContactInfo, schema_blocks, page_url: str) -> None:
    """Populate ContactInfo.addresses_raw from schema.org PostalAddress blocks."""
    seen = {a.text for a in info.addresses_raw}
    for blk in schema_blocks:
        data = blk.data if hasattr(blk, "data") else blk
        if not isinstance(data, dict):
            continue
        addr = data.get("address")
        if not addr:
            continue
        addrs = addr if isinstance(addr, list) else [addr]
        for a in addrs:
            if isinstance(a, dict):
                parts = [a.get("streetAddress"), a.get("addressLocality"),
                         a.get("addressRegion"), a.get("postalCode"),
                         a.get("addressCountry")]
                text = ", ".join(p for p in parts if isinstance(p, str) and p.strip())
            elif isinstance(a, str):
                text = a
            else:
                continue
            if text and text not in seen:
                seen.add(text)
                info.addresses_raw.append(AddressRecord(
                    text=text, evidence_block_id=None, page_url=page_url
                ))