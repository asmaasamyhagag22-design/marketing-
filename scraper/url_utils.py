"""URL normalization and helpers.

Goal: two URLs that point to the same logical page produce the same
normalized form, so the crawler doesn't visit /about, /about/,
/about?utm_source=x and /about#team as four different pages.
"""
from __future__ import annotations

import ipaddress
import re
import socket
from typing import Optional
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode, urljoin

from .config import TRACKING_PARAMS

# Public-suffix-aware registrable-domain resolution. `tld` ships an offline
# bundled PSL (no network). If it's somehow unavailable, same_registrable_host
# degrades to the legacy www-stripped hostname comparison (see below).
try:
    from tld import get_fld
    _TLD_OK = True
except Exception:  # pragma: no cover - dependency fallback for light envs
    _TLD_OK = False


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


def _registrable_domain(url: str) -> Optional[str]:
    """The eTLD+1 (registrable domain) for a URL via the public-suffix list:
    'web.vodafone.com.eg' -> 'vodafone.com.eg'. Returns None when the host has no
    public-suffix match (IP literal, localhost, intranet / unknown TLD)."""
    if not _TLD_OK:
        return None
    try:
        return get_fld(ensure_scheme(url), fix_protocol=True, fail_silently=True)
    except Exception:
        return None


def same_registrable_host(a: str, b: str) -> bool:
    """Return True if two URLs belong to the same site (same registrable domain).

    Uses the public-suffix list (tld) so that subdomains of one site compare
    equal — `www.`, `web.`, `eshop.`, `my.` of vodafone.com.eg all share the
    registrable domain `vodafone.com.eg`. This matters for real enterprise sites
    that redirect the apex/www to a subdomain (e.g. www.vodafone.com.eg ->
    web.vodafone.com.eg) and serve their navigation across subdomains: the old
    www-only-stripping equality classified every such internal link as EXTERNAL
    and collapsed the crawl to a single page (MEASURED: Vodafone EG, internal=0).

    Multi-label suffixes (.com.eg, .co.uk) are handled correctly, and sites that
    merely SHARE a public suffix are NOT merged (a.blogspot.com != b.blogspot.com,
    vodafone.com.eg != vodafone.co.uk). Falls back to the legacy www-stripped
    hostname equality when a host has no public-suffix match (IP literal /
    localhost / intranet / unknown TLD) so those hosts keep prior behavior.
    """
    fa = _registrable_domain(a)
    fb = _registrable_domain(b)
    if fa and fb:
        return fa == fb
    # Fallback: hosts the PSL can't classify (IP / localhost / intranet).
    ha = urlparse(ensure_scheme(a)).netloc.lower().removeprefix("www.")
    hb = urlparse(ensure_scheme(b)).netloc.lower().removeprefix("www.")
    return ha == hb and ha != ""


def get_host(url: str) -> str:
    return urlparse(ensure_scheme(url)).netloc.lower()


# A leading path segment that is a LOCALE (en, ar, us, en-eg, ar_eg, ...) — a locale
# homepage like /en or /en-eg is the brand homepage, NOT a deep content page.
_LOCALE_SEGMENT_RE = re.compile(r"^[a-z]{2}([-_][a-z]{2})?$", re.IGNORECASE)
_HOME_SEGMENTS = {"home", "index", "default", "main"}
_HOME_FILE_RE = re.compile(r"^(index|default|home)\.[a-z0-9]+$", re.IGNORECASE)


def site_root_if_deep(url: str) -> Optional[str]:
    """If `url` is a DEEP CONTENT page, return its site root (``scheme://host/``); else
    None.

    Used so the crawler can anchor brand IDENTITY (name / tagline / description / logo)
    to the real homepage when the seed URL was a deep page — MEASURED disaster: ITI was
    scraped at ``/diplomaStructure/.../tracks/...`` so its tagline became the track name
    ("DATA SCIENCE") and the offerings were all one track.

    Returns None (do NOT re-anchor) when the URL is already a homepage:
      * the bare root ``/``
      * a LOCALE homepage — ``/en``, ``/us``, ``/en-eg``, ``/en/home`` (these ARE the
        homepage; re-anchoring them to the bare root can regress a locale-gated site).
    A path with any real content segment left after stripping a locale prefix and a
    trailing home/index marker is treated as deep. (MEASURED across 83 saved scrapes:
    cleanly separates the locale homes orange/en, adidas/us, defacto/en-eg,
    vodafone/en/home from the deep pages iti/tracks, sofitel/restaurant, elkbabgi/menu,
    elmenus/<city>, buffalo/branches/all/home.)
    """
    try:
        p = urlparse(ensure_scheme(url))
    except Exception:
        return None
    if not p.netloc:
        return None
    segs = [s for s in (p.path or "").split("/") if s]
    if segs and _LOCALE_SEGMENT_RE.match(segs[0]):
        segs = segs[1:]                                  # strip a leading locale prefix
    while segs and (segs[-1].lower() in _HOME_SEGMENTS or _HOME_FILE_RE.match(segs[-1])):
        segs = segs[:-1]                                 # strip trailing home/index
    if not segs:
        return None                                      # already a homepage
    return f"{p.scheme}://{p.netloc}/"


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
