"""LLM-based extractors and supporting code.

Pipeline order:
- evidence_pack: builds the corpus the LLM reads from
- prompts: per-group prompt templates
- responses: per-group Pydantic schemas for structured outputs
- caller: OpenAI client wrapper + Mock for tests
- extractor: orchestrates the 4 grouped calls and aggregates usage
- validator: enforces "no evidence = no fact" — drops hallucinations
"""
from .caller import Caller, MockCaller, OpenAICaller, Usage
from .evidence_pack import EvidenceBlock, EvidencePack, build_evidence_pack
from .extractor import GroupResult, LLMExtractionResult, run_llm_extraction
from .responses import (
    IdentityResponse,
    OfferingItem,
    OfferingsResponse,
    PositioningResponse,
    StringListItem,
    TrustResponse,
)
from .validator import (
    RejectionCode,
    RejectionRecord,
    ValidatedIdentity,
    ValidatedListItem,
    ValidatedOffering,
    ValidatedOfferings,
    ValidatedPayload,
    ValidatedPositioning,
    ValidatedScalarField,
    ValidatedTrust,
    ValidationDiagnostics,
    validate_llm_extraction,
)

__all__ = [
    "EvidenceBlock", "EvidencePack", "build_evidence_pack",
    "Caller", "MockCaller", "OpenAICaller", "Usage",
    "GroupResult", "LLMExtractionResult", "run_llm_extraction",
    "IdentityResponse", "OfferingsResponse", "PositioningResponse", "TrustResponse",
    "OfferingItem", "StringListItem",
    "validate_llm_extraction", "ValidatedPayload",
    "ValidatedIdentity", "ValidatedOfferings", "ValidatedPositioning", "ValidatedTrust",
    "ValidatedOffering", "ValidatedScalarField", "ValidatedListItem",
    "ValidationDiagnostics",
    "RejectionCode", "RejectionRecord",
]
