"""Test that extruct is an optional dependency.

If extruct isn't installed (e.g. partial install, or someone running
the scraper without the new requirement pinned), the scraper must
still work. It just loses the Microdata/RDFa signal — JSON-LD
extraction is unaffected.
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


def test_structured_data_returns_empty_when_extruct_missing():
    """Simulate extruct ImportError. extract_structured_data must
    return [] rather than crash."""
    from scraper.extractors import structured_data

    # Replace the function's import of extruct with one that raises
    original_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

    def fake_import(name, *args, **kwargs):
        if name == "extruct":
            raise ImportError("simulated missing extruct")
        return original_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import):
        out = structured_data.extract_structured_data(
            "<div itemscope itemtype='https://schema.org/Restaurant'><span itemprop='name'>X</span></div>",
            "https://x.example/",
        )
    assert out == []


def test_metadata_still_extracts_jsonld_when_extruct_missing():
    """Even without extruct, JSON-LD extraction in metadata.py must work.
    The extruct call is guarded; only the Microdata/RDFa signal is lost.
    """
    from scraper.extractors import metadata as md

    original_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

    def fake_import(name, *args, **kwargs):
        if name == "extruct":
            raise ImportError("simulated missing extruct")
        return original_import(name, *args, **kwargs)

    html = """
    <html><head>
      <script type="application/ld+json">
        {"@context":"https://schema.org","@type":"Restaurant","name":"Andrea"}
      </script>
    </head><body>
      <div itemscope itemtype="https://schema.org/Restaurant">
        <h1 itemprop="name">Andrea</h1>
      </div>
    </body></html>
    """
    with patch("builtins.__import__", side_effect=fake_import):
        result = md.extract_metadata(html, "https://x.example/")

    # JSON-LD block must still be present
    json_ld_blocks = [b for b in result.schema_org if b.source == "json_ld"]
    assert len(json_ld_blocks) == 1
    assert json_ld_blocks[0].data["name"] == "Andrea"

    # Microdata block lost (extruct unavailable) — but no crash
    microdata_blocks = [b for b in result.schema_org if b.source == "microdata"]
    assert microdata_blocks == []