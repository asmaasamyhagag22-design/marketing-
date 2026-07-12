"""U9 social_intel — fixtures-first skeleton (owner governance 2026-07-11).

Tier ruling: Apify/Facebook = Tier-2 (enters ONLY after §10 financial sign-off, as
providers/apify_facebook.py behind the Protocol); direct IG scraper = Tier-4 REJECTED
(salvage: its parser becomes providers/snapshot_parser.py, Tier-3 human-saved HTML);
automated IG = Tier-1 Business Discovery API (Meta app review in progress). U9 stays
LAST in the build queue; this week = schema + protocol + fixtures + hermetic tests only.
NOTE: the SocialSignal shape below is designed from the v2.2 plan; it gets validated
against the owner's raw JSON samples (one per team source) when she provides them.
"""
from .schemas import SocialSignal
from .providers.base import SocialProvider
from .providers.fixture import FixtureSocialProvider

__all__ = ["SocialSignal", "SocialProvider", "FixtureSocialProvider"]
