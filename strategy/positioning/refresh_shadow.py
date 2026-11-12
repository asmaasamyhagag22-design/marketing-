"""Content comparison for advisory reporting. Approval and delivery never consume it."""
from __future__ import annotations

import re


POLICY = "capture-equivalence@1"
SHA256 = re.compile(r"[a-f0-9]{64}")
OPTION_PARTS = {
    "consumer_value_claim_ids": "Consumer value",
    "reason_to_believe_claim_ids": "Reason to believe",
    "differentiation_claim_ids": "Differentiation",
    "internal_supporting_claim_ids": "Supporting research",
}


def _pages(capture):
    return {url: digest for url, digest in capture.get("pages", {}).items()
            if isinstance(digest, str) and SHA256.fullmatch(digest)}


def compare_captures(before, after, dependencies):
    """Compare observed bytes only. SKIP is a counterfactual for this capture scope."""
    before, after = before or {}, after or {}
    result = {"mode": "shadow", "policy": POLICY, "decision": "UNKNOWN",
              "reasons": [], "changes": []}
    if not before.get("representation") or not after.get("representation"):
        result["reasons"].append("CAPTURE_MISSING")
        return result
    if before["representation"] != after["representation"]:
        result["reasons"].append("CAPTURE_REPRESENTATION_CHANGED")
        return result

    old_pages, new_pages = _pages(before), _pages(after)
    common = old_pages.keys() & new_pages.keys()
    if (before.get("complete") is not True or after.get("complete") is not True
            or len(old_pages) != len(before.get("pages", {}))
            or len(new_pages) != len(after.get("pages", {}))):
        result["reasons"].append("CAPTURE_INCOMPLETE")
    if old_pages.keys() != new_pages.keys():
        result["reasons"].append("CAPTURE_COVERAGE_CHANGED")
    if not dependencies or any(row.get("page_url") not in common or not row.get("before_quote")
                               for row in dependencies):
        result["reasons"].append("STRATEGY_EVIDENCE_UNCOVERED")

    for url in sorted(common):
        if old_pages[url] != new_pages[url]:
            result["changes"].append({
                "page_url": url, "before_sha256": old_pages[url], "after_sha256": new_pages[url],
                "impacts": [row for row in dependencies if row.get("page_url") == url],
            })
    if result["changes"]:
        result["decision"] = "REVIEW"
        result["reasons"].insert(0, "CAPTURE_CONTENT_CHANGED")
    elif common and not result["reasons"]:
        result["decision"] = "SKIP"
        result["reasons"].append("CAPTURE_CONTENT_UNCHANGED")
    return result


def strategy_dependencies(canonical):
    """Project the selected option and rationale onto their saved quote relationships."""
    decision = canonical.get("decision") or {}
    selected_id = decision.get("selected_option_id")
    option = next((row for row in decision.get("options") or []
                   if selected_id and row.get("option_id") == selected_id), {})
    if not option:
        return []
    parts = {ident: "Positioning rationale" for key in ("accepted_claim_ids", "rationale_claim_ids")
             for ident in decision.get(key) or []}
    for ident in option.get("supporting_claim_ids") or []:
        parts.setdefault(ident, "Positioning support")
    for key, part in OPTION_PARTS.items():
        for ident in option.get(key) or []:
            parts[ident] = part

    claims = {row["claim_id"]: row for row in canonical.get("claims") or []}
    evidence = {row["evidence_id"]: row for row in canonical.get("evidence") or []}
    dependencies = []
    for ident, part in parts.items():
        claim = claims.get(ident, {})
        ids = claim.get("supporting_evidence_ids") or [None]
        for evidence_id in ids:
            row = evidence.get(evidence_id, {})
            dependencies.append({
                "part": part, "claim_id": ident, "claim": claim.get("statement") or "",
                "evidence_id": evidence_id, "page_url": row.get("source_url") or "",
                "before_quote": row.get("excerpt") or "", "source_ref": row.get("source_ref") or "",
            })
    return dependencies


def _field_quotes(profile, field_name, url):
    field = profile.get(field_name)
    fields = field if isinstance(field, list) else [field]
    return {item["quote"] for row in fields if isinstance(row, dict)
            for item in row.get("evidence") or [] if isinstance(item, dict)
            and item.get("page_url") == url
            and isinstance(item.get("quote"), str) and item["quote"].strip()}


def current_profile_excerpt(before, after, dependency):
    """Show an exact surviving quote or a single observed substitution in the same field/page."""
    match = re.fullmatch(r"profile\.(\w+)\[\d+\]\.evidence\[\d+\]",
                         dependency["source_ref"])
    if not match:
        return ""
    field, url = match.group(1), dependency["page_url"]
    previous = dependency["before_quote"]
    old_quotes = _field_quotes(before, field, url)
    new_quotes = _field_quotes(after, field, url)
    if previous in old_quotes & new_quotes:
        return previous
    added = new_quotes - old_quotes
    if old_quotes - new_quotes == {previous} and len(added) == 1:
        return next(iter(added))
    return ""
