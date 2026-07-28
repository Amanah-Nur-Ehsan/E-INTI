/**
 * Maps a claim + its recommendations + acceptance state to one of the
 * spec's six highlight colours. The `if` order below *is* the
 * specification -- each state is checked only after ruling out every
 * state that should take priority over it.
 *
 * Label strings mirror app/services/scoring.py's LABEL_* constants
 * (backend test asserts that set is unchanged, so the two cannot drift
 * silently); duplicated here rather than fetched at runtime because they
 * are load-bearing UI logic, not display copy.
 */
import type { HighlightState } from "./segments";

const WEAK_LABELS = new Set([
  "Weak match",
  "Possible reference",
  "Cannot verify",
  "Do not recommend",
]);

const WEAK_SCORE_THRESHOLD = 60;

export interface ClaimForHighlight {
  needs_citation: boolean;
  claim_type: string | null;
  existing_citation_status: string;
}

export interface RecommendationForHighlight {
  user_decision: string;
  score_percentage: number;
  recommendation_label: string | null;
}

export function highlightFor(
  claim: ClaimForHighlight,
  recommendations: RecommendationForHighlight[],
  hasAccepted: boolean,
): HighlightState {
  if (hasAccepted) return "green";

  if (!claim.needs_citation || claim.claim_type === "NO_CITATION_NEEDED") {
    return "gray";
  }

  if (claim.existing_citation_status === "CITATION_EXISTS_AND_CONTRADICTED") {
    return "red";
  }

  if (claim.existing_citation_status !== "NO_CITATION_FOUND") {
    return "blue";
  }

  const best = [...recommendations]
    .filter((r) => r.user_decision !== "REJECTED" && r.user_decision !== "IRRELEVANT")
    .sort((a, b) => b.score_percentage - a.score_percentage)[0];

  if (!best || best.score_percentage < WEAK_SCORE_THRESHOLD || WEAK_LABELS.has(best.recommendation_label ?? "")) {
    return "orange";
  }

  return "yellow";
}

export const HIGHLIGHT_CLASSES: Record<HighlightState, string> = {
  yellow: "bg-amber-100 border-b-2 border-amber-400",
  blue: "bg-sky-100 border-b-2 border-sky-400",
  green: "bg-emerald-100 border-b-2 border-emerald-400",
  orange: "bg-orange-100 border-b-2 border-orange-400",
  red: "bg-red-100 border-b-2 border-red-400",
  gray: "",
};

export const HIGHLIGHT_LEGEND: Array<{ state: HighlightState; label: string }> = [
  { state: "yellow", label: "Claim detected, no citation yet" },
  { state: "blue", label: "Existing citation, review recommended" },
  { state: "green", label: "Suggestion accepted" },
  { state: "orange", label: "Only weak/partial suggestions" },
  { state: "red", label: "Existing citation appears unsupported" },
  { state: "gray", label: "No citation needed" },
];
