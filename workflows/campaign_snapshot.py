from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path

from strategy.campaign_package import valid_source_url
from strategy.campaign_research import Page, ResearchGap


def open_snapshot(directory: Path):
    records = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    pages = {}
    dates = []
    for url, record in records.items():
        name = record["file"]
        if not valid_source_url(url) or Path(name).name != name:
            raise ValueError("Invalid campaign snapshot entry")
        body = (directory / name).read_bytes()
        if sha256(body).hexdigest() != record["sha256"]:
            raise ValueError(f"Campaign snapshot checksum mismatch: {name}")
        date = datetime.fromisoformat(record["captured_at"])
        if date.utcoffset() is None:
            raise ValueError("Campaign snapshot requires a capture timezone")
        dates.append(date)
        pages[url] = Page(url, body, "publisher_snapshot", date.isoformat())
    frozen_time = max(dates)

    def load(url, timeout):
        if url not in pages:
            raise ResearchGap("SOURCE_NOT_IN_SNAPSHOT")
        return pages[url]

    return load, lambda: frozen_time
