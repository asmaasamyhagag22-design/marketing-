"""Fetch resource routing (render-speed + polite footprint, Pillar 1), hermetic.

LIGHT sub-page router (`_block_heavy_route`) aborts heavy NON-essential resources
(image/media/font) so light fetches render fast, while letting documents/scripts/XHR/CSS
through so JS-injected content is preserved. BOTH routers also drop third-party
analytics/ads/telemetry beacons (`_is_tracking_request`) — pure noise that inflates our
request footprint and helps trip a site's per-IP rate limit (the measured HTTP-429 cause).
The FULL homepage router (`_block_tracking_route`) drops ONLY trackers, so first-party
images/CSS/fonts still load for the screenshot.
"""
from __future__ import annotations

from scraper.fetcher import (
    _block_heavy_route, _block_tracking_route, _is_tracking_request,
)


class _FakeRequest:
    def __init__(self, resource_type, url="https://brand.example/asset"):
        self.resource_type = resource_type
        self.url = url


class _FakeRoute:
    def __init__(self, resource_type, url="https://brand.example/asset"):
        self.request = _FakeRequest(resource_type, url)
        self.aborted = False
        self.continued = False

    def abort(self):
        self.aborted = True

    def continue_(self):
        self.continued = True


# ---- LIGHT router -------------------------------------------------------------
def test_light_aborts_heavy_resources():
    for rt in ("image", "media", "font"):
        r = _FakeRoute(rt)
        _block_heavy_route(r)
        assert r.aborted and not r.continued, rt


def test_light_continues_essential_first_party():
    # documents / scripts / XHR / fetch / stylesheets must still load (JS content depends on them)
    for rt in ("document", "script", "xhr", "fetch", "stylesheet", "websocket", "other"):
        r = _FakeRoute(rt, url="https://brand.example/app.js")
        _block_heavy_route(r)
        assert r.continued and not r.aborted, rt


# ---- tracker detection --------------------------------------------------------
def test_is_tracking_matches_known_beacons_not_content():
    trackers = [
        "https://www.googletagmanager.com/gtm.js?id=GTM-X",
        "https://analytics.tiktok.com/i18n/pixel/events.js",
        "https://connect.facebook.net/en_US/fbevents.js",
        "https://ad.doubleclick.net/ddm/x",
        "https://www.googleadservices.com/pagead/conversion.js",
        "https://monorail-edge.shopifysvc.com/v1/produce",
        "https://app.converted.in/pixel",
    ]
    for u in trackers:
        assert _is_tracking_request(u), u
    # first-party content + the site's own product CDN must NEVER match
    for u in ("https://brand.example/products/shoe",
              "https://cdn.shopify.com/s/files/1/x/shoe.jpg",
              "https://judgeme-public-images.imgix.net/r.jpg",
              "https://fonts.gstatic.com/s/font.woff2"):
        assert not _is_tracking_request(u), u


# ---- tracker blocking in BOTH routers ----------------------------------------
def test_both_routers_block_trackers():
    for handler in (_block_heavy_route, _block_tracking_route):
        r = _FakeRoute("script", url="https://www.googletagmanager.com/gtm.js")
        handler(r)
        assert r.aborted and not r.continued, handler.__name__


def test_full_router_keeps_first_party_images():
    # the homepage screenshot + product-image URLs depend on first-party images loading
    for url in ("https://brand.example/hero.jpg",
                "https://cdn.shopify.com/s/files/1/x/product.jpg"):
        r = _FakeRoute("image", url=url)
        _block_tracking_route(r)
        assert r.continued and not r.aborted, url
