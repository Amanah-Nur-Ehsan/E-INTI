"use client";

import { Download } from "lucide-react";
import { useState } from "react";
import { FilePicker } from "@/components/FilePicker";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { missingAbstractsTemplateUrl } from "@/lib/api/client";
import {
  useImportLibrary,
  useLibraryStatus,
  useMissingAbstractsByYear,
  useRefreshLibrary,
} from "@/lib/api/hooks";

/** Moved from the public page's collapsible LibraryStrip -- this is the
 * whole point of the admin page now, so it's always expanded, no toggle. */
export function LibraryPanel() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const { data: status } = useLibraryStatus();
  const importLibrary = useImportLibrary();
  const refreshLibrary = useRefreshLibrary();
  const { data: missingByYear } = useMissingAbstractsByYear();

  return (
    <Card className="p-4">
      <h2 className="text-sm font-medium text-foreground">
        Reference library
        {status ? (
          <span className="ml-2 text-xs font-normal text-muted-foreground">
            {status.total} total
            {status.pending > 0 ? ` · ${status.pending} pending enrichment` : ""}
          </span>
        ) : null}
      </h2>

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
            {status.embed_pending > 0 ? ` (${status.embed_pending} pending)` : ""} · missing
            abstract {status.missing_abstract}
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
                    <a
                      href={missingAbstractsTemplateUrl(row.year)}
                      download
                      title="Download template for this year"
                    />
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
    </Card>
  );
}
