"""Microdata + RDFa extraction via extruct (PR-2).

What this module does:
    Walks HTML for Microdata (`itemtype` / `itemprop` attributes) and
    RDFa (`typeof` / `property` attributes), normalizes the result to
    the same shape as JSON-LD blocks already produced by `metadata.py`,
    and returns a list of `SchemaOrgBlock` records tagged with their
    source.

What this module does NOT do:
    - Parse JSON-LD. That is already done in `metadata.py` and we
      deliberately do not duplicate it (extruct would happily re-parse
      JSON-LD too, producing duplicate blocks).
    - Parse OpenGraph, Twitter Cards, or Microformats. Those are either
      already covered by `metadata.py` or out of scope for PR-2.
    - Make any network calls. Pure HTML-in, blocks-out.

Why a separate module:
    - Isolates the heavy `extruct` import (it pulls in mf2py and
      rdflib transitively) from callers that only need OG/title.
    - Makes the blast radius of any extruct behavior surprise exactly
      one file.

Normalization rules:
    Microdata:
        extruct returns Microdata in JSON-LD-equivalent shape already
        (with `uniform=True`). We pass it through, only filtering out
        items that aren't dict-shaped or have no useful content.

    RDFa:
        extruct returns RDFa with full-IRI keys and value-arrays:
            {"@type": ["https://schema.org/Dentist"],
             "https://schema.org/name": [{"@value": "Smile Clinic"}]}
        We normalize to:
            {"@type": "Dentist", "name": "Smile Clinic"}
        by stripping the schema.org namespace prefix and unwrapping
        single-element @value arrays. RDFa cruft (usesVocabulary, blank
        node anchors with no useful properties) is dropped.

The normalized blocks plug directly into the existing schema.org
walker (`business_profile/rules/from_schema_org.py`) without any
change there. That's the whole point — a Microdata-marked Restaurant
site now gets its category detected for free.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable, Optional

from ..schemas import SchemaOrgBlock

logger = logging.getLogger(__name__)


# Schema.org namespace prefixes that may appear in RDFa keys.
# We strip them so RDFa output matches the bare schema.org property names
# that JSON-LD and Microdata already use.
_SCHEMA_PREFIXES = (
    "https://schema.org/",
    "http://schema.org/",
)

# RDFa "noise" keys that are structural rather than informational.
_RDFA_NOISE_KEYS = {
    "http://www.w3.org/ns/rdfa#usesVocabulary",
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#type",  # rare
}


def extract_structured_data(html: str, page_url: str) -> list[SchemaOrgBlock]:
    """Extract Microdata + RDFa blocks from HTML.

    Returns an empty list on:
      - empty HTML
      - missing extruct (graceful degradation if not installed)
      - extruct parse errors

    Never raises.
    """
    if not html or not html.strip():
        return []

    try:
        import extruct  # lazy import — keeps cold-start cheap for non-html paths
    except ImportError:
        logger.info("extruct not installed; Microdata/RDFa extraction skipped.")
        return []

    try:
        raw = extruct.extract(
            html,
            base_url=page_url,
            syntaxes=["microdata", "rdfa"],  # NOT json-ld (metadata.py already does that)
            uniform=True,
            errors="ignore",
        )
    except Exception as exc:
        # extruct can raise on pathologically bad HTML, encoding issues,
        # rdflib namespace edge cases, etc. We must never propagate that
        # up the crawler — better to lose this signal than fail the scrape.
        logger.warning("extruct failed on %s: %s", page_url, exc)
        return []

    out: list[SchemaOrgBlock] = []

    for item in raw.get("microdata", []) or []:
        block = _microdata_to_block(item)
        if block:
            out.append(block)

    for item in raw.get("rdfa", []) or []:
        block = _rdfa_to_block(item)
        if block:
            out.append(block)

    return out


# ---------------------------------------------------------------------
# Microdata normalization (already mostly JSON-LD-shaped via uniform=True)
# ---------------------------------------------------------------------

def _microdata_to_block(item: Any) -> Optional[SchemaOrgBlock]:
    if not isinstance(item, dict):
        return None

    # Strip schema.org namespace from @type if extruct kept it as a full URI.
    # With uniform=True this rarely happens for Microdata, but we defend.
    normalized = _strip_namespace_in_dict(item)

    raw_type = normalized.get("@type")
    type_str = _flatten_type(raw_type)

    if not _has_useful_content(normalized):
        return None

    return SchemaOrgBlock(type=type_str, data=normalized, source="microdata")


# ---------------------------------------------------------------------
# RDFa normalization (more invasive — RDFa keys are full IRIs)
# ---------------------------------------------------------------------

def _rdfa_to_block(item: Any) -> Optional[SchemaOrgBlock]:
    if not isinstance(item, dict):
        return None

    # Drop obvious RDFa noise nodes (e.g. usesVocabulary anchors).
    if _is_rdfa_noise_node(item):
        return None

    # 2026-05 PR-universal-channels: extruct's RDFa parser fires on any
    # RDFa-conforming markup, which includes OpenGraph (`<meta property="og:..."`)
    # and AppLinks (`<meta property="al:..."`) and XHTML accessibility roles
    # (`<div role="..."`). None of those are schema.org data. They pollute
    # `site_metadata.schema_org` with no business signal and confuse downstream
    # walkers. We require a positive signal that this block is schema.org-related
    # BEFORE doing the (expensive) normalization. The rule:
    #
    #   Keep the block only if AT LEAST ONE of:
    #     (a) The raw `@type` value mentions schema.org, OR
    #     (b) At least one property key is a schema.org IRI.
    #
    # This is universal across all RDFa-marked sites: real schema.org RDFa
    # (WordPress restaurants, clinics, etc.) keeps coming through; OpenGraph
    # and accessibility cruft gets dropped.
    if not _has_schema_org_signal(item):
        return None

    normalized = _normalize_rdfa_object(item)
    if normalized is None or not isinstance(normalized, dict):
        return None

    raw_type = normalized.get("@type")
    type_str = _flatten_type(raw_type)

    if not _has_useful_content(normalized):
        return None

    return SchemaOrgBlock(type=type_str, data=normalized, source="rdfa")


def _has_schema_org_signal(item: dict) -> bool:
    """True if a raw RDFa item carries any schema.org data.

    Checks the raw (pre-normalization) item shape:
      - `@type` value (string or list) mentions schema.org, OR
      - any property key is itself a schema.org IRI.

    Drops blocks whose only content is OpenGraph (ogp.me), AppLinks (al:),
    XHTML accessibility (w3.org/xhtml), or other non-schema.org RDFa.
    """
    # Check @type
    raw_type = item.get("@type")
    if isinstance(raw_type, str):
        if any(raw_type.startswith(p) for p in _SCHEMA_PREFIXES):
            return True
        # Bare schema.org type without prefix (rare in RDFa, but defensive)
        if raw_type and not raw_type.startswith(("http://", "https://", "_:")):
            return True
    elif isinstance(raw_type, list):
        for t in raw_type:
            if isinstance(t, str) and any(t.startswith(p) for p in _SCHEMA_PREFIXES):
                return True
            if isinstance(t, str) and t and not t.startswith(("http://", "https://", "_:")):
                return True

    # Check property keys
    for key in item.keys():
        if not isinstance(key, str):
            continue
        if any(key.startswith(p) for p in _SCHEMA_PREFIXES):
            return True

    return False


def _is_rdfa_noise_node(item: dict) -> bool:
    """True if a top-level RDFa item is just structural cruft."""
    real_keys = [
        k for k in item.keys()
        if k != "@id" and k != "@type" and k not in _RDFA_NOISE_KEYS
    ]
    if not real_keys:
        return True
    # If every "real" key is a noise key after stripping, also noise.
    return all(k in _RDFA_NOISE_KEYS for k in real_keys)


def _normalize_rdfa_object(item: Any) -> Any:
    """Recursively normalize an RDFa value into JSON-LD-equivalent shape.

    - Strips `https://schema.org/` prefix from keys, from @type values,
      and from @id values when they're schema.org URIs (those are types
      represented as references).
    - Unwraps `[{"@value": v}]` and `[{"@id": ...}]` to plain values
      where unambiguous.
    - Drops noise keys (usesVocabulary, blank-node @id anchors).
    """
    if isinstance(item, dict):
        out: dict[str, Any] = {}
        for key, value in item.items():
            if key in _RDFA_NOISE_KEYS:
                continue
            # @id with a blank-node identifier ("_:N...") carries no information.
            if key == "@id" and isinstance(value, str) and value.startswith("_:"):
                continue
            short_key = _strip_namespace(key)
            normalized_value = _normalize_rdfa_value(value)
            # @type values should always be stripped of the schema.org prefix
            # so the downstream walker matches its bare-name category table.
            if short_key == "@type":
                normalized_value = _strip_type_value(normalized_value)
            # Don't keep keys with empty values
            if normalized_value is None or normalized_value == [] or normalized_value == "":
                continue
            out[short_key] = normalized_value
        return out
    if isinstance(item, list):
        # Lists of values — recurse and unwrap singletons
        normalized = [_normalize_rdfa_object(v) for v in item]
        normalized = [v for v in normalized if v is not None and v != "" and v != {}]
        if len(normalized) == 1:
            return normalized[0]
        return normalized
    return item


def _strip_type_value(value: Any) -> Any:
    """Strip the schema.org prefix from one or many @type values."""
    if isinstance(value, str):
        return _strip_namespace(value)
    if isinstance(value, list):
        return [_strip_namespace(v) if isinstance(v, str) else v for v in value]
    return value


def _normalize_rdfa_value(value: Any) -> Any:
    """Unwrap a single RDFa property value.

    Common shapes:
        [{"@value": "Smile Clinic"}]   →  "Smile Clinic"
        [{"@id": "https://x.com/y"}]   →  "https://x.com/y"
        [{"@type": "PostalAddress", ...}] → nested dict (recurse)
    """
    if isinstance(value, list):
        unwrapped = [_normalize_rdfa_value(v) for v in value]
        unwrapped = [v for v in unwrapped if v is not None and v != ""]
        if len(unwrapped) == 1:
            return unwrapped[0]
        return unwrapped
    if isinstance(value, dict):
        # Single-key sugar: {"@value": "x"} → "x"
        if set(value.keys()) == {"@value"}:
            return value["@value"]
        # Single-key sugar: {"@id": "url"} → "url" (only when not a node anchor)
        if set(value.keys()) == {"@id"}:
            id_val = value["@id"]
            if isinstance(id_val, str) and id_val.startswith("_:"):
                return None  # blank-node anchor; drop
            return id_val
        # Nested object — recurse
        return _normalize_rdfa_object(value)
    return value


# ---------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------

def _strip_namespace(key: str) -> str:
    if not isinstance(key, str):
        return key
    for prefix in _SCHEMA_PREFIXES:
        if key.startswith(prefix):
            return key[len(prefix):]
    return key


def _strip_namespace_in_dict(item: dict) -> dict:
    """Strip schema.org prefix from @type values, leave other keys alone.

    Used for Microdata where keys are already short but @type may
    occasionally still carry the full IRI.
    """
    out: dict[str, Any] = {}
    for key, value in item.items():
        if key == "@type":
            if isinstance(value, str):
                value = _strip_namespace(value)
            elif isinstance(value, list):
                value = [_strip_namespace(v) if isinstance(v, str) else v for v in value]
        out[key] = value
    return out


def _flatten_type(raw_type: Any) -> Optional[str]:
    """Pick a single @type string for the block.type column."""
    if isinstance(raw_type, str):
        return _strip_namespace(raw_type)
    if isinstance(raw_type, list) and raw_type:
        first = raw_type[0]
        if isinstance(first, str):
            return _strip_namespace(first)
    return None


def _has_useful_content(item: dict) -> bool:
    """True if the normalized item carries at least one informational
    field beyond @type / @context / @id, AND that field has a
    non-empty value. extruct can emit `"value": ""` for empty
    itemscopes; we don't want those to count as content."""
    structural = {"@type", "@context", "@id"}
    for k, v in item.items():
        if k in structural:
            continue
        if v is None:
            continue
        if isinstance(v, str) and not v.strip():
            continue
        if isinstance(v, (list, dict)) and not v:
            continue
        return True
    return False


# ---------------------------------------------------------------------
# Dedupe helper — used by metadata merge / crawler
# ---------------------------------------------------------------------

def dedupe_schema_blocks(blocks: Iterable[SchemaOrgBlock]) -> list[SchemaOrgBlock]:
    """De-duplicate SchemaOrgBlocks across sources.

    Two blocks are considered duplicates when they share the same
    `type` AND a matching `name` field (when present). This handles
    the common case where a site emits BOTH JSON-LD and Microdata
    for the same business and we'd otherwise count it twice.

    Tie-breaking when duplicates are found:
      json_ld  >  next_data  >  microdata  >  rdfa
    The higher-priority source wins (its block stays, others dropped).
    Reason: JSON-LD follows a formal spec and is the most reliably-shaped.
    Next.js data is the developer's authoritative server-rendered JSON —
    very high fidelity but per-app shape. Microdata is HTML-attribute
    scraping. RDFa is normalized from a different spec in this module
    and is most prone to edge cases.
    """
    priority = {"json_ld": 0, "next_data": 1, "microdata": 2, "rdfa": 3}

    # Group by (type, name) signature
    groups: dict[tuple, list[SchemaOrgBlock]] = {}
    untyped: list[SchemaOrgBlock] = []
    for b in blocks:
        name = b.data.get("name") if isinstance(b.data, dict) else None
        if not b.type and not name:
            # Can't dedupe — keep as-is
            untyped.append(b)
            continue
        sig_name = name.strip().lower() if isinstance(name, str) else None
        sig = (b.type or "", sig_name or "")
        groups.setdefault(sig, []).append(b)

    out: list[SchemaOrgBlock] = []
    for sig, group in groups.items():
        if len(group) == 1:
            out.append(group[0])
            continue
        # Pick the highest-priority source
        winner = min(group, key=lambda b: priority.get(b.source, 99))
        out.append(winner)
    out.extend(untyped)
    return out