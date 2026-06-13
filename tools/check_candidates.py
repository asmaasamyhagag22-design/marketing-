"""Benchmark URL candidate validator.

Run this on your own machine (NOT from a sandboxed CI environment) — it
makes one HTTP request per candidate, checks for structured markup,
fingerprints the site platform, and prints a per-URL summary.

The output gives you most of the checklist columns from the rubric:
  - has_real_content (view-source body)
  - JSON-LD count
  - Microdata count
  - robots.txt presence
  - sitemap.xml or directives
  - platform (Next.js, WordPress, Shopify, Wix, React-rendered, etc.)
  - language hint

What it CANNOT check (you need to eyeball):
  - hamburger or JS-only nav (resize browser to mobile width)
  - cookie modal / blocking overlay (open incognito)
  - menu/products in HTML text vs image vs PDF
  - whether the rendered DOM differs significantly from view-source

Usage:
    python tools/check_candidates.py
    python tools/check_candidates.py > candidate_check.txt 2>&1   # works on Windows

Edit CANDIDATES below to add/remove URLs.
"""
from __future__ import annotations

import io
import re
import sys
import urllib.error
import urllib.request
from urllib.parse import urlparse

# Force UTF-8 stdout/stderr. On Windows, Python defaults to the system
# codepage (often cp1252) when stdout is redirected to a file, which
# crashes on Unicode characters like → ✗ ö found in URLs, site titles,
# and our own output. UTF-8 is universally safe.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, io.UnsupportedOperation):
    # Older Python or non-standard stdout (e.g. some test runners).
    # Fall back: wrap stdout in a UTF-8 encoder that replaces unknowns.
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

CANDIDATES = [
    # (category, brand, url)
    ("Restaurant", "McDonald's Egypt", "https://www.mcdonalds.eg"),
    ("Restaurant", "Zooba", "https://zoobaeats.com"),
    ("Restaurant","elkbabgi" , "https://www.elkbabgi.com/menu"),
    ("Clinic", "Alameda (was Dar Al Fouad)", "https://alameda-hc.com"),
    ("Clinic", "Andalusia Hospitals", "https://www.andalusiaegypt.com"),
    ("Clinic", "As-Salam International", "https://assih.com"),
    ("Skincare", "Eva Cosmetics (shop)", "https://shop.eva-cosmetics.com"),
    ("Skincare", "Glamira (intl jewelry)", "https://www.glamira.com"),
    ("Skincare", "The Hair Addict", "https://thehairaddict.net"),
    ("Skincare", "Raw African", "https://rawafrican.net"),
    ("Skincare", "Norshek", "https://norshek.com"),
    ("Education", "Almentor", "https://almentor.net"),
    ("Education", "AUC SCE", "https://sce.aucegypt.edu"),
    ("Education", "Mumm", "https://mumm.io"),
]

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def fetch(url, timeout=10):
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": UA, "Accept-Language": "en,ar;q=0.9"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(2_000_000).decode("utf-8", errors="replace")
            return resp.status, dict(resp.headers), body, resp.geturl()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers) if e.headers else {}, "", url
    except Exception as e:
        return -1, {}, str(e), url


def fingerprint(html, headers):
    fp = []
    if "__NEXT_DATA__" in html:
        fp.append("Next.js")
    if "wp-content/" in html or "wp-includes/" in html:
        fp.append("WordPress")
    if "cdn.shopify.com" in html or "Shopify.theme" in html or "shopify" in headers.get("Server", "").lower():
        fp.append("Shopify")
    if "wix.com" in html or "wixstatic" in html or "X-Wix-Request-Id" in headers:
        fp.append("Wix")
    if "squarespace" in html.lower():
        fp.append("Squarespace")
    if "data-reactroot" in html or "data-react-root" in html:
        fp.append("React-rendered")
    if "__NUXT__" in html:
        fp.append("Nuxt")
    body_only = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.S)
    body_only = re.sub(r"<style[^>]*>.*?</style>", "", body_only, flags=re.S)
    visible = re.sub(r"<[^>]+>", " ", body_only)
    visible = re.sub(r"\s+", " ", visible).strip()
    if len(visible) < 300 and ("<div id=\"app\"" in html or "<div id=\"root\"" in html or "<div id=\"__next\"" in html):
        fp.append("SPA-empty-body")
    return fp, len(visible)


def check_robots(base_url):
    parsed = urlparse(base_url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    status, _, body, _ = fetch(robots_url, timeout=6)
    if status != 200 or not body:
        return False, []
    # Some hosts return an HTML 200 for /robots.txt. Reject those.
    head = body[:200].upper()
    if "<!DOCTYPE" in head or "<HTML" in head:
        return False, []
    sitemap_lines = [
        line.strip().split(":", 1)[1].strip()
        for line in body.splitlines()
        if line.strip().lower().startswith("sitemap:")
    ]
    return True, sitemap_lines


def check_sitemap_default(base_url):
    parsed = urlparse(base_url)
    sm_url = f"{parsed.scheme}://{parsed.netloc}/sitemap.xml"
    status, _, body, _ = fetch(sm_url, timeout=6)
    return status == 200 and ("<urlset" in body or "<sitemapindex" in body)


def evaluate(category, brand, url):
    print(f"\n{'='*72}")
    print(f"[{category}] {brand}")
    print(f"  {url}")

    status, headers, html, final_url = fetch(url)
    if status != 200:
        print(f"  [X] FETCH FAILED: status={status}")
        if html and len(html) < 300:
            print(f"    error: {html[:200]}")
        return {"brand": brand, "fatal": True, "status": status}

    if final_url != url:
        print(f"  -> redirected to: {final_url}")

    fps, visible_chars = fingerprint(html, headers)
    has_real_content = visible_chars > 500

    json_ld = len(re.findall(r'<script[^>]*type=["\']application/ld\+json["\']', html))
    microdata = len(re.findall(r'itemtype=["\']https?://schema\.org/', html))
    rdfa = len(re.findall(r'typeof=["\'][A-Za-z]', html))

    robots_ok, sm_directives = check_robots(url)
    default_sm = check_sitemap_default(url) if not sm_directives else False
    sitemap_present = bool(sm_directives) or default_sm

    lang_match = re.search(r'<html[^>]*\blang=["\']([^"\']+)["\']', html)
    html_lang = lang_match.group(1) if lang_match else None
    body_text = re.sub(r"<[^>]+>", " ", re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.S))
    has_arabic = bool(re.search(r"[\u0600-\u06FF]", body_text))

    title_match = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I)
    title = (title_match.group(1).strip() if title_match else "")[:80]

    print(f"  Title: {title!r}")
    print(f"  Body visible chars: {visible_chars} {'(content)' if has_real_content else '(SPA/thin)'}")
    print(f"  Platform: {', '.join(fps) if fps else '(unknown/custom)'}")
    print(f"  Structured: JSON-LD={json_ld}, Microdata={microdata}, RDFa-typeof={rdfa}")
    print(f"  Robots: {'yes' if robots_ok else 'no'}"
          f"{f', sitemap directives={len(sm_directives)}' if sm_directives else ''}")
    print(f"  /sitemap.xml default: {'yes' if default_sm else 'no'}")
    print(f"  lang={html_lang!r}, has_arabic_text={has_arabic}")

    # Score the 5 HTTP-detectable signals (out of 8 total — the other 3
    # require browser eyes: hamburger nav, cookie modal, image-vs-html offerings)
    sigs = sum([has_real_content, json_ld > 0, microdata > 0, robots_ok, sitemap_present])
    print(f"  HTTP-detectable signals: {sigs}/5")

    return {
        "brand": brand, "category": category, "url": url,
        "platform": fps, "json_ld": json_ld, "microdata": microdata,
        "robots_ok": robots_ok, "sitemap_present": sitemap_present,
        "has_real_content": has_real_content, "visible_chars": visible_chars,
        "html_lang": html_lang, "has_arabic": has_arabic,
        "http_sigs": sigs, "fatal": False,
    }


def main():
    results = [evaluate(*c) for c in CANDIDATES]
    print("\n\n" + "="*72)
    print("SUMMARY")
    print("="*72)
    for r in results:
        if r.get("fatal"):
            print(f"  [X] {r['brand']:<32} fetch failed (status={r['status']})")
            continue
        plat = ",".join(r["platform"]) or "-"
        print(f"  [{r['category']:<10}] {r['brand']:<28} "
              f"http_sigs={r['http_sigs']}/5  platform={plat}  "
              f"lang={r['html_lang']}  ar_text={r['has_arabic']}")


if __name__ == "__main__":
    main()