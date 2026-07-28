"use client";

import { useState } from "react";
import type { RecommendationRead } from "@/lib/api/hooks";
import { Badge, Button } from "@/components/ui/primitives";
import { ScoreBreakdownDrawer } from "./ScoreBreakdownDrawer";

const VERDICT_TONE: Record<string, "green" | "yellow" | "orange" | "red" | "neutral"> = {
  SUPPORTED: "green",
  PARTIALLY_SUPPORTED: "yellow",
  TOPICALLY_RELATED_BUT_NOT_EVIDENCE: "orange",
  INSUFFICIENT_EVIDENCE: "neutral",
  CONTRADICTED: "red",
  SKIPPED: "neutral",
};

function formatAuthors(authors: unknown[] | null): string {
  if (!authors || authors.length === 0) return "Unknown authors";
  const names = authors
    .map((a) => (typeof a === "object" && a !== null && "name" in a ? String((a as { name: unknown }).name) : null))
    .filter((n): n is string => Boolean(n));
  if (names.length <= 3) return names.join(", ");
  return `${names.slice(0, 3).join(", ")}, et al.`;
}

export function RecommendationCard({
  recommendation,
  onDecision,
  isPending,
}: {
  recommendation: RecommendationRead;
  onDecision: (decision: "ACCEPTED" | "REJECTED" | "IRRELEVANT") => void;
  isPending: boolean;
}) {
  const [showAbstract, setShowAbstract] = useState(false);
  const { reference } = recommendation;
  const decided = recommendation.user_decision !== "PENDING";

  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="text-lg font-semibold text-zinc-900">
            {recommendation.score_percentage.toFixed(1)}%
          </span>
          <span className="text-xs font-medium text-zinc-500">
            {recommendation.recommendation_label}
          </span>
        </div>
        <Badge tone={VERDICT_TONE[recommendation.verdict] ?? "neutral"}>
          {recommendation.verdict.replaceAll("_", " ")}
        </Badge>
      </div>

      <p className="mt-2 text-sm font-medium text-zinc-900">{reference.title}</p>
      <p className="mt-0.5 text-xs text-zinc-500">
        {formatAuthors(reference.authors)} &middot; {reference.year ?? "n.d."}
        {reference.source_title ? ` · ${reference.source_title}` : ""}
      </p>

      <div className="mt-1 flex gap-3 text-xs">
        {reference.doi && (
          <a
            href={`https://doi.org/${reference.doi}`}
            target="_blank"
            rel="noreferrer"
            className="text-sky-700 underline"
          >
            DOI
          </a>
        )}
        {reference.scopus_url && (
          <a
            href={reference.scopus_url}
            target="_blank"
            rel="noreferrer"
            className="text-sky-700 underline"
          >
            Open source ↗
          </a>
        )}
        {reference.abstract && (
          <button
            type="button"
            className="text-zinc-500 underline"
            onClick={() => setShowAbstract((v) => !v)}
          >
            {showAbstract ? "Hide abstract" : "View abstract"}
          </button>
        )}
      </div>

      {showAbstract && reference.abstract && (
        <p className="mt-2 rounded bg-zinc-50 p-2 text-xs text-zinc-600">{reference.abstract}</p>
      )}

      {recommendation.recommended_usage && (
        <p className="mt-2 text-xs text-zinc-600">
          <span className="font-medium">Suggested usage:</span> {recommendation.recommended_usage}
        </p>
      )}
      {recommendation.evidence_paraphrase && (
        <p className="mt-1 text-xs text-zinc-600">
          <span className="font-medium">Evidence:</span> {recommendation.evidence_paraphrase}
        </p>
      )}
      {recommendation.limitations && (
        <p className="mt-1 text-xs text-zinc-500">
          <span className="font-medium">Limitations:</span> {recommendation.limitations}
        </p>
      )}

      <ScoreBreakdownDrawer breakdown={recommendation.score_breakdown} />

      <div className="mt-3 flex flex-wrap gap-2">
        <Button
          size="sm"
          disabled={isPending || recommendation.user_decision === "ACCEPTED"}
          onClick={() => onDecision("ACCEPTED")}
        >
          {recommendation.user_decision === "ACCEPTED" ? "Accepted" : "Accept"}
        </Button>
        <Button
          size="sm"
          variant="secondary"
          disabled={isPending || recommendation.user_decision === "REJECTED"}
          onClick={() => onDecision("REJECTED")}
        >
          Reject
        </Button>
        <Button
          size="sm"
          variant="ghost"
          disabled={isPending || recommendation.user_decision === "IRRELEVANT"}
          onClick={() => onDecision("IRRELEVANT")}
        >
          Mark irrelevant
        </Button>
        {decided && (
          <span className="ml-auto self-center text-xs text-zinc-400">
            {recommendation.user_decision}
          </span>
        )}
      </div>
    </div>
  );
}
