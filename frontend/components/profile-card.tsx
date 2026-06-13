"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { BusinessProfile } from "@/lib/types";
import { EvidencedField } from "./evidenced-field";

interface ProfileCardProps {
  profile: BusinessProfile;
}

export function ProfileCard({ profile }: ProfileCardProps) {
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center gap-3">
          <CardTitle className="text-2xl">
            {profile.name.value ?? "Unknown business"}
          </CardTitle>

          {profile.category.value && (
            <Badge variant="secondary" className="capitalize">
              {String(profile.category.value).replace(/_/g, " ")}
            </Badge>
          )}

          <a
            href={profile.final_url ?? profile.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-muted-foreground hover:underline"
          >
            {profile.source_url}
          </a>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        <EvidencedField label="Name" field={profile.name} />
        <EvidencedField label="Tagline" field={profile.tagline} />
        <EvidencedField label="Description" field={profile.description} />
        <EvidencedField label="Category" field={profile.category} />

        <div className="grid gap-4 sm:grid-cols-2">
          <EvidencedField label="Audience" field={profile.audience_type} />
          <EvidencedField label="Tone of voice" field={profile.tone_of_voice} />
          <PricingVisibleField profile={profile} />
          <EvidencedField label="Pricing posture" field={profile.pricing_posture} />
        </div>
      </CardContent>
    </Card>
  );
}

function PricingVisibleField({ profile }: { profile: BusinessProfile }) {
  const value = profile.pricing_visible?.value;
  const note = profile.pricing_extraction_note;

  const menuPageUrl =
    profile.offerings.find((offering) =>
      offering.page_url?.toLowerCase().includes("menu")
    )?.page_url ?? null;

  let statusText = "Unknown";
  let helperText: string | null = null;

  if (value === true) {
    statusText = "Visible";
    helperText = "Prices were detected as visible text.";
  } else if (value === false) {
    statusText = "Not visible";
    helperText = "No visible pricing signals were detected.";
  } else if (note === "menu_page_found_but_prices_not_text_extracted") {
    statusText = "Unknown";
    helperText =
      "Menu page found, but prices were not extracted as visible text.";
  } else if (note === "menu_page_timeout_partial_or_failed") {
    statusText = "Unknown";
    helperText =
      "Menu page was found, but extraction was partial or timed out.";
  } else if (note) {
    statusText = "Unknown";
    helperText = note.replace(/_/g, " ");
  }

  return (
    <div className="space-y-1">
      <div className="flex items-start gap-2">
        <span className="mt-1.5 h-2 w-2 rounded-full bg-slate-300" />

        <div>
          <div className="text-xs uppercase tracking-wide text-muted-foreground">
            Pricing visible
          </div>

          <div className="text-sm font-medium">{statusText}</div>

          {helperText && (
            <div className="max-w-sm text-xs text-muted-foreground">
              {helperText}
            </div>
          )}

          {menuPageUrl && (
            <a
              href={menuPageUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-1 inline-block text-xs font-medium underline"
            >
              Open menu page
            </a>
          )}
        </div>
      </div>
    </div>
  );
}