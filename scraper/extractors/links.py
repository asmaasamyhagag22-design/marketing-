"""Link extraction.

Walks every <a href> in the rendered HTML and produces a list of
LinkRecord with a category. Categories:
- internal: same registrable host
- social: matches a known social platform domain
- contact_protocol: tel:/mailto:/wa.me/whatsapp.com
- cta: internal link whose anchor text is a known CTA verb
- external: everything else

Each LinkRecord can carry a `block_id` if the link was also captured
as a TextBlock — we resolve that mapping here so downstream stages
can trace a link back to its DOM position.
"""
from __future__ import annotations

from typing import Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from ..config import CTA_VERBS, SOCIAL_DOMAINS
from ..schemas import LinkCategory, LinkInventory, LinkRecord, TextBlock
from ..url_utils import is_http_url, normalize_url, resolve, same_registrable_host


# A SHARE / intent button lives on a social host but is NOT the brand's own account — it's an
# action that shares the CURRENT page. Counting them inflated "social links" absurdly (measured:
# Azza Fahmy 20 -> 5 real accounts; the extras were facebook/sharer.php, twitter/intent/tweet,
# pinterest/pin/create/button on every product page).
_SHARE_MARKERS = (
    "/sharer", "/share.php", "/share?", "/sharing/", "/intent/", "/pin/create", "sharearticle",
    "share-offsite", "/dialog/share", "/dialog/feed", "/submit", "shareurl", "/share/url",
)


def _is_share_url(href: str) -> bool:
    low = (href or "").lower()
    if any(m in low for m in _SHARE_MARKERS):
        return True
    try:                                    # a share intent carries the page as ?u=/?url=/text=
        from urllib.parse import parse_qs
        q = parse_qs(urlparse(low).query)
        if any(k in q for k in ("u", "url", "text", "title", "media")) and "http" in (low.split("?", 1)[-1]):
            return True
    except Exception:
        pass
    return False


def _social_platform(href: str) -> Optional[str]:
    if _is_share_url(href):                 # a share/intent button is not the brand's account
        return None
    try:
        host = urlparse(href).netloc.lower()
    except Exception:
        return None
    if not host:
        return None
    for dom, name in SOCIAL_DOMAINS.items():
        # Exact host or a subdomain of it. The old `dom in host` SUBSTRING test
        # misclassified any host merely CONTAINING a short social domain — `x.com` is a
        # substring of xerox.com/box.com/netflix.com/fedex.com (-> "twitter"), `t.me` of
        # content.medium.* (-> "telegram") — which mislabels external links and can strip
        # a subject's OWN links from the crawl frontier. Subdomains (l.facebook.com,
        # m.youtube.com) are still matched via the endswith clause.
        if host == dom or host.endswith("." + dom):
            return name
    return None


def _is_cta_anchor(anchor: str) -> bool:
    a = (anchor or "").strip().lower()
    if not a:
        return False
    if a in CTA_VERBS:
        return True
    # Special case (added 2026-05 from Buffalo Burger benchmark):
    # "menu" is a CTA verb but only as an exact anchor. The loose
    # starts-with rule below would otherwise match "menu of the day"
    # or "menu items" — which are page headers, not CTAs.
    _EXACT_ONLY = {"menu", "cart", "delivery"}
    # Loose check: if the anchor starts with a CTA verb and is short
    for verb in CTA_VERBS:
        if verb in _EXACT_ONLY:
            continue  # already checked via exact-match above
        if len(a) < 40 and a.startswith(verb):
            return True
    return False


def extract_links_from_html(
    html: str,
    page_url: str,
    site_url: str,
    text_blocks: list[TextBlock] | None = None,
) -> list[LinkRecord]:
    if not html:
        return []
    soup = BeautifulSoup(html, "lxml")

    # Map href -> first TextBlock that shares the href, for evidence
    block_by_href: dict[str, str] = {}
    if text_blocks:
        for b in text_blocks:
            if b.is_link and b.href:
                resolved = resolve(page_url, b.href)
                block_by_href.setdefault(resolved, b.block_id)

    out: list[LinkRecord] = []
    seen_keys: set[tuple[str, str]] = set()

    for a in soup.find_all("a", href=True):
        href_raw = a["href"].strip()
        if not href_raw or href_raw.startswith("javascript:"):
            continue
        anchor = (a.get_text() or "").strip()
        anchor_short = " ".join(anchor.split())[:200]

        # Protocol-only contact links
        lower = href_raw.lower()
        if lower.startswith(("tel:", "mailto:")):
            key = (lower, page_url)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            out.append(LinkRecord(
                href=href_raw,
                anchor_text=anchor_short,
                page_url=page_url,
                category=LinkCategory.CONTACT_PROTOCOL,
            ))
            continue

        # Skip mailto without 'mailto:' (rare) and pure fragments
        if href_raw.startswith("#"):
            continue

        resolved = resolve(page_url, href_raw)
        if not is_http_url(resolved):
            continue

        platform = _social_platform(resolved)
        if platform:
            category = LinkCategory.SOCIAL
        elif same_registrable_host(resolved, site_url):
            if _is_cta_anchor(anchor_short):
                category = LinkCategory.CTA
            else:
                category = LinkCategory.INTERNAL
        else:
            category = LinkCategory.EXTERNAL

        # Per-page dedup by (href, ANCHOR): the same href legitimately appears with
        # DIFFERENT anchors — e.g. a nav "Contact" link AND a "Book a Meeting" CTA
        # button both pointing at /contact/. Keying on href alone kept only the first
        # (the nav item) and silently dropped the CTA before classification ever saw
        # it -> cta_candidates=0 on sites whose CTA shares a nav href (MEASURED on
        # daturial.com). True duplicates (same href + same text, e.g. a footer repeat)
        # still collapse.
        key = (resolved, page_url, anchor_short.lower())
        if key in seen_keys:
            continue
        seen_keys.add(key)

        out.append(LinkRecord(
            href=resolved,
            anchor_text=anchor_short,
            page_url=page_url,
            block_id=block_by_href.get(resolved),
            category=category,
            platform=platform,
        ))

    return out


def _dedup_key(href: str) -> str:
    """Canonical href for cross-page dedup: tracking-stripped (normalize_url)
    plus any trailing slash removed so `/x` and `/x/` collapse (normalize_url
    only strips the slash on the root path)."""
    return normalize_url(href).rstrip("/")


def build_inventory(links: list[LinkRecord]) -> LinkInventory:
    inv = LinkInventory()
    # The crawl emits one LinkRecord per (page, link), so a site-wide nav/footer
    # link is repeated once per crawled page. Collapse those cross-page repeats
    # (first occurrence wins) for the two buckets whose COUNTS feed downstream
    # gap/SWOT scoring: social and cta_candidates. Social keys on canonical href;
    # CTAs additionally key on anchor_text so distinct calls-to-action sharing
    # one href survive. Other buckets (internal/external/contact_protocol) are
    # left exactly as-is.
    seen_social: set[str] = set()
    seen_cta: set[tuple[str, str]] = set()
    for link in links:
        if link.category == LinkCategory.INTERNAL:
            inv.internal.append(link)
        elif link.category == LinkCategory.SOCIAL:
            key = _dedup_key(link.href)
            if key in seen_social:
                continue
            seen_social.add(key)
            inv.social.append(link)
        elif link.category == LinkCategory.CONTACT_PROTOCOL:
            inv.contact_protocol.append(link)
        elif link.category == LinkCategory.EXTERNAL:
            inv.external.append(link)
        elif link.category == LinkCategory.CTA:
            # CTAs are also internal — surface in both. `internal` is an
            # unrelated bucket here, so its append stays unconditional.
            inv.internal.append(link)
            key = (_dedup_key(link.href), (link.anchor_text or "").strip())
            if key in seen_cta:
                continue
            seen_cta.add(key)
            inv.cta_candidates.append(link)
    return inv