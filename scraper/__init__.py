"""Marketing scraper v0.1.

Public entry point:
    from scraper import scrape
    manifest, out_dir = scrape("https://example.com")

The heavy crawler import is intentionally lazy so modules such as
``scraper.schemas`` and ``scraper.url_utils`` can be imported in tests/API
validation without requiring Playwright/contact-extraction dependencies first.
"""

__all__ = ["scrape"]
__version__ = "0.1.0"


def scrape(*args, **kwargs):
    from .crawler import scrape as _scrape

    return _scrape(*args, **kwargs)
