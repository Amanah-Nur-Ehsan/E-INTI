"use client";

import { useMemo, useState } from "react";
import { ReferenceRow } from "@/components/ReferenceRow";
import { Badge, Button, Card, Spinner } from "@/components/ui/primitives";
import { downloadUrl } from "@/lib/api/client";
import {
  useAnalysisStatus,
  useCreateExport,
  useClaims,
  useImportLibrary,
  useLibraryStatus,
  useRecommendationsByDraft,
  useRefreshLibrary,
  useRunAnalysis,
  useSetDecision,
  useUploadDraft,
} from "@/lib/api/hooks";
import { splitAroundSentence } from "@/lib/results";

function LibraryStrip() {
  const [open, setOpen] = useState(false);
  const { data: status } = useLibraryStatus();
  const importLibrary = useImportLibrary();
  const refreshLibrary = useRefreshLibrary();

  return (
    <Card className="p-3">
      <button
        type="button"
        className="flex w-full items-center justify-between text-left"
        onClick={() => setOpen((v) => !v)}
      >
        <span className="text-sm font-medium text-zinc-700">
          Reference library
          {status ? (
            <span className="ml-2 text-xs font-normal text-zinc-500">
              {status.total} total
              {status.pending > 0 ? ` · ${status.pending} pending enrichment` : ""}
            </span>
          ) : null}
        </span>
        <span className="text-xs text-zinc-400">{open ? "Hide" : "Manage"}</span>
      </button>
      {open && (
        <div className="mt-3 flex flex-wrap items-center gap-3 border-t border-zinc-100 pt-3">
          <label className="text-xs text-zinc-600">
            Import references (CSV)
            <input
              type="file"
              accept=".csv"
              className="mt-1 block text-xs"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) importLibrary.mutate(file);
                e.target.value = "";
              }}
            />
          </label>
          <Button
            size="sm"
            variant="secondary"
            disabled={refreshLibrary.isPending}
            onClick={() => refreshLibrary.mutate()}
          >
            {refreshLibrary.isPending ? "Enriching…" : "Enrich pending"}
          </Button>
          {status && (
            <span className="text-xs text-zinc-500">
              enriched {status.enriched} · incomplete {status.incomplete} · failed {status.failed} ·
              embedded {status.embedded}
            </span>
          )}
        </div>
      )}
    </Card>
  );
}

function ClaimRow({
  claimId,
  sectionTitle,
  localContext,
  sentenceText,
  recommendations,
  onUseRecommendation,
  isDeciding,
}: {
  claimId: string;
  sectionTitle: string | null;
  localContext: string;
  sentenceText: string;
  recommendations: import("@/lib/api/hooks").RecommendationRead[];
  onUseRecommendation: (recommendationId: string) => void;
  isDeciding: boolean;
}) {
  const { before, match, after } = splitAroundSentence(localContext, sentenceText);
  const top = recommendations.slice(0, 3);

  return (
    <Card className="p-4">
      {sectionTitle && <p className="text-xs font-medium uppercase text-zinc-400">{sectionTitle}</p>}
      <p className="mt-1 text-sm leading-relaxed text-zinc-700">
        {match ? (
          <>
            {before}
            <strong className="font-semibold text-zinc-900">{match}</strong>
            {after}
          </>
        ) : (
          before
        )}
      </p>
      <div className="mt-3 space-y-2">
        {top.length === 0 ? (
          <p className="text-xs text-zinc-400">No supporting reference found.</p>
        ) : (
          top.map((rec) => (
            <ReferenceRow
              key={rec.id}
              recommendation={rec}
              isPending={isDeciding}
              onUse={() => onUseRecommendation(rec.id)}
            />
          ))
        )}
      </div>
      <span className="sr-only">{claimId}</span>
    </Card>
  );
}

export default function Home() {
  const [draftId, setDraftId] = useState<string | null>(null);

  const uploadDraft = useUploadDraft();
  const runAnalysis = useRunAnalysis(draftId ?? "");
  const { data: status } = useAnalysisStatus(draftId ?? "");
  const { data: claims } = useClaims(draftId ?? "", true);
  const { data: recommendationsByClaim } = useRecommendationsByDraft(draftId ?? "");
  const setDecision = useSetDecision(draftId ?? "");
  const createExport = useCreateExport(draftId ?? "");

  const isRunning = status ? status.status === "PENDING" || status.status === "RUNNING" : false;
  const isCompleted = status?.status === "COMPLETED";

  const hasAcceptedCitation = useMemo(() => {
    if (!recommendationsByClaim) return false;
    return Object.values(recommendationsByClaim).some((recs) =>
      recs.some((r) => r.user_decision === "ACCEPTED"),
    );
  }, [recommendationsByClaim]);

  async function handleUpload(file: File) {
    const draft = await uploadDraft.mutateAsync(file);
    setDraftId(draft.id);
  }

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-8">
      <header>
        <h1 className="text-xl font-semibold text-zinc-900">CitationINTI</h1>
        <p className="text-sm text-zinc-500">
          Upload a draft, find Scopus-indexed citations for its claims, and export a marked-up
          docx.
        </p>
      </header>

      <LibraryStrip />

      <Card className="p-4">
        <h2 className="text-sm font-medium text-zinc-700">Upload paper</h2>
        <input
          type="file"
          accept=".docx,.doc,.pdf,.txt"
          className="mt-2 block text-sm"
          disabled={uploadDraft.isPending}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) handleUpload(file);
            e.target.value = "";
          }}
        />
        {uploadDraft.isPending && (
          <p className="mt-2 flex items-center gap-2 text-xs text-zinc-500">
            <Spinner className="h-3 w-3" /> Uploading…
          </p>
        )}
        {draftId && !status && (
          <Button
            size="sm"
            className="mt-3"
            disabled={runAnalysis.isPending}
            onClick={() => runAnalysis.mutate()}
          >
            {runAnalysis.isPending ? "Starting…" : "Run analysis"}
          </Button>
        )}
        {status && (
          <div className="mt-3 flex items-center gap-2 text-xs text-zinc-500">
            {isRunning && <Spinner className="h-3 w-3" />}
            <Badge tone={isCompleted ? "green" : isRunning ? "blue" : "red"}>
              {status.stage ?? status.status}
            </Badge>
            {status.error && <span className="text-red-600">{status.error}</span>}
          </div>
        )}
      </Card>

      {isCompleted && claims && (
        <section className="flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-medium text-zinc-700">
              Claims needing citation ({claims.length})
            </h2>
            {hasAcceptedCitation && (
              <Button
                size="sm"
                variant="secondary"
                disabled={createExport.isPending}
                onClick={async () => {
                  const exportResult = await createExport.mutateAsync({
                    format: "docx",
                    citation_style: "APA",
                    insertion_mode: "tracked_changes",
                    include_audit_report: true,
                  });
                  window.location.href = downloadUrl(exportResult.id);
                }}
              >
                {createExport.isPending ? "Preparing…" : "Download DOCX"}
              </Button>
            )}
          </div>

          {claims.length === 0 && (
            <p className="text-sm text-zinc-500">No claims needing citation were found.</p>
          )}

          {claims.map((claim) => (
            <ClaimRow
              key={claim.id}
              claimId={claim.id}
              sectionTitle={claim.section_title}
              localContext={claim.local_context}
              sentenceText={claim.sentence_text}
              recommendations={recommendationsByClaim?.[claim.id] ?? []}
              isDeciding={setDecision.isPending}
              onUseRecommendation={(recommendationId) =>
                setDecision.mutate({ recommendationId, decision: "ACCEPTED" })
              }
            />
          ))}
        </section>
      )}
    </main>
  );
}
