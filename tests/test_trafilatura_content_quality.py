"""Tests for scraper.extractors.content_quality (PR-3).

Confirms:
- Rich content pages return cleaned text + has_meaningful_content=True
- Nav/cookie-only pages return some text but has_meaningful_content=False
- Empty / whitespace input returns (None, False)
- Malformed HTML returns (None, False) or near-empty text with False
- Missing trafilatura degrades to (None, False) without crashing
- Density thresholds (length + word count + avg word length) all fire
"""
from __future__ import annotations

import sys
import types
from unittest.mock import patch

_fake = types.ModuleType("playwright")
_fake_sync = types.ModuleType("playwright.sync_api")
class _Stub: ...
for _n in ("Browser", "BrowserContext", "Page", "sync_playwright"):
    setattr(_fake_sync, _n, _Stub)
_fake_sync.TimeoutError = type("TimeoutError", (Exception,), {})
_fake_sync.Error = type("Error", (Exception,), {})
sys.modules.setdefault("playwright", _fake)
sys.modules.setdefault("playwright.sync_api", _fake_sync)

from scraper.extractors.content_quality import extract_content_quality  # noqa: E402


# ---------------------------------------------------------------------
# Rich content → meaningful
# ---------------------------------------------------------------------

def test_rich_article_page_is_meaningful():
    html = """
    <html><body>
      <nav><a>Home</a><a>About</a><a>Menu</a></nav>
      <main>
        <article>
          <h2>About Andrea</h2>
          <p>Andrea is a landmark restaurant in Cairo, serving authentic Egyptian
          dishes since 1976. We pride ourselves on heritage recipes and family
          atmosphere passed down through three generations.</p>
          <p>Our most popular dishes include grilled chicken, mezze platters,
          and traditional family feasts.</p>
        </article>
      </main>
      <footer>Copyright 2024</footer>
    </body></html>
    """
    text, meaningful = extract_content_quality(html, "https://andrea.example/about")
    assert meaningful is True
    assert text is not None
    assert "Egyptian" in text or "Andrea" in text or "heritage" in text
    # Boilerplate from footer should not dominate the cleaned text
    assert "Copyright 2024" not in text or "heritage" in text


# ---------------------------------------------------------------------
# Nav / cookie-only → not meaningful
# ---------------------------------------------------------------------

def test_nav_only_page_is_not_meaningful():
    html = """
    <html><body>
      <nav><a>Home</a><a>Menu</a><a>Contact</a></nav>
      <div class="cookie-banner">Accept cookies</div>
      <footer>Copyright 2024</footer>
    </body></html>
    """
    text, meaningful = extract_content_quality(html, "https://x.example/")
    assert meaningful is False
    # text may or may not be None depending on trafilatura's heuristic;
    # both are acceptable as long as meaningful=False


def test_cookie_banner_only_is_not_meaningful():
    html = """
    <html><body>
      <div>We use cookies. Accept All. Reject All.</div>
    </body></html>
    """
    _, meaningful = extract_content_quality(html, "https://x.example/")
    assert meaningful is False


def test_very_short_content_is_not_meaningful():
    """Even a clean paragraph that's below the char threshold doesn't qualify."""
    html = "<html><body><main><p>We are open.</p></main></body></html>"
    _, meaningful = extract_content_quality(html, "https://x.example/")
    assert meaningful is False


# ---------------------------------------------------------------------
# Graceful degradation
# ---------------------------------------------------------------------

def test_empty_html_returns_none_false():
    assert extract_content_quality("", "https://x.example/") == (None, False)
    assert extract_content_quality("   ", "https://x.example/") == (None, False)


def test_malformed_html_does_not_crash():
    text, meaningful = extract_content_quality("<<<broken html>>>", "https://x.example/")
    # Whatever trafilatura does with broken input, we must not crash.
    # The meaningful flag should be False because broken input doesn't
    # carry real content.
    assert meaningful is False


def test_returns_none_false_when_trafilatura_missing():
    """If trafilatura isn't installed, degrade gracefully."""
    original_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

    def fake_import(name, *args, **kwargs):
        if name == "trafilatura":
            raise ImportError("simulated missing trafilatura")
        return original_import(name, *args, **kwargs)

    html = """
    <html><body><main><article><p>This is a rich article body with enough
    words to easily pass the density threshold when trafilatura is
    actually present. Lorem ipsum dolor sit amet consectetur adipiscing
    elit sed do eiusmod tempor incididunt ut labore.</p></article></main></body></html>
    """
    with patch("builtins.__import__", side_effect=fake_import):
        result = extract_content_quality(html, "https://x.example/")
    assert result == (None, False)


# ---------------------------------------------------------------------
# Density thresholds
# ---------------------------------------------------------------------

def test_one_letter_link_explosion_is_not_meaningful():
    """A page that's just single-letter menu items: avg word length too low."""
    # Pad to over the char threshold but keep avg word length small
    html = "<html><body><main>" + " ".join(["a"] * 50) + "</main></body></html>"
    _, meaningful = extract_content_quality(html, "https://x.example/")
    assert meaningful is False