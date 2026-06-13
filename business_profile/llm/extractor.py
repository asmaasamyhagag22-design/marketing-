"""LLM extractor: runs grouped extraction calls and aggregates results.

This module is the LLM layer's main entry point. It:
1. Builds prompts per group using the evidence pack.
2. Calls the caller for each group (4 calls total).
3. Returns raw LLM responses + aggregate usage info.

It does NOT validate evidence or merge into the BusinessProfile.
Those happen in step 5 (validator) and step 6 (merger). Keeping
this module pure orchestration means we can swap callers (real vs
mock) and the rest of the pipeline doesn't care.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from .caller import Caller, Usage
from .evidence_pack import EvidencePack
from .prompts import (
    SYSTEM_PROMPT,
    build_identity_prompt,
    build_offerings_prompt,
    build_positioning_prompt,
    build_trust_prompt,
)
from .responses import (
    IdentityResponse,
    OfferingsResponse,
    PositioningResponse,
    TrustResponse,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# Aggregate result
# ---------------------------------------------------------------------

@dataclass
class GroupResult:
    """One group's outcome — either a parsed response or an error."""
    group: str
    response: Optional[object] = None
    usage: Optional[Usage] = None
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.response is not None and self.error is None


@dataclass
class LLMExtractionResult:
    """All four groups' results, plus aggregate usage."""
    identity: GroupResult
    offerings: GroupResult
    positioning: GroupResult
    trust: GroupResult

    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    total_calls: int = 0
    total_failed: int = 0
    model: str = ""
    duration_ms: int = 0

    @property
    def all_groups(self) -> list[GroupResult]:
        return [self.identity, self.offerings, self.positioning, self.trust]


# ---------------------------------------------------------------------
# Group runner
# ---------------------------------------------------------------------

_GROUPS = (
    ("identity", IdentityResponse, build_identity_prompt),
    ("offerings", OfferingsResponse, build_offerings_prompt),
    ("positioning", PositioningResponse, build_positioning_prompt),
    ("trust", TrustResponse, build_trust_prompt),
)


def run_llm_extraction(
    pack: EvidencePack,
    caller: Caller,
    skip_if_empty_pack: bool = True,
    rules_category: Optional[str] = None,
) -> LLMExtractionResult:
    """Run all four grouped LLM calls and aggregate the results.

    rules_category: optional. The rules-derived category value (e.g.
    "restaurant", "education") used to inject per-category guidance
    into the offerings prompt. When None, the generic guidance runs.
    The other three group prompts ignore this argument.

    If the pack is empty, returns an all-empty result without making
    any API calls (saves cost on broken scrapes).
    """
    import time
    started = time.monotonic()

    # If there's nothing to read, skip LLM entirely
    if skip_if_empty_pack and pack.block_count == 0:
        logger.warning("Evidence pack is empty; skipping LLM extraction")
        empty = lambda name: GroupResult(group=name, error="empty_pack")
        return LLMExtractionResult(
            identity=empty("identity"),
            offerings=empty("offerings"),
            positioning=empty("positioning"),
            trust=empty("trust"),
            duration_ms=int((time.monotonic() - started) * 1000),
        )

    results: dict[str, GroupResult] = {}
    total_in = 0
    total_out = 0
    total_cost = 0.0
    total_calls = 0
    total_failed = 0
    model = ""

    for group_name, response_model, prompt_builder in _GROUPS:
        # Offerings prompt is category-aware (v0.2-b1). Others take pack only.
        if group_name == "offerings":
            user_prompt = prompt_builder(pack, rules_category=rules_category)
        else:
            user_prompt = prompt_builder(pack)
        try:
            response, usage = caller(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=user_prompt,
                response_model=response_model,
                group_name=group_name,
            )
            results[group_name] = GroupResult(
                group=group_name, response=response, usage=usage,
            )
            total_in += usage.input_tokens
            total_out += usage.output_tokens
            total_cost += usage.cost_usd
            total_calls += 1
            model = usage.model or model
        except Exception as e:
            logger.error("LLM group '%s' failed: %s", group_name, e)
            results[group_name] = GroupResult(
                group=group_name, error=f"{type(e).__name__}: {e}",
            )
            total_failed += 1

    return LLMExtractionResult(
        identity=results["identity"],
        offerings=results["offerings"],
        positioning=results["positioning"],
        trust=results["trust"],
        total_input_tokens=total_in,
        total_output_tokens=total_out,
        total_cost_usd=total_cost,
        total_calls=total_calls,
        total_failed=total_failed,
        model=model,
        duration_ms=int((time.monotonic() - started) * 1000),
    )
