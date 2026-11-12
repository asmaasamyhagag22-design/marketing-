"""Exercise profile refresh and recovery in the offline demo with real Chromium and PostgreSQL."""
import argparse
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
from time import monotonic, sleep
from urllib.request import urlopen
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def serve_fixture(directory, port):
    from workflows.demo import isolate
    isolate()
    from api.routes import scrape
    from api import webapp_analysis
    from workflows import app_demo
    from workflows.synthetic import brand, field

    case = json.loads((directory / "demo.json").read_text())
    source = brand(case["domain"])
    source["_profile"]["trust_signals"][0] = field(
        "Published guided specialist onboarding checklist")
    fetches = 0

    def pipeline(job_id, url, recorder, **kwargs):
        nonlocal fetches
        assert url == case["url"]
        fetches += 1
        if fetches == 1:
            return None
        recorder.set_result_threadsafe(job_id, source["_profile"])
        return source["_profile"]

    def swot(document):
        assert document["_profile"]["trust_signals"] == source["_profile"]["trust_signals"]
        return {
            "has_swot": True,
            "swot": {"summary": "Synthetic SWOT for the refreshed profile"},
            "_full_result": source["_full_result"],
        }

    scrape.is_safe_public_url = lambda url: url == case["url"]
    scrape.run_pipeline_job = pipeline
    webapp_analysis.generate_swot = swot
    sys.argv = ["app_demo", "serve", "--directory", str(directory), "--port",
                str(port), "--synthetic-posters", "accepted"]
    app_demo.main()


def start_server(directory, origin, port, log):
    process = subprocess.Popen([
        sys.executable, __file__, "--serve-fixture", "--directory", str(directory),
        "--port", str(port),
    ], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    try:
        deadline = monotonic() + 40
        while monotonic() < deadline and process.poll() is None:
            try:
                with urlopen(origin + "/app", timeout=1) as response:
                    if response.status == 200:
                        return process
            except OSError:
                sleep(.2)
        raise RuntimeError("Fixture server unavailable. See server log.")
    except BaseException:
        stop(process)
        raise


def stop(process):
    if process and process.poll() is None:
        process.terminate()
        process.wait(timeout=30)


def explore(page, url):
    page.get_by_role("button", name="Discover", exact=True).click()
    page.fill("#adzy-url-input", url)
    page.click("#adzy-explore-btn")


def browser_journey(page, expect, case, evidence, restart):
    started = monotonic()
    page.fill("#auth-email", case["email"])
    page.fill("#auth-password", "SyntheticDemo42")
    page.click("#auth-submit-btn")
    page.wait_for_function("() => window.Adzy && Adzy.brand")
    page.get_by_role("button", name="Think", exact=True).click()
    page.get_by_role("button", name="Review strategy →").click()
    page.click("#adzy-lock-btn")
    page.get_by_role("button", name="Prepare the poster", exact=True).click()
    page.click("#adzy-make-btn")
    expect(page.locator("#adzy-download-final")).to_be_visible(timeout=120000)
    old = page.evaluate("""() => ({
        profile: Adzy.brand.profile_snapshot_id, swot: Adzy.brand.swot_run_id,
        strategy: Adzy.brand.strategy_version_id, poster: Adzy.creative.generation_run_id,
        checksum: Adzy.creative.delivery.checksum
    })""")

    explore(page, case["url"])
    expect(page.locator("#adzy-scan-error")).to_contain_text("Scrape processing failed")
    page.reload()
    page.wait_for_function("() => window.Adzy && Adzy.brand")
    assert page.evaluate("Adzy.brand.profile_snapshot_id") == old["profile"]
    assert page.evaluate("Adzy.brand.strategy_version_id") == old["strategy"]

    explore(page, case["url"])
    research = page.locator("#adzy-research")
    expect(research).to_be_visible()
    expect(research.get_by_role("status")).to_contain_text("out of date")
    assert page.evaluate("Adzy.brand.profile_snapshot_id") != old["profile"]
    assert page.evaluate("Adzy.brand.strategy_candidate.run_id") == old["strategy"]
    expect(page.locator("#adzy-approve-swot")).to_have_count(0)
    page.get_by_role("button", name="Discover", exact=True).click()
    expect(page.locator("#adzy-brand-strips")).to_contain_text("Evidence needs review")
    page.get_by_role("button", name="Think", exact=True).click()
    page.get_by_role("button", name="Pick the angle", exact=False).click()
    expect(page.locator("#adzy-workflow-status")).to_contain_text("Brand evidence needs review")
    expect(page.locator("#adzy-lock-btn")).to_have_count(0)
    page.locator("#adzy-approval").screenshot(path=str(evidence / "desktop-recovery.png"))

    restart()
    page.set_viewport_size({"width": 390, "height": 844})
    page.reload()
    expect(page.locator("#adzy-workflow-status")).to_contain_text("Brand evidence needs review")
    assert page.evaluate("document.documentElement.scrollWidth") <= 390
    page.locator("#adzy-approval").screenshot(path=str(evidence / "mobile-recovery.png"))
    page.get_by_role("button", name="Create", exact=True).click()
    expect(page.locator("#adzy-brief-status")).to_have_text("Brand evidence needs review")
    expect(page.locator("#adzy-make-btn")).to_be_disabled()
    expect(page.locator("#adzy-download-final")).to_be_hidden()
    expect(page.locator("#adzy-download-draft")).to_be_visible()
    with page.expect_download() as download:
        page.click("#adzy-download-draft")
    assert hashlib.sha256(Path(download.value.path()).read_bytes()).hexdigest() == old["checksum"]

    page.get_by_role("button", name="Think", exact=True).click()
    page.get_by_role("button", name="Regenerate SWOT", exact=True).click()
    expect(page.locator("#adzy-approve-swot")).to_be_enabled()
    assert page.evaluate("Adzy.brand.swot_run_id") != old["swot"]
    assert not page.evaluate("Adzy.brand.swot_approved")
    page.click("#adzy-approve-swot")
    page.get_by_role("button", name="Review strategy →").click()
    page.click("#adzy-find-angle-btn")
    expect(page.locator("#adzy-lock-btn")).to_be_enabled(timeout=20000)
    assert page.evaluate("Adzy.brand.strategy_candidate.run_id") != old["strategy"]
    assert not page.evaluate("Adzy.brand.strategy_version_id")
    page.click("#adzy-lock-btn")
    page.get_by_role("button", name="Prepare the poster", exact=True).click()
    expect(page.locator("#adzy-brief-status")).to_have_text("Locked by approved strategy")
    contract = page.evaluate("Adzy.contract")
    assert contract["profile_snapshot_id"] == page.evaluate("Adzy.brand.profile_snapshot_id")
    assert contract["strategy_version_id"] == page.evaluate("Adzy.brand.strategy_version_id")
    assert "Published guided specialist onboarding checklist" in json.dumps(contract)
    page.reload()
    expect(page.locator("#adzy-brief-status")).to_have_text("Locked by approved strategy")
    assert page.evaluate("Adzy.contract.creative_contract_id") == contract["creative_contract_id"]
    return {
        "failed_refresh_kept_approval": True,
        "stale_after_process_restart": True,
        "saved_brand_card_requests_review": True,
        "old_poster_draft_checksum_unchanged": True,
        "new_swot_and_strategy_required_explicit_approval": True,
        "recovered_contract_binds_new_profile_and_quote": True,
        "desktop_and_390px": True,
        "journey_seconds": round(monotonic() - started, 2),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--serve-fixture", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--port", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()
    directory = args.directory.resolve()
    if args.serve_fixture:
        serve_fixture(directory, args.port)
        return
    if args.evidence_dir is None:
        parser.error("--evidence-dir is required")

    from playwright.sync_api import expect, sync_playwright
    from sqlalchemy import func, select
    from db.models import Run, UsageRecord
    from workflows.demo import command, connect, isolate

    isolate()
    evidence = args.evidence_dir.resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    command([sys.executable, "-m", "workflows.app_demo", "init", "--directory", str(directory)])
    case = json.loads((directory / "demo.json").read_text())
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    origin = f"http://127.0.0.1:{port}"
    process = None
    errors = []
    try:
        with (evidence / "server.txt").open("w") as log, sync_playwright() as playwright:
            def restart():
                nonlocal process
                stop(process)
                process = start_server(directory, origin, port, log)

            restart()
            with playwright.chromium.launch() as browser:
                page = browser.new_page(
                    viewport={"width": 1440, "height": 1000}, accept_downloads=True,
                    reduced_motion="reduce")
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.route("**/*", lambda route: route.continue_() if
                           route.request.url.startswith((origin + "/", "data:", "blob:"))
                           else route.abort())
                page.goto(origin + "/app")
                result = browser_journey(page, expect, case, evidence, restart)

        service, _ = connect(case)
        with service._uow_factory() as uow:
            runs = select(Run).where(Run.created_by_user_id == UUID(case["actor"]),
                                     Run.kind == "poster").subquery()
            posters = uow.session.scalar(select(func.count()).select_from(runs))
            dispatches = uow.session.scalar(select(func.count()).select_from(UsageRecord)
                                             .join(runs, runs.c.id == UsageRecord.run_id))
        assert (posters, dispatches) == (1, 0)
        assert not errors, errors
        result.update(synthetic=True, poster_runs=posters, provider_dispatches=dispatches,
                      browser_errors=errors)
        (evidence / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2))
    finally:
        stop(process)
        command(["docker", "stop", case["container"]])


if __name__ == "__main__":
    main()
