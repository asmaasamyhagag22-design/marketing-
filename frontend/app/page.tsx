"use client";

import { Suspense, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";

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

      <section className="mt-8">
        <URLBar
          onSubmit={handleSubmit}
          disabled={isSubmitting || (jobId !== null && live.status === "running")}
        />
        {activeError && (
          <p className="mt-3 text-sm text-destructive">{activeError}</p>
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

      <section className="mt-8">
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
    <header>
      <div className="flex items-baseline justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            Marketing Strategist
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Evidence-based business profile from any URL. Every claim is
            traceable to its source.
          </p>
        </div>
        {demo && (
          <span className="rounded-full border bg-amber-50 px-3 py-1 text-xs font-medium text-amber-700">
            fixture: {demo}
          </span>
        )}
      </div>
    </header>
  );
}

function RunningPlaceholder() {
  return (
    <Card>
      <CardContent className="py-10 text-center text-sm text-muted-foreground">
        Pipeline running. Watch the timeline above; the profile will appear
        when the merge stage completes.
      </CardContent>
    </Card>
  );
}

function EmptyState() {
  return (
    <Card>
      <CardContent className="space-y-3 py-10 text-center">
        <h2 className="text-lg font-semibold">Try the pipeline</h2>
        <p className="text-sm text-muted-foreground">
          Paste a business URL above and click Analyze. The pipeline runs
          scraper → rules → LLM extraction → validator → merger, streaming
          progress in real time.
        </p>
        <p className="text-xs text-muted-foreground">
          Or load a fixture:{" "}
          <a href="/?demo=sp-clinic" className="underline">
            ?demo=sp-clinic
          </a>
        </p>
      </CardContent>
    </Card>
  );
}
