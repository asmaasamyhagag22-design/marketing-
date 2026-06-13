"use client";

import { ExternalLink } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { EvidenceItem, SourceType } from "@/lib/types";

interface EvidenceDialogProps {
  label: string; // e.g. "tagline", "Consultation"
  value?: string | null;
  evidence: EvidenceItem[];
  sourceType?: SourceType;
  trigger?: React.ReactNode;
}

function sourceVariant(s: SourceType | undefined) {
  if (s === "extracted") return "extracted" as const;
  if (s === "inferred") return "inferred" as const;
  return "missing" as const;
}

export function EvidenceDialog({
  label,
  value,
  evidence,
  sourceType,
  trigger,
}: EvidenceDialogProps) {
  return (
    <Dialog>
      <DialogTrigger asChild>
        {trigger ?? (
          <Button variant="ghost" size="sm" className="h-6 px-2 text-xs">
            view evidence
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <div className="flex items-center gap-2">
            <DialogTitle>{label}</DialogTitle>
            {sourceType && (
              <Badge variant={sourceVariant(sourceType)}>{sourceType}</Badge>
            )}
          </div>
          {value && (
            <DialogDescription className="pt-1 text-base text-foreground">
              {value}
            </DialogDescription>
          )}
        </DialogHeader>

        <div className="mt-2 space-y-3">
          {evidence.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No evidence recorded for this field.
            </p>
          ) : (
            evidence.map((ev, i) => (
              <EvidenceItemCard key={`${ev.block_id ?? "structural"}-${i}`} item={ev} />
            ))
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

function EvidenceItemCard({ item }: { item: EvidenceItem }) {
  return (
    <div className="rounded-md border bg-muted/40 p-3 text-sm">
      <div className="mb-2 flex items-center gap-2 text-xs font-medium text-muted-foreground">
        <span className="rounded bg-background px-1.5 py-0.5 font-mono">
          {item.block_id ?? "structural"}
        </span>
        <span>·</span>
        <span className="font-mono">{item.extractor}</span>
      </div>
      {item.quote && (
        <blockquote className="mb-2 border-l-2 border-slate-300 pl-3 italic">
          “{item.quote}”
        </blockquote>
      )}
      <a
        href={item.page_url}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-1 text-xs text-blue-600 hover:underline"
      >
        {item.page_url}
        <ExternalLink className="h-3 w-3" />
      </a>
    </div>
  );
}
