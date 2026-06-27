"""Brand-research deep-search step: sourced facts + grounded ad angles, no network.

Pins the 2026-06-16 feature that runs a web search before poster generation so the
copy is fresh+sourced instead of one verbatim line — WITHOUT eroding zero-hallucination
(every fact keeps a source URL; unsourced hard-claim angles are dropped).
"""
from __future__ import annotations

from dataclasses import dataclass

from poster.brand_research import (
    research_brand, pick_angle, BrandResearch, BrandAngle,
    _ResearchResponse, _Fact, _Angle,
)
from business_profile.llm.caller import MockCaller


@dataclass
class _Hit:
    title: str
    link: str
    snippet: str
    rank: int = 0


class _FakeProvider:
    name = "fake"

    def __init__(self, hits):
        self._hits = hits
        self.queries: list[str] = []

    def search(self, query, num=10):
        self.queries.append(query)
        return list(self._hits)


_HITS = [
    _Hit("Digilians — Presidential Initiative", "https://news.example/digilians",
         "Digilians is a presidential initiative to qualify Egyptian youth in ICT.", 1),
    _Hit("Digilians programs", "https://digilians.example/about",
         "Offers nanodegrees and specialized diplomas in tech.", 2),
]


def test_no_provider_returns_unused(monkeypatch):
    # Force the "no provider configured" path deterministically — do NOT rely on the
    # environment (a real SERPER_API_KEY would resolve a live provider and hit the
    # network). Same isolation gotcha noted in CLAUDE.md for web-discovery.
    import competitor.search_providers as sp
    monkeypatch.setattr(sp, "get_default_search_provider", lambda: None)
    r = research_brand("Digilians", provider=None, caller=None)
    assert isinstance(r, BrandResearch)
    assert r.used is False


def test_provider_no_caller_returns_raw_sourced_facts():
    prov = _FakeProvider(_HITS)
    r = research_brand("Digilians", provider=prov, caller=None)
    assert r.used is True and r.provider == "fake"
    assert r.facts and all(f.source_url.startswith("http") for f in r.facts)
    assert r.angles == []                      # no caller -> no crafted copy


def test_no_results_is_honest():
    r = research_brand("Digilians", provider=_FakeProvider([]), caller=None)
    assert r.used is True and r.facts == [] and "no results" in (r.note or "")


def test_caller_facts_and_angles_mapped_and_grounded():
    prov = _FakeProvider(_HITS)
    resp = _ResearchResponse(
        facts=[_Fact(text="A presidential initiative for youth ICT skills.",
                     source_url="https://news.example/digilians")],
        angles=[
            _Angle(headline="مبادرة رئاسية لتأهيل الشباب رقميًا", subheadline="",
                   grounded_in="https://news.example/digilians", asserts_hard_fact=True),
            _Angle(headline="ابدأ مستقبلك الرقمي", subheadline="نانوديجري ودبلومات متخصصة",
                   grounded_in="profile", asserts_hard_fact=False),
            # a hard claim with a BOGUS (non-URL, unknown) source -> downgraded to 'profile'
            _Angle(headline="الأول على مستوى الجمهورية", subheadline="",
                   grounded_in="made-up", asserts_hard_fact=True),
        ],
    )
    r = research_brand("Digilians", provider=prov, caller=MockCaller({"brand_research": resp}))
    assert r.used is True and len(r.angles) == 3
    # the unknown source was downgraded so we never imply a citation we can't back
    bogus = [a for a in r.angles if a.headline == "الأول على مستوى الجمهورية"][0]
    assert bogus.grounded_in == "profile"


def test_trend_context_reaches_the_copywriter_prompt():
    # The --trend wiring feeds current, on-topic trends to the copy LLM so it can tie an
    # angle to a live moment (the model decides; here we only verify the data flows in).
    prov = _FakeProvider(_HITS)
    mock = MockCaller({"brand_research": _ResearchResponse(facts=[], angles=[])})
    research_brand("Digilians", provider=prov, caller=mock,
                   trend_context="- AI upskilling boom across Egypt")
    assert "AI upskilling boom across Egypt" in mock.calls[0].user_prompt


def test_pick_angle_prefers_safe_and_is_deterministic():
    research = BrandResearch(used=True, angles=[
        BrandAngle(headline="HARD unsourced", grounded_in="profile", asserts_hard_fact=True),
        BrandAngle(headline="Safe evocative", grounded_in="profile", asserts_hard_fact=False),
        BrandAngle(headline="HARD sourced", grounded_in="https://x/y", asserts_hard_fact=True),
    ])
    # prefer_safe drops the unsourced hard claim; sourced-hard + evocative remain.
    picked = {pick_angle(research, "FB", variation=i)[0] for i in range(6)}
    assert "HARD unsourced" not in picked
    assert picked <= {"Safe evocative", "HARD sourced"}


def test_pick_angle_falls_back_to_verbatim_when_empty():
    head, sub, prov = pick_angle(BrandResearch(used=False, angles=[]), "Verbatim line")
    assert head == "Verbatim line" and prov == "profile"


def test_hallucinated_http_source_is_downgraded_and_not_surfaced():
    # A model-INVENTED http URL the search never returned must NOT count as a citation
    # (it gets downgraded to 'profile'), and the resulting unsourced hard claim must not
    # be surfaced as the headline — it falls back to the verbatim line.
    prov = _FakeProvider(_HITS)
    resp = _ResearchResponse(facts=[], angles=[
        _Angle(headline="Egypt's #1 Rated ICT Academy", subheadline="",
               grounded_in="https://invented.example/best-2026", asserts_hard_fact=True),
    ])
    r = research_brand("Digilians", provider=prov, caller=MockCaller({"brand_research": resp}))
    assert r.angles[0].grounded_in == "profile"        # invented URL -> downgraded
    head, _sub, prov_ = pick_angle(r, "Verbatim fallback", prefer_safe=True)
    assert head == "Verbatim fallback" and prov_ == "profile"   # unsourced hard claim NOT surfaced
