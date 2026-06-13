"""Full Business Profile pipeline orchestrator.

Steps:
1. Load manifest from disk (or accept a parsed manifest).
2. Run rule-based extractors -> partial BusinessProfile.
3. Build evidence pack from manifest + rules profile.
4. Run grouped LLM extraction (4 calls).
5. Validate every LLM-cited block_id and quote.
6. Merge validated payload into the rules profile.
7. Return final BusinessProfile (and the diagnostics if asked).

Two callers:
- `build_profile(manifest_path, caller)` — full pipeline, returns profile
- `build_profile_no_llm(manifest_path)` — rules only, for offline runs

Typical usage:

    from business_profile.build import build_profile
    from business_profile.llm.caller import OpenAICaller

    profile = build_profile(
        "scrapes/spclinic_net_.../manifest.json",
        caller=OpenAICaller(model="gpt-4o-mini"),
    )
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

from scraper.schemas import ScrapeManifest

from .llm.caller import Caller
from .llm.evidence_pack import EvidencePack, build_evidence_pack
from .llm.extractor import LLMExtractionResult, run_llm_extraction
from .llm.validator import ValidatedPayload, validate_llm_extraction
from .merger import merge_profile
from .rules.orchestrator import apply_rules
from .schemas import BusinessProfile

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# Result wrapper (full pipeline detail for debugging)
# ---------------------------------------------------------------------

@dataclass
class BuildResult:
    """Full pipeline output, including intermediates for debugging."""
    profile: BusinessProfile
    pack: EvidencePack
    llm_result: Optional[LLMExtractionResult]
    payload: Optional[ValidatedPayload]


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def _load_manifest(source: Union[str, Path, ScrapeManifest]) -> tuple[ScrapeManifest, str, str]:
    """Accept either a manifest path or a parsed manifest. Returns
    (manifest, path_string, manifest_hash)."""
    if isinstance(source, ScrapeManifest):
        return source, "<in-memory>", ""
    path = Path(source)
    raw = path.read_text(encoding="utf-8")
    manifest = ScrapeManifest.model_validate_json(raw)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return manifest, str(path), digest


def _diagnostics_from_manifest(manifest: ScrapeManifest):
    """Convert scraper-side ScrapeDiagnostics → business_profile-side
    ScrapeDiagnostics (the input shape for compute_readiness).

    Two different classes intentionally — the scraper-side carries
    additional fields (sitemap_urls_found) that the readiness layer
    doesn't need to know about. Returns None when the manifest carries
    no diagnostics (e.g. legacy manifests written before PR-1).
    """
    src = getattr(manifest, "scrape_diagnostics", None)
    if src is None:
        return None
    # Lazy import — avoids circular import risk
    from .schemas import ScrapeDiagnostics as ProfileScrapeDiagnostics
    return ProfileScrapeDiagnostics(
        pages_discovered=src.pages_discovered,
        pages_scraped=src.pages_scraped,
        pages_with_text_blocks=src.pages_with_text_blocks,
        pages_failed=src.pages_failed,
        sitemap_used=src.sitemap_used,
        js_rendering_used=src.js_rendering_used,
    )


# ---------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------

def build_profile_no_llm(
    source: Union[str, Path, ScrapeManifest],
) -> BusinessProfile:
    """Run only the rule-based extractors. No network calls."""
    manifest, path, digest = _load_manifest(source)
    profile = apply_rules(manifest, manifest_path=path)
    if digest:
        profile.extraction_meta.manifest_hash = digest
    # v0.2-b1: rules-only runs intentionally skip the LLM, so offerings
    # are always empty. Set the note so the frontend can render an
    # honest message (vs. a generic "LLM failed").
    if len(profile.offerings) == 0:
        profile.offerings_extraction_note = "llm_skipped"
    # PR-1: even on the rules-only path, attach readiness so the API
    # consumer sees a consistent shape. Diagnostics are passed through
    # so single-page-evidence detection works here too.
    from .readiness import compute_readiness
    profile.readiness = compute_readiness(
        profile,
        scrape_diagnostics=_diagnostics_from_manifest(manifest),
    )
    return profile


def build_profile(
    source: Union[str, Path, ScrapeManifest],
    caller: Caller,
    *,
    return_details: bool = False,
) -> Union[BusinessProfile, BuildResult]:
    """Run the full pipeline. Returns the final BusinessProfile.

    If return_details=True, returns a BuildResult that exposes the
    intermediate pack, LLM result, and validated payload — useful for
    debugging and for the CLI's verbose mode.
    """
    manifest, path, digest = _load_manifest(source)

    # 1. Rules
    rules_profile = apply_rules(manifest, manifest_path=path)
    if digest:
        rules_profile.extraction_meta.manifest_hash = digest

    # 2. Pack
    pack = build_evidence_pack(manifest, rules_profile)
    logger.info(
        "Evidence pack: %d blocks (from %d in manifest, %d after filter)",
        pack.block_count, pack.blocks_total_in_manifest, pack.blocks_after_filter,
    )

    # 3. LLM extract
    # Pass the rules-derived category (if any) so the offerings prompt
    # can swap in per-category guidance. None → generic guidance.
    rules_category_value = (
        rules_profile.category.value.value
        if rules_profile.category.value is not None
        else None
    )
    llm_result = run_llm_extraction(
        pack, caller, rules_category=rules_category_value,
    )
    logger.info(
        "LLM extraction: %d/4 calls ok, $%.4f, %d input + %d output tokens",
        llm_result.total_calls, llm_result.total_cost_usd,
        llm_result.total_input_tokens, llm_result.total_output_tokens,
    )

    # 4. Validate
    payload = validate_llm_extraction(llm_result, pack)
    logger.info(
        "Validation: %d rejections, %d fields dropped, %d items dropped",
        payload.diagnostics.total_rejections,
        len(payload.diagnostics.fields_dropped),
        payload.diagnostics.total_items_dropped,
    )

    # 5. Merge
    final_profile = merge_profile(
        rules_profile, payload, llm_result, expected_llm=True,
        scrape_diagnostics=_diagnostics_from_manifest(manifest),
    )
    if digest:
        final_profile.extraction_meta.manifest_hash = digest

    if return_details:
        return BuildResult(
            profile=final_profile, pack=pack,
            llm_result=llm_result, payload=payload,
        )
    return final_profile


def write_profile(
    profile: BusinessProfile, output_path: Union[str, Path],
) -> Path:
    """Write the profile as pretty JSON. Returns the path."""
    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        profile.model_dump_json(indent=2, exclude_none=False),
        encoding="utf-8",
    )
    return p