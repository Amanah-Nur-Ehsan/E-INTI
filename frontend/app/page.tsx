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
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
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
        <div className="mt-3 flex flex-col gap-3 border-t border-zinc-100 pt-3">
          <div className="flex flex-wrap items-center gap-2">
            <label className="text-xs text-zinc-600">
              Import references (xlsx, csv)
              <input
                type="file"
                accept=".xlsx,.xlsm,.xls,.csv,.tsv,.txt"
                className="mt-1 block text-xs"
                onChange={(e) => {
                  setSelectedFile(e.target.files?.[0] ?? null);
                  importLibrary.reset();
                }}
              />
            </label>
            <Button
              size="sm"
              disabled={!selectedFile || importLibrary.isPending}
              onClick={() => {
                if (!selectedFile) return;
                importLibrary.mutate(selectedFile, {
                  onSuccess: () => setSelectedFile(null),
                });
              }}
            >
              {importLibrary.isPending ? "Importing…" : "Import"}
            </Button>
            <Button
              size="sm"
              variant="secondary"
              disabled={refreshLibrary.isPending}
              onClick={() => refreshLibrary.mutate()}
            >
              {refreshLibrary.isPending ? "Enriching…" : "Enrich pending"}
            </Button>
          </div>

          {importLibrary.isError && (
            <p className="text-xs text-red-600">
              Import failed: {(importLibrary.error as Error).message}
            </p>
          )}
          {importLibrary.isSuccess && (
            <p className="text-xs text-green-700">
              Imported {importLibrary.data.imported}, skipped{" "}
              {importLibrary.data.skipped_duplicates} duplicate
              {importLibrary.data.skipped_duplicates === 1 ? "" : "s"}
              {importLibrary.data.skipped_invalid > 0
                ? `, ${importLibrary.data.skipped_invalid} invalid row${importLibrary.data.skipped_invalid === 1 ? "" : "s"}`
                : ""}
              .
            </p>
          )}
          {refreshLibrary.isError && (
            <p className="text-xs text-red-600">
              Enrich failed: {(refreshLibrary.error as Error).message}
            </p>
          )}
          {refreshLibrary.isSuccess && (
            <p className="text-xs text-green-700">Enrichment + embedding started.</p>
          )}

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
  const [selectedDraftFile, setSelectedDraftFile] = useState<File | null>(null);

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

  async function handleUpload() {
    if (!selectedDraftFile) return;
    const draft = await uploadDraft.mutateAsync(selectedDraftFile);
    setSelectedDraftFile(null);
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
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <input
            type="file"
            accept=".docx,.md,.markdown,.txt"
            className="block text-sm"
            disabled={uploadDraft.isPending}
            onChange={(e) => {
              setSelectedDraftFile(e.target.files?.[0] ?? null);
              uploadDraft.reset();
            }}
          />
          <Button size="sm" disabled={!selectedDraftFile || uploadDraft.isPending} onClick={handleUpload}>
            {uploadDraft.isPending ? "Uploading…" : "Upload"}
          </Button>
        </div>
        {uploadDraft.isPending && (
          <p className="mt-2 flex items-center gap-2 text-xs text-zinc-500">
            <Spinner className="h-3 w-3" /> Uploading…
          </p>
        )}
        {uploadDraft.isError && (
          <p className="mt-2 text-xs text-red-600">
            Upload failed: {(uploadDraft.error as Error).message}
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
          {status?.sdg_number && (
            <div className="flex items-center gap-2 text-xs text-zinc-500">
              <Badge tone="blue">SDG {status.sdg_number}</Badge>
              <span>
                {status.sdg_name}
                {status.sdg_keyword ? ` · ${status.sdg_keyword}` : ""}
              </span>
            </div>
          )}
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
