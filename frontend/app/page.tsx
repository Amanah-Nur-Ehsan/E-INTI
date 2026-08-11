"use client";

import { Loader2 } from "lucide-react";
import { useState } from "react";
import { BestReferencesPanel } from "@/components/BestReferencesPanel";
import { FilePicker } from "@/components/FilePicker";
import { SdgSummary } from "@/components/SdgSummary";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useAnalysisStatus, useLibraryStatus, useRunAnalysis, useUploadDraft } from "@/lib/api/hooks";
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

/** A one-line library size, kept on the public page since it gives useful
 * context ("is there anything to search against yet") without exposing
 * any of the admin-only import/enrich controls that used to live here. */
function LibraryCount() {
  const { data: status } = useLibraryStatus();
  if (!status) return null;
  return (
    <p className="text-xs text-muted-foreground">
      Reference library: {status.total} total
      {status.pending > 0 ? ` · ${status.pending} pending enrichment` : ""}
    </p>
  );
}

export default function Home() {
  const [draftId, setDraftId] = useState<string | null>(null);
  const [selectedDraftFile, setSelectedDraftFile] = useState<File | null>(null);
  const [hasStartedAnalysis, setHasStartedAnalysis] = useState(false);

  const uploadDraft = useUploadDraft();
  const runAnalysis = useRunAnalysis(draftId ?? "");
  const { data: status } = useAnalysisStatus(draftId ?? "", hasStartedAnalysis);

  const isRunning = status ? status.status === "PENDING" || status.status === "RUNNING" : false;
  const isCompleted = status?.status === "COMPLETED";

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

      <LibraryCount />

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
            sdgClosestNumber={status?.sdg_closest_number}
            sdgClosestName={status?.sdg_closest_name}
          />
          <BestReferencesPanel draftId={draftId ?? ""} enabled={isCompleted} />
        </>
      )}
    </main>
  );
}
