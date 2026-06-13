"use client";

import { Check, Loader2, X, Circle } from "lucide-react";

import { cn } from "@/lib/utils";
import { formatDuration } from "@/lib/utils";
import type { Stage, StageEvent, StageMeta, StageStatus } from "@/lib/types";

interface PipelineTimelineProps {
  stages: StageMeta[];
  events: StageEvent[];
  currentStage: Stage | null;
}

interface StageState {
  status: StageStatus;
  duration_ms: number | null;
  payload: Record<string, unknown> | null;
  error: string | null;
}

function deriveStageStates(
  stages: StageMeta[],
  events: StageEvent[],
): Record<Stage, StageState> {
  const states = {} as Record<Stage, StageState>;
  for (const s of stages) {
    states[s.id] = {
      status: "pending",
      duration_ms: null,
      payload: null,
      error: null,
    };
  }
  for (const ev of events) {
    const slot = states[ev.stage];
    if (!slot) continue;
    if (ev.status === "started") {
      slot.status = "started";
    } else if (ev.status === "done") {
      slot.status = "done";
      slot.duration_ms = ev.duration_ms;
      slot.payload = (ev.payload as Record<string, unknown> | null) ?? null;
    } else if (ev.status === "error") {
      slot.status = "error";
      slot.error = ev.error ?? "error";
    }
  }
  return states;
}

function StageDot({ status }: { status: StageStatus }) {
  if (status === "done") {
    return (
      <div className="flex h-8 w-8 items-center justify-center rounded-full bg-emerald-500 text-white">
        <Check className="h-4 w-4" />
      </div>
    );
  }
  if (status === "started") {
    return (
      <div className="flex h-8 w-8 items-center justify-center rounded-full bg-blue-500 text-white">
        <Loader2 className="h-4 w-4 animate-spin" />
      </div>
    );
  }
  if (status === "error") {
    return (
      <div className="flex h-8 w-8 items-center justify-center rounded-full bg-destructive text-destructive-foreground">
        <X className="h-4 w-4" />
      </div>
    );
  }
  return (
    <div className="flex h-8 w-8 items-center justify-center rounded-full border-2 border-slate-300 text-slate-400">
      <Circle className="h-3 w-3" />
    </div>
  );
}

export function PipelineTimeline({ stages, events }: PipelineTimelineProps) {
  const states = deriveStageStates(stages, events);

  return (
    <div className="w-full overflow-x-auto pb-2">
      <ol className="flex min-w-fit items-start gap-2">
        {stages.map((stage, idx) => {
          const state = states[stage.id];
          const isLast = idx === stages.length - 1;
          return (
            <li key={stage.id} className="flex flex-1 items-start">
              <div className="flex flex-col items-center text-center">
                <StageDot status={state.status} />
                <div className="mt-2 w-24 text-xs font-medium leading-tight">
                  {stage.label}
                </div>
                <div className="mt-0.5 w-24 text-[11px] leading-tight text-muted-foreground">
                  {state.status === "done" && state.duration_ms !== null
                    ? formatDuration(state.duration_ms)
                    : state.status === "started"
                      ? "running…"
                      : state.status === "error"
                        ? "failed"
                        : stage.description}
                </div>
              </div>
              {!isLast && (
                <div
                  className={cn(
                    "mx-2 mt-4 h-0.5 flex-1 min-w-8",
                    state.status === "done"
                      ? "bg-emerald-300"
                      : "bg-slate-200",
                  )}
                />
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
