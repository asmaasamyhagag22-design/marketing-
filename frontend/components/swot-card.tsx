"use client";

import { useState } from "react";
import { Loader2, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { postSwotFromProfile, ApiError } from "@/lib/api-client";
import type { BusinessProfile, SwotItem, SwotResponse } from "@/lib/types";

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
                        {items.map((it, i) => (
                          <li key={i} className="text-sm">
                            <span>{it.text}</span>
                            {it.citation.length > 0 && (
                              <span className="mt-0.5 block text-xs text-muted-foreground">
                                ↳ {it.citation.join(" · ")}
                              </span>
                            )}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                );
              })}
            </div>

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
