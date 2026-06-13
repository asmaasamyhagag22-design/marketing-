"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { EvidenceDialog } from "./evidence-dialog";
import type { Offering } from "@/lib/types";

interface OfferingsListProps {
  offerings: Offering[];
}

export function OfferingsList({ offerings }: OfferingsListProps) {
  if (offerings.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Offerings</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm italic text-muted-foreground">
            No offerings extracted. The LLM may have skipped this group or no
            services/products pages were scraped.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg">Offerings</CardTitle>
          <Badge variant="outline">{offerings.length}</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {offerings.map((o, i) => (
          <div
            key={`${o.name}-${i}`}
            className="rounded-md border p-3 transition-colors hover:bg-muted/30"
          >
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <div className="font-medium">{o.name}</div>
              {o.price_text && (
                <Badge variant="secondary" className="font-mono text-xs">
                  {o.price_text}
                </Badge>
              )}
            </div>
            {o.short_description && (
              <p className="mt-1 text-sm text-muted-foreground">
                {o.short_description}
              </p>
            )}
            <div className="mt-2 flex items-center gap-2">
              <EvidenceDialog
                label={o.name}
                value={o.short_description ?? o.name}
                evidence={o.evidence}
                sourceType="inferred"
              />
              {o.page_url && (
                <a
                  href={o.page_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-muted-foreground hover:underline"
                >
                  source page
                </a>
              )}
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
