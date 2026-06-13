"use client";

import { useState } from "react";

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
        <Input
          type="text"
          placeholder="https://example.com — any business website"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          disabled={disabled}
          className="flex-1"
          aria-label="Business URL"
        />
        <Button type="submit" disabled={disabled || !url.trim()} className="sm:w-32">
          {disabled ? "Analyzing…" : "Analyze"}
        </Button>
      </div>
      <label className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
        <input
          type="checkbox"
          checked={skipLlm}
          onChange={(e) => setSkipLlm(e.target.checked)}
          disabled={disabled}
          className="h-3 w-3"
        />
        Skip LLM (rules only) — useful for quick smoke tests
      </label>
    </form>
  );
}
