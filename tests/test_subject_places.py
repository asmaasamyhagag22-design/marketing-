"""find_subject_places — the subject's OWN Places listing (fills the Threats quadrant).

Hermetic (fake client, no network). The matching is deliberately conservative:
domain match first (the subject's own site — never wrong), exact normalized name
second, and NOTHING fuzzier — grounding the SWOT in someone else's ratings would
be worse than UNKNOWN (rule 4).
"""
from __future__ import annotations

from competitor.discovery import find_subject_places
from competitor.models import Candidate


class _FakeClient:
    def __init__(self, candidates, raise_on_search=False):
        self._candidates = candidates
        self._raise = raise_on_search
        self.queries = []

    def search_text(self, query, **kwargs):
        if self._raise:
            raise RuntimeError("places down")
        self.queries.append(query)
        return list(self._candidates)


def _cand(name, website=None, rating=4.2, reviews=120):
    return Candidate(place_id=f"pid_{name}", name=name, website=website,
                     rating=rating, review_count=reviews)


_PROFILE = {
    "name": {"value": "Qasr Elkbabgi"},
    "physical_address": {"value": "Cairo, Egypt"},
    "source_url": "https://elkbabgi.com/",
}


def test_matches_by_own_website_domain_first():
    right = _cand("Elkbabgi Restaurant", website="https://www.elkbabgi.com/menu")
    decoy = _cand("Qasr Elkbabgi", website="https://someone-else.com")  # same name, wrong site
    client = _FakeClient([decoy, right])

    got = find_subject_places(_PROFILE, client)
    assert got is right, "the domain match (the subject's OWN site) must win over a name match"
    # The query included the name (+ address when present).
    assert client.queries and "Qasr Elkbabgi" in client.queries[0]


def test_matches_by_exact_normalized_name_when_no_domain():
    match = _cand("qasr elkbabgi", website=None)
    other = _cand("Kebab Palace", website=None)
    profile = {**_PROFILE, "source_url": None}
    got = find_subject_places(profile, _FakeClient([other, match]))
    assert got is match


def test_no_grounded_match_returns_none_never_fuzzy():
    near_miss = _cand("Qasr Elkbabgi Downtown Branch 2", website="https://unrelated.example")
    assert find_subject_places(_PROFILE, _FakeClient([near_miss])) is None


def test_never_raises_and_handles_missing_inputs():
    assert find_subject_places(_PROFILE, None) is None
    assert find_subject_places(None, _FakeClient([])) is None
    assert find_subject_places({"name": None}, _FakeClient([])) is None
    assert find_subject_places(_PROFILE, _FakeClient([], raise_on_search=True)) is None


# --- _is_self: never list the subject (even a different-script branch) as its own competitor ---
from competitor.discovery import _is_self  # noqa: E402

# Real measured case: profile name is ENGLISH, source_url is iti.gov.eg, but the Places listing
# for the same brand is ARABIC with no website — the exact-name and domain checks both miss it.
_ITI = {"name": {"value": "Information Technology Institute"}, "source_url": "https://iti.gov.eg/"}


def test_is_self_drops_a_cross_script_branch_of_the_same_brand():
    self_branch = _cand("معهد تكنولوجيا المعلومات - ITI", website=None)   # brand acronym, other script
    assert _is_self(self_branch, _ITI) is True


def test_is_self_keeps_a_real_competitor_without_the_brand_token():
    faculty = _cand("كلية التربية جامعة عين شمس", website=None)           # unrelated peer -> kept
    assert _is_self(faculty, _ITI) is False


def test_is_self_still_matches_by_domain_and_exact_name():
    by_domain = _cand("ITI Training", website="https://iti.gov.eg/courses")
    assert _is_self(by_domain, _ITI) is True
    by_name = _cand("information technology institute", website=None)
    assert _is_self(by_name, _ITI) is True


def test_is_self_brand_label_ignores_generic_hosts():
    # A generic domain label ('store') must NOT drop a peer that merely has 'store' in its name.
    generic = {"name": {"value": "Acme"}, "source_url": "https://store.com/"}
    peer = _cand("Downtown Store", website=None)
    assert _is_self(peer, generic) is False
