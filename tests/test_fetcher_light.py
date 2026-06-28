"""Light sub-page fetch — resource-blocking handler (render-speed, Pillar 1), hermetic.

`_block_heavy_route` aborts heavy NON-essential resources (image/media/font) so light sub-page
fetches render faster, while letting documents/scripts/XHR/CSS through so JS-injected content
(products, links, lazy text) is preserved.
"""
from __future__ import annotations

from scraper.fetcher import _block_heavy_route


class _FakeRequest:
    def __init__(self, resource_type):
        self.resource_type = resource_type


class _FakeRoute:
    def __init__(self, resource_type):
        self.request = _FakeRequest(resource_type)
        self.aborted = False
        self.continued = False

    def abort(self):
        self.aborted = True

    def continue_(self):
        self.continued = True


def test_aborts_heavy_resources():
    for rt in ("image", "media", "font"):
        r = _FakeRoute(rt)
        _block_heavy_route(r)
        assert r.aborted and not r.continued, rt


def test_continues_essential_resources():
    # documents / scripts / XHR / fetch / stylesheets must still load (JS content depends on them)
    for rt in ("document", "script", "xhr", "fetch", "stylesheet", "websocket", "other"):
        r = _FakeRoute(rt)
        _block_heavy_route(r)
        assert r.continued and not r.aborted, rt
