"use client";

import { AlertTriangle, Check, X } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn, formatCost, formatTokens } from "@/lib/utils";
import type { BusinessProfile, StageEvent } from "@/lib/types";

interface DiagnosticsPanelProps {
  profile: BusinessProfile;
  events: StageEvent[];
}

// Human-readable explanations for the snake_case offerings note codes.
const OFFERINGS_NOTE_MESSAGES: Record<string, string> = {
  llm_skipped:
    "LLM extraction was skipped (rules-only mode). Offerings come from the LLM stage; run with skip_llm=false to populate them.",
  llm_group_failed:
    "The offerings LLM call failed (network error, response parse error, or schema mismatch). Check the LLM stage payload for details.",
  llm_returned_zero_offerings:
    "The LLM was given the evidence pack but returned an empty offerings list. This usually means the scraped pages don't describe what the business provides clearly enough.",
  all_candidates_rejected_by_validator:
    "The LLM proposed offerings, but every one was rejected by the validator (bad block_id, quote not in source, or blacklisted claim without supporting quote).",
  llm_silent_failure:
    "The LLM ran but produced no usable output across all groups. The pipeline cannot proceed to poster generation.",
  unknown:
    "Offerings list is empty but the diagnostics don't explain why. Inspect the validator output.",
};

// Human-readable poster blocker reasons.
const POSTER_BLOCKER_MESSAGES: Record<string, string> = {
  no_name: "No business name found.",
  no_category: "Could not determine a business category.",
  no_brand_statement:
    "No description, value proposition, or tagline to drive the poster message.",
  no_offer_or_strong_positioning:
    "No offerings AND no value-prop + audience pair — nothing concrete to feature.",
  no_visual_signals:
    "No brand palette or logo found. A poster needs visual identity to be grounded.",
  llm_silent_failure:
    "LLM extraction produced no usable output, so we can't trust downstream signals.",
};

const POSTER_WARNING_MESSAGES: Record<string, string> = {
  no_confident_primary_logo:
    "Logo candidates exist, but none is reliable enough to auto-use as the primary brand logo.",
  weak_brand_palette_confidence:
    "Brand palette confidence is weak; review raw colors before using Poster Studio.",
  palette_dominated_by_background:
    "The raw screenshot palette is dominated by page/background colors, not necessarily brand colors.",
  co_branding_detected:
    "Multiple likely brand/partner/authority logos were found. Manual logo choice is recommended.",
};

export function DiagnosticsPanel({ profile, events }: DiagnosticsPanelProps) {
  const meta = profile.extraction_meta;
  const quality = profile.quality;

  // Find the validate event payload (rejections + drops)
  const validateEvent = events
    .filter((e) => e.stage === "validate" && e.status === "done")
    .pop();
  const validatePayload = (validateEvent?.payload ?? {}) as Record<string, unknown>;
  const rejections = (validatePayload.rejections as number) ?? 0;
  const fieldsDropped = (validatePayload.fields_dropped as string[]) ?? [];
  const itemsDropped = (validatePayload.items_dropped as Record<string, number>) ?? {};
  const candidatesSeen =
    (validatePayload.candidates_seen as Record<string, number>) ?? {};
  const blacklistRejections =
    (validatePayload.blacklist_rejections as Record<string, number>) ?? {};

  // v0.2-b1: LLM warning detection from the LLM stage's done event.
  const llmEvent = events
    .filter((e) => e.stage === "llm" && e.status === "done")
    .pop();
  const llmWarning = (llmEvent?.payload as { warning?: string } | undefined)
    ?.warning;
  const llmSilentFailure = profile.llm_silent_failure ?? false;
  const offeringsNote = profile.offerings_extraction_note ?? null;
  const readyForPoster = quality.ready_for_poster ?? false;
  const posterBlockers = quality.poster_blockers ?? [];
  const posterWarnings = Array.from(
    new Set([...(quality.poster_warnings ?? []), ...(profile.visual.visual_warnings ?? [])]),
  );

  return (
    <div className="space-y-4">
      {/* v0.2-b1: warning banners — only render when there's something to say */}
      {(llmWarning || llmSilentFailure) && (
        <div className="flex items-start gap-3 rounded-md border border-destructive/40 bg-destructive/5 p-3">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
          <div className="text-sm">
            <div className="font-medium text-destructive">LLM stage warning</div>
            <div className="text-muted-foreground">
              {llmWarning ||
                "Silent LLM failure: extraction was requested but produced no usable output."}
              {" "}This profile may not be reliable. Inspect the LLM stage payload or
              re-run with verbose logging.
            </div>
          </div>
        </div>
      )}
      {offeringsNote && profile.offerings.length === 0 && (
        <div className="flex items-start gap-3 rounded-md border border-amber-200 bg-amber-50 p-3">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
          <div className="text-sm">
            <div className="font-medium text-amber-800">
              Offerings empty:{" "}
              <span className="font-mono text-xs">{offeringsNote}</span>
            </div>
            <div className="text-muted-foreground">
              {OFFERINGS_NOTE_MESSAGES[offeringsNote] ??
                OFFERINGS_NOTE_MESSAGES.unknown}
            </div>
          </div>
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {/* LLM */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">LLM usage</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1.5 text-sm">
            <Row label="Model" value={meta.llm_model ?? "—"} mono />
            <Row
              label="Calls"
              value={String(meta.llm_calls)}
              highlight={llmSilentFailure}
            />
            <Row label="Input tokens" value={formatTokens(meta.llm_tokens_input)} />
            <Row
              label="Output tokens"
              value={formatTokens(meta.llm_tokens_output)}
            />
            <Row label="Cost" value={formatCost(meta.llm_cost_usd)} highlight />
          </CardContent>
        </Card>

        {/* Validator */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Validator</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1.5 text-sm">
            <Row
              label="Rejections"
              value={String(rejections)}
              highlight={rejections > 0}
            />
            <Row
              label="Fields dropped"
              value={fieldsDropped.length > 0 ? fieldsDropped.join(", ") : "none"}
            />
            <Row
              label="Items dropped"
              value={
                Object.keys(itemsDropped).length === 0
                  ? "none"
                  : Object.entries(itemsDropped)
                      .map(([k, v]) => `${k}:${v}`)
                      .join(", ")
              }
            />
            {Object.keys(candidatesSeen).length > 0 && (
              <Row
                label="Candidates seen"
                value={Object.entries(candidatesSeen)
                  .map(([k, v]) => `${k}:${v}`)
                  .join(", ")}
                small
              />
            )}
            {Object.keys(blacklistRejections).length > 0 && (
              <Row
                label="Blacklist drops"
                value={Object.entries(blacklistRejections)
                  .map(([k, v]) => `${k}:${v}`)
                  .join(", ")}
                highlight
              />
            )}
          </CardContent>
        </Card>

        {/* Quality */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Readiness</CardTitle>
              <div className="flex flex-wrap items-center gap-1">
                <Badge
                  variant={quality.ready_for_strategy ? "extracted" : "missing"}
                  title="Threshold for downstream strategy/copy stages"
                >
                  strategy: {quality.ready_for_strategy ? "ready" : "not ready"}
                </Badge>
                <Badge
                  variant={readyForPoster ? "extracted" : "missing"}
                  title="Threshold for poster generation"
                >
                  poster: {readyForPoster ? "ready" : "not ready"}
                </Badge>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="grid grid-cols-2 gap-y-1 text-xs">
              <Flag label="name" ok={quality.has_name} />
              <Flag label="category" ok={quality.has_category} />
              <Flag label="offerings" ok={quality.has_offerings} />
              <Flag label="audience" ok={quality.has_audience} />
              <Flag label="value props" ok={quality.has_value_propositions} />
              <Flag label="tone" ok={quality.has_tone} />
              <Flag label="contact" ok={quality.has_contact} />
              <Flag label="visual" ok={quality.has_visual} />
            </div>
            <div className="border-t pt-2 text-xs">
              <Row
                label="extracted"
                value={String(quality.fields_extracted)}
                small
              />
              <Row
                label="inferred"
                value={String(quality.fields_inferred)}
                small
              />
              <Row label="missing" value={String(quality.fields_missing)} small />
            </div>
            {quality.major_missing.length > 0 && (
              <div className="text-xs text-amber-700">
                Major missing: {quality.major_missing.join(", ")}
              </div>
            )}
            {posterBlockers.length > 0 && (
              <div className="border-t pt-2 text-xs">
                <div className="mb-1 font-medium text-foreground">
                  Poster blockers
                </div>
                <ul className="space-y-1">
                  {posterBlockers.map((b) => (
                    <li key={b} className="text-muted-foreground">
                      <span className="font-mono text-[10px] text-foreground">
                        {b}
                      </span>{" "}
                      — {POSTER_BLOCKER_MESSAGES[b] ?? b.replace(/_/g, " ")}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {posterWarnings.length > 0 && (
              <div className="border-t pt-2 text-xs">
                <div className="mb-1 font-medium text-foreground">
                  Visual warnings
                </div>
                <ul className="space-y-1">
                  {posterWarnings.map((w) => (
                    <li key={w} className="text-muted-foreground">
                      <span className="font-mono text-[10px] text-foreground">
                        {w}
                      </span>{" "}
                      — {POSTER_WARNING_MESSAGES[w] ?? w.replace(/_/g, " ")}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {profile.schema_version && (
              <div className="border-t pt-2 text-[10px] font-mono text-muted-foreground">
                schema {profile.schema_version}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function Row({
  label,
  value,
  highlight,
  mono,
  small,
}: {
  label: string;
  value: string;
  highlight?: boolean;
  mono?: boolean;
  small?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <span
        className={cn(
          "text-muted-foreground",
          small ? "text-[11px]" : "text-xs",
        )}
      >
        {label}
      </span>
      <span
        className={cn(
          mono && "font-mono",
          small ? "text-xs" : "",
          highlight && "font-semibold",
        )}
      >
        {value}
      </span>
    </div>
  );
}

function Flag({ label, ok }: { label: string; ok: boolean }) {
  return (
    <div className="flex items-center gap-1.5">
      {ok ? (
        <Check className="h-3 w-3 text-emerald-600" />
      ) : (
        <X className="h-3 w-3 text-slate-400" />
      )}
      <span className={cn(ok ? "text-foreground" : "text-muted-foreground")}>
        {label}
      </span>
    </div>
  );
}
