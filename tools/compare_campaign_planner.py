"""Replay the frozen one-shot comparator against public pages captured by the planner."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from time import monotonic
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
MODEL = "qwen3.5:9b"
BASE = "http://127.0.0.1:11434"


def source_blocks(planner):
    blocks = []
    for page in planner["pages"]:
        for entry in page["entries"][:4]:
            blocks.append({"url": page["page_url"], "heading": entry["label"],
                           "quote": entry["quote"], "context": entry["context"][:650]})
        if page["title"]:
            blocks.append({"url": page["page_url"], "title": page["title"]})
    return blocks


def compare(inputs, blocks, page_calls, prompt):
    payload = {"model": MODEL, "think": False, "stream": True, "format": "json",
               "options": {"temperature": 0, "num_predict": 420, "num_ctx": 4096, "seed": 11},
               "prompt": prompt + "\n" + json.dumps({"input": inputs, "sources": blocks}, ensure_ascii=False)}
    request = Request(BASE + "/api/generate", json.dumps(payload).encode(),
                      {"Content-Type": "application/json"})
    started = monotonic()
    raw, receipt, reason = [], {}, None
    try:
        with urlopen(request, timeout=150) as response:
            for line in response:
                event = json.loads(line)
                if event.get("error"):
                    reason = "MODEL_ERROR"
                    break
                raw.append(event.get("response", ""))
                if event.get("done"):
                    receipt = {k: event.get(k) for k in ("eval_count", "prompt_eval_count", "done_reason")}
                    break
                if monotonic() - started >= 150:
                    reason = "DEADLINE"
                    break
    except OSError as exc:
        reason = type(exc).__name__
    text = "".join(raw)
    try:
        parsed = json.loads(text)
    except ValueError:
        parsed = None
    return {"model": MODEL, "prompt_sha256": sha256(prompt.encode()).hexdigest(),
            "request_sha256": sha256(request.data).hexdigest(), "public_visits_reused": page_calls,
            "model_calls": 1, "elapsed_seconds": round(monotonic() - started, 2), "cost_usd": 0,
            "error": reason or ("INCOMPLETE_JSON" if parsed is None else None),
            "receipt": receipt, "raw": text, "parsed": parsed, "source_blocks": blocks,
            "input": inputs}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("captures", nargs="+", type=Path)
    args = parser.parse_args()
    prompt = (ROOT / "docs/campaigns/planner/DIRECT_PROMPT.txt").read_text()
    args.output.mkdir(exist_ok=True, parents=True)
    with urlopen(BASE + "/api/tags", timeout=3) as response:
        tags = json.load(response)["models"]
    model_digest = next(item["digest"] for item in tags if item["name"] == MODEL)
    for path in args.captures:
        data = json.loads(path.read_text())
        if "source_blocks" in data:
            if data["prompt_sha256"] != sha256(prompt.encode()).hexdigest() or data["model_digest"] != model_digest:
                raise ValueError("Frozen prompt or model digest changed")
            result = compare(data["input"], data["source_blocks"], data["public_visits_reused"], prompt)
            if result["request_sha256"] != data["request_sha256"]:
                raise ValueError("Frozen request changed")
        else:
            planner = data.get("proposal", {}).get("planner") or data.get("planner") or data
            result = compare(planner["input"], source_blocks(planner), planner["page_calls"], prompt)
        result["model_digest"] = model_digest
        name = f"{path.parent.name}.json" if path.name == "draft.json" else path.name
        (args.output / name).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        print(name, result["error"], result["elapsed_seconds"], result["receipt"], flush=True)


if __name__ == "__main__":
    main()
