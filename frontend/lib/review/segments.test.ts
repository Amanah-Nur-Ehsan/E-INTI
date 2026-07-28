import { describe, expect, it } from "vitest";
import { buildSegments, type ClaimLike, type ParsedBlock } from "./segments";

function block(overrides: Partial<ParsedBlock> = {}): ParsedBlock {
  return {
    text: "First sentence here. Second sentence follows.",
    char_start: 0,
    char_end: 47,
    paragraph_index: 0,
    section_title: "Introduction",
    is_heading: false,
    ...overrides,
  };
}

function claim(overrides: Partial<ClaimLike> = {}): ClaimLike {
  return {
    id: "claim-1",
    char_start: 0,
    char_end: 20,
    sentence_text: "First sentence here.",
    ...overrides,
  };
}

describe("buildSegments", () => {
  it("returns one plain segment for a block with no claims", () => {
    const rendered = buildSegments([block()], []);
    expect(rendered).toHaveLength(1);
    expect(rendered[0].segments).toEqual([
      { key: "text-0-0-end", text: "First sentence here. Second sentence follows." },
    ]);
  });

  it("wraps a single claim in its own segment, preserving surrounding text", () => {
    const rendered = buildSegments([block()], [claim()]);
    const texts = rendered[0].segments.map((s) => s.text);
    expect(texts.join("")).toBe(block().text);
    const claimSegment = rendered[0].segments.find((s) => s.claimId === "claim-1");
    expect(claimSegment?.text).toBe("First sentence here.");
  });

  it("handles a claim at the very start of a block (no leading text segment)", () => {
    const rendered = buildSegments([block()], [claim({ char_start: 0, char_end: 20 })]);
    expect(rendered[0].segments[0].claimId).toBe("claim-1");
  });

  it("handles a claim that ends exactly at the block boundary (no trailing segment)", () => {
    const b = block({ char_start: 0, char_end: 20, text: "First sentence here." });
    const rendered = buildSegments([b], [claim({ char_start: 0, char_end: 20 })]);
    expect(rendered[0].segments).toHaveLength(1);
  });

  it("handles two claims in the same block with a gap between them", () => {
    const b = block();
    const claims = [
      claim({ id: "a", char_start: 0, char_end: 20, sentence_text: "First sentence here." }),
      claim({
        id: "b",
        char_start: 21,
        char_end: 47,
        sentence_text: "Second sentence follows.",
      }),
    ];
    const rendered = buildSegments([b], claims);
    const claimIds = rendered[0].segments.filter((s) => s.claimId).map((s) => s.claimId);
    expect(claimIds).toEqual(["a", "b"]);
    // The single space between the two sentences must survive as its own segment.
    const gap = rendered[0].segments.find((s) => !s.claimId);
    expect(gap?.text).toBe(" ");
  });

  it("attaches ghost text only to claims present in the map", () => {
    const rendered = buildSegments([block()], [claim()], { "claim-1": "(Smith, 2024)" });
    const claimSegment = rendered[0].segments.find((s) => s.claimId === "claim-1");
    expect(claimSegment?.ghostText).toBe("(Smith, 2024)");
  });

  it("ignores claims with null offsets rather than crashing", () => {
    const rendered = buildSegments([block()], [claim({ char_start: null, char_end: null })]);
    expect(rendered[0].segments.every((s) => !s.claimId)).toBe(true);
  });

  it("ignores a claim outside every block's range", () => {
    const rendered = buildSegments([block()], [claim({ char_start: 500, char_end: 520 })]);
    expect(rendered[0].segments.every((s) => !s.claimId)).toBe(true);
  });

  it("defensively skips a claim that overlaps an already-placed one", () => {
    const b = block();
    const claims = [
      claim({ id: "a", char_start: 0, char_end: 20 }),
      // Overlaps "a" (start 10 < a's end 20) -- sentences from the parser
      // are disjoint by construction, so this should never happen in
      // practice, but the renderer must not corrupt output if it does.
      claim({ id: "overlap", char_start: 10, char_end: 30 }),
    ];
    const rendered = buildSegments([b], claims);
    const claimIds = rendered[0].segments.filter((s) => s.claimId).map((s) => s.claimId);
    expect(claimIds).toEqual(["a"]);
  });

  it("preserves heading blocks distinctly from body blocks", () => {
    const heading = block({
      paragraph_index: 0,
      char_start: 0,
      char_end: 12,
      text: "Introduction",
      is_heading: true,
    });
    const body = block({
      paragraph_index: 1,
      char_start: 14,
      char_end: 30,
      text: "Body text here.",
      is_heading: false,
    });
    const rendered = buildSegments([heading, body], []);
    expect(rendered[0].isHeading).toBe(true);
    expect(rendered[1].isHeading).toBe(false);
  });

  it("concatenating every segment's text reconstructs each block's text exactly", () => {
    const b = block();
    const claims = [
      claim({ id: "a", char_start: 0, char_end: 20 }),
      claim({ id: "b", char_start: 21, char_end: 47, sentence_text: "Second sentence follows." }),
    ];
    const rendered = buildSegments([b], claims);
    const reconstructed = rendered[0].segments.map((s) => s.text).join("");
    expect(reconstructed).toBe(b.text);
  });
});
