"""Benchmark graders — score a BusinessProfile against per-URL ground truth.

This module is the product's quality scorer. Two families of grader:

  * STRUCTURAL graders (`grade_name`, `grade_category`, `grade_offerings`,
    `grade_pricing_visible`, `grade_contact_phone`, `grade_contact_email`,
    `grade_languages`, `grade_locations_count`) score a field against the URL's
    metadata alone (brand, vertical, tier, expected_languages) — no human-written
    ground truth needed. They return 1.0 / 0.5 / 0.0.

  * FUZZY graders (`grade_fuzzy_string`, `grade_fuzzy_enum`, `grade_fuzzy_list`)
    score an extracted value against an optional human ground-truth string/list.
    When no ground truth is provided they return `score=None` (UNGRADED) so the
    field neither helps nor hurts the average — honest about what we can't check.

`grade_profile` runs all 16 graders (8 structural + 8 fuzzy) and tags the 7
SWOT-critical fields (name, category, offerings, contact_phone, audience_type,
value_propositions, tone_of_voice).

Scoring is deterministic and language-agnostic where it can be: names are matched
after NFKD diacritic-stripping (Zööba == Zooba), SEO "chrome" suffixes are peeled
at a separator, and a non-Latin extracted name is credited when the brand is
confirmed by the URL slug (Arabic "مستشفى أندلسية" for andalusiaegypt.com).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, List, Optional


# ---------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------

@dataclass
class Grade:
    """One graded field. `score` is None when the field could not be graded
    (a fuzzy field with no ground truth) — distinct from 0.0 (graded, failed)."""
    field_name: str
    score: Optional[float]
    swot_critical: bool = False
    reason: str = ""


@dataclass
class UrlGradeSet:
    """All grades for one URL."""
    url_id: str
    grades: List[Grade] = field(default_factory=list)

    def avg_score(self, only_swot_critical: bool = False) -> Optional[float]:
        """Mean of graded scores, ignoring UNGRADED (None) fields. Returns None
        if nothing was graded. With `only_swot_critical=True`, averages only the
        SWOT-critical fields (the readiness signal the harness gates on)."""
        scored = [
            g.score for g in self.grades
            if g.score is not None and (g.swot_critical or not only_swot_critical)
        ]
        if not scored:
            return None
        return sum(scored) / len(scored)


# ---------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------

def _norm(s: Optional[str]) -> str:
    """NFKD-normalize, drop combining marks (diacritics), lowercase, strip.

    'Zööba' -> 'zooba', 'Café' -> 'cafe', 'résumé' -> 'resume'. Non-Latin
    scripts (Arabic, etc.) pass through unchanged but lowercased/stripped.
    """
    if not s:
        return ""
    decomposed = unicodedata.normalize("NFKD", str(s))
    no_marks = "".join(c for c in decomposed if not unicodedata.combining(c))
    return no_marks.lower().strip()


def _sig_tokens(s: Optional[str]) -> List[str]:
    """Significant tokens for fuzzy matching: alphanumeric, length > 2, and not
    purely numeric (a bare year like '2010' is not a content token)."""
    return [
        t for t in re.split(r"\W+", _norm(s))
        if len(t) > 2 and not t.isdigit()
    ]


def _coverage_score(ratio: float) -> float:
    """Map a coverage ratio to the discrete 1.0 / 0.5 / 0.0 scale used by the
    fuzzy graders: full coverage -> 1.0, at least a quarter -> 0.5, else 0.0."""
    if ratio >= 0.999:
        return 1.0
    if ratio >= 0.25:
        return 0.5
    return 0.0


# SEO "chrome" words that commonly trail a brand name after a separator
# ("Buffalo Burger | Online Ordering"). Used by _strip_chrome.
_CHROME_WORDS = {
    "online", "order", "ordering", "delivery", "official", "website", "web",
    "home", "homepage", "best", "shop", "store", "buy", "menu", "experience",
    "welcome", "get", "now", "today", "free", "sale", "deals", "offers", "app",
    "reservation", "reserve", "book", "booking", "discover", "explore", "world",
    "worlds", "the", "your", "our",
}

# Separators (with surrounding spaces, so hyphenated brands like "Coca-Cola"
# are NOT split) after which SEO chrome typically appears.
_CHROME_SEPARATORS = (" | ", " — ", " – ", " - ", " : ", "| ", " |", ": ")


def _looks_like_chrome(text: str) -> bool:
    toks = _sig_tokens(text) + [t for t in _norm(text).split() if t]
    return any(t in _CHROME_WORDS for t in toks)


def _strip_chrome(name: str) -> tuple[str, bool]:
    """Peel an SEO-chrome suffix off a name. Returns (cleaned_name, was_chrome).

    'buffalo burger | online ordering'        -> ('buffalo burger', True)
    'raw african's ... - get the experience!' -> ('raw african's ...', True)
    'auc school of continuing education'       -> (unchanged, False)   # no separator

    Only fires when there is a separator AND the suffix looks like chrome, so a
    real subtitle after a dash is left intact (returns was_chrome=False).
    """
    if not name:
        return name, False
    for sep in _CHROME_SEPARATORS:
        if sep in name:
            left, _, right = name.partition(sep)
            left, right = left.strip(), right.strip()
            if left and _looks_like_chrome(right):
                return left, True
    return name, False


def _value_of(ev_field: Any) -> Any:
    """Read .value off an EvidencedField (None when missing/absent)."""
    return getattr(ev_field, "value", None)


def _enum_str(value: Any) -> str:
    """A plain string for an enum value, a raw string, or None."""
    if value is None:
        return ""
    return str(getattr(value, "value", value))


def _domain_slug(url: Optional[str]) -> str:
    """'https://andalusiaegypt.com/' -> 'andalusiaegypt_com'. Best-effort; never
    raises (returns '' on anything unparseable)."""
    if not url:
        return ""
    try:
        from scraper.url_utils import get_domain_slug
        return get_domain_slug(url)
    except Exception:
        return ""


# ---------------------------------------------------------------------
# Structural graders
# ---------------------------------------------------------------------

def grade_name(profile: Any, url_meta: dict) -> Grade:
    """Did we extract the business name? Matched against url_meta['brand'].

    Match paths (any -> 1.0): exact (after diacritic-normalization); exact after
    peeling an SEO-chrome suffix; a significant brand token appears in the name;
    or — for a NON-Latin extracted name only — the brand is confirmed by the URL
    slug. Otherwise 0.0. Always SWOT-critical.
    """
    brand = url_meta.get("brand", "")
    raw = _value_of(profile.name if hasattr(profile, "name") else None)
    if not raw:
        return Grade("name", 0.0, swot_critical=True, reason="name missing")

    nn, nb = _norm(raw), _norm(brand)
    btoks = [t for t in re.split(r"\W+", nb) if len(t) >= 3]

    if nn and nn == nb:
        return Grade("name", 1.0, swot_critical=True, reason="exact match")

    cleaned, was_chrome = _strip_chrome(raw)
    hay = nn
    if was_chrome:
        ncl = _norm(cleaned)
        if ncl == nb or any(t in ncl for t in btoks):
            return Grade("name", 1.0, swot_critical=True,
                         reason=f"chrome stripped: {raw!r} -> {cleaned!r}")
        hay = ncl  # match tokens against the de-chromed name below

    if btoks and any(t in hay for t in btoks):
        return Grade("name", 1.0, swot_critical=True, reason="brand token matched")

    # Non-Latin extracted name (e.g. Arabic): we can't string-match a Latin brand,
    # so credit it only when the brand is independently confirmed by the URL.
    if not re.search(r"[a-z]", nn):
        slug = _norm(url_meta.get("id", "")) + " " + _norm(_domain_slug(
            getattr(profile, "source_url", "") or getattr(profile, "final_url", "")))
        if btoks and any(t in slug for t in btoks):
            return Grade("name", 1.0, swot_critical=True,
                         reason="non-Latin name; brand confirmed via URL slug")

    return Grade("name", 0.0, swot_critical=True, reason=f"name mismatch ({raw!r} vs brand {brand!r})")


# Vertical -> acceptable BusinessCategory values (a small synonym map; a direct
# value match always counts too).
_VERTICAL_CATEGORIES = {
    "restaurant": {"restaurant", "cafe", "hospitality"},
    "cafe": {"cafe", "restaurant"},
    "clinic": {"clinic", "hospital"},
    "hospital": {"hospital", "clinic"},
    "skincare": {"beauty", "ecommerce", "retail"},
    "beauty": {"beauty", "ecommerce", "retail"},
    "ecommerce": {"ecommerce", "retail"},
    "retail": {"retail", "ecommerce"},
    "education": {"education"},
    "fitness": {"fitness"},
    "real_estate": {"real_estate"},
    "automotive": {"automotive"},
}


def grade_category(profile: Any, url_meta: dict) -> Grade:
    """Did we classify the vertical correctly? 1.0 if the category matches
    url_meta['vertical'] (directly or via the synonym map), else 0.0. SWOT-critical."""
    vertical = _norm(url_meta.get("vertical", ""))
    cat = _enum_str(_value_of(getattr(profile, "category", None)))
    if not cat:
        return Grade("category", 0.0, swot_critical=True, reason="category missing")
    ncat = _norm(cat)
    accepted = _VERTICAL_CATEGORIES.get(vertical, {vertical})
    if ncat == vertical or ncat in accepted:
        return Grade("category", 1.0, swot_critical=True, reason=f"{cat} matches {vertical}")
    return Grade("category", 0.0, swot_critical=True, reason=f"{cat} != vertical {vertical}")


def grade_offerings(profile: Any, url_meta: dict) -> Grade:
    """Did we extract offerings? Tier-aware: a 'messy' site gets full credit for
    any offering; a typical/clean site wants >=2 (1 -> partial 0.5). SWOT-critical."""
    n = len(getattr(profile, "offerings", []) or [])
    tier = _norm(url_meta.get("tier", ""))
    if n == 0:
        return Grade("offerings", 0.0, swot_critical=True, reason="no offerings extracted")
    if tier == "messy":
        return Grade("offerings", 1.0, swot_critical=True, reason=f"{n} offering(s) on messy tier")
    if n >= 2:
        return Grade("offerings", 1.0, swot_critical=True, reason=f"{n} offerings")
    return Grade("offerings", 0.5, swot_critical=True, reason="only 1 offering on a typical-tier site")


def grade_pricing_visible(profile: Any, url_meta: dict) -> Grade:
    """1.0 if pricing was detected as visible, else 0.0. Not SWOT-critical."""
    val = _value_of(getattr(profile, "pricing_visible", None))
    if val is True:
        return Grade("pricing_visible", 1.0, reason="pricing visible")
    return Grade("pricing_visible", 0.0, reason="pricing not visible / unknown")


def grade_contact_phone(profile: Any, url_meta: dict) -> Grade:
    """1.0 if any phone channel exists — INCLUDING a short-code hotline (e164 may
    be None) — else 0.0. SWOT-critical."""
    cc = getattr(profile, "contact_channels", None)
    phones = getattr(cc, "phones", []) or [] if cc else []
    if phones:
        return Grade("contact_phone", 1.0, swot_critical=True, reason=f"{len(phones)} phone channel(s)")
    return Grade("contact_phone", 0.0, swot_critical=True, reason="no phone")


def grade_contact_email(profile: Any, url_meta: dict) -> Grade:
    """1.0 if any email exists, else 0.0. Not SWOT-critical."""
    cc = getattr(profile, "contact_channels", None)
    emails = getattr(cc, "emails", []) or [] if cc else []
    if emails:
        return Grade("contact_email", 1.0, reason=f"{len(emails)} email(s)")
    return Grade("contact_email", 0.0, reason="no email")


def grade_languages(profile: Any, url_meta: dict) -> Grade:
    """Fraction of expected languages we detected: full -> 1.0, some -> 0.5,
    none -> 0.0. UNGRADED (None) if the URL has no expected_languages. Not SWOT-critical."""
    expected = [str(l).lower()[:2] for l in (url_meta.get("expected_languages") or [])]
    if not expected:
        return Grade("languages", None, reason="no expected languages given")
    detected = {str(l).lower()[:2] for l in (getattr(profile, "languages", []) or [])}
    matched = sum(1 for e in expected if e in detected)
    ratio = matched / len(expected)
    score = 1.0 if ratio >= 0.999 else (0.5 if ratio > 0 else 0.0)
    return Grade("languages", score, reason=f"{matched}/{len(expected)} expected languages detected")


# Verticals where having zero physical locations is normal (no penalty).
_LOCATION_OPTIONAL = {"skincare", "ecommerce", "saas", "online", "beauty", "retail"}


def grade_locations_count(profile: Any, url_meta: dict) -> Grade:
    """Location coverage, vertical-aware. Online/skincare verticals: 0 is fine
    (1.0). Location-bound verticals (clinic, restaurant, ...): >=1 -> 1.0, 0 ->
    0.5 (lenient — many sites bury the address). Not SWOT-critical."""
    vertical = _norm(url_meta.get("vertical", ""))
    n = len(getattr(profile, "locations", []) or [])
    if vertical in _LOCATION_OPTIONAL:
        return Grade("locations", 1.0, reason=f"{vertical}: locations optional")
    if n >= 1:
        return Grade("locations", 1.0, reason=f"{n} location(s)")
    return Grade("locations", 0.5, reason=f"{vertical} expects a location; none found")


# ---------------------------------------------------------------------
# Fuzzy graders (need human ground truth; None ground truth -> UNGRADED)
# ---------------------------------------------------------------------

def grade_fuzzy_string(ev_field: Any, ground_truth: Optional[str], field_name: str) -> Grade:
    """Token-overlap score of an extracted string vs a ground-truth string.
    No ground truth -> score None (ungraded)."""
    if ground_truth is None:
        return Grade(field_name, None, reason="no ground truth")
    extracted = _norm(_value_of(ev_field))
    gt_tokens = _sig_tokens(ground_truth)
    if not gt_tokens:
        return Grade(field_name, None, reason="ground truth has no significant tokens")
    ext_tokens = set(_norm(extracted).split())
    matched = sum(1 for t in gt_tokens if t in ext_tokens)
    ratio = matched / len(gt_tokens)
    return Grade(field_name, _coverage_score(ratio),
                 reason=f"{matched}/{len(gt_tokens)} ground-truth tokens present")


def grade_fuzzy_enum(ev_field: Any, ground_truth: Optional[str], field_name: str) -> Grade:
    """Exact (normalized) enum-value match vs ground truth. None gt -> ungraded."""
    if ground_truth is None:
        return Grade(field_name, None, reason="no ground truth")
    extracted = _norm(_enum_str(_value_of(ev_field)))
    if not extracted:
        return Grade(field_name, 0.0, reason="nothing extracted")
    score = 1.0 if extracted == _norm(ground_truth) else 0.0
    return Grade(field_name, score, reason=f"{extracted!r} vs {ground_truth!r}")


def grade_fuzzy_list(ev_fields: Any, ground_truth: Optional[list], field_name: str) -> Grade:
    """Coverage of expected list items by extracted items (token overlap per
    item). full -> 1.0, >=25% -> 0.5, none -> 0.0. None gt -> ungraded."""
    if ground_truth is None:
        return Grade(field_name, None, reason="no ground truth")
    if not ground_truth:
        return Grade(field_name, None, reason="empty ground truth")
    extracted_token_sets = [
        set(_sig_tokens(_value_of(ef))) for ef in (ev_fields or [])
    ]
    covered = 0
    for expected in ground_truth:
        exp_tokens = _sig_tokens(expected)
        if not exp_tokens:
            continue
        for ext in extracted_token_sets:
            if ext and sum(1 for t in exp_tokens if t in ext) / len(exp_tokens) >= 0.6:
                covered += 1
                break
    ratio = covered / len(ground_truth)
    return Grade(field_name, _coverage_score(ratio),
                 reason=f"{covered}/{len(ground_truth)} expected items covered")


# ---------------------------------------------------------------------
# Full-profile grading
# ---------------------------------------------------------------------

# Fuzzy field plan: (grade_field_name, kind, profile_attribute, swot_critical)
_FUZZY_PLAN = [
    ("tagline", "string", "tagline", False),
    ("description", "string", "description", False),
    ("audience_type", "enum", "audience_type", True),
    ("tone_of_voice", "enum", "tone_of_voice", True),
    ("pricing_posture", "enum", "pricing_posture", False),
    ("value_propositions", "list", "value_propositions", True),
    ("trust_signals", "list", "trust_signals", False),
    ("service_areas", "list", "service_areas", False),
]


def grade_profile(profile: Any, url_meta: dict, ground_truth: dict) -> UrlGradeSet:
    """Grade every field: 8 structural + 8 fuzzy = 16 grades. The 7 SWOT-critical
    fields are tagged. `ground_truth` is a dict keyed by fuzzy field name; a
    missing key leaves that fuzzy field UNGRADED (score None)."""
    ground_truth = ground_truth or {}
    grades: List[Grade] = [
        grade_name(profile, url_meta),
        grade_category(profile, url_meta),
        grade_offerings(profile, url_meta),
        grade_pricing_visible(profile, url_meta),
        grade_contact_phone(profile, url_meta),
        grade_contact_email(profile, url_meta),
        grade_languages(profile, url_meta),
        grade_locations_count(profile, url_meta),
    ]

    for name, kind, attr, swot in _FUZZY_PLAN:
        gt = ground_truth.get(name)
        value = getattr(profile, attr, None)
        if kind == "string":
            g = grade_fuzzy_string(value, gt, name)
        elif kind == "enum":
            g = grade_fuzzy_enum(value, gt, name)
        else:  # list
            g = grade_fuzzy_list(value, gt, name)
        g.swot_critical = swot
        grades.append(g)

    url_id = url_meta.get("id", url_meta.get("brand", "unknown"))
    return UrlGradeSet(url_id=url_id, grades=grades)
