"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import { EvidenceDialog } from "./evidence-dialog";
import type { EvidencedField as EFType, SourceType } from "@/lib/types";

interface EvidencedFieldProps {
  label: string;
  field: EFType<unknown> | undefined;
  display?: (v: unknown) => string;
  className?: string;
  showLabel?: boolean;
}

function defaultDisplay(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "string") return v;
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (typeof v === "number") return String(v);
  return JSON.stringify(v);
}

function dotColor(s: SourceType | undefined) {
  if (s === "extracted") return "bg-emerald-500";
  if (s === "inferred") return "bg-amber-500";
  return "bg-slate-300";
}

/**
 * Renders a single claim with its source-type indicator and an
 * inline evidence button. Used everywhere in the profile UI so
 * every value visible to the user is one click from its source.
 */
export function EvidencedField({
  label,
  field,
  display = defaultDisplay,
  className,
  showLabel = true,
}: EvidencedFieldProps) {
  const value = field?.value ?? null;
  const sourceType: SourceType = field?.source_type ?? "missing";
  const hasValue = value !== null && value !== "";
  const evidence = field?.evidence ?? [];

  return (
    <div className={cn("group flex items-start gap-2", className)}>
      <span
        className={cn(
          "mt-1.5 inline-block h-2 w-2 shrink-0 rounded-full",
          dotColor(sourceType),
        )}
        aria-hidden
      />
      <div className="flex-1 space-y-0.5">
        {showLabel && (
          <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {label}
          </div>
        )}
        <div className="flex flex-wrap items-center gap-2">
          <span
            className={cn(
              "text-sm",
              !hasValue && "italic text-muted-foreground",
            )}
          >
            {hasValue ? display(value) : "missing"}
          </span>
          {evidence.length > 0 && (
            <EvidenceDialog
              label={label}
              value={hasValue ? display(value) : null}
              evidence={evidence}
              sourceType={sourceType}
            />
          )}
        </div>
      </div>
    </div>
  );
}
