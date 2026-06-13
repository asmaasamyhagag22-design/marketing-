"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type {
  ContactChannels,
  SocialAccount,
  VisualIdentitySummary,
} from "@/lib/types";

interface VisualIdentityCardProps {
  visual: VisualIdentitySummary;
  contact: ContactChannels;
  socials: SocialAccount[];
  languages: string[];
}

type LogoCandidate = {
  src?: string | null;
  alt?: string | null;
  text_wordmark?: string | null;
  source_type?: string | null;
  classification?: string | null;
  confidence?: number | null;
  score?: number | null;
  reasons?: string[];
  width?: number | null;
  height?: number | null;
  aspect_ratio?: number | null;
};

function formatWarning(warning: string) {
  return warning.replace(/_/g, " ");
}

function pct(value?: number | null) {
  if (value == null) return null;
  return `${Math.round(value * 100)}%`;
}

export function VisualIdentityCard({
  visual,
  contact,
  socials,
  languages,
}: VisualIdentityCardProps) {
  const primaryLogo = visual.primary_logo as LogoCandidate | null | undefined;
  const logoCandidates = (visual.logo_candidates ?? []) as LogoCandidate[];
  const visualWarnings = visual.visual_warnings ?? [];

  const brandPalette =
    visual.brand_palette && visual.brand_palette.length > 0
      ? visual.brand_palette
      : visual.palette_hex ?? [];

  const brandPaletteConfidence =
    visual.brand_palette_confidence && visual.brand_palette_confidence.length > 0
      ? visual.brand_palette_confidence
      : visual.palette_dominance ?? [];

  const rawPalette = visual.raw_palette ?? [];
  const rawPaletteDominance = visual.raw_palette_dominance ?? [];

  const primaryBrandColor =
    visual.primary_brand_color ?? visual.primary_color ?? null;

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Visual identity</CardTitle>
        </CardHeader>

        <CardContent className="space-y-5">
          {/* Logo */}
          <div>
            <div className="mb-2 text-xs uppercase tracking-wide text-muted-foreground">
              Logo
            </div>

            {primaryLogo?.source_type === "text_wordmark" ? (
              <div className="rounded border bg-muted/30 p-4">
                <div className="text-xl font-bold tracking-wide">
                  {primaryLogo.text_wordmark || primaryLogo.alt}
                </div>
                <div className="mt-1 text-xs text-muted-foreground">
                  Text wordmark detected from header/navigation.
                </div>
              </div>
            ) : primaryLogo?.src ? (
              <div className="rounded border bg-muted/30 p-4">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={primaryLogo.src}
                  alt={primaryLogo.alt || "Primary logo"}
                  className="max-h-24 max-w-full object-contain"
                />
              </div>
            ) : visual.logo_url ? (
              <div className="rounded border bg-muted/30 p-4">
                {/* legacy fallback */}
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={visual.logo_url}
                  alt="Brand logo"
                  className="max-h-24 max-w-full object-contain"
                />
              </div>
            ) : (
              <div className="rounded border border-amber-200 bg-amber-50 p-3">
                <p className="text-sm font-medium text-amber-900">
                  No confident primary logo found.
                </p>
                <p className="mt-1 text-xs text-amber-800">
                  {logoCandidates.length} logo candidate
                  {logoCandidates.length === 1 ? "" : "s"} preserved for review.
                </p>
              </div>
            )}

            {visual.visual_extraction_note && (
              <div className="mt-2 text-xs text-muted-foreground">
                Note:{" "}
                <span className="font-mono">
                  {visual.visual_extraction_note}
                </span>
              </div>
            )}

            {logoCandidates.length > 0 && (
              <div className="mt-3 text-xs text-muted-foreground">
                Logo candidates:{" "}
                <span className="font-medium text-foreground">
                  {logoCandidates.length}
                </span>
              </div>
            )}

            {visual.co_branding_detected && (
              <Badge variant="outline" className="mt-2 border-amber-300">
                co-branding detected
              </Badge>
            )}
          </div>

          {/* Visual warnings */}
          {visualWarnings.length > 0 && (
            <div>
              <div className="mb-2 text-xs uppercase tracking-wide text-muted-foreground">
                Visual warnings
              </div>
              <div className="flex flex-wrap gap-2">
                {visualWarnings.map((warning) => (
                  <Badge
                    key={warning}
                    variant="outline"
                    className="border-amber-300 bg-amber-50 text-amber-800"
                  >
                    {formatWarning(warning)}
                  </Badge>
                ))}
              </div>
            </div>
          )}

          {/* Brand palette */}
          {brandPalette.length > 0 && (
            <PaletteBlock
              title="Brand palette"
              colors={brandPalette}
              dominance={brandPaletteConfidence}
            />
          )}

          {/* Raw palette */}
          {rawPalette.length > 0 && (
            <PaletteBlock
              title="Raw screenshot palette"
              colors={rawPalette}
              dominance={rawPaletteDominance}
              muted
            />
          )}

          {/* Primary brand color */}
          {primaryBrandColor && (
            <div className="text-xs text-muted-foreground">
              Primary brand color:{" "}
              <span
                className="ml-1 inline-block h-3 w-3 rounded border align-middle"
                style={{ backgroundColor: primaryBrandColor }}
              />{" "}
              <span className="font-mono">{primaryBrandColor}</span>
            </div>
          )}

          {/* Palette note */}
          {visual.palette_extraction_note && (
            <div className="text-xs text-muted-foreground">
              Palette note:{" "}
              <span className="font-mono">
                {visual.palette_extraction_note}
              </span>
            </div>
          )}

          {/* Fonts */}
          {(visual.body_font || visual.heading_font) && (
            <div>
              <div className="mb-1 text-xs uppercase tracking-wide text-muted-foreground">
                Fonts
              </div>
              <div className="text-sm">
                {visual.heading_font && (
                  <div>
                    Heading:{" "}
                    <span className="font-medium">{visual.heading_font}</span>
                  </div>
                )}
                {visual.body_font && (
                  <div>
                    Body:{" "}
                    <span className="font-medium">{visual.body_font}</span>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Candidate preview */}
          {logoCandidates.length > 0 && (
            <div>
              <div className="mb-2 text-xs uppercase tracking-wide text-muted-foreground">
                Logo candidate review
              </div>
              <div className="space-y-2">
                {logoCandidates.slice(0, 4).map((candidate, index) => (
                  <div
                    key={`${candidate.src ?? candidate.text_wordmark ?? index}-${index}`}
                    className="rounded border bg-muted/20 p-2 text-xs"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium">
                        {candidate.source_type ?? "unknown"}
                      </span>
                      {candidate.confidence != null && (
                        <span className="text-muted-foreground">
                          confidence {Math.round(candidate.confidence * 100)}%
                        </span>
                      )}
                    </div>

                    {candidate.text_wordmark && (
                      <div className="mt-1 font-semibold">
                        {candidate.text_wordmark}
                      </div>
                    )}

                    {candidate.src && !candidate.src.startsWith("text-wordmark:") && (
                      <div className="mt-1 break-all font-mono text-[10px] text-muted-foreground">
                        {candidate.src}
                      </div>
                    )}

                    {candidate.classification && (
                      <div className="mt-1 text-muted-foreground">
                        {candidate.classification}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Contact &amp; social</CardTitle>
        </CardHeader>

        <CardContent className="space-y-4 text-sm">
          {(() => {
            // Prefer the structured `phones` list (e164 or dialable raw); fall
            // back to the deprecated `phones_e164` for older fixtures.
            const phoneList = (
              contact.phones && contact.phones.length
                ? contact.phones.map((p) => p.e164 || p.raw).filter(Boolean)
                : contact.phones_e164
            ) ?? [];
            return phoneList.length > 0 ? (
              <div>
                <div className="text-xs uppercase tracking-wide text-muted-foreground">
                  Phones
                </div>
                <div className="font-mono">{phoneList.join(", ")}</div>
              </div>
            ) : null;
          })()}

          {contact.emails?.length > 0 && (
            <div>
              <div className="text-xs uppercase tracking-wide text-muted-foreground">
                Emails
              </div>
              <div className="font-mono break-all">
                {contact.emails.join(", ")}
              </div>
            </div>
          )}

          {contact.whatsapp_numbers?.length > 0 && (
            <div>
              <div className="text-xs uppercase tracking-wide text-muted-foreground">
                WhatsApp
              </div>
              <div className="font-mono">
                {contact.whatsapp_numbers.join(", ")}
              </div>
            </div>
          )}

          <div className="flex flex-wrap gap-2">
            {contact.has_contact_form && (
              <Badge variant="outline">Contact form</Badge>
            )}

            {contact.map_embed_present && (
              <Badge variant="outline">Map embed</Badge>
            )}

            {languages?.map((l) => (
              <Badge key={l} variant="outline" className="font-mono uppercase">
                {l}
              </Badge>
            ))}
          </div>

          {socials?.length > 0 && (
            <div>
              <div className="text-xs uppercase tracking-wide text-muted-foreground">
                Social
              </div>
              <div className="mt-1 flex flex-wrap gap-2">
                {socials.map((s) => (
                  <a
                    key={s.url}
                    href={s.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="rounded border bg-muted/30 px-2 py-1 text-xs hover:bg-muted/60"
                  >
                    {s.platform}
                  </a>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function PaletteBlock({
  title,
  colors,
  dominance,
  muted,
}: {
  title: string;
  colors: string[];
  dominance?: number[];
  muted?: boolean;
}) {
  return (
    <div>
      <div className="mb-2 text-xs uppercase tracking-wide text-muted-foreground">
        {title}
      </div>

      <div className="flex flex-wrap gap-2">
        {colors.map((hex, i) => (
          <div
            key={`${title}-${hex}-${i}`}
            className="flex flex-col items-center text-xs"
          >
            <div
              className={`h-12 w-12 rounded border ${muted ? "opacity-80" : ""}`}
              style={{ backgroundColor: hex }}
              title={hex}
            />
            <div className="mt-1 font-mono text-[10px]">{hex}</div>
            {pct(dominance?.[i]) && (
              <div className="text-[10px] text-muted-foreground">
                {pct(dominance?.[i])}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
