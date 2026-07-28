"use client";

import { useState } from "react";
import type { RecommendationRead } from "@/lib/api/hooks";

const LABELS: Array<[keyof RecommendationRead["score_breakdown"], string]> = [
  ["semantic_similarity", "Semantic similarity"],
  ["lexical_similarity", "Lexical similarity"],
  ["keyword_overlap", "Keyword overlap"],
  ["field_match", "Field match"],
  ["reranker_score", "Reranker score"],
  ["llm_support_score", "LLM support score"],
];

/** A null component score (e.g. llm_support_score when the verdict was
 * SKIPPED, or reranker_score in a fake-model test run) is rendered as
 * "not available" rather than an empty bar -- an empty bar reads as
 * "scored zero", which misrepresents why the score is missing. */
export function ScoreBreakdownDrawer({
  breakdown,
}: {
  breakdown: RecommendationRead["score_breakdown"];
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className="mt-2">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="text-xs font-medium text-zinc-500 underline"
      >
        {open ? "Hide" : "Show"} score breakdown
      </button>
      {open && (
        <div className="mt-2 flex flex-col gap-1.5">
          {LABELS.map(([key, label]) => {
            const value = breakdown[key];
            return (
              <div key={key} className="flex items-center gap-2 text-xs">
                <span className="w-36 shrink-0 text-zinc-500">{label}</span>
                {value === null ? (
                  <span className="text-zinc-400 italic">not available</span>
                ) : (
                  <>
                    <div className="h-1.5 flex-1 rounded-full bg-zinc-100">
                      <div
                        className="h-1.5 rounded-full bg-zinc-700"
                        style={{ width: `${Math.round(value * 100)}%` }}
                      />
                    </div>
                    <span className="w-10 text-right text-zinc-600">
                      {Math.round(value * 100)}%
                    </span>
                  </>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
