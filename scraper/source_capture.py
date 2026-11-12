"""Fingerprint the in-memory scrape result before it is separated from the job."""
from hashlib import sha256
import json
import re


def source_capture(manifest):
    pages = {}
    complete = bool(manifest.pages) and not (manifest.failures or manifest.deep_search)
    for page in manifest.pages:
        if (page.http_status != 200 or page.failures or not page.final_url
                or not re.fullmatch(r"[a-f0-9]{64}", page.content_hash or "")):
            complete = False
            continue
        payload = [page.content_hash, page.viewport_width, page.viewport_height,
                   [block.text for block in page.text_blocks if block.tag == "api"]]
        digest = sha256(json.dumps(payload, ensure_ascii=False).encode()).hexdigest()
        if page.final_url in pages and pages[page.final_url] != digest:
            complete = False
        pages[page.final_url] = digest
    return {"representation": "rendered-dom-and-api@1", "complete": complete, "pages": pages}
