"""Human-readable run logs — a PRODUCT layer on top of the U7 telemetry JSONL.

Phase 0 of the client-deliverable mission (owner directive: "a logs/ folder where every
project step is inspectable"). This module does NOT instrument anything new — it READS the
existing `runs/<run_id>/telemetry.jsonl` (RunTelemetry) and renders:
  * logs/<run_id>/<brand>.log  — plain-language, bilingual step lines a non-engineer reads;
  * logs/INDEX.md              — one row per run (run · brand · date · outcome · link);
  * a cost/latency summary the dashboard surfaces (per-run spend, from telemetry cost_usd).

Everything degrades to a graceful empty result — a missing/partial telemetry file never
raises. Pure read + append; safe to call after any run.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

# Stage id -> (Arabic plain label, English plain label). Unknown stages fall back to a
# cleaned-up id. Kept deliberately business-plain (no jargon) — this is client-inspectable.
_STAGE_LABELS: dict[str, tuple[str, str]] = {
    "scrape": ("قراءة موقع البراند", "Reading the brand's website"),
    "crawl": ("تصفّح صفحات الموقع", "Crawling the site pages"),
    "extract": ("استخلاص هوية البراند", "Extracting the brand identity"),
    "profile": ("بناء ملف البراند", "Building the brand profile"),
    "business_profile": ("بناء ملف البراند", "Building the brand profile"),
    "competitors": ("اكتشاف المنافسين", "Discovering competitors"),
    "discovery": ("اكتشاف المنافسين", "Discovering competitors"),
    "swot": ("تحليل نقاط القوة والضعف", "SWOT analysis"),
    "tows": ("اشتقاق الاستراتيجيات", "Deriving strategies (TOWS)"),
    "market_definition": ("تعريف السوق", "Defining the market"),
    "media_plan": ("بناء خطة الشراء الإعلاني", "Building the media plan"),
    "content_calendar": ("جدولة المحتوى", "Scheduling content"),
    "calendar": ("جدولة المحتوى", "Scheduling content"),
    "trends": ("رصد اتجاهات السوق", "Reading market trends"),
    "reviews": ("قراءة آراء العملاء", "Reading customer reviews"),
    "absa": ("تحليل صوت العملاء", "Analyzing customer voice"),
    "poster": ("تصميم البوستر", "Designing the poster"),
    "reel": ("إنتاج الريل", "Producing the reel"),
    "reel_scene_qa": ("مراجعة جودة مشاهد الريل", "Reviewing reel scene quality"),
    "reel_seed_gate": ("مراجعة الإطارات قبل التحريك", "Vetting frames before animation"),
    "dashboard": ("تجميع لوحة العرض", "Assembling the dashboard"),
}

_STATUS_AR = {"ok": "تم", "error": "تعذّر", "skip": "تخطّي", "skipped": "تخطّي"}
_STATUS_EN = {"ok": "done", "error": "could not complete", "skip": "skipped",
              "skipped": "skipped"}


def _label(stage: str) -> tuple[str, str]:
    if stage in _STAGE_LABELS:
        return _STAGE_LABELS[stage]
    clean = stage.replace("_", " ").strip().title()
    return clean, clean


def read_run(run_id: str, *, runs_dir: str = "runs") -> list[dict]:
    """The telemetry rows of one run, in order. [] when the file is missing/unreadable."""
    p = Path(runs_dir) / run_id / "telemetry.jsonl"
    if not p.is_file():
        return []
    rows: list[dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except Exception:  # noqa: BLE001
            continue
    return rows


def run_cost(run_id: str, *, runs_dir: str = "runs") -> dict:
    """Per-run spend/latency summary the dashboard surfaces (telemetry census gap: cost was
    tracked but never shown). All-honest: zeros when nothing recorded a cost."""
    rows = read_run(run_id, runs_dir=runs_dir)
    cost = sum(float(r.get("cost_usd") or 0.0) for r in rows)
    tin = sum(int(r.get("tokens_in") or 0) for r in rows)
    tout = sum(int(r.get("tokens_out") or 0) for r in rows)
    latency = sum(float(r.get("latency_ms") or 0.0) for r in rows)
    llm_calls = sum(1 for r in rows if r.get("model"))
    return {"run_id": run_id, "cost_usd": round(cost, 4), "tokens_in": tin,
            "tokens_out": tout, "llm_calls": llm_calls, "stages": len(rows),
            "wall_ms": round(latency, 0),
            "errors": sum(1 for r in rows if r.get("status") == "error")}


def render_run_log(run_id: str, brand: str, *, runs_dir: str = "runs",
                   logs_dir: str = "logs") -> Optional[Path]:
    """Write logs/<run_id>/<brand>.log — plain bilingual step lines. None if no telemetry."""
    rows = read_run(run_id, runs_dir=runs_dir)
    if not rows:
        return None
    out = Path(logs_dir) / run_id / f"{brand}.log"
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# {brand} — سجل التشغيل / run log", f"run: {run_id}", ""]
    for r in rows:
        ar, en = _label(str(r.get("stage") or ""))
        st = str(r.get("status") or "ok")
        ts = str(r.get("ts") or "")[11:19]
        secs = (f"  ({float(r['latency_ms']) / 1000:.1f}s)"
                if r.get("latency_ms") is not None else "")
        cost = (f"  ~${float(r['cost_usd']):.4f}" if r.get("cost_usd") else "")
        mark = {"ok": "✓", "error": "⚠", "skip": "–", "skipped": "–"}.get(st, "•")
        note = f"  — {r['note']}" if r.get("note") else ""
        lines.append(f"{ts} {mark} {ar} · {en} [{_STATUS_AR.get(st, st)}/"
                     f"{_STATUS_EN.get(st, st)}]{secs}{cost}{note}")
    summary = run_cost(run_id, runs_dir=runs_dir)
    lines += ["", "— الملخص / summary —",
              f"مراحل/stages: {summary['stages']} · نداءات ذكاء/LLM calls: "
              f"{summary['llm_calls']} · تكلفة/cost: ~${summary['cost_usd']:.4f} · "
              f"زمن/wall: {summary['wall_ms'] / 1000:.0f}s · "
              f"تعذّر/errors: {summary['errors']}"]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def update_index(run_id: str, brand: str, *, date: str = "", outcome: str = "",
                 logs_dir: str = "logs") -> None:
    """Append/refresh one row in logs/INDEX.md. `date`/`outcome` are caller-supplied
    (Date.now is unavailable to workflows; callers pass real timestamps)."""
    idx = Path(logs_dir) / "INDEX.md"
    row = (f"| {run_id} | {brand} | {date} | {outcome} | "
           f"[{brand}.log]({run_id}/{brand}.log) |")
    if not idx.is_file():
        idx.parent.mkdir(parents=True, exist_ok=True)
        idx.write_text("# Run index\n\n| run_id | brand | date (UTC) | outcome | log |\n"
                       "|--------|-------|-----------|---------|-----|\n" + row + "\n",
                       encoding="utf-8")
        return
    text = idx.read_text(encoding="utf-8")
    if run_id in text and brand in text:                    # refresh an existing row
        lines = [ln for ln in text.splitlines()
                 if not (ln.startswith(f"| {run_id} ") and f"| {brand} " in ln)]
        text = "\n".join(lines).rstrip() + "\n"
    idx.write_text(text.rstrip() + "\n" + row + "\n", encoding="utf-8")
