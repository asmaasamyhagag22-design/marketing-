"""The creative-direction sampler. Draws one entry per library (archetypes / motif domains
/ protagonist slots), FILTERED by audience fit from the grounded profile, so a run's creative
direction is deliberately varied — never left to chance (owner directive 2026-07-13).

Reproducible: pass `forced=` to re-inject an exact triple (the run manifest logs the sampled
triple), or `seed=` for deterministic draws in tests. `avoid=` down-ranks recently-used entries
(the campaign history AVOID list) so consecutive runs for one client don't echo each other.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, asdict
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import yaml

_DIR = Path(__file__).resolve().parent
_LIBRARIES = {
    "archetype": ("narrative_archetypes.yaml", "archetypes"),
    "motif_domain": ("motif_domains.yaml", "motif_domains"),
    "protagonist_slot": ("protagonist_slots.yaml", "protagonist_slots"),
}


@lru_cache(maxsize=None)
def load_library(kind: str) -> tuple:
    """Return the list of entries for a library kind ('archetype'|'motif_domain'|
    'protagonist_slot'). Cached; returns a tuple so it stays hashable/immutable."""
    if kind not in _LIBRARIES:
        raise KeyError(f"unknown library {kind!r}")
    fname, root = _LIBRARIES[kind]
    data = yaml.safe_load((_DIR / fname).read_text(encoding="utf-8")) or {}
    entries = data.get(root) or []
    return tuple(entries)


@dataclass(frozen=True)
class CreativeDirection:
    archetype: str
    motif_domain: str
    protagonist_slot: str
    archetype_desc: str = ""
    motif_domain_desc: str = ""
    protagonist_slot_desc: str = ""

    @property
    def triple(self) -> dict:
        """The reproducible, loggable triple (keys only) — re-injectable via `forced=`."""
        return {"archetype": self.archetype, "motif_domain": self.motif_domain,
                "protagonist_slot": self.protagonist_slot}

    def to_manifest(self) -> dict:
        return asdict(self)


def _profile_tokens(profile: Optional[dict]) -> set[str]:
    """Audience-fit tokens from the grounded profile: category + audience type/signals +
    tone. Lowercased words; drives which library entries are a fit."""
    p = (profile or {}).get("profile", profile) if isinstance(profile, dict) else {}
    p = p or {}

    def _val(x: Any) -> str:
        return str((x or {}).get("value") if isinstance(x, dict) else (x or ""))

    parts = [_val(p.get("category")), _val(p.get("audience_type"))]
    for sig in (p.get("audience_signals") or [])[:8]:
        parts.append(_val(sig))
    parts.append(_val(p.get("tone_of_voice")))
    toks: set[str] = set()
    import re
    for part in parts:
        toks |= {w for w in re.findall(r"[a-z]{3,}", part.lower())}
    return toks


def _fits(entry: dict, tokens: set[str]) -> bool:
    """An entry fits when it is universal or one of its audience_fit tags matches a
    profile token (substring either direction, so 'ecommerce' matches 'e-commerce')."""
    fit = [str(t).lower() for t in (entry.get("audience_fit") or [])]
    if "universal" in fit:
        return True
    for tag in fit:
        if tag in tokens or any(tag in tok or tok in tag for tok in tokens):
            return True
    return False


def _pick(kind: str, tokens: set[str], rng: random.Random,
          avoid_keys: set[str]) -> dict:
    """Choose one fitting entry, de-prioritising avoided keys; fall back to all entries
    when nothing fits (never fail to produce a direction)."""
    entries = list(load_library(kind))
    fitting = [e for e in entries if _fits(e, tokens)] or entries
    fresh = [e for e in fitting if e.get("key") not in avoid_keys]
    pool = fresh or fitting
    return rng.choice(pool)


def sample_direction(profile: Optional[dict] = None, *, seed: Optional[int] = None,
                     forced: Optional[dict] = None,
                     avoid: Optional[list[str]] = None,
                     rng: Optional[random.Random] = None) -> CreativeDirection:
    """Draw one (archetype, motif_domain, protagonist_slot), audience-filtered.

    `forced` (a dict with any of the three keys) pins those axes exactly — for reproducing a
    logged triple or honouring an owner override. `avoid` is a flat list of keys (any library)
    to de-prioritise. `seed`/`rng` make the draw deterministic for tests."""
    rng = rng or random.Random(seed)
    tokens = _profile_tokens(profile)
    forced = forced or {}
    avoid_keys = set(avoid or [])

    def _resolve(kind: str) -> dict:
        forced_key = forced.get(kind)
        if forced_key:
            for e in load_library(kind):
                if e.get("key") == forced_key:
                    return e
            raise KeyError(f"forced {kind}={forced_key!r} not in library")
        return _pick(kind, tokens, rng, avoid_keys)

    a = _resolve("archetype")
    m = _resolve("motif_domain")
    p = _resolve("protagonist_slot")
    return CreativeDirection(
        archetype=a["key"], motif_domain=m["key"], protagonist_slot=p["key"],
        archetype_desc=(a.get("description") or "").strip(),
        motif_domain_desc=(m.get("description") or "").strip(),
        protagonist_slot_desc=(p.get("description") or "").strip(),
    )


def sample_distinct_directions(profile: Optional[dict] = None, *, n: int = 3,
                               seed: Optional[int] = None,
                               avoid: Optional[list[str]] = None
                               ) -> list[CreativeDirection]:
    """`n` directions with DISTINCT archetypes (and, where the fitting pool allows, distinct
    motif domains + protagonist slots) — the raw material for an n-candidate HITL package."""
    rng = random.Random(seed)
    out: list[CreativeDirection] = []
    used_arch: set[str] = set()
    used_motif: set[str] = set()
    used_slot: set[str] = set()
    guard = 0
    while len(out) < n and guard < n * 40:
        guard += 1
        d = sample_direction(profile, rng=rng,
                             avoid=list(set(avoid or []) | used_motif | used_slot))
        if d.archetype in used_arch:
            continue
        used_arch.add(d.archetype)
        used_motif.add(d.motif_domain)
        used_slot.add(d.protagonist_slot)
        out.append(d)
    # If distinct archetypes ran out (small fitting pool), top up allowing repeats.
    while len(out) < n:
        out.append(sample_direction(profile, rng=rng, avoid=avoid))
    return out
