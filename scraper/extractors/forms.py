"""Form extraction.

Walk every <form> and capture:
- action (resolved against page URL)
- method
- fields: name, type, placeholder, required
- a short surrounding-text excerpt for context (the form's header
  or the nearest preceding heading)
"""
from __future__ import annotations

from typing import Optional

from bs4 import BeautifulSoup

from ..schemas import FormField, FormRecord
from ..url_utils import resolve


def _surrounding_text(form_el) -> Optional[str]:
    """Find a short label for this form: legend, preceding h*, or aria-label."""
    legend = form_el.find("legend")
    if legend and legend.get_text(strip=True):
        return legend.get_text(strip=True)[:200]

    label = form_el.get("aria-label")
    if label and label.strip():
        return label.strip()[:200]

    # Walk up to find a nearby heading
    parent = form_el.parent
    hops = 0
    while parent is not None and hops < 3:
        # Look for a heading before the form in this parent's children
        prev = form_el
        while True:
            prev = prev.find_previous_sibling()
            if prev is None:
                break
            if prev.name in ("h1", "h2", "h3", "h4"):
                text = prev.get_text(strip=True)
                if text:
                    return text[:200]
        parent = parent.parent
        hops += 1

    return None


def extract_forms(html: str, page_url: str) -> list[FormRecord]:
    if not html:
        return []
    soup = BeautifulSoup(html, "lxml")
    out: list[FormRecord] = []

    for form in soup.find_all("form"):
        action_attr = form.get("action")
        action = resolve(page_url, action_attr) if action_attr else None
        method = (form.get("method") or "get").lower()

        fields: list[FormField] = []
        # Honor <input>, <textarea>, <select>
        for el in form.find_all(["input", "textarea", "select"]):
            ftype = (el.get("type") or el.name or "text").lower()
            # Skip hidden / csrf / submit-button fields we don't want to surface as data fields
            if ftype in ("hidden",):
                continue
            fields.append(FormField(
                name=el.get("name"),
                field_type=ftype,
                placeholder=el.get("placeholder"),
                required=el.has_attr("required") or el.get("aria-required") == "true",
            ))

        if not fields:
            # Skip empty forms (likely search-only or pure UI)
            continue

        out.append(FormRecord(
            page_url=page_url,
            action=action,
            method=method,
            fields=fields,
            surrounding_text=_surrounding_text(form),
        ))

    return out
