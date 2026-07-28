/**
 * Turns raw_text + the claim list into a flat sequence of renderable
 * segments, without any editor state. The draft is read-only in this MVP
 * -- the user accepts/rejects, they do not edit prose -- so there is no
 * ProseMirror/Lexical document model to keep in sync with claim offsets.
 * A pure function over plain strings is what keeps char_start/char_end
 * meaningful all the way from the parser to the screen.
 */

export type HighlightState = "yellow" | "blue" | "green" | "orange" | "red" | "gray";

export interface ParsedBlock {
  text: string;
  char_start: number;
  char_end: number;
  paragraph_index: number;
  section_title: string | null;
  is_heading: boolean;
}

export interface ClaimLike {
  id: string;
  char_start: number | null;
  char_end: number | null;
  sentence_text: string;
}

/** One paragraph's worth of segments, so the caller can wrap each in its
 * own <p>/<h2> element and headings render distinctly from body text. */
export interface RenderedBlock {
  key: string;
  isHeading: boolean;
  segments: Segment[];
}

export interface Segment {
  key: string;
  text: string;
  claimId?: string;
  ghostText?: string;
}

/**
 * Splits `blocks` into renderable segments, inserting a claim boundary
 * wherever a claim's [char_start, char_end) falls inside a block. Claims
 * outside every block's range, or ones that overlap each other, are
 * skipped defensively rather than corrupting the render -- sentences from
 * the parser are disjoint by construction, so overlap should never
 * actually happen, but a render function must not crash if it does.
 */
export function buildSegments(
  blocks: ParsedBlock[],
  claims: ClaimLike[],
  ghostTextByClaimId: Record<string, string> = {},
): RenderedBlock[] {
  const sorted = [...claims]
    .filter((c) => c.char_start !== null && c.char_end !== null)
    .sort((a, b) => (a.char_start ?? 0) - (b.char_start ?? 0));

  const rendered: RenderedBlock[] = [];
  let lastClaimEnd = -1;

  for (const block of blocks) {
    const segments: Segment[] = [];
    let cursor = block.char_start;

    const blockClaims = sorted.filter(
      (c) => (c.char_start ?? 0) >= block.char_start && (c.char_end ?? 0) <= block.char_end,
    );

    for (const claim of blockClaims) {
      const start = claim.char_start ?? 0;
      const end = claim.char_end ?? 0;
      if (start < lastClaimEnd) continue; // defensive: overlapping claims

      if (start > cursor) {
        segments.push({
          key: `text-${block.paragraph_index}-${cursor}`,
          text: block.text.slice(cursor - block.char_start, start - block.char_start),
        });
      }
      segments.push({
        key: `claim-${claim.id}`,
        text: block.text.slice(start - block.char_start, end - block.char_start),
        claimId: claim.id,
        ghostText: ghostTextByClaimId[claim.id],
      });
      cursor = end;
      lastClaimEnd = end;
    }

    if (cursor < block.char_end) {
      segments.push({
        key: `text-${block.paragraph_index}-${cursor}-end`,
        text: block.text.slice(cursor - block.char_start),
      });
    }

    rendered.push({
      key: `block-${block.paragraph_index}`,
      isHeading: block.is_heading,
      segments,
    });
  }

  return rendered;
}
