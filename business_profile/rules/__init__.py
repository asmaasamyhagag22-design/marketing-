"""Rule-based extractors. Run before any LLM call.

Each module returns either an EvidencedField, a list, or a sub-model
fragment. The orchestrator (build.py) composes them into a partial
BusinessProfile.

Rule philosophy:
- High confidence by construction (we control the rule)
- block_id=None is OK when evidence is structural (schema.org, og tag)
- For aggregate observations (e.g. "no pricing found"), use the
  extractor field to carry the reasoning, page_url="<aggregate>"
"""
