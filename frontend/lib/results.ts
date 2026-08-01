/**
 * Splits a claim's local_context paragraph around its sentence_text so the
 * page can render the sentence emphasized within its surrounding paragraph.
 *
 * Falls back to returning the whole context as `before` (with empty
 * `match`/`after`) when the sentence can't be found verbatim -- parser
 * whitespace normalization can cause near-misses between local_context and
 * sentence_text even though both come from the same source paragraph.
 */
export function splitAroundSentence(
  context: string,
  sentence: string,
): { before: string; match: string; after: string } {
  if (!sentence) {
    return { before: context, match: "", after: "" };
  }
  const index = context.indexOf(sentence);
  if (index === -1) {
    return { before: context, match: "", after: "" };
  }
  return {
    before: context.slice(0, index),
    match: context.slice(index, index + sentence.length),
    after: context.slice(index + sentence.length),
  };
}
