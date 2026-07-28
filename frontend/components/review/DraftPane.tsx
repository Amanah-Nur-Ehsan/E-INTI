"use client";

import { useMemo } from "react";
import { buildSegments, type ClaimLike, type HighlightState, type ParsedBlock } from "@/lib/review/segments";
import { HIGHLIGHT_CLASSES, highlightFor } from "@/lib/review/highlight";
import type { ClaimRead, RecommendationRead } from "@/lib/api/hooks";

export function DraftPane({
  blocks,
  claims,
  recommendationsByClaim,
  acceptedTextByClaim,
  selectedClaimId,
  onSelectClaim,
}: {
  blocks: ParsedBlock[];
  claims: ClaimRead[];
  recommendationsByClaim: Record<string, RecommendationRead[]>;
  acceptedTextByClaim: Record<string, string>;
  selectedClaimId: string | null;
  onSelectClaim: (claimId: string) => void;
}) {
  const claimsById = useMemo(() => new Map(claims.map((c) => [c.id, c])), [claims]);

  const rendered = useMemo(() => {
    const claimLikes: ClaimLike[] = claims.map((c) => ({
      id: c.id,
      char_start: c.char_start,
      char_end: c.char_end,
      sentence_text: c.sentence_text,
    }));
    return buildSegments(blocks, claimLikes, acceptedTextByClaim);
  }, [blocks, claims, acceptedTextByClaim]);

  return (
    <div className="prose prose-sm max-w-none">
      {rendered.map((block) => {
        const Tag = block.isHeading ? "h2" : "p";
        return (
          <Tag
            key={block.key}
            className={block.isHeading ? "text-base font-semibold text-zinc-900" : "leading-relaxed text-zinc-800"}
          >
            {block.segments.map((segment) => {
              if (!segment.claimId) return <span key={segment.key}>{segment.text}</span>;

              const claim = claimsById.get(segment.claimId);
              const recs = recommendationsByClaim[segment.claimId] ?? [];
              const hasAccepted = Boolean(acceptedTextByClaim[segment.claimId]);
              const state: HighlightState = claim
                ? highlightFor(claim, recs, hasAccepted)
                : "gray";

              return (
                <span key={segment.key}>
                  <mark
                    className={`cursor-pointer rounded-sm px-0.5 ${HIGHLIGHT_CLASSES[state]} ${
                      selectedClaimId === segment.claimId ? "ring-2 ring-zinc-900" : ""
                    }`}
                    onClick={() => onSelectClaim(segment.claimId!)}
                  >
                    {segment.text}
                  </mark>
                  {segment.ghostText && (
                    <span className="italic text-zinc-400"> {segment.ghostText}</span>
                  )}
                </span>
              );
            })}
          </Tag>
        );
      })}
    </div>
  );
}
