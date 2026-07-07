"""Competitor discovery for the marketing pipeline.

Public entry point:
    from competitor import discover_competitors, PlacesClient

    client = PlacesClient()                      # reads GOOGLE_MAPS_API_KEY from env
    result = discover_competitors(profile, client)
    for c in result.competitors:
        print(c.selection.why_selected, "->", len(c.reviews), "reviews")
"""

from .models import (
    Candidate,
    CompetitorProfile,
    MatchCriteria,
    PeerFitBreakdown,
    PeerMatchResult,
    Review,
    SelectionRecord,
)
from .peer_match import select_peers, score_candidate, passes_hard_filters
from .places_client import PlacesClient, PlacesError
from .discovery import (
    discover_competitors, build_match_criteria, CATEGORY_TYPE_MAP, find_subject_places,
)
from .matrix import (
    build_matrix, ComparativeGapMatrix, DIMENSIONS,
    extract_scraped_dimensions, dimensions_from_manifest,
)
from .swot import synthesize_swot, SWOT, SWOTItem, ReviewTheme, format_swot
from .tows import build_tows, TowsResult, TowsStrategy, PriorityAction
from .themes import ReviewThemeExtractor, extract_review_themes
from .business_type import classify_business_type, BusinessType, BusinessTypeResult
from .router import route_discovery, WebDiscoveryEngine, NullWebDiscoveryEngine

__all__ = [
    "discover_competitors",
    "find_subject_places",
    "route_discovery",
    "WebDiscoveryEngine",
    "NullWebDiscoveryEngine",
    "classify_business_type",
    "BusinessType",
    "BusinessTypeResult",
    "build_match_criteria",
    "CATEGORY_TYPE_MAP",
    "PlacesClient",
    "PlacesError",
    "select_peers",
    "score_candidate",
    "passes_hard_filters",
    "build_matrix",
    "ComparativeGapMatrix",
    "DIMENSIONS",
    "extract_scraped_dimensions",
    "dimensions_from_manifest",
    "synthesize_swot",
    "SWOT",
    "SWOTItem",
    "ReviewTheme",
    "format_swot",
    "build_tows",
    "TowsResult",
    "TowsStrategy",
    "PriorityAction",
    "ReviewThemeExtractor",
    "extract_review_themes",
    "Candidate",
    "CompetitorProfile",
    "MatchCriteria",
    "PeerFitBreakdown",
    "PeerMatchResult",
    "Review",
    "SelectionRecord",
]