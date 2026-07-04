"use client";

import { useState } from "react";
import { Compass, Loader2, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { postSwotFromProfile, ApiError } from "@/lib/api-client";
import type {
  BusinessProfile,
  ClaimStrength,
  SwotItem,
  SwotResponse,
} from "@/lib/types";

const STRENGTH_BADGE: Record<ClaimStrength, { label: string; cls: string }> = {
  validated: { label: "validated", cls: "bg-emerald-100 text-emerald-700" },
  directional_not_validated: {
    label: "directional",
    cls: "bg-amber-100 text-amber-800",
  },
  internally_supported: {
    label: "own-site",
    cls: "bg-slate-100 text-slate-600",
  },
};

const TOWS_TYPE_CLS: Record<string, string> = {
  SO: "border-emerald-200 bg-emerald-50 text-emerald-800",
  ST: "border-amber-200 bg-amber-50 text-amber-800",
  WO: "border-sky-200 bg-sky-50 text-sky-800",
  WT: "border-rose-200 bg-rose-50 text-rose-800",
};

interface SwotCardProps {
  profile: BusinessProfile;
}

type QuadrantKey = "strengths" | "weaknesses" | "opportunities" | "threats";

const QUADRANTS: { key: QuadrantKey; label: string; cls: string }[] = [
  { key: "strengths", label: "Strengths", cls: "border-emerald-200 bg-emerald-50" },
  { key: "weaknesses", label: "Weaknesses", cls: "border-rose-200 bg-rose-50" },
  { key: "opportunities", label: "Opportunities", cls: "border-sky-200 bg-sky-50" },
  { key: "threats", label: "Threats", cls: "border-amber-200 bg-amber-50" },
];

export function SwotCard({ profile }: SwotCardProps) {
  const [swot, setSwot] = useState<SwotResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function generate() {
    setLoading(true);
    setError(null);
    try {
      setSwot(await postSwotFromProfile(profile));
    } catch (err) {
      setError(err instanceof ApiError ? `${err.status}: ${err.message}` : String(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <CardTitle className="text-lg">SWOT Analysis</CardTitle>
            <p className="mt-1 text-sm text-muted-foreground">
              Competitor-grounded SWOT derived from the scraped profile. Degrades to a
              standalone (profile-only) analysis when no comparable competitors are found.
            </p>
          </div>

          <Button onClick={generate} disabled={loading}>
            {loading ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Analyzing…
              </>
            ) : (
              <>
                <Sparkles className="mr-2 h-4 w-4" />
                Generate SWOT
              </>
            )}
          </Button>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {error && (
          <div className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {error}
          </div>
        )}

        {swot && (
          <>
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <Badge variant="outline">
                {swot.mode === "standalone" ? "Standalone (profile-only)" : "Competitive"}
              </Badge>
              <span className="text-muted-foreground">
                {swot.competitor_count} competitor{swot.competitor_count === 1 ? "" : "s"} found
              </span>
            </div>

            {(swot.competitors?.length ?? 0) > 0 && (
              <div className="rounded-xl border p-3">
                <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Compared against
                </div>
                <div className="grid gap-2 sm:grid-cols-2">
                  {swot.competitors!.map((c, i) => (
                    <div
                      key={i}
                      className="rounded-lg border bg-muted/20 p-2.5 text-sm"
                      title={c.why_selected}
                    >
                      <div className="flex items-center justify-between gap-2">
                        {c.website ? (
                          <a
                            href={c.website}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="font-medium underline decoration-muted-foreground/40 underline-offset-2 hover:decoration-current"
                          >
                            {c.name}
                          </a>
                        ) : (
                          <span className="font-medium">{c.name}</span>
                        )}
                        <span
                          className={`rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${
                            c.source === "places"
                              ? "bg-emerald-100 text-emerald-700"
                              : "bg-sky-100 text-sky-700"
                          }`}
                        >
                          {c.source === "places" ? "Google Maps" : "Web"}
                        </span>
                      </div>
                      {(c.rating != null || c.review_count != null) && (
                        <div className="mt-0.5 text-xs text-muted-foreground">
                          {c.rating != null && <>★ {c.rating}</>}
                          {c.review_count != null && <> · {c.review_count.toLocaleString()} reviews</>}
                        </div>
                      )}
                      {c.why_selected && (
                        <div className="mt-0.5 line-clamp-2 text-[11px] text-muted-foreground">
                          {c.why_selected}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="grid gap-3 sm:grid-cols-2">
              {QUADRANTS.map((q) => {
                const items = swot[q.key] as SwotItem[];
                return (
                  <div key={q.key} className={`rounded border p-3 ${q.cls}`}>
                    <div className="mb-2 text-sm font-semibold">
                      {q.label} ({items.length})
                    </div>
                    {items.length === 0 ? (
                      <p className="text-xs text-muted-foreground">None.</p>
                    ) : (
                      <ul className="space-y-2">
                        {items.map((it, i) => {
                          const badge = it.claim_strength
                            ? STRENGTH_BADGE[it.claim_strength]
                            : null;
                          return (
                            <li key={i} className="text-sm">
                              <span>{it.text}</span>
                              {badge && (
                                <span
                                  className={`ml-1.5 rounded-full px-1.5 py-0.5 align-middle text-[10px] font-semibold ${badge.cls}`}
                                >
                                  {badge.label}
                                </span>
                              )}
                              {it.citation.length > 0 && (
                                <span className="mt-0.5 block text-xs text-muted-foreground">
                                  ↳ {it.citation.join(" · ")}
                                </span>
                              )}
                            </li>
                          );
                        })}
                      </ul>
                    )}
                  </div>
                );
              })}
            </div>

            {swot.tows && (swot.tows.strategies.length > 0 || swot.tows.priority_actions.length > 0) && (
              <div className="space-y-3 rounded-xl border p-4 animate-fade-up">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2 text-sm font-semibold">
                    <Compass className="h-4 w-4 text-primary" />
                    Strategy (TOWS)
                  </div>
                  <Badge variant="outline" className="capitalize">
                    posture: {swot.tows.posture}
                  </Badge>
                </div>

                {swot.tows.strategies.length > 0 && (
                  <ul className="space-y-2">
                    {swot.tows.strategies.map((s, i) => (
                      <li key={i} className="rounded-lg border p-2.5 text-sm">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <span
                            className={`rounded-full border px-1.5 py-0.5 text-[10px] font-bold ${TOWS_TYPE_CLS[s.type] ?? ""}`}
                          >
                            {s.type}
                          </span>
                          <span className="font-medium">{s.title}</span>
                          <span
                            className={`rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${STRENGTH_BADGE[s.claim_strength]?.cls ?? ""}`}
                          >
                            {STRENGTH_BADGE[s.claim_strength]?.label ?? s.claim_strength}
                          </span>
                        </div>
                        <p className="mt-1 text-xs text-muted-foreground">
                          {s.description}
                          <span className="ml-1 text-[10px]">
                            [{s.anchors.join(", ")}]
                          </span>
                        </p>
                      </li>
                    ))}
                  </ul>
                )}

                {swot.tows.priority_actions.length > 0 && (
                  <div>
                    <div className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      Priority actions
                    </div>
                    <ol className="space-y-1">
                      {swot.tows.priority_actions.map((a) => (
                        <li key={a.rank} className="flex items-start gap-2 text-sm">
                          <span className="mt-0.5 text-xs font-bold text-muted-foreground">
                            {a.rank}.
                          </span>
                          <span>
                            {a.action}
                            <span
                              className={`ml-1.5 rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${
                                a.horizon === "now"
                                  ? "bg-emerald-100 text-emerald-700"
                                  : a.horizon === "next"
                                    ? "bg-sky-100 text-sky-700"
                                    : "bg-slate-100 text-slate-600"
                              }`}
                            >
                              {a.horizon}
                            </span>
                          </span>
                        </li>
                      ))}
                    </ol>
                  </div>
                )}
              </div>
            )}

            {swot.notes.length > 0 && (
              <div className="rounded border bg-muted/30 p-3 text-xs text-muted-foreground">
                {swot.notes.map((n, i) => (
                  <div key={i}>• {n}</div>
                ))}
              </div>
            )}
          </>
        )}

        {!swot && !error && (
          <div className="rounded border border-dashed p-6 text-center text-sm text-muted-foreground">
            No SWOT yet. Click Generate SWOT to analyze this profile.
          </div>
        )}
      </CardContent>
    </Card>
  );
}
