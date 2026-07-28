"use client";

import { use, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  useAnalysisStatus,
  useDrafts,
  useImportReferences,
  useReferenceStatus,
  useRunAnalysis,
  useUploadDraft,
} from "@/lib/api/hooks";
import { Badge, Button, Card, Spinner } from "@/components/ui/primitives";

function UploadCard({
  title,
  description,
  accept,
  onUpload,
  isPending,
  error,
  status,
}: {
  title: string;
  description: string;
  accept: string;
  onUpload: (file: File) => void;
  isPending: boolean;
  error?: string | null;
  status?: React.ReactNode;
}) {
  const inputRef = useRef<HTMLInputElement>(null);

  return (
    <Card className="p-5">
      <p className="font-medium text-zinc-900">{title}</p>
      <p className="mt-1 text-xs text-zinc-500">{description}</p>
      <div className="mt-4 flex items-center gap-3">
        <input
          ref={inputRef}
          type="file"
          accept={accept}
          className="hidden"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) onUpload(file);
            event.target.value = "";
          }}
        />
        <Button
          variant="secondary"
          onClick={() => inputRef.current?.click()}
          disabled={isPending}
        >
          {isPending ? <Spinner className="h-4 w-4" /> : "Choose file"}
        </Button>
        {status}
      </div>
      {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
    </Card>
  );
}

const STAGE_LABELS: Record<string, string> = {
  ENRICHING: "Enriching references from Scopus",
  EMBEDDING: "Embedding references",
  PARSING: "Parsing draft",
  DETECTING: "Detecting claims",
  RECOMMENDING: "Generating recommendations",
};

export default function SetupPage({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = use(params);
  const router = useRouter();

  const { data: drafts } = useDrafts(projectId);
  const { data: refStatus } = useReferenceStatus(projectId);
  const { data: analysis } = useAnalysisStatus(projectId);

  const uploadDraft = useUploadDraft(projectId);
  const importReferences = useImportReferences(projectId);
  const runAnalysis = useRunAnalysis(projectId);

  const [runError, setRunError] = useState<string | null>(null);

  const latestDraft = drafts?.[0];
  const hasDraft = Boolean(latestDraft);
  const hasReferences = Boolean(refStatus && refStatus.total > 0);
  const isRunning = analysis && ["PENDING", "RUNNING"].includes(analysis.status);

  async function handleRunAnalysis() {
    setRunError(null);
    try {
      await runAnalysis.mutateAsync(undefined);
    } catch (err) {
      setRunError(err instanceof Error ? err.message : "Failed to start analysis");
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h2 className="text-lg font-semibold text-zinc-900">Setup</h2>
        <p className="text-sm text-zinc-500">
          Upload the draft paper and the reference dataset, then run analysis.
        </p>
      </div>

      <UploadCard
        title="1. Draft paper"
        description="A .docx, .md, or .txt file. DOCX export with tracked changes requires a .docx source."
        accept=".docx,.md,.markdown,.txt"
        onUpload={(file) => uploadDraft.mutate(file)}
        isPending={uploadDraft.isPending}
        error={uploadDraft.isError ? (uploadDraft.error as Error).message : null}
        status={
          latestDraft && (
            <span className="text-xs text-zinc-600">
              {latestDraft.original_filename} &middot;{" "}
              <Badge tone={latestDraft.parse_status === "PARSED" ? "green" : "neutral"}>
                {latestDraft.parse_status}
              </Badge>
            </span>
          )
        }
      />

      <UploadCard
        title="2. Reference dataset"
        description="An .xlsx or .csv file with DOCUMENT TITLE and LINK columns (Scopus export or similar)."
        accept=".xlsx,.csv"
        onUpload={(file) => importReferences.mutate(file)}
        isPending={importReferences.isPending}
        error={importReferences.isError ? (importReferences.error as Error).message : null}
        status={
          refStatus &&
          refStatus.total > 0 && (
            <span className="text-xs text-zinc-600">
              {refStatus.total} imported &middot; {refStatus.enriched} enriched &middot;{" "}
              {refStatus.pending} pending
            </span>
          )
        }
      />
      {importReferences.data && importReferences.data.warnings.length > 0 && (
        <p className="-mt-4 text-xs text-amber-700">
          {importReferences.data.warnings.length} warning(s) during import (e.g. rows with no
          resolvable identifier).
        </p>
      )}

      <Card className="p-5">
        <p className="font-medium text-zinc-900">3. Run analysis</p>
        <p className="mt-1 text-xs text-zinc-500">
          Enriches references, embeds them, parses the draft, detects claims, and generates
          recommendations. This can take several minutes -- Groq&apos;s rate limits dominate
          runtime for larger drafts.
        </p>
        <div className="mt-4 flex items-center gap-3">
          <Button
            onClick={handleRunAnalysis}
            disabled={!hasDraft || !hasReferences || Boolean(isRunning)}
          >
            {isRunning ? <Spinner className="h-4 w-4" /> : "Run analysis"}
          </Button>
          {!hasDraft && <span className="text-xs text-zinc-500">Upload a draft first.</span>}
          {hasDraft && !hasReferences && (
            <span className="text-xs text-zinc-500">Import references first.</span>
          )}
          {analysis && (
            <Badge
              tone={
                analysis.status === "COMPLETED"
                  ? "green"
                  : analysis.status === "FAILED"
                    ? "red"
                    : "yellow"
              }
            >
              {analysis.status}
              {analysis.stage ? ` · ${STAGE_LABELS[analysis.stage] ?? analysis.stage}` : ""}
            </Badge>
          )}
        </div>
        {(runError || analysis?.error) && (
          <p className="mt-2 text-xs text-red-600">{runError ?? analysis?.error}</p>
        )}
        {analysis?.status === "COMPLETED" && (
          <Button
            variant="secondary"
            className="mt-4"
            onClick={() => router.push(`/projects/${projectId}/review`)}
          >
            Go to Review &rarr;
          </Button>
        )}
      </Card>
    </div>
  );
}
