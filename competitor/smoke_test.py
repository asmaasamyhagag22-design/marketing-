"""Offline smoke test for the peer-match engine.

Runs the scoring + selection logic against hand-built candidates so you can
verify the LOGIC without an API key or network. It does NOT call Google.

    python -m competitor.smoke_test          # from your project root
    # or:  python smoke_test.py              # if run inside the package dir

Expected behaviour demonstrated below:
  - the off-vertical gym is filtered out (category_mismatch)
  - the 3-review clinic is filtered out (too_few_reviews; floor is 5)
  - the no-website clinic still PASSES (website is not required by default)
  - a 50x-bigger hospital chain scores LOW on size_similarity
  - the closest same-tier dermatology clinic ranks #1
  - select_peers returns ALL peers above the floor, ranked; the caller truncates
"""

from __future__ import annotations

try:  # support both `python -m competitor.smoke_test` and direct run
    from .models import Candidate, MatchCriteria
    from .peer_match import select_peers
except ImportError:  # pragma: no cover
    from models import Candidate, MatchCriteria  # type: ignore
    from peer_match import select_peers          # type: ignore


def fake_candidates():
    return [
        Candidate(place_id="A", name="Cairo Derma Skin Clinic", primary_type="dermatologist",
                  types=["dermatologist", "doctor"], distance_m=900, rating=4.6,
                  review_count=420, website="https://cairoderma.example",
                  business_status="OPERATIONAL", price_level="PRICE_LEVEL_MODERATE"),
        Candidate(place_id="B", name="Nile Aesthetic & Laser Center", primary_type="dermatologist",
                  types=["dermatologist", "spa"], distance_m=2300, rating=4.4,
                  review_count=610, website="https://nileaesthetic.example",
                  business_status="OPERATIONAL", price_level="PRICE_LEVEL_EXPENSIVE"),
        Candidate(place_id="C", name="Maadi Family Dermatology", primary_type="dermatologist",
                  types=["dermatologist", "doctor"], distance_m=5200, rating=4.7,
                  review_count=300, website="https://maadiderma.example",
                  business_status="OPERATIONAL", price_level="PRICE_LEVEL_MODERATE"),
        # giant chain -> low size_similarity
        Candidate(place_id="D", name="MegaHealth Hospital Group", primary_type="hospital",
                  types=["hospital", "doctor"], distance_m=4000, rating=4.0,
                  review_count=21000, website="https://megahealth.example",
                  business_status="OPERATIONAL", price_level="PRICE_LEVEL_EXPENSIVE"),
        # filtered: wrong vertical
        Candidate(place_id="E", name="PowerFit Gym", primary_type="gym",
                  types=["gym"], distance_m=600, rating=4.8, review_count=900,
                  website="https://powerfit.example", business_status="OPERATIONAL"),
        # filtered: too few reviews (floor is 5)
        Candidate(place_id="F", name="New Derma Spot", primary_type="dermatologist",
                  types=["dermatologist"], distance_m=700, rating=5.0, review_count=3,
                  website="https://newderma.example", business_status="OPERATIONAL"),
        # passes now (website is NOT required by default) — kept to show that
        Candidate(place_id="G", name="Heliopolis Skin Care", primary_type="dermatologist",
                  types=["dermatologist"], distance_m=1500, rating=4.5, review_count=180,
                  website=None, business_status="OPERATIONAL",
                  price_level="PRICE_LEVEL_MODERATE"),
    ]


def main():
    crit = MatchCriteria(
        category="clinic",
        place_types=["dermatologist", "doctor", "medical_clinic"],
        offering_keywords=["derma", "skin", "laser", "dermatology"],
        audience_tier="mid",
        audience_confidence=0.8,
        languages=["ar", "en"],
        lat=30.0444, lng=31.2357,
        review_count_self=350,
    )

    ranked, stats = select_peers(fake_candidates(), crit)
    selected = ranked[:4]

    print("stats:", stats)
    print()
    for rank, (cand, rec) in enumerate(selected, 1):
        bd = rec.breakdown
        print(f"#{rank}  {cand.name}")
        print(f"     score={rec.peer_fit_score}")
        print(f"     why  ={rec.why_selected}")
        print(f"     dims =subvert:{bd.sub_vertical} prox:{bd.proximity} "
              f"size:{bd.size_similarity} tier:{bd.audience_tier} lang:{bd.language}")
        print(f"     wts  ={bd.weights_used}")
        print()

    if len(selected) < 4:
        print(f"THIN PEER SET: only {len(selected)} cleared the floor "
              f"(would NOT pad with sub-floor candidates).")


if __name__ == "__main__":
    main()