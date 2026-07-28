import { describe, expect, it } from "vitest";
import { highlightFor, type ClaimForHighlight, type RecommendationForHighlight } from "./highlight";

function claim(overrides: Partial<ClaimForHighlight> = {}): ClaimForHighlight {
  return {
    needs_citation: true,
    claim_type: "EMPIRICAL_RESULT",
    existing_citation_status: "NO_CITATION_FOUND",
    ...overrides,
  };
}

function rec(overrides: Partial<RecommendationForHighlight> = {}): RecommendationForHighlight {
  return {
    user_decision: "PENDING",
    score_percentage: 80,
    recommendation_label: "Recommended",
    ...overrides,
  };
}

describe("highlightFor", () => {
  it("accepted always wins, regardless of any other state", () => {
    const state = highlightFor(
      claim({ existing_citation_status: "CITATION_EXISTS_AND_CONTRADICTED" }),
      [rec({ score_percentage: 10, recommendation_label: "Do not recommend" })],
      true,
    );
    expect(state).toBe("green");
  });

  it("no citation needed reads gray even with strong recommendations", () => {
    const state = highlightFor(
      claim({ needs_citation: false }),
      [rec({ score_percentage: 95 })],
      false,
    );
    expect(state).toBe("gray");
  });

  it("NO_CITATION_NEEDED claim_type reads gray even if needs_citation is true", () => {
    const state = highlightFor(
      claim({ claim_type: "NO_CITATION_NEEDED" }),
      [rec({ score_percentage: 95 })],
      false,
    );
    expect(state).toBe("gray");
  });

  it("contradicted existing citation reads red, ahead of the recommendation quality", () => {
    const state = highlightFor(
      claim({ existing_citation_status: "CITATION_EXISTS_AND_CONTRADICTED" }),
      [rec({ score_percentage: 95 })],
      false,
    );
    expect(state).toBe("red");
  });

  it("any other existing-citation status reads blue", () => {
    for (const status of [
      "CITATION_EXISTS_NOT_CHECKED",
      "CITATION_EXISTS_AND_SUPPORTED",
      "CITATION_EXISTS_BUT_WEAK",
    ]) {
      const state = highlightFor(
        claim({ existing_citation_status: status }),
        [rec({ score_percentage: 95 })],
        false,
      );
      expect(state).toBe("blue");
    }
  });

  it("no recommendations at all reads orange", () => {
    const state = highlightFor(claim(), [], false);
    expect(state).toBe("orange");
  });

  it("best recommendation below the weak-score threshold reads orange", () => {
    const state = highlightFor(claim(), [rec({ score_percentage: 59 })], false);
    expect(state).toBe("orange");
  });

  it("best recommendation carrying a weak label reads orange even at a high score", () => {
    const state = highlightFor(
      claim(),
      [rec({ score_percentage: 90, recommendation_label: "Cannot verify" })],
      false,
    );
    expect(state).toBe("orange");
  });

  it("a strong, unlabelled-weak recommendation reads yellow", () => {
    const state = highlightFor(
      claim(),
      [rec({ score_percentage: 75, recommendation_label: "Strong recommendation" })],
      false,
    );
    expect(state).toBe("yellow");
  });

  it("rejected and irrelevant recommendations are excluded from the 'best' calculation", () => {
    const state = highlightFor(
      claim(),
      [
        rec({ score_percentage: 95, user_decision: "REJECTED" }),
        rec({ score_percentage: 50, user_decision: "PENDING", recommendation_label: "Weak match" }),
      ],
      false,
    );
    // Best remaining candidate is the 50% one, which is below threshold -> orange.
    expect(state).toBe("orange");
  });

  it("picks the highest-scoring non-rejected recommendation as 'best'", () => {
    const state = highlightFor(
      claim(),
      [
        rec({ score_percentage: 40, recommendation_label: "Weak match" }),
        rec({ score_percentage: 85, recommendation_label: "Strong recommendation" }),
      ],
      false,
    );
    expect(state).toBe("yellow");
  });
});
