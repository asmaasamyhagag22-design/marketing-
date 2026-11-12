"""Serve the real app with a disposable PostgreSQL and a fictional versioned publisher."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

from workflows import app_demo, demo
from workflows.v2_cases import ENDS, NOW, home, offer_page


MODES = ("initial", "price", "exception", "repaired", "expired")
EXCEPTION = "لا يسري العرض في عطلة نهاية الأسبوع."
REPAIRED_TERMS = "الحجز المسبق مطلوب. العرض للجلسة الأولى فقط. " + EXCEPTION


def set_scenario(directory, mode):
    if mode not in MODES:
        raise ValueError("Unknown fixture scenario")
    manifest = json.loads((directory / "demo.json").read_text())
    if manifest.get("synthetic") is not True:
        raise ValueError("Synthetic demo directory required")
    pending = directory / "publisher.tmp"
    pending.write_text(mode, encoding="utf-8")
    pending.replace(directory / "publisher.txt")


def configure(directory, app, manifest):
    from api.routes.v2_campaigns import get_clock, get_page_loader
    from strategy.campaign_research import Page, same_source

    def scenario():
        return (directory / "publisher.txt").read_text(encoding="utf-8").strip()

    def clock():
        return datetime.fromisoformat(ENDS if scenario() == "expired" else NOW)

    def load(url, timeout):
        if not same_source(url, manifest["url"]):
            raise OSError("Synthetic publisher owns one origin")
        route = urlsplit(url).path
        mode = scenario()
        if route in {"", "/"}:
            body = home(["team", "contact", "terms"])
        elif route == "/terms":
            values = {"price": "40" if mode == "initial" else "55"}
            if mode == "exception":
                values["extra"] = f"<p>{EXCEPTION}</p>"
            if mode in {"repaired", "expired"}:
                values["terms"] = REPAIRED_TERMS
            body = offer_page(**values)
        else:
            raise OSError("Fixture page unavailable")
        return Page(url, body, "synthetic_fixture")

    app.dependency_overrides[get_clock] = lambda: clock
    app.dependency_overrides[get_page_loader] = lambda: load


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("init", "serve", "scenario", "cleanup"))
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8020)
    parser.add_argument("--mode", choices=MODES)
    args = parser.parse_args()
    directory = args.directory.resolve()
    if args.action == "scenario":
        set_scenario(directory, args.mode)
        return
    if args.action == "cleanup":
        sys.argv = ["demo", "cleanup", "--directory", str(directory)]
        demo.main()
        return
    sys.argv = ["app_demo", args.action, "--directory", str(directory), "--port", str(args.port)]
    app_demo.main(lambda app, manifest: configure(directory, app, manifest))
    if args.action == "init":
        set_scenario(directory, "initial")
        manifest = json.loads((directory / "demo.json").read_text())
        print(json.dumps({"fixture_source": manifest["url"], "synthetic": True}))


if __name__ == "__main__":
    main()
