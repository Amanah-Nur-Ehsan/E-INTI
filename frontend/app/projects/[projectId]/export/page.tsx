"use client";

import { use, useState } from "react";
import { useCreateExport, useExports } from "@/lib/api/hooks";
import { Badge, Button, Card, Spinner } from "@/components/ui/primitives";

const FORMATS = [
  { value: "docx", label: "DOCX (tracked changes)" },
  { value: "md", label: "Markdown" },
  { value: "csv", label: "CSV (audit report)" },
  { value: "json", label: "JSON (audit report)" },
] as const;

const INSERTION_MODES = [
  { value: "tracked_changes", label: "Tracked changes (review in Word)" },
  { value: "direct", label: "Direct (permanent text)" },
  { value: "placeholder", label: "Placeholder markers" },
] as const;

export default function ExportPage({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = use(params);
  const { data: exports } = useExports(projectId);
  const createExport = useCreateExport(projectId);

  const [format, setFormat] = useState<(typeof FORMATS)[number]["value"]>("docx");
  const [insertionMode, setInsertionMode] =
    useState<(typeof INSERTION_MODES)[number]["value"]>("tracked_changes");
  const [includeAudit, setIncludeAudit] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function handleExport() {
    setError(null);
    try {
      await createExport.mutateAsync({
        format,
        citation_style: "APA",
        insertion_mode: insertionMode,
        include_audit_report: includeAudit,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Export failed");
    }
  }

  const lastResult = createExport.data;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h2 className="text-lg font-semibold text-zinc-900">Export</h2>
        <p className="text-sm text-zinc-500">
          Generate a revised draft with accepted citations inserted, plus a bibliography and
          citation audit report.
        </p>
      </div>

      <Card className="p-5">
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="block text-xs font-medium text-zinc-600">Format</label>
            <select
              className="mt-1 w-full rounded-md border border-zinc-300 px-3 py-2 text-sm"
              value={format}
              onChange={(event) => setFormat(event.target.value as typeof format)}
            >
              {FORMATS.map((f) => (
                <option key={f.value} value={f.value}>
                  {f.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-zinc-600">
              Insertion mode {format !== "docx" && "(DOCX only)"}
            </label>
            <select
              className="mt-1 w-full rounded-md border border-zinc-300 px-3 py-2 text-sm disabled:bg-zinc-50 disabled:text-zinc-400"
              value={insertionMode}
              disabled={format !== "docx"}
              onChange={(event) => setInsertionMode(event.target.value as typeof insertionMode)}
            >
              {INSERTION_MODES.map((m) => (
                <option key={m.value} value={m.value}>
                  {m.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        <label className="mt-4 flex items-center gap-2 text-sm text-zinc-700">
          <input
            type="checkbox"
            checked={includeAudit}
            onChange={(event) => setIncludeAudit(event.target.checked)}
          />
          Include citation audit report
        </label>

        <Button className="mt-4" onClick={handleExport} disabled={createExport.isPending}>
          {createExport.isPending ? <Spinner className="h-4 w-4" /> : "Generate export"}
        </Button>
        {error && <p className="mt-2 text-xs text-red-600">{error}</p>}

        {lastResult && (
          <div className="mt-4 rounded-md border border-zinc-200 bg-zinc-50 p-3 text-sm">
            <p className="font-medium text-zinc-900">{lastResult.filename}</p>
            <p className="mt-1 text-xs text-zinc-500">
              {lastResult.inserted_count} citation(s) inserted
              {lastResult.mismatch_count > 0 && (
                <span className="text-amber-700">
                  {" "}
                  &middot; {lastResult.mismatch_count} skipped because the draft changed since
                  analysis
                </span>
              )}
            </p>
            <a
              href={`/api/v1/exports/${lastResult.id}/download`}
              className="mt-2 inline-block text-sm font-medium text-zinc-900 underline"
            >
              Download &darr;
            </a>
          </div>
        )}
      </Card>

      <Card className="p-5">
        <p className="mb-3 text-sm font-medium text-zinc-900">Export history</p>
        {!exports || exports.length === 0 ? (
          <p className="text-sm text-zinc-500">No exports yet.</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {exports.map((exp) => (
              <li
                key={exp.id}
                className="flex items-center justify-between rounded-md border border-zinc-100 px-3 py-2 text-sm"
              >
                <div>
                  <span className="font-medium text-zinc-900">{exp.filename}</span>
                  <span className="ml-2 text-xs text-zinc-500">
                    {new Date(exp.created_at).toLocaleString()}
                  </span>
                  {exp.mismatch_count > 0 && (
                    <Badge tone="orange" className="ml-2">
                      {exp.mismatch_count} mismatch(es)
                    </Badge>
                  )}
                </div>
                <a
                  href={`/api/v1/exports/${exp.id}/download`}
                  className="text-xs font-medium text-zinc-900 underline"
                >
                  Download
                </a>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
