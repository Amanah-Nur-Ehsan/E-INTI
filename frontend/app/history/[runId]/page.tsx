"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { RedirectTo } from "@/components/auth/RedirectTo";
import { DashboardShell } from "@/components/dashboard/DashboardShell";
import { Card } from "@/components/ui/card";
import {
  useAnalysisHistoryDetail,
  useSession,
  type AnalysisRecommendation,
  type AnalysisSnapshot,
} from "@/lib/api/hooks";
import { cn } from "@/lib/utils";

function VerdictBadge({ verdict }: { verdict: string }) {
  const cls =
    verdict === "SUPPORTED"
      ? "bg-green-100 text-green-800"
      : verdict === "CONTRADICTED"
        ? "bg-red-100 text-red-800"
        : verdict === "SKIPPED"
          ? "bg-zinc-100 text-zinc-600"
          : "bg-orange-100 text-orange-800";
  return (
    <span className={cn("shrink-0 rounded-full px-2 py-0.5 text-xs font-medium", cls)}>
      {verdict}
    </span>
  );
}

function RecommendationRow({ rec }: { rec: AnalysisRecommendation }) {
  return (
    <div className="rounded-lg border border-border p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-medium text-foreground">{rec.reference.title}</p>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {rec.reference.authors?.join(", ") || "Unknown authors"}
            {rec.reference.year ? ` (${rec.reference.year})` : ""}
            {rec.reference.source ? ` · ${rec.reference.source}` : ""}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <span className="text-sm font-semibold text-foreground">{Math.round(rec.score)}%</span>
          <VerdictBadge verdict={rec.verdict} />
        </div>
      </div>
      {rec.evidence && (
        <p className="mt-2 text-xs text-muted-foreground">{rec.evidence}</p>
      )}
      {rec.decision && rec.decision !== "PENDING" && (
        <p className="mt-1.5 text-xs">
          <span className="font-medium text-foreground">Decision:</span>{" "}
          <span className="text-muted-foreground">{rec.decision}</span>
        </p>
      )}
    </div>
  );
}

function SdgCard({ sdg }: { sdg: AnalysisSnapshot["sdg"] }) {
  if (!sdg.number && !sdg.name && !sdg.rationale) return null;
  return (
    <Card className="p-4">
      <h2 className="text-sm font-medium text-foreground">SDG classification</h2>
      <div className="mt-2 space-y-1 text-sm">
        {sdg.number && (
          <p className="text-foreground">
            <span className="font-semibold">SDG {sdg.number}</span>
            {sdg.name ? ` · ${sdg.name}` : ""}
          </p>
        )}
        {sdg.keyword && <p className="text-xs text-muted-foreground">Keyword: {sdg.keyword}</p>}
        {sdg.rationale && <p className="text-xs text-muted-foreground">{sdg.rationale}</p>}
        {sdg.closest_number && (
          <p className="text-xs text-muted-foreground">
            Closest match: SDG {sdg.closest_number}
            {sdg.closest_name ? ` · ${sdg.closest_name}` : ""}
          </p>
        )}
      </div>
    </Card>
  );
}

export default function HistoryDetailPage() {
  const params = useParams<{ runId: string }>();
  const { data: session, isLoading } = useSession();
  const { data: s, isLoading: detailLoading } = useAnalysisHistoryDetail(params.runId);

  if (isLoading) {
    return (
      <main className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-8">
        <p className="text-sm text-muted-foreground">Loading…</p>
      </main>
    );
  }
  if (!session?.authenticated) {
    return <RedirectTo to="/login" />;
  }

  return (
    <DashboardShell>
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-6">
        <div>
          <Link href="/history" className="text-sm font-medium text-red-600 hover:text-red-700">
            ← History
          </Link>
        </div>

        {detailLoading && (
          <p className="text-sm text-muted-foreground">Loading…</p>
        )}

        {s && (
          <>
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <h1 className="truncate text-xl font-semibold text-foreground">
                  {s.draft.filename}
                </h1>
                <p className="mt-0.5 text-sm text-muted-foreground">
                  {s.run.finished_at ? new Date(s.run.finished_at).toLocaleString() : ""}
                </p>
              </div>
              <span
                className={cn(
                  "shrink-0 rounded-full px-2 py-0.5 text-xs font-medium",
                  s.run.status === "COMPLETED"
                    ? "bg-green-100 text-green-800"
                    : s.run.status === "FAILED"
                      ? "bg-red-100 text-red-800"
                      : "bg-orange-100 text-orange-800",
                )}
              >
                {s.run.status}
              </span>
            </div>

            {s.run.error && (
              <p className="rounded-lg bg-red-50 px-3.5 py-2.5 text-sm text-red-700">
                {s.run.error}
              </p>
            )}

            <Card className="p-4">
              <h2 className="text-sm font-medium text-foreground">Summary</h2>
              <div className="mt-3 grid grid-cols-2 gap-4 sm:grid-cols-4">
                <div>
                  <p className="text-xs uppercase tracking-wide text-muted-foreground">Claims</p>
                  <p className="mt-1 text-2xl font-semibold text-foreground">
                    {s.summary.claims_total}
                  </p>
                </div>
                <div>
                  <p className="text-xs uppercase tracking-wide text-muted-foreground">
                    Need citation
                  </p>
                  <p className="mt-1 text-2xl font-semibold text-foreground">
                    {s.summary.claims_needing_citation}
                  </p>
                </div>
                <div>
                  <p className="text-xs uppercase tracking-wide text-muted-foreground">
                    Recommendations
                  </p>
                  <p className="mt-1 text-2xl font-semibold text-foreground">
                    {s.summary.recommendations}
                  </p>
                </div>
                <div>
                  <p className="text-xs uppercase tracking-wide text-muted-foreground">Accepted</p>
                  <p className="mt-1 text-2xl font-semibold text-foreground">{s.summary.accepted}</p>
                </div>
              </div>
            </Card>

            <SdgCard sdg={s.sdg} />

            <Card className="p-4">
              <h2 className="text-sm font-medium text-foreground">Draft text</h2>
              <pre className="mt-3 max-h-80 overflow-auto whitespace-pre-wrap rounded-lg border border-border bg-muted/30 p-3 text-xs leading-relaxed text-foreground">
                {s.draft.raw_text || "(no text extracted)"}
              </pre>
            </Card>

            <div className="flex flex-col gap-3">
              <h2 className="text-sm font-medium text-foreground">Claims & recommendations</h2>
              {s.claims.length === 0 && (
                <Card className="p-4">
                  <p className="text-sm text-muted-foreground">No claims detected.</p>
                </Card>
              )}
              {s.claims.map((claim) => (
                <Card key={claim.id} className="p-4">
                  <div className="flex items-start justify-between gap-3">
                    <p className="text-sm leading-relaxed text-foreground">{claim.sentence}</p>
                    {claim.needs_citation && (
                      <span className="shrink-0 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800">
                        needs citation
                      </span>
                    )}
                  </div>
                  {claim.claim_type && (
                    <p className="mt-1 text-xs uppercase tracking-wide text-muted-foreground">
                      {claim.claim_type}
                    </p>
                  )}
                  {claim.recommendations.length > 0 ? (
                    <div className="mt-3 flex flex-col gap-2">
                      {claim.recommendations.map((rec) => (
                        <RecommendationRow key={rec.id} rec={rec} />
                      ))}
                    </div>
                  ) : (
                    <p className="mt-3 text-xs text-muted-foreground">No recommendations.</p>
                  )}
                </Card>
              ))}
            </div>

            {s.accepted_citations.length > 0 && (
              <Card className="p-4">
                <h2 className="text-sm font-medium text-foreground">Accepted citations</h2>
                <ul className="mt-2 divide-y divide-border">
                  {s.accepted_citations.map((acc, i) => (
                    <li key={i} className="py-2 text-sm text-foreground">
                      {acc.citation_text || acc.reference.title}
                    </li>
                  ))}
                </ul>
              </Card>
            )}
          </>
        )}
      </div>
    </DashboardShell>
  );
}
