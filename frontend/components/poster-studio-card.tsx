"use client";

import { useState } from "react";
import {
  Download,
  ExternalLink,
  History,
  Loader2,
  ShieldCheck,
  Sparkles,
} from "lucide-react";

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

interface ComplianceRow {
  copy_field: string;
  copy_text: string;
  claim: string | null;
  status: "verified" | "unverified" | "no_checkable_claims";
  basis: string;
  source_url?: string | null;
  matched_quote?: string | null;
  source_tier?: string | null;
  lang_mismatch?: boolean;
}

interface ComplianceRemediationRow {
  copy_field: string;
  original_text: string;
  claim: string;
  status: "softened" | "dropped";
  basis: string;
  note?: string | null;
}

interface ComplianceSheet {
  title: string;
  asset_type: string;
  generated_by: string;
  verdict: "PASS" | "NEEDS_REVIEW";
  policy?: string | null;
  coverage?: {
    covered_surfaces: string[];
    excluded_surfaces: Record<string, string>;
  } | null;
  evidence_count?: number | null;
  summary: {
    rows: number;
    claims_verified: number;
    claims_unverified: number;
    fields_without_claims: number;
    claims_remediated: number;
  };
  shipped_copy: ComplianceRow[];
  remediation: ComplianceRemediationRow[];
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
  audit?: Record<string, unknown> | null;
  compliance_sheet?: ComplianceSheet | null;
  engine_used?: "oneshot" | "classic";
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
  const [showCompliance, setShowCompliance] = useState(false);
  const [engine, setEngine] = useState<"oneshot" | "classic">("oneshot");
  const [language, setLanguage] = useState<"auto" | "ar" | "en">("auto");

  const selected =
    versions.find((version) => version.id === selectedId) ?? versions[0] ?? null;

  const imageSrc = selected
    ? `data:image/png;base64,${selected.image_base64}`
    : null;

  const sheet = selected?.compliance_sheet ?? null;

  function downloadComplianceSheet() {
    if (!sheet || !selected) return;
    const blob = new Blob([JSON.stringify(sheet, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = selected.render.filename.replace(/\.png$/i, "") + ".compliance.json";
    a.click();
    URL.revokeObjectURL(url);
  }

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
          engine,
          language,
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
            <CardTitle className="text-lg">Poster Studio ✨</CardTitle>
            <p className="mt-1 text-sm text-muted-foreground">
              An on-brand poster from the scraped profile: an AI art-director designs the
              layout per brand, Imagen paints a text-free background, and the real
              logo + evidence-grounded copy are overlaid crisply. Each run varies the look.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value as "auto" | "ar" | "en")}
              className="h-8 rounded-lg border bg-background px-2 text-xs font-medium"
              title="Copy language"
            >
              <option value="auto">Auto</option>
              <option value="ar">عربي</option>
              <option value="en">English</option>
            </select>
            <div className="flex rounded-lg border p-0.5 text-xs" title="Design engine">
              <button
                type="button"
                onClick={() => setEngine("oneshot")}
                className={`rounded-md px-2.5 py-1.5 font-medium transition-colors ${
                  engine === "oneshot"
                    ? "bg-brand-gradient text-white"
                    : "text-muted-foreground hover:bg-muted"
                }`}
              >
                AI-designed
              </button>
              <button
                type="button"
                onClick={() => setEngine("classic")}
                className={`rounded-md px-2.5 py-1.5 font-medium transition-colors ${
                  engine === "classic"
                    ? "bg-brand-gradient text-white"
                    : "text-muted-foreground hover:bg-muted"
                }`}
              >
                Classic
              </button>
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
                {selected.engine_used === "oneshot" ? "AI-designed (one-shot)" : "Classic overlay"}
                {" · "}
                {selected.background.model ?? selected.background.provider}
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

        {imageSrc && selected && (
          <div className="space-y-3 animate-fade-up">
            <div className="overflow-hidden rounded-xl border bg-muted/20 p-3">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={imageSrc}
                alt="Generated marketing poster"
                className="mx-auto max-h-[820px] w-auto animate-pop rounded-lg shadow-lg shadow-primary/20"
              />
            </div>

            <div className="flex flex-wrap items-center gap-2">
              {/* The poster PNG can't be clickable — surface the real, evidence-backed
                  CTA as an actual button beside it (uses brief.cta_url). */}
              {selected.brief.cta_url && (
                <a
                  href={selected.brief.cta_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center rounded-lg bg-brand-gradient px-5 py-2 text-sm font-semibold text-white shadow-md shadow-primary/25 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg hover:shadow-primary/40"
                >
                  {selected.brief.cta_text || "Visit site"}
                  <ExternalLink className="ml-2 h-4 w-4" />
                </a>
              )}

              <a
                href={imageSrc}
                download={selected.render.filename}
                className="inline-flex items-center rounded-lg border px-4 py-2 text-sm font-medium transition-colors hover:bg-muted"
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

              {sheet && (
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setShowCompliance((value) => !value)}
                >
                  <ShieldCheck className="mr-2 h-4 w-4" />
                  {showCompliance ? "Hide compliance" : "Compliance Sheet"}
                  <span
                    className={`ml-2 rounded-full px-2 py-0.5 text-[10px] font-bold ${
                      sheet.verdict === "PASS"
                        ? "bg-emerald-100 text-emerald-700"
                        : "bg-amber-100 text-amber-800"
                    }`}
                  >
                    {sheet.verdict === "PASS" ? "PASS" : "REVIEW"}
                  </span>
                </Button>
              )}
            </div>

            {sheet && showCompliance && (
              <div className="space-y-3 rounded-xl border p-4 text-sm animate-fade-up">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2 font-semibold">
                    <ShieldCheck className="h-4 w-4 text-emerald-600" />
                    Ad Compliance Sheet
                    <span
                      className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
                        sheet.verdict === "PASS"
                          ? "bg-emerald-100 text-emerald-700"
                          : "bg-amber-100 text-amber-800"
                      }`}
                    >
                      {sheet.verdict}
                    </span>
                  </div>
                  <button
                    onClick={downloadComplianceSheet}
                    className="inline-flex items-center rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors hover:bg-muted"
                  >
                    <Download className="mr-1.5 h-3.5 w-3.5" />
                    Download sheet
                  </button>
                </div>

                <p className="text-xs text-muted-foreground">
                  Every factual claim in the shipped copy, mapped to its real source —
                  {" "}
                  {sheet.summary.claims_verified} verified
                  {sheet.summary.claims_remediated > 0 &&
                    ` · ${sheet.summary.claims_remediated} caught & remediated before publish`}
                  {sheet.summary.claims_unverified > 0 &&
                    ` · ${sheet.summary.claims_unverified} need review`}
                  {typeof sheet.evidence_count === "number" &&
                    ` · checked against ${sheet.evidence_count} evidence items`}
                  .
                </p>

                <div className="overflow-x-auto">
                  <table className="w-full min-w-[560px] border-collapse text-xs">
                    <thead>
                      <tr className="border-b text-left text-muted-foreground">
                        <th className="py-2 pr-3 font-medium">Copy</th>
                        <th className="py-2 pr-3 font-medium">Claim</th>
                        <th className="py-2 pr-3 font-medium">Status</th>
                        <th className="py-2 font-medium">Basis</th>
                      </tr>
                    </thead>
                    <tbody>
                      {sheet.shipped_copy.map((row, i) => (
                        <tr key={`s-${i}`} className="border-b align-top">
                          <td className="py-2 pr-3">
                            <div className="font-medium">{row.copy_text}</div>
                            <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
                              {row.copy_field}
                            </div>
                          </td>
                          <td className="py-2 pr-3">{row.claim ?? "—"}</td>
                          <td className="py-2 pr-3 whitespace-nowrap">
                            {row.status === "verified" && (
                              <span className="font-semibold text-emerald-600">✓ Verified</span>
                            )}
                            {row.status === "no_checkable_claims" && (
                              <span className="text-muted-foreground">— No factual claims</span>
                            )}
                            {row.status === "unverified" && (
                              <span className="font-semibold text-amber-600">⚠ Needs review</span>
                            )}
                          </td>
                          <td className="py-2">
                            {row.basis}
                            {row.source_url && (
                              <a
                                href={row.source_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="ml-1 inline-flex items-center text-primary underline"
                              >
                                source
                                <ExternalLink className="ml-0.5 h-3 w-3" />
                              </a>
                            )}
                            {row.matched_quote && (
                              <div className="mt-1 rounded bg-muted/50 p-1.5 text-[11px] text-muted-foreground">
                                “{row.matched_quote}”
                              </div>
                            )}
                          </td>
                        </tr>
                      ))}
                      {sheet.remediation.map((row, i) => (
                        <tr key={`r-${i}`} className="border-b bg-amber-50/50 align-top">
                          <td className="py-2 pr-3">
                            <div className="font-medium line-through decoration-amber-500/70">
                              {row.original_text}
                            </div>
                            <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
                              {row.copy_field}
                            </div>
                          </td>
                          <td className="py-2 pr-3">{row.claim}</td>
                          <td className="py-2 pr-3 whitespace-nowrap">
                            <span className="font-semibold text-amber-700">
                              ↓ {row.status === "dropped" ? "Dropped" : "Softened"}
                            </span>
                          </td>
                          <td className="py-2">{row.basis}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {sheet.coverage && (
                  <p className="text-[11px] text-muted-foreground">
                    Covers: {sheet.coverage.covered_surfaces.join("; ")}.
                    {Object.keys(sheet.coverage.excluded_surfaces ?? {}).length > 0 && (
                      <> Excluded: {Object.entries(sheet.coverage.excluded_surfaces)
                        .map(([k, v]) => `${k} (${v})`)
                        .join("; ")}.</>
                    )}
                  </p>
                )}
              </div>
            )}

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