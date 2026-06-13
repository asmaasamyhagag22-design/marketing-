"use client";

import { useState } from "react";
import { Download, History, Loader2, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { BusinessProfile } from "@/lib/types";

interface PosterStudioCardProps {
  profile: BusinessProfile;
}

interface PosterBrief {
  business_name: string;
  category?: string | null;
  headline: string;
  subheadline?: string | null;
  offerings: string[];
  cta_text: string;
  cta_url?: string | null;
  contact_line?: string | null;
  palette_hex: string[];
  warnings: string[];
  logo_url?: string | null;
  logo_text?: string | null;
  logo_source_type?: string | null;
  logo_confidence?: number | null;
}

interface PosterArtDirection {
  provider_prompt: string;
  negative_prompt: string;
  concept: string;
  category: string;
  mood: string;
  layout: string;
  background_style: string;
  safe_overlay_copy: string;
  color_notes: string[];
  source_fields_used: string[];
}

interface BackgroundResult {
  provider: string;
  model?: string | null;
  prompt: string;
  background_path: string;
  filename: string;
  width: number;
  height: number;
  fallback_used: boolean;
  fallback_reason?: string | null;
}

interface PosterResponse {
  brief: PosterBrief;
  art_direction: PosterArtDirection;
  background: BackgroundResult;
  render: {
    poster_path: string;
    filename: string;
    width: number;
    height: number;
    mime_type: "image/png";
  };
  image_base64: string;
}

interface PosterVersion extends PosterResponse {
  id: string;
  generatedAt: string;
}

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000/api";

export function PosterStudioCard({ profile }: PosterStudioCardProps) {
  const [versions, setVersions] = useState<PosterVersion[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showPrompt, setShowPrompt] = useState(false);

  const selected =
    versions.find((version) => version.id === selectedId) ?? versions[0] ?? null;

  const imageSrc = selected
    ? `data:image/png;base64,${selected.image_base64}`
    : null;

  async function generatePoster() {
    setIsGenerating(true);
    setError(null);

    try {
      const response = await fetch(`${API_BASE}/poster/from-profile`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          profile,
          output_format: "poster_1080x1350",
        }),
      });

      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || "Poster generation failed.");
      }

      const data = (await response.json()) as PosterResponse;

      const version: PosterVersion = {
        ...data,
        id: crypto.randomUUID(),
        generatedAt: new Date().toLocaleString(),
      };

      setVersions((current) => [version, ...current]);
      setSelectedId(version.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Poster generation failed.");
    } finally {
      setIsGenerating(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <CardTitle className="text-lg">Poster Studio</CardTitle>
            <p className="mt-1 text-sm text-muted-foreground">
              Generate a real poster from the scraped profile using OpenAI background generation and deterministic text/logo overlay.
            </p>
          </div>

          <Button onClick={generatePoster} disabled={isGenerating}>
            {isGenerating ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Generating...
              </>
            ) : (
              <>
                <Sparkles className="mr-2 h-4 w-4" />
                Generate Poster
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

        {selected?.brief && (
          <div className="rounded border bg-muted/30 p-3 text-sm">
            <div className="flex items-center justify-between gap-3">
              <div className="font-medium">Generated brief</div>
              <div className="text-xs text-muted-foreground">
                {selected.background.provider}
                {selected.background.model ? ` · ${selected.background.model}` : ""}
                {selected.background.fallback_used ? " · fallback" : ""}
              </div>
            </div>

            <div className="mt-2 grid gap-2 sm:grid-cols-2">
              <div>
                <span className="text-muted-foreground">Business:</span>{" "}
                {selected.brief.business_name}
              </div>

              <div>
                <span className="text-muted-foreground">Category:</span>{" "}
                {selected.brief.category ?? "unknown"}
              </div>

              <div>
                <span className="text-muted-foreground">Headline:</span>{" "}
                {selected.brief.headline}
              </div>

              <div>
                <span className="text-muted-foreground">Logo:</span>{" "}
                {selected.brief.logo_url
                  ? "logo image"
                  : selected.brief.logo_text
                    ? "wordmark fallback"
                    : "none"}
              </div>

              <div className="sm:col-span-2">
                <span className="text-muted-foreground">Offerings:</span>{" "}
                {selected.brief.offerings.join(", ")}
              </div>

              {selected.brief.cta_url && (
                <div className="sm:col-span-2">
                  <span className="text-muted-foreground">CTA:</span>{" "}
                  <a
                    href={selected.brief.cta_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="underline"
                  >
                    {selected.brief.cta_text}
                  </a>
                </div>
              )}
            </div>

            {selected.background.fallback_used && selected.background.fallback_reason && (
              <div className="mt-3 rounded border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800">
                Background fallback used: {selected.background.fallback_reason}
              </div>
            )}

            {selected.brief.warnings.length > 0 && (
              <div className="mt-3 rounded border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800">
                {selected.brief.warnings[0]}
              </div>
            )}
          </div>
        )}

        {versions.length > 0 && (
          <div className="rounded border p-3">
            <div className="mb-3 flex items-center gap-2 text-sm font-medium">
              <History className="h-4 w-4" />
              Poster History
            </div>

            <div className="flex flex-wrap gap-2">
              {versions.map((version, index) => (
                <button
                  key={version.id}
                  onClick={() => setSelectedId(version.id)}
                  className={`rounded border px-3 py-1.5 text-xs ${
                    selected?.id === version.id
                      ? "bg-foreground text-background"
                      : "hover:bg-muted"
                  }`}
                >
                  Version {versions.length - index}
                </button>
              ))}
            </div>
          </div>
        )}

        {imageSrc && selected && (
          <div className="space-y-3">
            <div className="overflow-hidden rounded border bg-muted/20 p-3">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={imageSrc}
                alt="Generated marketing poster"
                className="mx-auto max-h-[820px] w-auto rounded shadow"
              />
            </div>

            <div className="flex flex-wrap gap-2">
              <a
                href={imageSrc}
                download={selected.render.filename}
                className="inline-flex items-center rounded-md border px-4 py-2 text-sm font-medium hover:bg-muted"
              >
                <Download className="mr-2 h-4 w-4" />
                Download PNG
              </a>

              <Button
                type="button"
                variant="outline"
                onClick={() => setShowPrompt((value) => !value)}
              >
                {showPrompt ? "Hide prompt" : "Show prompt"}
              </Button>
            </div>

            {showPrompt && (
              <div className="space-y-3 rounded border bg-muted/30 p-3 text-xs">
                <div>
                  <div className="mb-1 font-medium">Concept</div>
                  <p className="text-muted-foreground">
                    {selected.art_direction.concept}
                  </p>
                </div>

                <div>
                  <div className="mb-1 font-medium">Image prompt</div>
                  <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded bg-background p-3">
                    {selected.background.prompt}
                  </pre>
                </div>
              </div>
            )}
          </div>
        )}

        {!selected && !error && (
          <div className="rounded border border-dashed p-6 text-center text-sm text-muted-foreground">
            No poster generated yet. Click Generate Poster to create a real profile-grounded poster.
          </div>
        )}
      </CardContent>
    </Card>
  );
}