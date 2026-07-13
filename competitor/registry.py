"""Competitor Registry — the stable competitive baseline (owner-caught non-determinism).

THE FLAW (owner, 2026-07-12): every scrape rebuilds the competitor set from live search +
LLM selection, so "who are my competitors" drifts run-to-run and the SWOT quietly changes
underneath the client. THE FIX: the first approved discovery PERSISTS as the baseline (per
brand); every later run produces a DIFF against it — still-present ✓ / disappeared ⚠ / new
candidate → pending owner approval — never a silent replacement. SWOT computes against the
APPROVED registry, not the raw live pool. Identity changes (approve/remove) are the owner's
call (HITL), so this module only COMPUTES and PERSISTS; it never auto-approves a newcomer.

Pure + deterministic; JSON persistence under `registry/<brand_slug>.json` (gitignored — it is
per-machine run state, like runs/). Never raises for ordinary input.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

_STORE = "registry"


def competitor_key(name: str = "", website: str = "") -> str:
    """A STABLE identity for a competitor — its domain (protocol/www/path stripped), else a
    normalized name. This is what survives run-to-run so the same rival is the same entry."""
    w = str(website or "").strip().lower()
    if w:
        dom = re.sub(r"^https?://", "", w)
        dom = re.sub(r"^www\.", "", dom).split("/")[0].split("?")[0].strip()
        if dom:
            return dom
    return re.sub(r"[^a-z0-9؀-ۿ]+", "", str(name or "").strip().lower())


def _entry_of(comp: dict) -> dict:
    sel = comp.get("selection") or {}
    cand = comp.get("candidate") or {}
    name = str(sel.get("name") or cand.get("name") or "").strip()
    site = str(sel.get("website") or cand.get("website") or "").strip()
    return {"key": competitor_key(name, site), "name": name, "website": site}


def registry_path(brand_ref: str, *, store_dir: str = _STORE) -> Path:
    slug = re.sub(r"[^a-z0-9]+", "_", str(brand_ref or "").strip().lower()).strip("_") or "brand"
    return Path(store_dir) / f"{slug}.json"


def load_registry(brand_ref: str, *, store_dir: str = _STORE) -> dict:
    """The persisted registry for a brand, or an empty new one. Never raises."""
    p = registry_path(brand_ref, store_dir=store_dir)
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
    return {"brand_ref": brand_ref, "entries": []}


def save_registry(registry: dict, *, store_dir: str = _STORE) -> Path:
    p = registry_path(registry.get("brand_ref") or "brand", store_dir=store_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def diff_competitors(registry: dict, discovered: list, *, now: str = "") -> dict:
    """Compare a fresh discovery against the persisted registry WITHOUT mutating it.
    Returns {still_present, disappeared, new_pending} lists of entries — the non-silent
    contract: a newcomer is 'pending' (needs owner approval), a missing baseline peer is
    'disappeared' (flagged, not deleted)."""
    reg_entries = {e["key"]: e for e in (registry.get("entries") or []) if e.get("key")}
    found = {}
    for comp in (discovered or []):
        e = _entry_of(comp)
        if e["key"]:
            found[e["key"]] = e
    approved = {k: e for k, e in reg_entries.items() if e.get("status", "approved") != "removed"}
    still_present = [reg_entries[k] for k in approved if k in found]
    disappeared = [reg_entries[k] for k in approved if k not in found]
    new_pending = [found[k] for k in found if k not in reg_entries]
    return {"still_present": still_present, "disappeared": disappeared,
            "new_pending": new_pending}


def establish_or_diff(brand_ref: str, discovered: list, *, store_dir: str = _STORE,
                      now: str = "") -> dict:
    """The live entrypoint. If no registry exists, ESTABLISH the baseline from this discovery
    (all approved — the first run is trusted) and persist it. Otherwise DIFF (read-only) and
    return the diff + the approved baseline for SWOT. Never auto-adds a newcomer."""
    reg = load_registry(brand_ref, store_dir=store_dir)
    if not (reg.get("entries") or []):
        entries = []
        seen = set()
        for comp in (discovered or []):
            e = _entry_of(comp)
            if e["key"] and e["key"] not in seen:
                seen.add(e["key"])
                e.update({"status": "approved", "first_seen": now, "last_seen": now})
                entries.append(e)
        reg = {"brand_ref": brand_ref, "entries": entries}
        save_registry(reg, store_dir=store_dir)
        return {"established": True, "diff": {"still_present": entries, "disappeared": [],
                "new_pending": []}, "approved_keys": [e["key"] for e in entries]}
    diff = diff_competitors(reg, discovered, now=now)
    approved_keys = [e["key"] for e in (reg.get("entries") or [])
                     if e.get("status", "approved") != "removed"]
    return {"established": False, "diff": diff, "approved_keys": approved_keys}


def approved_competitors(discovered: list, approved_keys: list) -> list:
    """Filter a live discovery down to the APPROVED registry keys — what SWOT should compute
    against (never the raw live pool). Order preserved."""
    keys = set(approved_keys or [])
    return [c for c in (discovered or []) if _entry_of(c)["key"] in keys]
