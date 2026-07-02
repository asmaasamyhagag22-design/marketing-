"use client";

import { useState } from "react";
import { Clapperboard, Download, History, Loader2, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { BusinessProfile } from "@/lib/types";

interface ReelStudioCardProps {
  profile: BusinessProfile;
}

interface ReelResponse {
  video_base64: string;
  filename: string;
  mime_type: "video/mp4";
  width: number;
  height: number;
  duration_s: number;
  scene_count: number;
  mode: string; // "generated" (from brand ads) | "motion" (real photos)
  business_name: string;
  warnings: string[];
}

interface ReelVersion extends ReelResponse {
  id: string;
  generatedAt: string;
}

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000/api";

const MODE_LABEL: Record<string, string> = {
  generated: "Generated from the brand's real ads (understand → invent)",
  motion: "Cinematic motion over the brand's real photos",
};

export function ReelStudioCard({ profile }: ReelStudioCardProps) {
  const [versions, setVersions] = useState<ReelVersion[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selected =
    versions.find((v) => v.id === selectedId) ?? versions[0] ?? null;
  const videoSrc = selected
    ? `data:video/mp4;base64,${selected.video_base64}`
    : null;

  async function generateReel() {
    setIsGenerating(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/reel/from-profile`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ profile }), // n_scenes: backend default (5 — the calmer pacing)
      });
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || "Reel generation failed.");
      }
      const data = (await response.json()) as ReelResponse;
      const version: ReelVersion = {
        ...data,
        id: crypto.randomUUID(),
        generatedAt: new Date().toLocaleString(),
      };
      setVersions((cur) => [version, ...cur]);
      setSelectedId(version.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reel generation failed.");
    } finally {
      setIsGenerating(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <CardTitle className="text-lg">Reel Studio 🎬</CardTitle>
            <p className="mt-1 max-w-prose text-sm text-muted-foreground">
              A vertical brand reel — we UNDERSTAND the brand from its real ads (found via search)
              and INVENT fresh on-brand scenes, then animate them cinematically (eased motion +
              transitions). No website-photo slideshow. Each run varies.
            </p>
          </div>
          <Button onClick={generateReel} disabled={isGenerating}>
            {isGenerating ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Generating…
              </>
            ) : (
              <>
                <Sparkles className="mr-2 h-4 w-4" />
                Generate Reel
              </>
            )}
          </Button>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {isGenerating && (
          <div className="flex items-center gap-3 rounded-lg border bg-muted/30 p-4 text-sm">
            <Loader2 className="h-5 w-5 animate-spin text-primary" />
            <div>
              <div className="font-medium">Directing your reel…</div>
              <div className="text-xs text-muted-foreground">
                Understanding the brand’s real ads → inventing scenes → animating. This takes a
                minute or two.
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {error}
          </div>
        )}

        {versions.length > 0 && (
          <div className="rounded border p-3">
            <div className="mb-3 flex items-center gap-2 text-sm font-medium">
              <History className="h-4 w-4" />
              Reel History
            </div>
            <div className="flex flex-wrap gap-2">
              {versions.map((version, index) => (
                <button
                  key={version.id}
                  onClick={() => setSelectedId(version.id)}
                  className={`rounded-lg border px-3 py-1.5 text-xs transition-colors ${
                    selected?.id === version.id
                      ? "border-transparent bg-brand-gradient font-semibold text-white"
                      : "hover:bg-muted"
                  }`}
                >
                  Version {versions.length - index}
                </button>
              ))}
            </div>
          </div>
        )}

        {videoSrc && selected && (
          <div className="space-y-3 animate-fade-up">
            <div className="rounded-lg border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
              {MODE_LABEL[selected.mode] ?? selected.mode} · {selected.scene_count} scenes
            </div>
            <div className="overflow-hidden rounded-xl border bg-black/90 p-3">
              {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
              <video
                key={selected.id}
                src={videoSrc}
                controls
                autoPlay
                loop
                muted
                playsInline
                className="mx-auto max-h-[820px] w-auto animate-pop rounded-lg shadow-lg shadow-primary/20"
              />
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <a
                href={videoSrc}
                download={selected.filename}
                className="inline-flex items-center rounded-lg bg-brand-gradient px-5 py-2 text-sm font-semibold text-white shadow-md shadow-primary/25 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg hover:shadow-primary/40"
              >
                <Download className="mr-2 h-4 w-4" />
                Download MP4
              </a>
            </div>

            {selected.warnings.length > 0 && (
              <div className="rounded border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800">
                {selected.warnings[0]}
              </div>
            )}
          </div>
        )}

        {!selected && !error && !isGenerating && (
          <div className="rounded border border-dashed p-6 text-center text-sm text-muted-foreground">
            <Clapperboard className="mx-auto mb-2 h-6 w-6 opacity-60" />
            No reel yet. Click Generate Reel to invent a cinematic, on-brand reel from the brand’s
            real ads.
          </div>
        )}
      </CardContent>
    </Card>
  );
}
