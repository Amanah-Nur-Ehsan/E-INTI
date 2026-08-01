"use client";

import { Badge, Button } from "@/components/ui/primitives";
import type { RecommendationRead } from "@/lib/api/hooks";

const VERDICT_BADGE: Record<string, { label: string; tone: "green" | "yellow" | "red" | "gray" }> = {
  SUPPORTED: { label: "Supported", tone: "green" },
  PARTIALLY_SUPPORTED: { label: "Partially supported", tone: "yellow" },
  TOPICALLY_RELATED_BUT_NOT_EVIDENCE: { label: "Topically related", tone: "yellow" },
  INSUFFICIENT_EVIDENCE: { label: "Insufficient evidence", tone: "gray" },
  CONTRADICTED: { label: "Contradicted", tone: "red" },
  SKIPPED: { label: "Not verified", tone: "gray" },
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
  const badge = VERDICT_BADGE[recommendation.verdict] ?? { label: recommendation.verdict, tone: "gray" as const };
  const accepted = recommendation.user_decision === "ACCEPTED";

  return (
    <div className="rounded-md border border-zinc-200 bg-white p-3">
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm font-medium text-zinc-900">{reference.title}</p>
        <Badge tone={badge.tone}>{badge.label}</Badge>
      </div>
      <p className="mt-0.5 text-xs text-zinc-500">
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
        <Button size="sm" variant={accepted ? "secondary" : "primary"} disabled={isPending || accepted} onClick={onUse}>
          {accepted ? "Used" : "Use this"}
        </Button>
      </div>
    </div>
  );
}
