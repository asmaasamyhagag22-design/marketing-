"""Fictional publisher pages. The application and release replay use the same parser."""
from html import escape

from strategy.campaign_research import Page

ROOT = "https://studio.example.test/"
NAME = "جلسة تصميم للمبتدئين"
NOW = "2026-11-12T10:00:00+02:00"
ENDS = "2026-11-30T23:59:00+02:00"


def offer_page(*, name=NAME, price="40", currency="EUR", branch="فرع الميناء",
               ends=ENDS, terms="الحجز المسبق مطلوب. العرض للجلسة الأولى فقط.", extra=""):
    fields = {
        "name": name, "price": price, "priceCurrency": currency,
        "availableAtOrFrom": branch, "validThrough": ends, "description": terms,
    }
    markup = "".join(f'<p itemprop="{key}">{escape(value)}</p>' for key, value in fields.items())
    return (f'<html><body><article itemscope itemtype="https://schema.org/Offer">'
            f'{markup}</article>{extra}</body></html>').encode()


def home(links):
    labels = {"offer": "Workshop offer", "terms": "Price and terms",
              "arabic_terms": "شروط الحجز والسعر", "team": "Our team", "contact": "Contact"}
    anchors = "".join(f'<a href="/{key}">{labels[key]}</a>' for key in links)
    return f"<html><body>{anchors}</body></html>".encode()


def release_loader(case):
    def load(url, timeout):
        key = url.removeprefix(ROOT)
        if key == case.get("unavailable"):
            raise OSError("synthetic source unavailable")
        if not key:
            return Page(url, home(case["links"]), "synthetic_fixture")
        if key == case["complete"]:
            ends = "2026-11-11T23:59:00+02:00" if case.get("expired") else ENDS
            extra = "<p>لا يسري العرض في عطلة الأسبوع.</p>" if case.get("unparsed") else ""
            return Page(url, offer_page(ends=ends, extra=extra), "synthetic_fixture")
        return Page(url, b"<html><body>About this studio.</body></html>")
    return load
