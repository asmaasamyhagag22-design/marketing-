"""Business Profile Extractor v0.1.

Reads a scrape manifest, applies rule-based extractors first, then
calls the LLM only for fields that rules can't fill. Validates every
LLM-cited block_id exists in the manifest. Outputs business_profile.json
with full evidence chain.

Entry point:
    from business_profile import build_profile
    profile = build_profile("scrapes/example_com_.../manifest.json")
"""
from .schemas import BusinessProfile

__all__ = ["BusinessProfile"]
__version__ = "0.1.0"
