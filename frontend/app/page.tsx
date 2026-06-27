"use client";

import { Suspense, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { AlertCircle, Loader2, Sparkles } from "lucide-react";

import { URLBar } from "@/components/url-bar";
import { PipelineTimeline } from "@/components/pipeline-timeline";
import { TabsShell } from "@/components/tabs-shell";
import { Card, CardContent } from "@/components/ui/card";

import { postRun, ApiError } from "@/lib/api-client";
import {
  getFixture,
  isFixtureKey,
  synthesizeStageEvents,
  TIMELINE_STAGES,
} from "@/lib/fixtures";
import type { BusinessProfile, StageEvent } from "@/lib/types";
import { useJobStream } from "@/hooks/use-job-stream";

export default function HomePage() {
  return (
    <Suspense fallback={<PageLoading />}>
      <HomeInner />
    </Suspense>
  );
}

function PageLoading() {
  return (
    <main className="mx-auto max-w-6xl px-4 py-8">
      <div className="text-sm text-muted-foreground">Loading…</div>
    </main>
  );
}

function HomeInner() {
  const searchParams = useSearchParams();
  const demo = searchParams.get("demo");

  // Three modes:
  // 1. Fixture mode: ?demo=sp-clinic → load static profile + synthesized events
  // 2. Live mode: jobId set → SSE stream + result
  // 3. Empty: just the URL bar
  const [jobId, setJobId] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const live = useJobStream(jobId);

  // Compute the active mode
  const fixtureProfile: BusinessProfile | null = useMemo(() => {
    if (isFixtureKey(demo)) {
      return getFixture(demo);
    }
    return null;
  }, [demo]);

  const fixtureEvents: StageEvent[] = useMemo(() => {
    if (fixtureProfile) {
      return synthesizeStageEvents("fixture", fixtureProfile);
    }
    return [];
  }, [fixtureProfile]);

  const enablePosterTab =
    process.env.NEXT_PUBLIC_ENABLE_POSTER_TAB !== "false";

  const activeProfile = fixtureProfile ?? live.result;
  const activeEvents = fixtureProfile ? fixtureEvents : live.events;
  const activeStage = fixtureProfile ? null : live.currentStage;
  const activeError = submitError ?? live.error;

  const handleSubmit = async (url: string, opts: { skipLlm: boolean }) => {
    setSubmitError(null);
    setIsSubmitting(true);
    try {
      const resp = await postRun({ url, skip_llm: opts.skipLlm });
      setJobId(resp.job_id);
    } catch (err) {
      if (err instanceof ApiError) {
        setSubmitError(`${err.status}: ${err.message}`);
      } else {
        setSubmitError(String(err));
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const showTimeline =
    fixtureProfile !== null ||
    jobId !== null ||
    live.events.length > 0;

  return (
    <main className="mx-auto max-w-6xl px-4 py-8">
      <Header demo={demo} />

      <section className="mt-8 animate-fade-up [animation-delay:80ms]">
        <URLBar
          onSubmit={handleSubmit}
          disabled={isSubmitting || (jobId !== null && live.status === "running")}
        />
        {activeError && (
          <div
            role="alert"
            className="mt-3 flex items-start gap-2.5 rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive animate-fade-up"
          >
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <div>
              <span className="font-semibold">Couldn&apos;t analyze that URL.</span>{" "}
              <span className="text-destructive/85">{activeError}</span>
            </div>
          </div>
        )}
      </section>

      {showTimeline && (
        <section className="mt-8">
          <PipelineTimeline
            stages={TIMELINE_STAGES}
            events={activeEvents}
            currentStage={activeStage}
          />
        </section>
      )}

      <section className="mt-8 animate-fade-up [animation-delay:160ms]">
        {activeProfile ? (
          <TabsShell
            profile={activeProfile}
            events={activeEvents}
            enablePosterTab={enablePosterTab}
          />
        ) : jobId && live.status === "running" ? (
          <RunningPlaceholder />
        ) : !demo && !jobId ? (
          <EmptyState />
        ) : null}
      </section>
    </main>
  );
}

function Header({ demo }: { demo: string | null }) {
  return (
    <header className="animate-fade-up">
      <div className="flex items-start justify-between gap-4">
        <div>
          <span className="mb-3 inline-flex items-center gap-1.5 rounded-full border border-primary/20 bg-secondary px-3 py-1 text-xs font-semibold text-primary">
            <Sparkles className="h-3.5 w-3.5" />
            AI Marketing Studio
          </span>
          <h1 className="text-3xl font-extrabold tracking-tight sm:text-4xl">
            <span className="text-gradient animate-gradient">Marketing Strategist</span>
          </h1>
          <p className="mt-2 max-w-xl text-sm text-muted-foreground">
            Turn any business URL into an evidence-based profile, a SWOT, and
            on-brand creative — every claim traceable to its source.
          </p>
        </div>
        {demo && (
          <span className="shrink-0 rounded-full border border-primary/20 bg-secondary px-3 py-1 text-xs font-medium text-primary">
            fixture: {demo}
          </span>
        )}
      </div>
    </header>
  );
}

function RunningPlaceholder() {
  return (
    <Card className="overflow-hidden border-primary/10">
      <div className="h-1.5 bg-brand-gradient animate-gradient" />
      <CardContent className="flex flex-col items-center gap-4 py-12 text-center">
        <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-secondary">
          <Loader2 className="h-7 w-7 animate-spin text-primary" />
        </div>
        <div className="space-y-1.5">
          <h2 className="text-lg font-bold">Reading the website…</h2>
          <p className="mx-auto max-w-md text-sm text-muted-foreground">
            Scraping pages, extracting every claim, and grounding it in evidence.
            Follow the live timeline above — your profile appears the moment the
            merge stage finishes.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

function EmptyState() {
  return (
    <Card className="card-hover overflow-hidden border-primary/10">
      <div className="h-1.5 bg-brand-gradient animate-gradient" />
      <CardContent className="space-y-3 py-12 text-center">
        <div className="mx-auto flex h-14 w-14 animate-float items-center justify-center rounded-2xl bg-brand-gradient text-white shadow-lg shadow-primary/30">
          <Sparkles className="h-7 w-7" />
        </div>
        <h2 className="text-xl font-bold">Let&apos;s make something 🎉</h2>
        <p className="mx-auto max-w-md text-sm text-muted-foreground">
          Paste a business URL above and hit Analyze. The pipeline runs
          scraper → rules → LLM extraction → validator → merger, streaming
          progress live.
        </p>
        <p className="text-xs text-muted-foreground">
          Or load a demo:{" "}
          <a href="/?demo=sp-clinic" className="font-medium text-primary underline-offset-4 hover:underline">
            ?demo=sp-clinic
          </a>
        </p>
      </CardContent>
    </Card>
  );
}
