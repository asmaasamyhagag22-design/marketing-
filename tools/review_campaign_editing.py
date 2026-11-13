"""Export blinded static Campaign pairs and verify returned reviewer edits."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import random
import secrets
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import monotonic
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.demo_campaign_lifecycle import LocalCampaign, audit_database
from workflows import demo
from workflows.campaign_eval import COPY_FIELDS, EDITING_FIXTURES, case_set, review_input
from workflows.campaign_monitor import events
from workflows.campaign_telemetry import CampaignTrace

REASONS = {
    "WRONG_EVIDENCE": "الدليل لصنف أو موضوع آخر",
    "SCOPE": "الوعد أوسع من المصدر",
    "CTA": "الدعوة لا تناسب الهدف أو الوجهة",
    "WORDING": "صياغة ضعيفة",
    "PREFERENCE": "تفضيل شخصي",
    "OTHER": "سبب آخر",
}
PAIRS = ("buffalo-menu", "five-guys-bacon", "nandos-wrap", "nasa-mars-orbit",
         "sqlite-embedded-sql", "debian-hardware")
RELEASES = ("stable", "candidate")
CHOICES = ("A", "B", "tie", "both_need_edits")


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def exercise(app, cases):
    drafts = {}
    for release in RELEASES:
        for case_id in PAIRS:
            case = cases[case_id]
            started = monotonic()
            with app.serve(release=release, case=case):
                app.login()
                planned = app.plan(case)
                proposal = planned["proposal"]
                assert proposal["planner"]["version"]["release"] == release
                reviewed = app.copy(planned, None)
                approved = app.approve(planned["domain_key"], reviewed)
                bundle = app.export(planned["domain_key"], approved)
                assert approved["proposal"]["evidence"] == proposal["evidence"]
                expected = case.get("cta", {}).get(release)
                if expected is not None:
                    package = approved["proposal"]["package"]
                    assert package["copy"]["cta"] == expected and package["caption"].endswith(f"{expected}.")
                assert approved["proposal"]["package"]["source_url"] == case["expected"]["destination"]
                probes = {}
                for edit in case.get("edits", []):
                    if edit.get("critical"):
                        conflict = app.copy({**reviewed, "domain_key": planned["domain_key"]}, edit, expected=409)
                        assert conflict["detail"]["code"] == "COPY_REQUIRES_EVIDENCE_REVIEW"
                        probes[edit["id"]] = conflict["detail"]["code"]
                drafts[case_id, release] = {
                    "planned": planned, "approved": approved, "zip": bundle,
                    "critical_probes": probes, "elapsed_seconds": round(monotonic() - started, 3),
                }
    for case_id in PAIRS:
        left, right = (drafts[case_id, release]["approved"]["proposal"] for release in RELEASES)
        assert left["evidence"] == right["evidence"]
        assert left["planner"]["page_calls"] == right["planner"]["page_calls"]
        index = left["brief"]["selected"]
        assert right["brief"]["selected"] == index
        assert left["planner"]["options"][index]["action"] == right["planner"]["options"][index]["action"]
    case_id = "nasa-mars-orbit"
    saved = drafts[case_id, "candidate"]
    approved = saved["approved"]
    domain = saved["planned"]["domain_key"]
    with app.serve(release="stable", case=cases[case_id]):
        app.login()
        recovered = app.api("GET", f"/{domain}").json()
        assert recovered["approved"]
        assert all(recovered[key] == approved[key] for key in (
            "run_id", "approval_id", "profile_snapshot_id", "proposal",
        ))
        assert app.export(domain, recovered) == saved["zip"]
        fresh = app.plan(cases[case_id])
        assert fresh["proposal"]["planner"]["version"]["release"] == "stable"
        assert fresh["proposal"]["brief"]["directions"][0]["cta"] == cases[case_id]["cta"]["stable"]
        database = audit_database(app.manifest, approved)
        assert database["provider_usage_rows"] == 0
        rollback = {
            "prior_zip_byte_equal": True, "prior_proposal_equal": True, "prior_approval_preserved": True,
            "fresh_run_id": fresh["run_id"], "fresh_proposal_sha256": fresh["proposal"]["sha256"],
            "fresh_trace_id": fresh["proposal"]["planner"]["trace_id"],
            "fresh_version": fresh["proposal"]["planner"]["version"],
            "fresh_cta": fresh["proposal"]["brief"]["directions"][0]["cta"], "database": database,
        }
    return drafts, rollback


def export_packets(output, gate, cases, drafts, rollback):
    blind = output / "blind"
    blind.mkdir()
    artifacts = output / "artifacts"
    artifacts.mkdir()
    seed = secrets.randbits(64)
    rng = random.Random(seed)
    public, key = {}, {}
    for case_id in PAIRS:
        order = list(RELEASES)
        rng.shuffle(order)
        public[case_id] = {"input": cases[case_id]["input"], "drafts": {}}
        key[case_id] = {}
        for slot, release in zip(("A", "B"), order, strict=True):
            sample = drafts[case_id, release]
            bundle = sample["zip"]
            destination = artifacts / case_id / release
            destination.mkdir(parents=True)
            (destination / "campaign.zip").write_bytes(bundle)
            with ZipFile(BytesIO(bundle)) as archive:
                campaign = json.loads(archive.read("campaign.json"))
                for size in ("square", "portrait"):
                    image = archive.read(f"poster-{size}.png")
                    (destination / f"poster-{size}.png").write_bytes(image)
                    (blind / f"{case_id}-{slot}-{size}.png").write_bytes(image)
            write_json(destination / "campaign.json", campaign)
            write_json(destination / "draft.json", sample["planned"])
            proposal = campaign["proposal"]
            planner = proposal["planner"]
            public[case_id]["drafts"][slot] = {
                "copy": proposal["package"]["copy"], "caption": proposal["package"]["caption"],
                "url": proposal["package"]["source_url"],
                "evidence": [{name: fact[name] for name in ("quote", "scope", "page_url")}
                             for fact in proposal["evidence"]],
            }
            key[case_id][slot] = {
                "release": release, "run_id": campaign["run_id"], "approval_id": campaign["approval_id"],
                "draft_run_id": sample["planned"]["run_id"], "draft_sha256": sample["planned"]["proposal"]["sha256"],
                "proposal_sha256": proposal["sha256"], "trace_id": planner["trace_id"],
                "snapshot_id": planner["snapshot_id"], "version": planner["version"],
                "zip_sha256": sha256(bundle).hexdigest(), "critical_probes": sample["critical_probes"],
                "elapsed_seconds": sample["elapsed_seconds"],
            }
    packet_id = sha256(json.dumps(public, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    write_json(output / "review-key.json", {
        "packet_id": packet_id, "randomization_seed": seed, "eval_set_id": gate["eval_set_id"],
        "cases": key, "rollback": rollback,
    })
    template = (EDITING_FIXTURES / "review.html").read_text(encoding="utf-8")
    data = json.dumps({"packet_id": packet_id, "cases": public, "fields": COPY_FIELDS, "reasons": REASONS},
                      ensure_ascii=False).replace("<", "\\u003c")
    (blind / "index.html").write_text(template.replace("/*PACKET*/", data), encoding="utf-8")


def verify_notes(output, response, *, reviewer_role):
    from strategy.campaign_package import digest
    from strategy.campaign_planner import review_draft
    from strategy.campaign_release import code_commit, implementation_hash
    from strategy.campaign_v2 import CampaignConflict

    key = json.loads((output / "review-key.json").read_text())
    form = json.loads(response.read_text())
    if form["packet_id"] != key["packet_id"]:
        raise ValueError("Review belongs to a different packet")
    if not form["reviewer"].strip() or not set(form["reviews"]) <= set(key["cases"]):
        raise ValueError("Missing reviewer or unknown case")
    recorded = {}
    for case_id, row in form["reviews"].items():
        if row["choice"] not in CHOICES or set(row["drafts"]) != {"A", "B"}:
            raise ValueError("Invalid choice or draft slots")
        recorded[case_id] = {**row, "drafts": {}}
        for slot, result in row["drafts"].items():
            link = key["cases"][case_id][slot]
            draft = json.loads((output / "artifacts" / case_id / link["release"] / "draft.json").read_text())
            proposal = draft["proposal"]
            if (draft["run_id"] != link["draft_run_id"] or proposal["sha256"] != link["draft_sha256"]
                    or digest({k: v for k, v in proposal.items() if k != "sha256"}) != proposal["sha256"]):
                raise ValueError("Review draft checksum mismatch")
            if result["decision"] not in {"ready", "needs_edits"}:
                raise ValueError("Invalid draft decision")
            seconds = result.get("seconds")
            if seconds is not None and (not isinstance(seconds, (int, float)) or not 0 <= seconds < float("inf")):
                raise ValueError("Invalid elapsed time")
            required = sum(note.get("required") is True for note in result["notes"])
            if bool(required) != (result["decision"] == "needs_edits"):
                raise ValueError("Draft decision and required edits disagree")
            notes = []
            for note in result["notes"]:
                if note["field"] not in (*COPY_FIELDS, "evidence", "poster") or note["reason"] not in REASONS:
                    raise ValueError("Invalid review note")
                evidence_index = note.get("evidence_index")
                evidence_ref = None
                if evidence_index is not None:
                    if type(evidence_index) is not int or not 0 <= evidence_index < len(proposal["evidence"]):
                        raise ValueError("Unknown evidence index")
                    evidence = proposal["evidence"][evidence_index]
                    evidence_ref = {key: evidence[key] for key in ("scope", "quote", "page_url", "body_sha256")}
                change = note.get("replacement", "")
                verdict = "NO_REPLACEMENT"
                if change:
                    if note["field"] not in COPY_FIELDS:
                        raise ValueError("Copy replacement requires a copy field")
                    from pydantic import ValidationError
                    try:
                        edit = review_input(proposal["brief"], {"field": note["field"], "text": change})
                        trace = CampaignTrace(mode=proposal["planner"]["source_mode"], emit=True)
                        trace.telemetry.trace_id = link["trace_id"]
                        updated = review_draft(proposal, edit, trace=trace)
                    except (CampaignConflict, ValidationError) as exc:
                        verdict = str(exc) if isinstance(exc, CampaignConflict) else "INVALID_COPY"
                    else:
                        package = updated["package"]
                        observed = package["caption"] if note["field"] == "caption" else package["copy"][note["field"]]
                        verdict = "GATE_ACCEPTED_NEEDS_SOURCE_REVIEW" if observed == change else "EDIT_OUTPUT_MISMATCH"
                notes.append({**note, "evidence": evidence_ref, "copy_check": verdict})
            recorded[case_id]["drafts"][slot] = {
                **result, **link, "evidence_sha256": digest(proposal["evidence"]),
                "required_edits": required, "notes": notes,
            }
    checker = {"commit": code_commit(), "files": {path: implementation_hash(path) for path in (
        "strategy/campaign_copy.py", "strategy/campaign_planner.py", "strategy/campaign_editions.py",
    )}}
    print(json.dumps({"packet_id": key["packet_id"], "reviewer": form["reviewer"],
                      "verification_build": checker,
                      "reviewer_role": reviewer_role, "conditions": form["conditions"],
                      "checked_at": datetime.now(timezone.utc).isoformat(), "reviews": recorded},
                     ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--verify-notes", type=Path)
    parser.add_argument("--reviewer-role", choices=("human", "automated"), default="human")
    args = parser.parse_args()
    output = args.output.resolve()
    if args.verify_notes:
        demo.isolate()
        verify_notes(output, args.verify_notes, reviewer_role=args.reviewer_role)
        return
    output.mkdir(parents=True, exist_ok=False)
    gate_path = output / "replay.json"
    subprocess.run([sys.executable, "-m", "workflows.campaign_eval", "--output", str(gate_path)], check=True, cwd=ROOT)
    gate = json.loads(gate_path.read_text())
    cases = {case["id"]: case for case in case_set()[0]}
    demo.isolate()
    command = [sys.executable, "-m", "workflows.public_campaign_demo"]
    with TemporaryDirectory(prefix="adzy-editing-") as directory:
        runtime = Path(directory)
        state = runtime / "state"
        subprocess.run([*command, "init", "--directory", str(state)], check=True, cwd=ROOT, stdout=subprocess.DEVNULL)
        try:
            app = LocalCampaign(runtime)
            try:
                drafts, rollback = exercise(app, cases)
            finally:
                app.client.close()
            export_packets(output, gate, cases, drafts, rollback)
        finally:
            if (runtime / "server.log").exists():
                log = (runtime / "server.log").read_text(encoding="utf-8")
                write_json(output / "trace.json", list(events(log.splitlines())))
            subprocess.run([*command, "cleanup", "--directory", str(state)], check=True, cwd=ROOT)
    print(output / "blind" / "index.html")


if __name__ == "__main__":
    main()
