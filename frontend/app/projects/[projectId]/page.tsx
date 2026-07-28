"use client";

import { use } from "react";
import Link from "next/link";
import { useProjectSummary } from "@/lib/api/hooks";
import { Badge, Card, Spinner } from "@/components/ui/primitives";

function StatCard({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <Card className="p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-zinc-900">{value}</p>
      {sub && <p className="mt-1 text-xs text-zinc-500">{sub}</p>}
    </Card>
  );
}

function CoverageRing({ percentage }: { percentage: number }) {
  const radius = 42;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - percentage / 100);

  return (
    <div className="relative flex h-32 w-32 items-center justify-center">
      <svg viewBox="0 0 100 100" className="h-full w-full -rotate-90">
        <circle cx="50" cy="50" r={radius} fill="none" stroke="#e4e4e7" strokeWidth="10" />
        <circle
          cx="50"
          cy="50"
          r={radius}
          fill="none"
          stroke="#059669"
          strokeWidth="10"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
        />
      </svg>
      <span className="absolute text-xl font-semibold text-zinc-900">
        {percentage.toFixed(0)}%
      </span>
    </div>
  );
}

const STAGES = ["ENRICHING", "EMBEDDING", "PARSING", "DETECTING", "RECOMMENDING"];

function AnalysisStepper({ status, stage }: { status: string; stage: string | null }) {
  const currentIndex = stage ? STAGES.indexOf(stage) : -1;
  return (
    <div className="flex items-center gap-2">
      {STAGES.map((s, i) => {
        const done = status === "COMPLETED" || (currentIndex >= 0 && i < currentIndex);
        const active = status === "RUNNING" && i === currentIndex;
        return (
          <div key={s} className="flex items-center gap-2">
            <div
              className={`h-2.5 w-2.5 rounded-full ${
                done ? "bg-emerald-500" : active ? "animate-pulse bg-amber-500" : "bg-zinc-200"
              }`}
              title={s}
            />
            {i < STAGES.length - 1 && <div className="h-px w-4 bg-zinc-200" />}
          </div>
        );
      })}
    </div>
  );
}

export default function DashboardPage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = use(params);
  const { data: summary, isLoading } = useProjectSummary(projectId);

  if (isLoading || !summary) {
    return (
      <div className="flex justify-center py-16 text-zinc-400">
        <Spinner className="h-6 w-6" />
      </div>
    );
  }

  if (!summary.draft_id) {
    return (
      <Card className="p-8 text-center">
        <p className="text-sm text-zinc-600">
          No draft uploaded yet. Head to the Setup tab to upload a draft and import your reference
          dataset.
        </p>
        <Link
          href={`/projects/${projectId}/setup`}
          className="mt-3 inline-block text-sm font-medium text-zinc-900 underline"
        >
          Go to Setup &rarr;
        </Link>
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard
          label="Claims detected"
          value={summary.claims.total}
          sub={`${summary.claims.needs_citation} need a citation`}
        />
        <StatCard
          label="References enriched"
          value={summary.references.enriched}
          sub={`of ${summary.references.total} total`}
        />
        <StatCard
          label="Incomplete references"
          value={summary.references.incomplete}
          sub="no abstract retrieved"
        />
        <StatCard
          label="Accepted suggestions"
          value={summary.accepted_citations}
          sub={`across ${summary.claims_with_accepted} claims`}
        />
      </div>

      <Card className="flex flex-col items-center gap-4 p-6 sm:flex-row sm:justify-between">
        <div>
          <p className="text-sm font-medium text-zinc-900">Citation coverage</p>
          <p className="mt-1 max-w-sm text-xs text-zinc-500">
            Share of citation-worthy claims that currently have an accepted reference.
          </p>
          <Link
            href={`/projects/${projectId}/review`}
            className="mt-3 inline-block text-sm font-medium text-zinc-900 underline"
          >
            Review claims &rarr;
          </Link>
        </div>
        <CoverageRing percentage={summary.coverage_percentage} />
      </Card>

      {summary.latest_run && (
        <Card className="p-5">
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-zinc-900">Latest analysis run</p>
            <Badge
              tone={
                summary.latest_run.status === "COMPLETED"
                  ? "green"
                  : summary.latest_run.status === "FAILED"
                    ? "red"
                    : "yellow"
              }
            >
              {summary.latest_run.status}
            </Badge>
          </div>
          <div className="mt-3">
            <AnalysisStepper status={summary.latest_run.status} stage={summary.latest_run.stage} />
          </div>
          {summary.latest_run.error && (
            <p className="mt-3 text-xs text-red-600">{summary.latest_run.error}</p>
          )}
        </Card>
      )}
    </div>
  );
}
