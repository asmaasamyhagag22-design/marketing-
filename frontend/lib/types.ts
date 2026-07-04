/**
 * TypeScript types mirroring the Python backend's Pydantic schemas.
 *
 * Keep this file in sync with:
 *   - business_profile/schemas.py  (BusinessProfile + EvidencedField)
 *   - api/schemas.py               (Stage, StageStatus, JobStatus, StageEvent)
 *
 * If drift becomes a problem we'll generate these from the Pydantic
 * JSON schema. For Day 2 we hand-maintain them.
 */

// ---------------------------------------------------------------------
// Pipeline stages — single source of truth for the timeline UI.
// Includes optional future stages for the Poster Studio so the
// timeline component doesn't need refactoring when those land.
// ---------------------------------------------------------------------

export type Stage =
  | "scrape"
  | "rules"
  | "evidence_pack"
  | "llm"
  | "validate"
  | "merge"
  | "final"
  // Future stages — not emitted by Day 1 backend yet:
  | "poster_brief"
  | "image_gen"
  | "compose";

export type StageStatus = "pending" | "started" | "done" | "error";

export type JobStatus = "queued" | "running" | "succeeded" | "failed";

export interface StageMeta {
  id: Stage;
  label: string;
  description: string;
  optional?: boolean;
}

/** Stages shown in the MVP timeline (in order). */
export const MVP_STAGES: StageMeta[] = [
  {
    id: "scrape",
    label: "Scrape",
    description: "Render pages + capture evidence",
  },
  {
    id: "rules",
    label: "Rules",
    description: "Extract deterministic fields",
  },
  {
    id: "evidence_pack",
    label: "Pack",
    description: "Build LLM evidence corpus",
  },
  {
    id: "llm",
    label: "LLM",
    description: "Grouped extraction calls",
  },
  {
    id: "validate",
    label: "Validate",
    description: "Reject hallucinations",
  },
  {
    id: "merge",
    label: "Merge",
    description: "Combine rules + LLM",
  },
  {
    id: "final",
    label: "Final",
    description: "Profile ready",
  },
];

/** Future stages for Poster Studio — not in MVP timeline yet. */
export const POSTER_STAGES: StageMeta[] = [
  {
    id: "poster_brief",
    label: "Poster Brief",
    description: "Grounded poster brief",
    optional: true,
  },
  {
    id: "image_gen",
    label: "Image Gen",
    description: "Generate background (no text)",
    optional: true,
  },
  {
    id: "compose",
    label: "Compose",
    description: "Pillow overlay + final PNG",
    optional: true,
  },
];

// ---------------------------------------------------------------------
// SSE event shape
// ---------------------------------------------------------------------

export interface StageEvent {
  job_id: string;
  stage: Stage;
  status: StageStatus;
  timestamp: string;
  duration_ms: number;
  payload?: Record<string, unknown> | null;
  error?: string | null;
}

// ---------------------------------------------------------------------
// Evidence + EvidencedField
// ---------------------------------------------------------------------

export type Confidence = "high" | "medium" | "low" | "none";
export type SourceType = "extracted" | "inferred" | "missing";

export interface EvidenceItem {
  block_id: string | null;
  page_url: string;
  quote: string | null;
  extractor: string;
}

export interface EvidencedField<T = unknown> {
  value: T | null;
  evidence: EvidenceItem[];
  confidence: Confidence;
  source_type: SourceType;
}

// ---------------------------------------------------------------------
// BusinessProfile sub-shapes
// ---------------------------------------------------------------------

export interface Offering {
  name: string;
  short_description: string | null;
  price_text: string | null;
  page_url: string | null;
  evidence: EvidenceItem[];
  confidence: Confidence;
}

export interface SocialAccount {
  platform: string;
  url: string;
  evidence: EvidenceItem[];
}

export interface Location {
  label: string | null;
  address_text: string | null;
  city: string | null;
  region: string | null;
  country: string | null;
  postal_code: string | null;
  latitude: number | null;
  longitude: number | null;
  evidence: EvidenceItem[];
}

export interface PhoneChannel {
  e164: string | null;
  raw: string;
  is_short_code: boolean;
}

export interface ContactChannels {
  // The live API serializes the structured `phones` list. `phones_e164` is a
  // deprecated, non-serialized @property on the backend (kept here only for old
  // fixtures). Read `phones` first; fall back to `phones_e164`.
  phones?: PhoneChannel[];
  phones_e164?: string[];
  emails: string[];
  whatsapp_numbers: string[];
  has_contact_form: boolean;
  physical_addresses: string[];
  map_embed_present: boolean;
  evidence: EvidenceItem[];
}

export interface LogoCandidateSummary {
  src?: string | null;
  alt?: string | null;
  text_wordmark?: string | null;
  source_type?: string | null;
  classification?: string | null;
  confidence?: number | null;
  score?: number | null;
  reasons?: string[];
  width?: number | null;
  height?: number | null;
  aspect_ratio?: number | null;
}

export interface VisualIdentitySummary {
  // Legacy fields — old frontend/backend compatibility
  palette_hex: string[];
  palette_dominance: number[];
  primary_color: string | null;
  body_font: string | null;
  heading_font: string | null;
  logo_url: string | null;

  // v0.2 visual identity fields
  primary_logo?: LogoCandidateSummary | null;
  logo_candidates?: LogoCandidateSummary[];

  partner_logos?: LogoCandidateSummary[];
  authority_logos?: LogoCandidateSummary[];
  co_branding_detected?: boolean;
  visual_extraction_note?: string | null;

  raw_palette?: string[];
  raw_palette_dominance?: number[];

  brand_palette?: string[];
  brand_palette_confidence?: number[];
  primary_brand_color?: string | null;

  accent_colors?: string[];
  neutral_colors?: string[];
  background_colors?: string[];
  text_colors?: string[];

  palette_extraction_note?: string | null;
  visual_warnings?: string[];
}

export interface ExtractionMeta {
  manifest_path: string;
  manifest_hash: string | null;
  extracted_at: string;
  duration_ms: number;
  rule_extractors_used: string[];
  llm_calls: number;
  llm_tokens_input: number;
  llm_tokens_output: number;
  llm_model: string | null;
  llm_cost_usd: number | null;
  extractor_version: string;
}

export interface ProfileQuality {
  has_name: boolean;
  has_category: boolean;
  has_offerings: boolean;
  has_audience: boolean;
  has_value_propositions: boolean;
  has_tone: boolean;
  has_contact: boolean;
  has_visual: boolean;

  fields_extracted: number;
  fields_inferred: number;
  fields_missing: number;

  major_missing: string[];

  ready_for_strategy: boolean;

  // v0.2 poster readiness fields
  ready_for_poster?: boolean;
  poster_blockers?: string[];
  poster_warnings?: string[];
}

// ---------------------------------------------------------------------
// Top-level BusinessProfile
// ---------------------------------------------------------------------

export interface BusinessProfile {
  // v0.2-b1: schema versioning — optional for backward compat with old fixtures
  schema_version?: string;

  source_url: string;
  final_url: string | null;

  name: EvidencedField<string>;
  tagline: EvidencedField<string>;
  description: EvidencedField<string>;
  category: EvidencedField<string>;

  offerings: Offering[];
  pricing_visible: EvidencedField<boolean>;
  pricing_posture: EvidencedField<string>;
  pricing_extraction_note?: string | null;

  // v0.2-b1: honest failure reasons + LLM silent-failure flag
  offerings_extraction_note?: string | null;
  llm_silent_failure?: boolean;

  audience_type: EvidencedField<string>;
  audience_signals: EvidencedField<string>[];
  value_propositions: EvidencedField<string>[];
  tone_of_voice: EvidencedField<string>;

  locations: Location[];
  service_areas: EvidencedField<string>[];
  languages: string[];
  hours: unknown | null;

  contact_channels: ContactChannels;
  existing_ctas: EvidencedField<string>[];
  social_presence: SocialAccount[];

  trust_signals: EvidencedField<string>[];

  visual: VisualIdentitySummary;

  extraction_meta: ExtractionMeta;
  quality: ProfileQuality;
}

// ---------------------------------------------------------------------
// API response shapes
// ---------------------------------------------------------------------

export interface RunResponse {
  job_id: string;
}

export interface JobStatusResponse {
  job_id: string;
  status: JobStatus;
  current_stage: Stage | null;
  created_at: string;
  updated_at: string;
  error: string | null;
  events: StageEvent[];
  manifest_path: string | null;
  profile_path: string | null;
}

export interface JobResultResponse {
  job_id: string;
  status: JobStatus;
  profile: BusinessProfile;
  manifest_path: string | null;
  profile_path: string | null;
}

// ---------------------------------------------------------------------
// SWOT (mirrors api/routes/swot.py)
// ---------------------------------------------------------------------

export type SwotMode = "competitive" | "standalone";

export type ClaimStrength =
  | "validated"
  | "directional_not_validated"
  | "internally_supported";

export interface SwotItem {
  text: string;
  citation: string[];
  evidence: string;
  claim_strength?: ClaimStrength;
}

export interface TowsStrategy {
  type: "SO" | "ST" | "WO" | "WT";
  title: string;
  description: string;
  anchors: string[];
  claim_strength: ClaimStrength;
  source: "rules" | "llm" | "llm_text_replaced";
}

export interface TowsPriorityAction {
  rank: number;
  action: string;
  horizon: "now" | "next" | "later";
  anchors: string[];
  rationale: string;
}

export interface TowsResult {
  strategies: TowsStrategy[];
  priority_actions: TowsPriorityAction[];
  posture: string;
  notes: string[];
}

export interface CompetitorBrief {
  name: string;
  website?: string | null;
  rating?: number | null;
  review_count?: number | null;
  source: "places" | "web";
  why_selected: string;
}

export interface SwotResponse {
  mode: SwotMode;
  strengths: SwotItem[];
  weaknesses: SwotItem[];
  opportunities: SwotItem[];
  threats: SwotItem[];
  notes: string[];
  competitor_count: number;
  competitors?: CompetitorBrief[];
  tows?: TowsResult | null;
}