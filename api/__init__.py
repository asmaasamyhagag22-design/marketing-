"""FastAPI HTTP wrapper for the business-profile pipeline.

Thin adapter — does not contain pipeline logic. All pipeline work
happens inside `scraper/` and `business_profile/`; this module
exposes them over HTTP with streaming progress events.

Entry point:
    uvicorn api.main:app --reload --port 8000
"""

__version__ = "0.1.0"
