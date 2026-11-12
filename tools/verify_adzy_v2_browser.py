"""Run the V2 UI through its normal HTTP entry points and restart it."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import socket
import subprocess
import sys
from time import monotonic, sleep
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from workflows.v2_cases import NAME  # noqa: E402
from workflows.v2_demo import EXCEPTION, set_scenario  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    args = parser.parse_args()
    directory, evidence = args.directory.resolve(), args.evidence_dir.resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-m", "workflows.v2_demo"]
    subprocess.run([*cmd, "init", "--directory", str(directory)], cwd=ROOT, check=True)
    case = json.loads((directory / "demo.json").read_text())
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
        process = subprocess.Popen([*cmd, "serve", "--directory", str(directory), "--port", str(port)],
                                   cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        deadline = monotonic() + 40
        while monotonic() < deadline and process.poll() is None:
            try:
                with urlopen(origin + "/app", timeout=1) as response:
                    if response.status == 200:
                        return
            except OSError:
                sleep(.2)
        raise RuntimeError("Fixture server unavailable")

    def saved(page):
        return page.evaluate("domain => window.api('GET', '/api/v2/campaigns/' + domain)", case["domain"])

    try:
        from playwright.sync_api import expect, sync_playwright
        with (evidence / "server.txt").open("w") as log, sync_playwright() as playwright:
            start = monotonic()
            restart(log)
            with playwright.chromium.launch() as browser:
                page = browser.new_page(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.route("**/*", lambda route: route.continue_() if route.request.url.startswith(
                    (origin + "/", "data:", "blob:")) else route.abort())
                page.goto(origin + "/app")
                page.fill("#auth-email", case["email"])
                page.fill("#auth-password", "SyntheticDemo42")
                page.click("#auth-submit-btn")
                page.wait_for_function("() => window.Adzy && Adzy.brand")
                page.get_by_role("button", name="Campaign", exact=True).click()
                page.select_option('#v2-form select[name="goal"]', "TRIAL_BOOKINGS")
                page.fill('#v2-form input[name="booking_target"]', "30")
                page.fill('#v2-form input[name="offer_name"]', NAME)
                page.get_by_role("button", name="ابحث عن أدلة العرض").click()
                expect(page.locator("#v2-trace li")).to_have_count(2)
                expect(page.locator("#v2-question")).to_contain_text("الشروط")
                expect(page.locator("#v2-stop")).to_have_text("أُغلقت فجوة الدليل")
                expect(page.locator("#v2-strategy")).to_contain_text("30 حجزًا")
                expect(page.locator("#v2-strategy")).to_contain_text("مصدر مصطنع للديمو")
                page.click("#v2-approve")
                card = page.locator("#v2-creative")
                expect(card).to_contain_text("40 EUR")
                expect(card).to_contain_text("فرع الميناء")
                expect(card).to_contain_text("SYNTHETIC Studio")
                original = saved(page)
                with page.expect_response(lambda response: "/api/v2/campaigns/" in response.url):
                    page.locator("#adzy-brand-select").dispatch_event("change")
                expect(card).to_contain_text("40 EUR")
                card.screenshot(path=str(evidence / "campaign-desktop.png"))

                restart(log)
                page.reload()
                expect(card).to_contain_text("40 EUR")
                restored = saved(page)
                assert restored["run_id"] == original["run_id"]
                assert restored["approval_id"] == original["approval_id"]
                assert restored["proposal"]["creative"]["sha256"] == original["proposal"]["creative"]["sha256"]
                page.set_viewport_size({"width": 390, "height": 844})
                assert page.evaluate("document.documentElement.scrollWidth") <= 390
                card.screenshot(path=str(evidence / "campaign-mobile.png"))

                set_scenario(directory, "price")
                page.click("#v2-refresh")
                expect(page.locator("#v2-changes")).to_contain_text("رسالة السعر")
                expect(card).to_have_count(0)
                price_revision = saved(page)
                assert price_revision["proposal"]["creative"]["copy"]["price"] == "55 EUR"
                assert price_revision["run_id"] != original["run_id"]
                page.click("#v2-approve")
                expect(card).to_contain_text("55 EUR")

                set_scenario(directory, "exception")
                page.click("#v2-refresh")
                expect(page.locator("#v2-changes")).to_contain_text(EXCEPTION)
                expect(card).to_have_count(0)
                expect(page.locator("#v2-approve")).to_have_count(0)
                page.locator("#v2-changes").scroll_into_view_if_needed()
                expect(page.locator("#v2-changes")).to_be_visible()
                assert page.evaluate("document.documentElement.scrollWidth") <= 390
                page.screenshot(path=str(evidence / "exception.png"), full_page=True)

                set_scenario(directory, "repaired")
                page.click("#v2-refresh")
                expect(page.locator("#v2-approve")).to_be_visible()
                page.click("#v2-approve")
                expect(card).to_contain_text(EXCEPTION)

                set_scenario(directory, "expired")
                page.reload()
                expect(page.locator("#v2-blocker")).to_contain_text("انتهت صلاحية العرض")
                expect(card).to_have_count(0)
                page.click("#v2-refresh")
                expect(page.locator("#v2-changes")).to_contain_text("انتهت صلاحية العرض")
                impact = saved(page)["proposal"]["changes"][0]
                assert impact["before_sha256"] == impact["after_sha256"]
                assert not errors, errors
            from sqlalchemy import func, select
            from db.models import Approval, Run, UsageRecord
            from workflows.demo import connect
            service, _ = connect(case)
            with service._uow_factory() as uow:
                calls = uow.session.scalar(select(func.count()).select_from(UsageRecord))
                runs = uow.session.scalar(select(func.count()).select_from(Run).where(Run.kind == "campaign"))
                decisions = uow.session.scalar(select(func.count()).select_from(Approval).where(
                    Approval.subject_kind == "campaign"))
            assert (calls, runs, decisions) == (0, 5, 3)
            result = {
                "synthetic": True, "provider_calls": calls, "campaign_runs": runs,
                "human_actions_simulated": decisions, "brand_reselected": True,
                "restart": True, "price_repair": True,
                "exception_blocks": True, "explicit_qualified_revision": True,
                "expiry_unchanged_capture": True, "desktop_and_390px": True,
                "browser_errors": errors, "elapsed_seconds": round(monotonic() - start, 2),
                "image_sha256": {file.name: sha256(file.read_bytes()).hexdigest()
                                 for file in evidence.glob("*.png")},
            }
            (evidence / "result.json").write_text(json.dumps(result, indent=2) + "\n")
            print(json.dumps(result, indent=2))
    finally:
        stop()
        subprocess.run([*cmd, "cleanup", "--directory", str(directory)], cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
