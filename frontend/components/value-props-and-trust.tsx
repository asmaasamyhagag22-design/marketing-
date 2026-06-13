"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { EvidenceDialog } from "./evidence-dialog";
import type { EvidencedField } from "@/lib/types";

interface EvidencedListProps {
  title: string;
  items: EvidencedField<string>[];
  emptyMessage?: string;
}

function EvidencedList({ title, items, emptyMessage }: EvidencedListProps) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg">{title}</CardTitle>
          <Badge variant="outline">{items.length}</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        {items.length === 0 ? (
          <p className="text-sm italic text-muted-foreground">
            {emptyMessage ?? "None extracted."}
          </p>
        ) : (
          items.map((item, i) => (
            <div
              key={i}
              className="flex items-start justify-between gap-3 rounded border bg-muted/20 px-3 py-2"
            >
              <div className="text-sm">{item.value}</div>
              <EvidenceDialog
                label={title}
                value={item.value ?? undefined}
                evidence={item.evidence}
                sourceType={item.source_type}
              />
            </div>
          ))
        )}
      </CardContent>
    </Card>
  );
}

interface ValuePropsAndTrustProps {
  valuePropositions: EvidencedField<string>[];
  trustSignals: EvidencedField<string>[];
  audienceSignals: EvidencedField<string>[];
  serviceAreas: EvidencedField<string>[];
  existingCtas: EvidencedField<string>[];
}

export function ValuePropsAndTrust({
  valuePropositions,
  trustSignals,
  audienceSignals,
  serviceAreas,
  existingCtas,
}: ValuePropsAndTrustProps) {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <EvidencedList
        title="Value propositions"
        items={valuePropositions}
        emptyMessage="The LLM didn't find distinct value propositions."
      />
      <EvidencedList
        title="Trust signals"
        items={trustSignals}
        emptyMessage="No credentials, awards, or testimonials surfaced."
      />
      <EvidencedList
        title="Audience signals"
        items={audienceSignals}
        emptyMessage="Audience signals are inferred from copy; none found."
      />
      <EvidencedList title="Service areas" items={serviceAreas} />
      <EvidencedList
        title="Existing CTAs"
        items={existingCtas}
        emptyMessage="No call-to-action links found on the scraped pages."
      />
    </div>
  );
}
