"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import type { RecommendationRead } from "@/lib/api/hooks";

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

export function ReferenceRow({
  recommendation,
  onUse,
  isPending,
}: {
  recommendation: RecommendationRead;
  onUse: () => void;
  isPending: boolean;
}) {
  const { reference } = recommendation;
  const badge = VERDICT_BADGE[recommendation.verdict] ?? {
    label: recommendation.verdict,
    className: "bg-zinc-100 text-zinc-600 border-zinc-200",
  };
  const accepted = recommendation.user_decision === "ACCEPTED";

  return (
    <Card className="p-3">
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm font-medium text-foreground">{reference.title}</p>
        <Badge variant="outline" className={badge.className}>
          {badge.label}
        </Badge>
      </div>
      <p className="mt-0.5 text-xs text-muted-foreground">
        {formatAuthors(reference.authors)} &middot; {reference.year ?? "n.d."}
        {reference.source_title ? ` · ${reference.source_title}` : ""}
        {" · "}
        {recommendation.score_percentage.toFixed(0)}% ({recommendation.recommendation_label})
      </p>
      {recommendation.evidence_paraphrase && (
        <p className="mt-1 text-xs text-zinc-600">{recommendation.evidence_paraphrase}</p>
      )}
      <div className="mt-2 flex items-center gap-3">
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
          variant={accepted ? "secondary" : "default"}
          disabled={isPending || accepted}
          onClick={onUse}
        >
          {accepted ? "Used" : "Use this"}
        </Button>
      </div>
    </Card>
  );
}
