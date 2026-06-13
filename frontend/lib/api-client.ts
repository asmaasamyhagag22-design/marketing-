/**
 * Typed fetch wrappers for the Day 1 backend.
 *
 * Base URL is read from NEXT_PUBLIC_API_URL at build time, defaulting
 * to http://localhost:8000 for `npm run dev`.
 */
import type {
  BusinessProfile,
  JobResultResponse,
  JobStatusResponse,
  RunResponse,
  SwotResponse,
} from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface RunOptions {
  url: string;
  skip_llm?: boolean;
  model?: string;
  persist_to_disk?: boolean;
}

export class ApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

async function jsonOrThrow<T>(resp: Response): Promise<T> {
  if (!resp.ok) {
    let detail = "";
    try {
      const body = (await resp.json()) as { detail?: string; error?: string };
      detail = body.detail || body.error || "";
    } catch {
      detail = await resp.text();
    }
    throw new ApiError(resp.status, detail || `HTTP ${resp.status}`);
  }
  return (await resp.json()) as T;
}

export async function postRun(opts: RunOptions): Promise<RunResponse> {
  const resp = await fetch(`${API_BASE}/api/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      url: opts.url,
      skip_llm: opts.skip_llm ?? false,
      model: opts.model ?? "gpt-4o-mini",
      persist_to_disk: opts.persist_to_disk ?? true,
    }),
  });
  return jsonOrThrow<RunResponse>(resp);
}

export async function getJobStatus(jobId: string): Promise<JobStatusResponse> {
  const resp = await fetch(`${API_BASE}/api/jobs/${jobId}`);
  return jsonOrThrow<JobStatusResponse>(resp);
}

export async function getJobResult(jobId: string): Promise<JobResultResponse> {
  const resp = await fetch(`${API_BASE}/api/jobs/${jobId}/result`);
  return jsonOrThrow<JobResultResponse>(resp);
}

/**
 * SSE URL for the given job. Components open EventSource(url) and
 * subscribe via the use-job-stream hook.
 */
export function jobStreamUrl(jobId: string): string {
  return `${API_BASE}/api/jobs/${jobId}/stream`;
}

/**
 * Generate a competitor-grounded SWOT from an already-built profile.
 * Degrades to a standalone (profile-only) SWOT when no competitors are found.
 */
export async function postSwotFromProfile(
  profile: BusinessProfile,
): Promise<SwotResponse> {
  const resp = await fetch(`${API_BASE}/api/swot/from-profile`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ profile }),
  });
  return jsonOrThrow<SwotResponse>(resp);
}
