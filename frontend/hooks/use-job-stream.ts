"use client";

import { useEffect, useRef, useState } from "react";

import { getJobResult, jobStreamUrl } from "@/lib/api-client";
import type {
  BusinessProfile,
  JobStatus,
  Stage,
  StageEvent,
} from "@/lib/types";

export interface JobStreamState {
  events: StageEvent[];
  status: JobStatus;
  currentStage: Stage | null;
  result: BusinessProfile | null;
  error: string | null;
}

/**
 * Subscribe to /api/jobs/{jobId}/stream and accumulate events.
 *
 * - Status starts as "queued" and transitions on event arrival.
 * - When the FINAL/DONE event arrives (or job hits FAILED), the hook
 *   fetches /api/jobs/{jobId}/result to obtain the BusinessProfile.
 * - On unmount, the EventSource is closed.
 */
export function useJobStream(jobId: string | null): JobStreamState {
  const [events, setEvents] = useState<StageEvent[]>([]);
  const [status, setStatus] = useState<JobStatus>("queued");
  const [currentStage, setCurrentStage] = useState<Stage | null>(null);
  const [result, setResult] = useState<BusinessProfile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!jobId) return;

    // Reset state when jobId changes
    setEvents([]);
    setStatus("queued");
    setCurrentStage(null);
    setResult(null);
    setError(null);

    const es = new EventSource(jobStreamUrl(jobId));
    esRef.current = es;

    const onStage = (e: MessageEvent) => {
      try {
        const ev = JSON.parse(e.data) as StageEvent;
        setEvents((prev) => [...prev, ev]);

        if (ev.status === "started") {
          setStatus("running");
          setCurrentStage(ev.stage);
        } else if (ev.status === "error") {
          setStatus("failed");
          setError(ev.error || `${ev.stage} failed`);
          es.close();
        } else if (ev.stage === "final" && ev.status === "done") {
          setStatus("succeeded");
          setCurrentStage(null);
          // Fetch the final result
          getJobResult(jobId)
            .then((r) => setResult(r.profile))
            .catch((err) => setError(String(err)));
          es.close();
        }
      } catch (parseErr) {
        // Skip malformed events; the next ping will arrive shortly
        console.warn("Failed to parse SSE event", parseErr);
      }
    };

    const onError = () => {
      // EventSource auto-reconnects; we only surface the error if the job
      // hasn't reached a terminal state. A normal close after the final
      // event is not an error.
      // We don't setError here to avoid flashing the UI red on close.
    };

    es.addEventListener("stage", onStage);
    es.addEventListener("error", onError);

    return () => {
      es.removeEventListener("stage", onStage);
      es.removeEventListener("error", onError);
      es.close();
      esRef.current = null;
    };
  }, [jobId]);

  return { events, status, currentStage, result, error };
}
