/**
 * Fixture mode.
 *
 * `?demo=sp-clinic` short-circuits the live API: the static
 * fixtures/sp-clinic.json is loaded as if /api/jobs/{id}/result had
 * returned it, and a sequence of fake "done" StageEvents is
 * synthesized so the timeline renders fully complete.
 *
 * This lets the UI be iterated on without spending OpenAI dollars
 * or running uvicorn.
 */
import type { BusinessProfile, Stage, StageEvent } from "./types";
import { MVP_STAGES } from "./types";

// Static import — Next.js will bundle the JSON at build time.
// Replace frontend/fixtures/sp-clinic.json with your real run.
import spClinicProfile from "@/fixtures/sp-clinic.json";

export const AVAILABLE_FIXTURES = {
  "sp-clinic": spClinicProfile as unknown as BusinessProfile,
} as const;

export type FixtureKey = keyof typeof AVAILABLE_FIXTURES;

export function isFixtureKey(s: string | null): s is FixtureKey {
  return s != null && s in AVAILABLE_FIXTURES;
}

export function getFixture(key: FixtureKey): BusinessProfile {
  return AVAILABLE_FIXTURES[key];
}

/**
 * Build a full sequence of completed stage events for the timeline.
 * Generates STARTED + DONE for each MVP stage with realistic-looking
 * payloads drawn from the fixture profile.
 */
export function synthesizeStageEvents(
  jobId: string,
  profile: BusinessProfile,
): StageEvent[] {
  const events: StageEvent[] = [];
  const t0 = new Date("2026-05-16T12:00:00Z").getTime();

  let cursor = t0;
  const advance = (ms: number): { started: string; done: string; duration: number } => {
    const started = new Date(cursor).toISOString();
    cursor += ms;
    const done = new Date(cursor).toISOString();
    cursor += 100; // small gap between stages
    return { started, done, duration: ms };
  };

  const push = (
    stage: Stage,
    timing: { started: string; done: string; duration: number },
    payload: Record<string, unknown>,
  ) => {
    events.push({
      job_id: jobId,
      stage,
      status: "started",
      timestamp: timing.started,
      duration_ms: 0,
    });
    events.push({
      job_id: jobId,
      stage,
      status: "done",
      timestamp: timing.done,
      duration_ms: timing.duration,
      payload,
    });
  };

  // Approximate timings from a real SP Clinic run.
  push("scrape", advance(18000), {
    manifest_path: profile.extraction_meta.manifest_path,
    pages_succeeded: 5,
    pages_attempted: 5,
    ready_for_extraction: true,
    languages: profile.languages,
    failures: 0,
  });
  push("rules", advance(80), {
    extractors_used: profile.extraction_meta.rule_extractors_used,
    fields_extracted: profile.quality.fields_extracted,
    fields_missing: profile.quality.fields_missing,
    major_missing: profile.quality.major_missing,
  });
  push("evidence_pack", advance(40), {
    blocks_total_in_manifest: 396,
    blocks_after_filter: 220,
    block_count: 200,
    page_type_distribution: { homepage: 60, services: 50, contact: 40, about: 35, booking: 15 },
    missing_fields: profile.quality.major_missing,
  });
  push("llm", advance(13000), {
    calls: profile.extraction_meta.llm_calls,
    failed: 0,
    input_tokens: profile.extraction_meta.llm_tokens_input,
    output_tokens: profile.extraction_meta.llm_tokens_output,
    cost_usd: profile.extraction_meta.llm_cost_usd,
    model: profile.extraction_meta.llm_model,
  });
  push("validate", advance(20), {
    rejections: 0,
    fields_dropped: [],
    items_dropped: {},
  });
  push("merge", advance(15), {
    ready_for_strategy: profile.quality.ready_for_strategy,
    fields_extracted: profile.quality.fields_extracted,
    fields_inferred: profile.quality.fields_inferred,
    fields_missing: profile.quality.fields_missing,
    major_missing: profile.quality.major_missing,
  });
  // Final
  events.push({
    job_id: jobId,
    stage: "final",
    status: "done",
    timestamp: new Date(cursor).toISOString(),
    duration_ms: 0,
    payload: {
      ready_for_strategy: profile.quality.ready_for_strategy,
      llm_cost_usd: profile.extraction_meta.llm_cost_usd,
      llm_calls: profile.extraction_meta.llm_calls,
      profile_path: "fixture",
    },
  });

  return events;
}

/** Stage list ordering used by the timeline for both fixture + live modes. */
export const TIMELINE_STAGES = MVP_STAGES;
