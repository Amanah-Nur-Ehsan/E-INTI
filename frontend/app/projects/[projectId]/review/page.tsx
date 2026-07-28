"use client";

import { use, useEffect, useMemo, useState } from "react";
import {
  useAcceptedCitations,
  useClaims,
  useDraft,
  useDrafts,
  useRecommendationsByDraft,
  useSetDecision,
} from "@/lib/api/hooks";
import { Card, Spinner } from "@/components/ui/primitives";
import { DraftPane } from "@/components/review/DraftPane";
import { RecommendationCard } from "@/components/review/RecommendationCard";
import { HIGHLIGHT_CLASSES, HIGHLIGHT_LEGEND } from "@/lib/review/highlight";
import type { ParsedBlock } from "@/lib/review/segments";

export default function ReviewPage({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = use(params);
  const { data: drafts } = useDrafts(projectId);
  const draftId = drafts?.[0]?.id;

  const { data: draft } = useDraft(draftId ?? "");
  const { data: claims } = useClaims(draftId ?? "", true);
  const { data: recommendationsByClaim } = useRecommendationsByDraft(draftId ?? "");
  const { data: acceptedText } = useAcceptedCitations(draftId ?? "");
  const setDecision = useSetDecision(draftId ?? "");

  const [explicitClaimId, setSelectedClaimId] = useState<string | null>(null);
  // Falls back to the first claim once data loads, without a
  // set-state-in-effect round trip: the default is derived at render time
  // rather than synchronized after the fact.
  const selectedClaimId = explicitClaimId ?? claims?.[0]?.id ?? null;

  const blocks = useMemo<ParsedBlock[]>(() => {
    const raw = draft?.parsed_content?.blocks;
    return Array.isArray(raw) ? (raw as ParsedBlock[]) : [];
  }, [draft]);

  useEffect(() => {
    function handleKey(event: KeyboardEvent) {
      if (!claims || claims.length === 0) return;
      const index = claims.findIndex((c) => c.id === selectedClaimId);
      if (event.key === "j" || event.key === "ArrowDown") {
        const next = claims[Math.min(index + 1, claims.length - 1)];
        if (next) setSelectedClaimId(next.id);
      } else if (event.key === "k" || event.key === "ArrowUp") {
        const prev = claims[Math.max(index - 1, 0)];
        if (prev) setSelectedClaimId(prev.id);
      } else if ((event.key === "a" || event.key === "r") && selectedClaimId) {
        const recs = recommendationsByClaim?.[selectedClaimId];
        const top = recs?.[0];
        if (top) {
          setDecision.mutate({
            recommendationId: top.id,
            decision: event.key === "a" ? "ACCEPTED" : "REJECTED",
          });
        }
      }
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [claims, selectedClaimId, recommendationsByClaim, setDecision]);

  if (!draftId) {
    return (
      <Card className="p-8 text-center text-sm text-zinc-600">
        No draft uploaded yet. Go to Setup to upload one.
      </Card>
    );
  }

  if (!draft || !claims || !recommendationsByClaim) {
    return (
      <div className="flex justify-center py-16 text-zinc-400">
        <Spinner className="h-6 w-6" />
      </div>
    );
  }

  const selectedRecommendations = selectedClaimId
    ? (recommendationsByClaim[selectedClaimId] ?? [])
    : [];
  const selectedClaim = claims.find((c) => c.id === selectedClaimId);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3 text-xs text-zinc-500">
        {HIGHLIGHT_LEGEND.map((item) => (
          <span key={item.state} className="flex items-center gap-1">
            <span className={`inline-block h-3 w-3 rounded-sm ${HIGHLIGHT_CLASSES[item.state] || "bg-zinc-200"}`} />
            {item.label}
          </span>
        ))}
        <span className="ml-auto">j/k to move &middot; a to accept &middot; r to reject</span>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[3fr_2fr]">
        <Card className="max-h-[75vh] overflow-y-auto p-6">
          <DraftPane
            blocks={blocks}
            claims={claims}
            recommendationsByClaim={recommendationsByClaim}
            acceptedTextByClaim={acceptedText ?? {}}
            selectedClaimId={selectedClaimId}
            onSelectClaim={setSelectedClaimId}
          />
        </Card>

        <div className="flex max-h-[75vh] flex-col overflow-y-auto">
          {selectedClaim ? (
            <>
              <Card className="mb-3 p-4">
                <p className="text-xs font-medium text-zinc-500">
                  {selectedClaim.section_title ?? "Untitled section"} &middot;{" "}
                  {selectedClaim.claim_type ?? "General"}
                </p>
                <p className="mt-1 text-sm text-zinc-800">{selectedClaim.sentence_text}</p>
              </Card>

              {selectedRecommendations.length === 0 ? (
                <Card className="p-4 text-sm text-zinc-500">No candidate references found.</Card>
              ) : (
                <div className="flex flex-col gap-3">
                  {selectedRecommendations.map((rec) => (
                    <RecommendationCard
                      key={rec.id}
                      recommendation={rec}
                      isPending={setDecision.isPending}
                      onDecision={(decision) =>
                        setDecision.mutate({ recommendationId: rec.id, decision })
                      }
                    />
                  ))}
                </div>
              )}
            </>
          ) : (
            <Card className="p-4 text-sm text-zinc-500">Select a claim to review it.</Card>
          )}

          <div className="mt-4 rounded-md border border-zinc-200 bg-zinc-50 p-3 text-xs text-zinc-500">
            Recommendation score — a similarity and support estimate, not proof of scientific
            validity.
          </div>
        </div>
      </div>
    </div>
  );
}
