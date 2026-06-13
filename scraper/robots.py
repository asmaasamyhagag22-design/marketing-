"""robots.txt checking.

We respect robots.txt. If a site disallows our user agent for a path,
we skip it and record ROBOTS_DISALLOWED in the manifest.
"""
from __future__ import annotations

import urllib.robotparser
import urllib.request
from urllib.parse import urlparse, urlunparse

from .config import USER_AGENT
from .schemas import RobotsRecord


def _robots_url_for(url: str) -> str:
    p = urlparse(url)
    return urlunparse((p.scheme, p.netloc, "/robots.txt", "", "", ""))


def load_robots(url: str, timeout: float = 5.0) -> tuple[urllib.robotparser.RobotFileParser, RobotsRecord]:
    """Fetch and parse robots.txt for the given URL's host.

    Returns (parser, record). If the file is missing or unreachable,
    we default to allowing crawling — this matches major-crawler
    behavior. The record makes the decision auditable.
    """
    robots_url = _robots_url_for(url)
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(robots_url)

    record_args = {
        "checked": True,
        "allowed": True,
        "robots_url": robots_url,
        "crawl_delay_seconds": 0.0,
        "note": None,
    }

    try:
        # RobotFileParser.read() uses urllib.request.urlopen with no timeout
        # built in. We fetch manually to enforce a timeout, then feed lines.
        req = urllib.request.Request(robots_url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        rp.parse(body.splitlines())

        # PR-1: pull Sitemap: directives out of the body. These are global
        # per the robots.txt spec (not tied to a user-agent block) so we
        # collect them once. Errors here must never block crawling.
        try:
            from .sitemap import extract_sitemap_urls_from_robots
            record_args["sitemap_urls"] = extract_sitemap_urls_from_robots(body, url)
        except Exception:
            record_args["sitemap_urls"] = []

        # crawl-delay is per-user-agent; the parser exposes it.
        cd = rp.crawl_delay(USER_AGENT) or rp.crawl_delay("*")
        if cd:
            try:
                record_args["crawl_delay_seconds"] = float(cd)
            except (TypeError, ValueError):
                pass

        # Test the input URL itself
        record_args["allowed"] = rp.can_fetch(USER_AGENT, url)
        if not record_args["allowed"]:
            record_args["note"] = "Input URL disallowed by robots.txt"
    except Exception as e:
    # Missing / unreachable robots.txt -> assume allowed.
    # IMPORTANT: a RobotFileParser that never parsed robots.txt may return
    # False from can_fetch() in some Python versions. Mark it explicitly so
    # subpage checks do not contradict the root robots record.
        setattr(rp, "_assume_allowed", True)
        record_args["allowed"] = True
        record_args["note"] = f"robots.txt unavailable ({type(e).__name__}); assuming allowed"
    return rp, RobotsRecord(**record_args)



def can_fetch(rp: urllib.robotparser.RobotFileParser, url: str) -> bool:
    if getattr(rp, "_assume_allowed", False):
        return True
    try:
        return rp.can_fetch(USER_AGENT, url)
    except Exception:
        return True