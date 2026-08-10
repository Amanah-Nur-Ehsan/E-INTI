"use client";

import { useState } from "react";
import { CopyButton } from "@/components/CopyButton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useRewriteParagraph, useSetDecision } from "@/lib/api/hooks";
import type { BestReferenceRead } from "@/lib/api/hooks";
import { splitAroundSentence } from "@/lib/results";
import { cn } from "@/lib/utils";

const STYLES = ["APA", "CHICAGO", "IEEE"] as const;

const VERDICT_BADGE: Record<string, { label: string; className: string }> = {
  SUPPORTED: { label: "Supported", className: "bg-green-100 text-green-800 border-green-200" },
  PARTIALLY_SUPPORTED: {
    label: "Partially supported",
    className: "bg-amber-100 text-amber-800 border-amber-200",
  },
  TOPICALLY_RELATED_BUT_NOT_EVIDENCE: {
    label: "Topically related",
    className: "bg-amber-100 text-amber-800 border-amber-200",
  },
  INSUFFICIENT_EVIDENCE: {
    label: "Insufficient evidence",
    className: "bg-zinc-100 text-zinc-600 border-zinc-200",
  },
  CONTRADICTED: { label: "Contradicted", className: "bg-red-100 text-red-800 border-red-200" },
  SKIPPED: { label: "Not verified", className: "bg-zinc-100 text-zinc-600 border-zinc-200" },
};

function formatAuthors(authors: unknown[] | null): string {
  if (!authors || authors.length === 0) return "Unknown authors";
  const names = authors
    .map((a) =>
      typeof a === "object" && a !== null && "name" in a
        ? String((a as { name: unknown }).name)
        : null,
    )
    .filter((n): n is string => Boolean(n));
  if (names.length === 0) return "Unknown authors";
  if (names.length <= 3) return names.join(", ");
  return `${names.slice(0, 3).join(", ")}, et al.`;
}

/** One reference in the paper-level shortlist: its claim/paragraph, score,
 * expandable details, a citation-style selector, and the "generate cited
 * paragraph" + "use this" actions. Each card owns its own open/style state
 * -- expanding one reference's details or picking a style for it must not
 * affect any other card in the list. */
export function ReferenceCard({ draftId, item }: { draftId: string; item: BestReferenceRead }) {
  const setDecision = useSetDecision(draftId);
  const rewriteParagraph = useRewriteParagraph();
  const [style, setStyle] = useState<(typeof STYLES)[number]>("APA");
  const [detailsOpen, setDetailsOpen] = useState(false);

  const { recommendation, claim, reference, meets_threshold, is_recommended } = item;
  const badge = VERDICT_BADGE[recommendation.verdict] ?? {
    label: recommendation.verdict,
    className: "bg-zinc-100 text-zinc-600 border-zinc-200",
  };
  const accepted = recommendation.user_decision === "ACCEPTED";
  const { before, match, after } = splitAroundSentence(claim.local_context, claim.sentence_text);

  return (
    <Card className="p-4">
      {!meets_threshold && (
        <p className="mb-2 rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800">
          Closest match found, but below the {item.min_score_threshold}% threshold -- treat as a
          weak candidate, not a confident recommendation.
        </p>
      )}
      {meets_threshold && !is_recommended && (
        <p className="mb-2 rounded-md border border-blue-200 bg-blue-50 p-2 text-xs text-blue-800">
          Clears the {item.min_score_threshold}% threshold but not the{" "}
          {item.recommended_score_threshold}% recommended bar.
        </p>
      )}

      {claim.section_title && (
        <p className="text-xs font-medium uppercase text-muted-foreground">
          {claim.section_title}
        </p>
      )}
      <p className="mt-1 text-sm leading-relaxed text-foreground/90">
        {match ? (
          <>
            {before}
            <strong className="font-semibold text-foreground">{match}</strong>
            {after}
          </>
        ) : (
          before
        )}
      </p>

      <div className="mt-3 border-t pt-3">
        <div className="flex items-start justify-between gap-2">
          <p className="text-sm font-medium text-foreground">{reference.title}</p>
          <Badge
            variant="outline"
            className={cn(
              badge.className,
              !meets_threshold && "opacity-70",
              is_recommended && "ring-1 ring-green-400",
            )}
          >
            {badge.label}
          </Badge>
        </div>
        <p className="mt-0.5 text-xs text-muted-foreground">
          {formatAuthors(reference.authors)} &middot; {reference.year ?? "n.d."}
          {reference.source_title ? ` · ${reference.source_title}` : ""}
          {" · "}
          {recommendation.score_percentage.toFixed(1)}% ({recommendation.recommendation_label})
        </p>
        {recommendation.evidence_paraphrase && (
          <p className="mt-1 text-xs text-zinc-600">{recommendation.evidence_paraphrase}</p>
        )}

        <div className="mt-2 flex flex-wrap items-center gap-3">
          {reference.doi && (
            <a
              href={`https://doi.org/${reference.doi}`}
              target="_blank"
              rel="noreferrer"
              className="text-xs text-sky-700 underline"
            >
              DOI
            </a>
          )}
          <Button
            size="sm"
            variant="ghost"
            className="h-7 px-2 text-xs"
            onClick={() => setDetailsOpen((v) => !v)}
          >
            {detailsOpen ? "Hide details" : "View details"}
          </Button>
          <Button
            size="sm"
            variant={accepted ? "secondary" : "default"}
            disabled={setDecision.isPending || accepted}
            onClick={() =>
              setDecision.mutate({ recommendationId: recommendation.id, decision: "ACCEPTED" })
            }
          >
            {accepted ? "Used" : "Use this"}
          </Button>
        </div>

        {detailsOpen && (
          <dl className="mt-3 grid grid-cols-1 gap-x-4 gap-y-1 rounded-md bg-muted/50 p-3 text-xs sm:grid-cols-2">
            {reference.document_type && (
              <div>
                <dt className="text-muted-foreground">Document type</dt>
                <dd className="text-foreground">{reference.document_type}</dd>
              </div>
            )}
            {reference.field_of_study && (
              <div>
                <dt className="text-muted-foreground">Field of study</dt>
                <dd className="text-foreground">{reference.field_of_study}</dd>
              </div>
            )}
            {reference.citation_count !== null && reference.citation_count !== undefined && (
              <div>
                <dt className="text-muted-foreground">Citation count</dt>
                <dd className="text-foreground">{reference.citation_count}</dd>
              </div>
            )}
            {reference.source_link && (
              <div>
                <dt className="text-muted-foreground">Source</dt>
                <dd className="truncate text-foreground">
                  <a href={reference.source_link} target="_blank" rel="noreferrer" className="underline">
                    {reference.source_link}
                  </a>
                </dd>
              </div>
            )}
            {reference.author_keywords && reference.author_keywords.length > 0 && (
              <div className="sm:col-span-2">
                <dt className="text-muted-foreground">Author keywords</dt>
                <dd className="text-foreground">{reference.author_keywords.join(", ")}</dd>
              </div>
            )}
            {reference.index_keywords && reference.index_keywords.length > 0 && (
              <div className="sm:col-span-2">
                <dt className="text-muted-foreground">Index keywords</dt>
                <dd className="text-foreground">{reference.index_keywords.join(", ")}</dd>
              </div>
            )}
            {reference.subject_areas && reference.subject_areas.length > 0 && (
              <div className="sm:col-span-2">
                <dt className="text-muted-foreground">Subject areas</dt>
                <dd className="text-foreground">{reference.subject_areas.join(", ")}</dd>
              </div>
            )}
            {reference.abstract && (
              <div className="sm:col-span-2">
                <dt className="text-muted-foreground">Abstract</dt>
                <dd className="text-foreground">{reference.abstract}</dd>
              </div>
            )}
          </dl>
        )}
      </div>

      <div className="mt-3 border-t pt-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-muted-foreground">Citation style</span>
          <select
            className="rounded-md border border-input bg-background px-2 py-1 text-xs"
            value={style}
            onChange={(e) => {
              setStyle(e.target.value as (typeof STYLES)[number]);
              rewriteParagraph.reset();
            }}
          >
            {STYLES.map((s) => (
              <option key={s} value={s}>
                {s === "APA" ? "APA" : s === "CHICAGO" ? "Chicago" : "IEEE"}
              </option>
            ))}
          </select>
          <Button
            size="sm"
            disabled={rewriteParagraph.isPending}
            onClick={() => rewriteParagraph.mutate({ recommendationId: recommendation.id, style })}
          >
            {rewriteParagraph.isPending ? "Generating…" : "Generate cited paragraph"}
          </Button>
        </div>

        {rewriteParagraph.isError && (
          <p className="mt-2 text-xs text-destructive">
            Could not generate the paragraph: {(rewriteParagraph.error as Error).message}
          </p>
        )}

        {rewriteParagraph.isSuccess && (
          <div className="mt-3 flex flex-col gap-2">
            <div className="rounded-md bg-muted/50 p-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-muted-foreground">
                  Rewritten paragraph
                </span>
                <CopyButton text={rewriteParagraph.data.paragraph} />
              </div>
              <p className="mt-1 text-sm leading-relaxed text-foreground/90">
                {rewriteParagraph.data.paragraph}
              </p>
            </div>
            <div className="rounded-md bg-muted/50 p-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-muted-foreground">
                  Bibliography entry ({rewriteParagraph.data.style})
                </span>
                <CopyButton text={rewriteParagraph.data.bibliography_entry} />
              </div>
              <p className="mt-1 text-sm text-foreground/90">
                {rewriteParagraph.data.bibliography_entry}
              </p>
            </div>
          </div>
        )}
      </div>
    </Card>
  );
}
