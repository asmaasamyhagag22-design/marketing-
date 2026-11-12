"""Verify public sources, review export, direction revision and restore from Chromium."""
import argparse
from base64 import b64decode
from hashlib import sha256
import io
import json
from pathlib import Path
import socket
import subprocess
import sys
from time import monotonic, sleep
from urllib.request import urlopen
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def unpack(download, destination, state):
    from PIL import Image

    archive_bytes = download.path().read_bytes()
    with ZipFile(io.BytesIO(archive_bytes)) as archive:
        report = json.loads(archive.read("campaign.json"))
        assert report["run_id"] == state["run_id"] and report["approval_id"] == state["approval_id"]
        assert report["proposal"]["sha256"] == state["proposal"]["sha256"]
        for label, height in (("portrait", 1350), ("square", 1080)):
            name = f"poster-{label}.png"
            image = archive.read(name)
            assert Image.open(io.BytesIO(image)).size == (1080, height)
            assert sha256(image).hexdigest() == report["poster_measurements"][label]["sha256"]
            (destination / name).write_bytes(image)
    (destination / "campaign.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    (destination / "campaign.zip").write_bytes(archive_bytes)
    return {label: item["sha256"] for label, item in report["poster_measurements"].items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("cases", nargs="+", type=Path)
    args = parser.parse_args()
    directory, evidence = args.directory.resolve(), args.evidence_dir.resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, "-m", "workflows.public_campaign_demo"]
    subprocess.run([*command, "init", "--directory", str(directory),
                    *(item for case in args.cases for item in ("--case", str(case.resolve())))],
                   cwd=ROOT, check=True)
    manifest = json.loads((directory / "demo.json").read_text())
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    origin = f"http://127.0.0.1:{port}"
    process = None
    errors = []

    def stop():
        if process and process.poll() is None:
            process.terminate()
            process.wait(timeout=25)

    def restart(log):
        nonlocal process
        stop()
        process = subprocess.Popen([*command, "serve", "--directory", str(directory), "--port", str(port)],
                                   cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        deadline = monotonic() + 40
        while monotonic() < deadline and process.poll() is None:
            try:
                with urlopen(origin + "/app", timeout=1) as response:
                    if response.status == 200:
                        return
            except OSError:
                sleep(.2)
        raise RuntimeError("Campaign server unavailable")

    try:
        from playwright.sync_api import expect, sync_playwright
        with (evidence / "server.txt").open("w") as log, sync_playwright() as playwright:
            started = monotonic()
            restart(log)
            results = {}
            with playwright.chromium.launch() as browser:
                page = browser.new_page(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.route("**/*", lambda route: route.continue_() if route.request.url.startswith(
                    (origin + "/", "data:", "blob:")) else route.abort())
                page.goto(origin + "/app")
                page.fill("#auth-email", manifest["email"])
                page.fill("#auth-password", "LocalCampaignReview42")
                page.click("#auth-submit-btn")
                page.wait_for_function("() => window.Adzy && Adzy.brand")
                for case in args.cases:
                    before = monotonic()
                    target = evidence / case.name
                    target.mkdir(exist_ok=True)
                    domain = manifest["brands"][case.name]
                    page.locator("#adzy-brand-select").select_option(domain)
                    page.get_by_role("button", name="Campaign", exact=True).click()
                    api_path = "/api/v2/campaigns/" + domain

                    def saved():
                        return page.evaluate("path => window.api('GET', path)", api_path)

                    if page.locator("#v2-package-import").get_attribute("open") is None:
                        page.locator("#v2-package-import summary").click()
                    page.locator("#v2-package-form input").set_input_files(str(case / "brief.json"))
                    with page.expect_response(lambda response: response.url.endswith(api_path + "/package")) as requested:
                        page.locator("#v2-package-form button").click()
                    assert requested.value.ok, requested.value.text()
                    initial = saved()
                    assert initial["proposal"]["status"] == "READY", initial["proposal"]["evidence"]
                    assert all(item["capture_kind"] == "public_http" for item in initial["proposal"]["evidence"])
                    previews = {}
                    for size in ("portrait", "square"):
                        with page.expect_response(lambda response: response.url.endswith("&size=" + size)) as preview:
                            page.locator(f"[data-v2-preview='{size}']").click()
                        assert preview.value.ok, preview.value.text()
                        poster = page.locator("#v2-poster-preview img").and_(page.get_by_alt_text(
                            "البوستر الطولي" if size == "portrait" else "البوستر المربّع", exact=True,
                        ))
                        expect(poster).to_be_visible()
                        url = poster.get_attribute("src")
                        assert url.startswith("data:image/png;base64,")
                        previews[size] = sha256(b64decode(url.split(",", 1)[1])).hexdigest()
                    page.click("#v2-approve")

                    def download(dest):
                        dest.mkdir(exist_ok=True)
                        with page.expect_download(timeout=25000) as item:
                            page.click("#v2-download")
                        return unpack(item.value, dest, saved())

                    initial_hashes = download(target / "initial")
                    assert initial_hashes == previews, (initial_hashes, previews)
                    page.locator("[data-v2-direction='1']").click()
                    expect(page.locator("#v2-approve")).to_be_visible()
                    revision = saved()
                    assert revision["run_id"] != initial["run_id"] and not revision["approved"]
                    assert revision["proposal"]["evidence"] == initial["proposal"]["evidence"]
                    assert revision["proposal"]["brief"]["selected"] == 1
                    stale = page.evaluate(
                        """url => fetch(url, {headers: window.authHeaders()}).then(r => r.status)""",
                        api_path + "/package/export?run_id=" + initial["run_id"],
                    )
                    assert stale == 409
                    page.click("#v2-approve")
                    hashes = download(target)
                    assert all(hashes[k] != initial_hashes[k] for k in hashes)
                    final = saved()
                    restart(log)
                    page.reload()
                    expect(page.locator("#v2-download")).to_be_visible()
                    recovered = saved()
                    assert recovered["run_id"] == final["run_id"] and recovered["approval_id"] == final["approval_id"]
                    assert recovered["proposal"]["sha256"] == final["proposal"]["sha256"]
                    assert download(target / "replay") == hashes
                    assert (target / "replay/campaign.zip").read_bytes() == (target / "campaign.zip").read_bytes()
                    page.set_viewport_size({"width": 390, "height": 844})
                    card = page.locator("#v2-package-card")
                    expect(card).to_be_visible()
                    assert page.evaluate("document.documentElement.scrollWidth") <= 390
                    card.screenshot(path=str(target / "mobile-preview.png"))
                    page.set_viewport_size({"width": 1440, "height": 1000})
                    results[case.name] = {"seconds": round(monotonic() - before, 2), "public_pages": 2,
                                          "stale_export_http": stale, "restored_png_sha256": hashes}
            from sqlalchemy import func, select
            from db.models import Approval, Run, UsageRecord
            from workflows.demo import connect
            service, _ = connect(manifest)
            with service._uow_factory() as uow:
                usage = uow.session.scalar(select(func.count()).select_from(UsageRecord))
                runs = uow.session.scalar(select(func.count()).select_from(Run).where(Run.kind == "campaign"))
                decisions = uow.session.scalar(select(func.count()).select_from(Approval).where(
                    Approval.subject_kind == "campaign"))
            assert (usage, runs, decisions) == (0, 2 * len(args.cases), 2 * len(args.cases))
            assert not errors, errors
            report = {"cases": results, "elapsed_seconds": round(monotonic() - started, 2),
                      "campaign_runs": runs, "automated_review_actions": decisions,
                      "provider_usage_rows": usage, "browser_errors": errors}
            (evidence / "result.json").write_text(json.dumps(report, indent=2) + "\n")
            print(json.dumps(report, indent=2))
    finally:
        stop()
        subprocess.run([*command, "cleanup", "--directory", str(directory)], cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
