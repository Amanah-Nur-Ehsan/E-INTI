"use client";

import { Download, Loader2 } from "lucide-react";
import { useState } from "react";
import { BestReferencesPanel } from "@/components/BestReferencesPanel";
import { SdgSummary } from "@/components/SdgSummary";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { downloadUrl, missingAbstractsTemplateUrl } from "@/lib/api/client";
import {
  useAcceptedCitations,
  useAnalysisStatus,
  useCreateExport,
  useImportLibrary,
  useLibraryStatus,
  useMissingAbstractsByYear,
  useRefreshLibrary,
  useRunAnalysis,
  useUploadDraft,
} from "@/lib/api/hooks";
import { cn } from "@/lib/utils";
import type { AnalysisRunStatus } from "@/lib/api/hooks";

//: The raw RunStage enum values are backend vocabulary; show what the
//: stage is actually doing to the user's paper instead.
const STAGE_LABEL: Record<string, string> = {
  PARSING: "Reading the paper",
  CLASSIFYING_SDG: "Identifying the SDG",
  DETECTING: "Finding claims that need a citation",
  RECOMMENDING: "Matching references to claims",
};

/** Counts for the stage in flight, so a multi-minute wait shows movement. */
function progressDetail(status: AnalysisRunStatus): string {
  if (status.stage === "RECOMMENDING") {
    const done = status.claims.with_recommendations;
    const total = status.claims.needs_citation;
    return total > 0 ? `${done} of ${total} claims` : "";
  }
  if (status.stage === "DETECTING" && status.claims.total > 0) {
    return `${status.claims.needs_citation} of ${status.claims.total} sentences need citations`;
  }
  return "";
}

function FilePicker({
  file,
  onSelect,
  disabled,
  accept,
}: {
  file: File | null;
  onSelect: (file: File | null) => void;
  disabled?: boolean;
  accept: string;
}) {
  return (
    <>
      <label
        className={cn(
          "rounded-md border border-input bg-background px-2.5 py-1 text-xs font-medium text-foreground",
          disabled ? "cursor-not-allowed opacity-50" : "cursor-pointer hover:bg-muted",
        )}
      >
        Choose file
        <input
          type="file"
          accept={accept}
          className="sr-only"
          disabled={disabled}
          onChange={(e) => onSelect(e.target.files?.[0] ?? null)}
        />
      </label>
      <span className="text-xs text-muted-foreground">{file ? file.name : "No file chosen"}</span>
    </>
  );
}

function LibraryStrip() {
  const [open, setOpen] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const { data: status } = useLibraryStatus();
  const importLibrary = useImportLibrary();
  const refreshLibrary = useRefreshLibrary();
  const { data: missingByYear } = useMissingAbstractsByYear(open);

  return (
    <Card className="p-3">
      <button
        type="button"
        className="flex w-full items-center justify-between text-left"
        onClick={() => setOpen((v) => !v)}
      >
        <span className="text-sm font-medium text-foreground">
          Reference library
          {status ? (
            <span className="ml-2 text-xs font-normal text-muted-foreground">
              {status.total} total
              {status.pending > 0 ? ` · ${status.pending} pending enrichment` : ""}
            </span>
          ) : null}
        </span>
        <span className="text-xs text-muted-foreground">{open ? "Hide" : "Manage"}</span>
      </button>
      {open && (
        <div className="mt-3 flex flex-col gap-3 border-t pt-3">
          <div className="flex flex-col gap-2">
            <span className="text-xs text-muted-foreground">
              Import references (xlsx, csv) — re-upload the same file with an ABSTRACT column
              filled in to backfill abstracts on rows already in the library, without touching
              anything else on them.
            </span>
            <div className="flex flex-wrap items-center gap-2">
              <FilePicker
                file={selectedFile}
                onSelect={(f) => {
                  setSelectedFile(f);
                  importLibrary.reset();
                }}
                accept=".xlsx,.xlsm,.xls,.csv,.tsv,.txt"
              />
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
          </div>

          {importLibrary.isError && (
            <p className="text-xs text-destructive">
              Import failed: {(importLibrary.error as Error).message}
            </p>
          )}
          {importLibrary.isSuccess && (
            <p className="text-xs text-green-700">
              Imported {importLibrary.data.imported}, skipped{" "}
              {importLibrary.data.skipped_duplicates} duplicate
              {importLibrary.data.skipped_duplicates === 1 ? "" : "s"}
              {importLibrary.data.backfilled_abstracts > 0
                ? `, backfilled ${importLibrary.data.backfilled_abstracts} abstract${importLibrary.data.backfilled_abstracts === 1 ? "" : "s"}`
                : ""}
              {importLibrary.data.skipped_invalid > 0
                ? `, ${importLibrary.data.skipped_invalid} invalid row${importLibrary.data.skipped_invalid === 1 ? "" : "s"}`
                : ""}
              .
            </p>
          )}
          {refreshLibrary.isError && (
            <p className="text-xs text-destructive">
              Enrich failed: {(refreshLibrary.error as Error).message}
            </p>
          )}
          {refreshLibrary.isSuccess && (
            <p className="text-xs text-green-700">Enrichment + embedding started.</p>
          )}

          {status && (
            <span className="text-xs text-muted-foreground">
              enriched {status.enriched} · incomplete {status.incomplete} · failed {status.failed} ·
              embedded {status.embedded}
            </span>
          )}

          {missingByYear && missingByYear.length > 0 && (
            <div className="flex flex-col gap-1">
              <span className="text-xs text-muted-foreground">
                Missing abstracts by year (worst first) — fill these in first. Click a year to
                download a template listing exactly those rows: fill in the ABSTRACT column and
                re-upload it above to backfill.
              </span>
              <div className="flex flex-wrap gap-1.5">
                {missingByYear.map((row) => (
                  <Badge
                    key={row.year ?? "unknown"}
                    variant="outline"
                    className="cursor-pointer text-xs"
                    render={
                      <a href={missingAbstractsTemplateUrl(row.year)} download title="Download template for this year" />
                    }
                  >
                    {row.year ?? "Unknown year"}: {row.missing}/{row.total}
                    <Download className="h-3 w-3" />
                  </Badge>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

export default function Home() {
  const [draftId, setDraftId] = useState<string | null>(null);
  const [selectedDraftFile, setSelectedDraftFile] = useState<File | null>(null);
  const [hasStartedAnalysis, setHasStartedAnalysis] = useState(false);

  const uploadDraft = useUploadDraft();
  const runAnalysis = useRunAnalysis(draftId ?? "");
  const { data: status } = useAnalysisStatus(draftId ?? "", hasStartedAnalysis);
  const { data: acceptedCitations } = useAcceptedCitations(draftId ?? "");
  const createExport = useCreateExport(draftId ?? "");

  const isRunning = status ? status.status === "PENDING" || status.status === "RUNNING" : false;
  const isCompleted = status?.status === "COMPLETED";
  const hasAcceptedCitation = Boolean(
    acceptedCitations && Object.keys(acceptedCitations).length > 0,
  );

  async function handleUpload() {
    if (!selectedDraftFile) return;
    const draft = await uploadDraft.mutateAsync(selectedDraftFile);
    setHasStartedAnalysis(false);
    setDraftId(draft.id);
  }

  function handleReset() {
    setDraftId(null);
    setSelectedDraftFile(null);
    setHasStartedAnalysis(false);
    uploadDraft.reset();
  }

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-8">
      <header>
        <h1 className="text-xl font-semibold text-foreground">CitationINTI</h1>
        <p className="text-sm text-muted-foreground">
          Upload a draft, find Scopus-indexed citations for its claims, and export a marked-up
          docx.
        </p>
      </header>

      <LibraryStrip />

      <Card className="p-4">
        <h2 className="text-sm font-medium text-foreground">Upload paper</h2>
        <p className="mt-1 text-xs text-muted-foreground">
          Accepted formats: .docx, .md, .markdown, .txt
        </p>
        {draftId ? (
          <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
            <Badge variant="outline" className="bg-green-100 text-green-800 border-green-200">
              Uploaded
            </Badge>
            <span className="text-foreground">{selectedDraftFile?.name}</span>
            <Button size="sm" variant="ghost" onClick={handleReset}>
              Upload a different paper
            </Button>
          </div>
        ) : (
          <>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <FilePicker
                file={selectedDraftFile}
                onSelect={(f) => {
                  setSelectedDraftFile(f);
                  uploadDraft.reset();
                }}
                disabled={uploadDraft.isPending}
                accept=".docx,.md,.markdown,.txt"
              />
              <Button size="sm" disabled={!selectedDraftFile || uploadDraft.isPending} onClick={handleUpload}>
                {uploadDraft.isPending ? "Uploading…" : "Upload"}
              </Button>
            </div>
            {uploadDraft.isPending && (
              <p className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
                <Loader2 className="h-3 w-3 animate-spin" /> Uploading…
              </p>
            )}
            {uploadDraft.isError && (
              <p className="mt-2 text-xs text-destructive">
                Upload failed: {(uploadDraft.error as Error).message}
              </p>
            )}
          </>
        )}
        {draftId && !status && (
          <Button
            size="sm"
            className="mt-3"
            disabled={runAnalysis.isPending}
            onClick={() => {
              setHasStartedAnalysis(true);
              runAnalysis.mutate();
            }}
          >
            {runAnalysis.isPending ? "Starting…" : "Run analysis"}
          </Button>
        )}
        {status && (
          <div className="mt-3 flex items-center gap-2 text-xs text-muted-foreground">
            {isRunning && <Loader2 className="h-3 w-3 animate-spin" />}
            <Badge
              variant="outline"
              className={cn(
                isCompleted
                  ? "bg-green-100 text-green-800 border-green-200"
                  : isRunning
                    ? "bg-blue-100 text-blue-800 border-blue-200"
                    : "bg-red-100 text-red-800 border-red-200",
              )}
            >
              {STAGE_LABEL[status.stage ?? ""] ?? status.stage ?? status.status}
            </Badge>
            {isRunning && <span>{progressDetail(status)}</span>}
            {status.error && <span className="text-destructive">{status.error}</span>}
          </div>
        )}
      </Card>

      {isCompleted && (
        <>
          <SdgSummary
            sdgNumber={status?.sdg_number}
            sdgName={status?.sdg_name}
            sdgKeyword={status?.sdg_keyword}
            sdgRationale={status?.sdg_rationale}
          />
          <BestReferencesPanel draftId={draftId ?? ""} enabled={isCompleted} />

          <div className="flex flex-col items-end gap-1">
            <Button
              size="sm"
              variant="secondary"
              disabled={createExport.isPending || !hasAcceptedCitation}
              onClick={async () => {
                const exportResult = await createExport.mutateAsync({
                  format: "docx",
                  citation_style: "APA",
                  insertion_mode: "tracked_changes",
                  // The audit table is an internal QA report, not manuscript
                  // content -- the exported paper should come back clean.
                  include_audit_report: false,
                });
                window.location.href = downloadUrl(exportResult.id);
              }}
            >
              {createExport.isPending ? "Preparing…" : "Download DOCX"}
            </Button>
            {!hasAcceptedCitation && (
              <span className="text-xs text-muted-foreground">
                Select at least one citation to download
              </span>
            )}
          </div>
        </>
      )}
    </main>
  );
}
