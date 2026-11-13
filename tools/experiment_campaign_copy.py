"""Bounded text-only experiments. Use a persistent ledger directory for this task."""
import argparse
from fcntl import LOCK_EX, flock
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path
from time import monotonic
from zipfile import ZipFile

from openai import APIStatusError, OpenAI


ROOT = Path(__file__).resolve().parents[1]
MODEL = "gpt-4o-mini-2024-07-18"
PRICE_IN, PRICE_OUT = Decimal("0.15"), Decimal("0.60")
RESERVE = Decimal("0.01")
CAP = Decimal("10")


def inputs(path):
    with ZipFile(path) as archive:
        proposal = json.loads(archive.read("campaign.json"))["proposal"]
    brief = proposal["brief"]
    decision = proposal["planner"]["options"][brief["selected"]]
    return {
        "brief": {k: brief[k] for k in ("objective", "summary", "audience", "language", "tone", "strategy_reason")},
        "evidence": [{k: e.get(k) for k in ("page_url", "label", "quote", "context", "constraints")}
                     for e in proposal["evidence"]],
        "destination": decision["destination"], "action": decision["action"],
        "baseline": proposal["package"]["copy"],
    }


def save(path, item):
    with path.open("x", encoding="utf-8") as output:
        json.dump(item, output, ensure_ascii=False, indent=2)
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())


def exposure(directory):
    total = Decimal(0)
    for intent in directory.glob("*.dispatch.json"):
        receipt = intent.with_name(intent.name.replace(".dispatch.", ".receipt."))
        if receipt.exists():
            result = json.loads(receipt.read_text())
            if result["estimated_charge"] is not None:
                total += Decimal(result["estimated_charge"])
                continue
        total += RESERVE
    return total


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--provider", choices=("openai", "anthropic", "vertex"), default="openai")
    parser.add_argument("--round", required=True, choices=("development", "heldout", "compact"))
    parser.add_argument("packages", nargs="+", type=Path)
    args = parser.parse_args()
    if len(args.packages) > 4:
        parser.error("at most four text requests in a batch")
    args.ledger.mkdir(exist_ok=True, parents=True)
    lock = (args.ledger / ".lock").open("a")
    flock(lock, LOCK_EX)
    compact = args.round != "development"
    output_limit = 1300 if compact else 650
    prompt_name = "WRITER_COMPACT.txt" if compact else "WRITER.txt"
    prompt = (ROOT / "docs/campaigns/quality" / prompt_name).read_text()
    from dotenv import dotenv_values

    provider = args.provider
    settings = dotenv_values(args.key_file)
    token = settings.get(f"{provider.upper()}_API_KEY")
    model = MODEL if provider == "openai" else "claude-haiku-4-5-20251001"
    rates = (PRICE_IN, PRICE_OUT) if provider == "openai" else (Decimal("1"), Decimal("5"))
    if provider == "vertex":
        from google import genai
        from google.genai import types

        model = "gemini-3.1-flash-lite"
        rates = Decimal("0.45"), Decimal("2.70")
        vertex = genai.Client(vertexai=True, project=settings["GOOGLE_CLOUD_PROJECT"], location="global",
                              http_options=types.HttpOptions(timeout=35000, retry_options=types.HttpRetryOptions(attempts=1)))
    if provider != "vertex" and not token:
        parser.error("missing OpenAI credential")
    client = OpenAI(api_key=token, max_retries=0, timeout=35.0) if provider == "openai" else None
    for package in args.packages:
        label = f"{args.round}-{package.parent.name}" + ("" if client else f"-{provider}")
        intent = args.ledger / f"{label}.dispatch.json"
        if intent.exists():
            print(label, "already attempted", flush=True)
            continue
        spec = inputs(package)
        wire = json.dumps({k: v for k, v in spec.items() if k != "baseline"}, ensure_ascii=False)
        if len((prompt + wire).encode()) > 8000:
            raise ValueError("input exceeds experiment bound")
        before = exposure(args.ledger)
        if before + RESERVE > CAP:
            raise RuntimeError("task spend cap")
        save(intent, {"model": model, "prompt_sha256": sha256(prompt.encode()).hexdigest(),
                      "input": spec, "output_limit": output_limit, "reserve_usd": str(RESERVE), "task_exposure_before": str(before)})
        started = monotonic()
        result = {"outcome": "UNKNOWN", "estimated_charge": None}
        try:
            if client:
                response = client.chat.completions.create(
                    model=model, messages=[{"role": "system", "content": prompt}, {"role": "user", "content": wire}],
                    max_completion_tokens=output_limit, temperature=0.5, response_format={"type": "json_object"}, store=False,
                )
                choice = response.choices[0]
                content, finish, used_in, used_out = (choice.message.content, choice.finish_reason,
                    response.usage.prompt_tokens, response.usage.completion_tokens)
                resolved = response.model
            elif provider == "vertex":
                from google.genai import errors

                try:
                    response = vertex.models.generate_content(
                        model=model, contents=wire, config=types.GenerateContentConfig(
                            system_instruction=prompt, max_output_tokens=output_limit, temperature=0.5,
                            response_mime_type="application/json",
                            thinking_config=types.ThinkingConfig(thinking_level="MINIMAL"),
                        ),
                    )
                except errors.APIError as error:
                    result.update(outcome="REJECTED", http_status=error.code, code=error.status)
                    raise
                content, finish, resolved = response.text, response.candidates[0].finish_reason.value, response.model_version
                usage = response.usage_metadata
                used_in = usage.prompt_token_count
                used_out = (usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0)
            else:
                body = {"model": model, "system": prompt, "max_tokens": output_limit, "temperature": 0.5,
                        "messages": [{"role": "user", "content": wire}]}
                request = Request("https://api.anthropic.com/v1/messages", json.dumps(body).encode(),
                                  {"x-api-key": token, "anthropic-version": "2023-06-01", "Content-Type": "application/json"})
                with urlopen(request, timeout=35) as reply:
                    response = json.load(reply)
                content = "".join(block["text"] for block in response["content"] if block["type"] == "text")
                finish, resolved = response["stop_reason"], response["model"]
                used_in, used_out = response["usage"]["input_tokens"], response["usage"]["output_tokens"]
            cost = (rates[0] * used_in + rates[1] * used_out) / 1_000_000
            result.update(outcome="COMPLETE" if finish in {"stop", "end_turn", "STOP"} else "TRUNCATED",
                          content=content, finish_reason=finish, model=resolved,
                          prompt_tokens=used_in, completion_tokens=used_out, estimated_charge=str(cost))
        except HTTPError as error:
            result.update(outcome="REJECTED", http_status=error.code)
        except APIStatusError as error:
            result.update(outcome="REJECTED", http_status=error.status_code, code=error.code)
        except Exception as error:
            result["error_class"] = type(error).__name__
        result["seconds"] = round(monotonic() - started, 2)
        save(args.ledger / f"{label}.receipt.json", result)
        print(label, result["outcome"], result.get("http_status"), result["estimated_charge"],
              "remaining_after_reserve", str(CAP - exposure(args.ledger)), flush=True)
        if result["outcome"] in {"REJECTED", "UNKNOWN"}:
            break


if __name__ == "__main__":
    main()
