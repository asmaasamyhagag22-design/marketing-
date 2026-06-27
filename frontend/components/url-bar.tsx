"use client";

import { useState } from "react";
import { Globe, Loader2, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface URLBarProps {
  onSubmit: (url: string, opts: { skipLlm: boolean }) => void;
  disabled?: boolean;
}

export function URLBar({ onSubmit, disabled }: URLBarProps) {
  const [url, setUrl] = useState("");
  const [skipLlm, setSkipLlm] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = url.trim();
    if (!trimmed) return;
    let normalized = trimmed;
    if (!/^https?:\/\//i.test(normalized)) {
      normalized = "https://" + normalized;
    }
    onSubmit(normalized, { skipLlm });
  };

  return (
    <form onSubmit={handleSubmit} className="w-full">
      <div className="flex flex-col gap-3 sm:flex-row">
        <div className="relative flex-1">
          <Globe
            className="pointer-events-none absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-primary/70"
            aria-hidden
          />
          <Input
            type="text"
            inputMode="url"
            autoComplete="off"
            spellCheck={false}
            placeholder="Paste any business website — e.g. nti.sci.eg"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            disabled={disabled}
            className="h-12 rounded-xl pl-12 text-base shadow-sm focus-visible:ring-primary"
            aria-label="Business URL"
          />
        </div>
        <Button
          type="submit"
          disabled={disabled || !url.trim()}
          className="h-12 gap-2 px-7 text-base sm:w-44"
        >
          {disabled ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Analyzing…
            </>
          ) : (
            <>
              <Sparkles className="h-4 w-4" />
              Analyze
            </>
          )}
        </Button>
      </div>
      <label className="mt-2.5 flex w-fit cursor-pointer items-center gap-2 text-xs text-muted-foreground">
        <input
          type="checkbox"
          checked={skipLlm}
          onChange={(e) => setSkipLlm(e.target.checked)}
          disabled={disabled}
          className="h-3.5 w-3.5 accent-primary"
        />
        Skip AI extraction (rules only) — faster smoke test
      </label>
    </form>
  );
}
