"""URL normalization and helpers.

Goal: two URLs that point to the same logical page produce the same
normalized form, so the crawler doesn't visit /about, /about/,
/about?utm_source=x and /about#team as four different pages.
"""
from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode, urljoin

from .config import TRACKING_PARAMS


_ABSOLUTE_URL_RE = re.compile(r"https?://", re.IGNORECASE)


def is_malformed_concatenated_url(url: str) -> bool:
    """Detect inputs like https://a.com/https://b.com/.

    Pydantic's HttpUrl can treat the second absolute URL as part of the path,
    but for this product it is almost always accidental pasted/concatenated
    input. We reject it instead of silently scraping the wrong site.
    """
    raw = (url or "").strip()
    matches = list(_ABSOLUTE_URL_RE.finditer(raw))
    return len(matches) > 1


def validate_input_url(url: str) -> str:
    url = (url or "").strip()
    if is_malformed_concatenated_url(url):
        raise ValueError(
            "Malformed URL: multiple absolute URLs detected. Provide one clean business URL only."
        )
    return url


def ensure_scheme(url: str) -> str:
    """Add https:// if no scheme is provided."""
    url = validate_input_url(url)
    if not url:
        return url
    if not url.startswith(("http://", "https://")):
        return "https://" + url
    return url


def is_safe_public_url(url: str) -> bool:
    """SSRF guard: True only for an http(s) URL whose host resolves ENTIRELY to
    public IPs.

    Blocks non-http(s) schemes and any host that resolves to a loopback /
    private / link-local (incl. the cloud-metadata endpoint 169.254.169.254) /
    reserved / multicast / unspecified address. Use before the server makes an
    outbound request to a user-supplied URL.

    Limitation (documented, not over-claimed): this resolves DNS at check time,
    so it does not fully close the TOCTOU / DNS-rebinding window — that needs
    pinning the resolved IP at fetch time. It is a strong baseline that stops the
    common SSRF targets (localhost, internal ranges, cloud metadata).
    """
    try:
        parts = urlparse(url if "://" in (url or "") else "https://" + (url or ""))
    except Exception:
        return False
    if parts.scheme not in ("http", "https"):
        return False
    host = parts.hostname
    if not host:
        return False
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except Exception:
        return False
    if not infos:
        return False
    for info in infos:
        ip = info[4][0]
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return False
        if (
            addr.is_private or addr.is_loopback or addr.is_link_local
            or addr.is_reserved or addr.is_multicast or addr.is_unspecified
        ):
            return False
    return True


def normalize_url(url: str) -> str:
    """Normalize a URL for deduplication.

    Steps:
    - lowercase the scheme and host
    - strip fragment
    - drop tracking query params (utm_*, fbclid, gclid, ...)
    - sort remaining query params for deterministic order
    - remove default ports (:80 / :443)
    - collapse a trailing slash on the root path; preserve elsewhere
    """
    url = ensure_scheme(url)
    parts = urlparse(url)

    scheme = parts.scheme.lower()
    netloc = parts.netloc.lower()

    # Strip default ports
    if scheme == "http" and netloc.endswith(":80"):
        netloc = netloc[:-3]
    elif scheme == "https" and netloc.endswith(":443"):
        netloc = netloc[:-4]

    # Filter query params
    kept = [
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=False)
        if k.lower() not in TRACKING_PARAMS
    ]
    kept.sort()
    query = urlencode(kept)

    # Path: ensure leading slash; only modify trailing slash on root
    path = parts.path or "/"

    return urlunparse((scheme, netloc, path, parts.params, query, ""))


def same_registrable_host(a: str, b: str) -> bool:
    """Return True if two URLs point to the same site.

    Treats `example.com` and `www.example.com` as the same host.
    This is good enough for our purposes; a full PSL-based check
    is overkill for v0.1.
    """
    ha = urlparse(ensure_scheme(a)).netloc.lower().removeprefix("www.")
    hb = urlparse(ensure_scheme(b)).netloc.lower().removeprefix("www.")
    return ha == hb and ha != ""


def get_host(url: str) -> str:
    return urlparse(ensure_scheme(url)).netloc.lower()


def get_domain_slug(url: str) -> str:
    """Make a filesystem-safe slug from a host: 'www.example.com' -> 'example_com'."""
    host = get_host(url).removeprefix("www.")
    return host.replace(".", "_").replace(":", "_")


def resolve(base_url: str, href: str) -> str:
    """Resolve a possibly-relative href against base_url."""
    return urljoin(base_url, href)


def is_http_url(url: str) -> bool:
    p = urlparse(url)
    return p.scheme in ("http", "https") and bool(p.netloc)
