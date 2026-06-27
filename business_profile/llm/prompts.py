"""Prompt templates for LLM extraction groups.

Each group's prompt makes the same hard rules explicit:

1. Every claim MUST cite block_ids from the provided pack.
2. Never invent a block_id; never quote text that's not in the input.
3. If no evidence exists, return value=null (or [] for lists).
4. Quotes must be verbatim substrings of the cited block's text.

The system prompt is shared across all groups. The user prompt
embeds the pack + group-specific instructions.
"""
from __future__ import annotations

from .evidence_pack import EvidencePack


SYSTEM_PROMPT = """You are a business profile extractor. You read structured text blocks scraped from a business's website and produce a strictly-evidenced profile.

ABSOLUTE RULES:
1. EVERY value you emit must be backed by evidence from the provided text blocks.
2. EVERY evidence entry must cite a block_id that appears EXACTLY as written in the input.
3. EVERY quote must be a verbatim substring of the cited block's text. Do not paraphrase quotes.
4. NEVER invent block_ids. NEVER quote text that isn't in the input.
5. If a field has no supporting evidence, return value=null (or an empty list for list fields). Do not guess.
6. Prefer extracted facts over inferred ones. When a field is inferred from copy rather than directly stated, you may still emit it, but you must cite the blocks that support the inference.
7. Keep quotes short (under 200 characters). Truncate longer blocks to the most relevant substring.
8. Be conservative. "We are the best" alone is not a value proposition — it must be paired with specifics.
"""


def _format_pack_for_prompt(pack: EvidencePack, max_chars: int = 30_000) -> str:
    """Render the pack as text the LLM reads from."""
    return pack.as_llm_text(max_chars=max_chars)


def _common_header(pack: EvidencePack) -> str:
    return (
        f"Source URL: {pack.source_url}\n"
        f"Languages detected: {', '.join(pack.languages) or 'unknown'}\n"
        f"Missing fields (what rules could not fill): {', '.join(pack.missing_fields) or 'none'}\n"
        f"\nTEXT BLOCKS (each line is one block in the format: [block_id] (metadata) \"text\"):\n"
    )


# ---------------------------------------------------------------------
# Identity group: tagline, description, category
# ---------------------------------------------------------------------

CATEGORY_VALUES = (
    "restaurant", "cafe", "clinic", "hospital", "retail", "ecommerce",
    "services_b2b", "services_b2c", "education", "government", "agency",
    "hospitality", "real_estate", "professional_services", "fitness",
    "beauty", "automotive", "nonprofit", "other",
)


def build_identity_prompt(pack: EvidencePack) -> str:
    return (
        _common_header(pack)
        + _format_pack_for_prompt(pack)
        + "\n\nEXTRACT:\n"
        + "1. tagline: a single concise self-description, ideally from a homepage h1/h2 above_fold. Verbatim from the page.\n"
        + "2. description: a 2-3 sentence summary of what the business does, who it serves, and where. Synthesize from multiple blocks; cite all blocks used.\n"
        + f"3. category: choose ONE from this fixed list: {', '.join(CATEGORY_VALUES)}. Pick the most specific that fits. If none clearly fit, return 'other'.\n"
        + "\nFor each field, return value, evidence (list of block_id+quote), confidence (high/medium/low/none), and a short reasoning string."
    )


# ---------------------------------------------------------------------
# Offerings group: offerings[], pricing_posture
# ---------------------------------------------------------------------

PRICING_POSTURE_VALUES = ("budget", "mid", "premium", "unknown")


# Per-category guidance — picked at prompt-build time based on the
# rules-derived category. When category is unknown, the GENERIC block runs.
# Each block describes what counts as an "offering" for that category.
# Single prompt, swappable guidance — no per-category code branches.
_OFFERINGS_GUIDANCE: dict[str, str] = {
    "clinic": (
        "This is a CLINIC / MEDICAL CENTER. Offerings include:\n"
        "  - medical services, treatments, procedures\n"
        "  - specialties (cardiology, dermatology, etc.)\n"
        "  - consultations, diagnostic services\n"
        "  - packages or bundled care plans when named\n"
        "Look in services pages, treatments pages, and homepage for "
        "named specialties or service descriptions."
    ),
    "hospital": (
        "This is a HOSPITAL. Offerings include medical services, "
        "specialty departments, treatments, and care programs."
    ),
    "restaurant": (
        "This is a RESTAURANT or CAFE. Offerings are the SPECIFIC named items the "
        "page actually lists:\n"
        "  - named signature dishes / menu items (verbatim from the menu)\n"
        "  - named menu sections, ONLY when no individual dishes are listed\n"
        "  - service modes the brand explicitly states: delivery, takeaway, "
        "catering, dine-in — only if a section mentions it\n"
        "Do NOT emit a bare cuisine adjective, the word 'menu', or the brand name "
        "as an offering. Each offering must cite a block_id with its quote."
    ),
    "cafe": (
        "This is a CAFE. Same guidance as restaurants — coffee, drinks, "
        "pastries, breakfast items, dining experience, delivery, branches."
    ),
    "education": (
        "This is an EDUCATION or TRAINING INSTITUTE. Offerings include:\n"
        "  - courses (specific titles when listed)\n"
        "  - programs, diplomas, degrees, certificates\n"
        "  - training tracks, academies, specializations\n"
        "  - workshops, bootcamps\n"
        "  - research or applied-services lines when described\n"
        "Look in courses, programs, admissions, and academic pages."
    ),
    "ecommerce": (
        "This is an ECOMMERCE / PRODUCT BRAND. Offerings include:\n"
        "  - product categories (e.g., 'sofas', 'bean bags')\n"
        "  - collections by name\n"
        "  - best sellers and signature products when called out\n"
        "  - bundles, subscriptions\n"
        "  - explicitly-stated product benefits (only when the page "
        "asserts them — do not invent benefits)\n"
        "  - delivery / shipping options when described\n"
        "Avoid returning every SKU; pick category- or collection-level "
        "offerings unless an individual product is featured."
    ),
    "retail": (
        "This is a RETAIL business. Same as ecommerce: product categories, "
        "collections, signature lines, store-level offerings, branches."
    ),
    "beauty": (
        "This is a BEAUTY / SKINCARE / COSMETICS brand or salon.\n"
        "  - For salons: services (facials, treatments, manicures, etc.)\n"
        "  - For brands: product categories (skincare, haircare, makeup), "
        "collections, signature products\n"
        "  - Avoid clinical claims unless explicit in the source text."
    ),
    "services_b2b": (
        "This is a B2B SERVICE BUSINESS. Offerings include:\n"
        "  - service lines (consulting, audit, implementation)\n"
        "  - packages, retainers, fixed-scope engagements\n"
        "  - industry specializations when named"
    ),
    "professional_services": (
        "This is a PROFESSIONAL SERVICES firm (legal, accounting, "
        "consulting). Offerings are practice areas, service lines, "
        "advisory packages, and named expertise."
    ),
    "agency": (
        "This is an AGENCY. Offerings are service lines, capabilities, "
        "packages, and named expertise (e.g., 'SEO', 'brand identity')."
    ),
    "fitness": (
        "This is a FITNESS business. Offerings: classes, memberships, "
        "personal training, programs, and named amenities."
    ),
    "hospitality": (
        "This is a HOSPITALITY business. Offerings: room types, packages, "
        "experiences, dining options, and amenities."
    ),
    "real_estate": (
        "This is a REAL ESTATE business. Offerings: property listings "
        "by type, services (rental, sales, management)."
    ),
    "automotive": (
        "This is an AUTOMOTIVE business. Offerings: vehicle categories, "
        "services (sales, leasing, maintenance), named brands."
    ),
    "nonprofit": (
        "This is a NONPROFIT or NGO. Offerings: programs, initiatives, "
        "services to beneficiaries, named campaigns."
    ),
    "government": (
        "This is a GOVERNMENT entity. Offerings: public services, "
        "programs, departments, named initiatives."
    ),
    "_generic": (
        "Offerings are anything this organization provides to its "
        "audience: services, products, courses, programs, menu items, "
        "experiences, memberships, locations of service. Pick the most "
        "prominent set. Each must cite block_id evidence."
    ),
}


# Universal blacklist of claims that must not be inferred — only accepted
# when the cited quote LITERALLY contains the claim token. The validator
# enforces this; the prompt warns the LLM in advance to reduce wasted
# generations.
UNSUBSTANTIATED_CLAIM_TOKENS = (
    # Dietary / religious
    "halal", "kosher", "vegan", "vegetarian", "gluten-free", "gluten free",
    "sugar-free", "sugar free", "keto", "paleo",
    # Health
    "organic", "healthy", "nutritious", "low-calorie", "low calorie",
    "all-natural", "all natural",
    # Certification
    "certified", "iso", "iso-9001", "iso 9001", "haccp", "usda",
    "fda-approved", "fda approved", "medical-grade", "medical grade",
    # Medical efficacy (skincare/beauty caution)
    "clinically proven", "scientifically proven", "dermatologist-approved",
    "dermatologist approved", "hypoallergenic",
)


def _category_key(rules_category: Optional[str]) -> str:
    """Map a profile category (or None) to a guidance key."""
    if not rules_category:
        return "_generic"
    key = rules_category.lower().strip()
    return key if key in _OFFERINGS_GUIDANCE else "_generic"


def build_offerings_prompt(
    pack: EvidencePack,
    rules_category: Optional[str] = None,
) -> str:
    """Build the universal offerings prompt.

    The prompt is single — only the category guidance block is swapped
    based on rules_category. Pass the rules-derived category (which may
    be from schema.org or None). Passing None falls through to generic
    guidance.
    """
    guidance = _OFFERINGS_GUIDANCE[_category_key(rules_category)]

    return (
        _common_header(pack)
        + _format_pack_for_prompt(pack)
        + "\n\nWHAT THIS ORGANIZATION OFFERS TO ITS AUDIENCE\n"
        + "============================================\n"
        + guidance
        + "\n\nUNIVERSAL RULES FOR OFFERINGS:\n"
        + "- Each offering has: name (short, verbatim or close to verbatim), "
        "short_description (one sentence when available), price_text "
        "(verbatim if shown; null otherwise), and evidence "
        "(blocks that support its existence).\n"
        + "- Look in services/products/menu/pricing/booking/courses/"
        "programs/branches pages first; homepage second.\n"
        + "- Skip blog-post titles and generic mentions.\n"
        + "- Cap: at most 12 offerings — pick the most prominent.\n"
        + "- Prefer SPECIFIC named offerings (actual dish / service / program / "
        "product names the page lists). If only broad categories exist, capture at "
        "most 1-2 of them; if nothing concrete is listed, return an EMPTY list — "
        "honest-empty is better than padding.\n"
        + "- NEVER emit the business's OWN NAME as an offering, and never emit vague "
        "filler ('menu', 'our services', 'diverse menu', 'special menu', 'products', "
        "'offerings') as an offering name.\n\n"
        + "FORBIDDEN CLAIMS (must NOT be inferred):\n"
        + "Do not invent dietary, health, certification, or medical-efficacy "
        "claims. Words like halal, vegan, gluten-free, organic, "
        "healthy, certified, ISO, clinically proven, dermatologist-approved "
        "must NEVER appear in an offering's name or description unless "
        "the cited quote LITERALLY contains them. The validator will "
        "reject any unsupported claim.\n\n"
        + f"PRICING POSTURE: choose one of {', '.join(PRICING_POSTURE_VALUES)}.\n"
        + "  - 'premium' = explicit positioning language "
        "('luxury', 'exclusive', 'world-class') OR high visible prices.\n"
        + "  - 'budget' = explicit affordability language "
        "('affordable', 'best value') OR low prices.\n"
        + "  - 'mid' = neutral positioning, mid-range prices.\n"
        + "  - 'unknown' = no clear signal.\n"
        + "  Cite the specific blocks justifying the posture."
    )


# ---------------------------------------------------------------------
# Positioning group: audience_type, audience_signals[], value_propositions[], tone_of_voice
# ---------------------------------------------------------------------

AUDIENCE_TYPE_VALUES = ("B2C", "B2B", "B2G", "mixed", "unknown")
TONE_VALUES = (
    "formal", "professional", "friendly", "casual",
    "playful", "luxury", "clinical", "inspirational", "unknown",
)


def build_positioning_prompt(pack: EvidencePack) -> str:
    return (
        _common_header(pack)
        + _format_pack_for_prompt(pack)
        + "\n\nEXTRACT:\n"
        + f"1. audience_type: one of {', '.join(AUDIENCE_TYPE_VALUES)}.\n"
        + "   - 'B2C' = direct-to-consumer signals (individual customers, personal pronouns, retail prices)\n"
        + "   - 'B2B' = business buyer signals (enterprise, corporate, partnerships, RFQs)\n"
        + "   - 'B2G' = government clients (ministries, public sector, tenders)\n"
        + "   - 'mixed' = clear signals for two or more\n"
        + "   - 'unknown' = no clear signal\n"
        + "2. audience_signals: short phrases (3-8 words) that describe the audience the copy is speaking to. Examples: 'young professionals in Cairo', 'pregnant mothers', 'enterprise IT teams'. Cap at 5 items, most specific first. Each item must cite the blocks it came from.\n"
        + "3. value_propositions: the distinctive promises the business makes — what differentiates them. Each is a short phrase (5-15 words). Skip generic claims like 'high quality' unless paired with specifics. Cap at 5 items. Each must cite evidence.\n"
        + f"4. tone_of_voice: one of {', '.join(TONE_VALUES)}. Based on word choice across multiple blocks (formality, jargon, warmth, imagery). Cite 2-3 representative blocks.\n"
        + "5. other_unique_insights: a CATCH-ALL for a genuinely UNIQUE competitive edge or "
        "operational detail that does NOT fit the fields above — e.g. a stated differentiator "
        "('the only X in the city'), an unusual guarantee/policy, a notable scale fact, a "
        "distinctive process. STRICT: each must be a CONCRETE FACT stated on the page (cite "
        "block_id + verbatim quote), NOT your opinion or a generic strength. If nothing "
        "genuinely unique stands out, return an EMPTY list. Cap at 3 items."
    )


# ---------------------------------------------------------------------
# Trust group: trust_signals[], service_areas[]
# ---------------------------------------------------------------------

def build_trust_prompt(pack: EvidencePack) -> str:
    return (
        _common_header(pack)
        + _format_pack_for_prompt(pack)
        + "\n\nEXTRACT:\n"
        + "1. trust_signals: concrete proof points that build credibility. Examples:\n"
        + "   - certifications ('ISO 9001 certified', 'Board-certified')\n"
        + "   - awards ('Best Restaurant 2023')\n"
        + "   - notable clients or partners ('Trusted by Aramco, Vodafone')\n"
        + "   - tenure ('15 years in business', 'founded in 2008')\n"
        + "   - team credentials ('Harvard-trained surgeons')\n"
        + "   - testimonials (only when a real quote with attribution is present)\n"
        + "   Each is one short phrase. Skip vague self-praise. Cap at 8 items.\n"
        + "2. service_areas: geographic regions the business explicitly serves. Cities, districts, countries. Example: ['Cairo', 'Giza', 'Alexandria']. Skip mailing addresses — only places they say they SERVE. Cap at 10 items."
    )
