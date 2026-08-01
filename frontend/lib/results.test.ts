import { describe, expect, it } from "vitest";
import { splitAroundSentence } from "./results";

describe("splitAroundSentence", () => {
  it("splits when the sentence is in the middle of the context", () => {
    const context = "First sentence. Target sentence. Last sentence.";
    const result = splitAroundSentence(context, "Target sentence.");
    expect(result).toEqual({
      before: "First sentence. ",
      match: "Target sentence.",
      after: " Last sentence.",
    });
  });

  it("splits when the sentence is at the very start of the context", () => {
    const context = "Target sentence. Second sentence.";
    const result = splitAroundSentence(context, "Target sentence.");
    expect(result).toEqual({
      before: "",
      match: "Target sentence.",
      after: " Second sentence.",
    });
  });

  it("splits when the sentence is at the very end of the context", () => {
    const context = "First sentence. Target sentence.";
    const result = splitAroundSentence(context, "Target sentence.");
    expect(result).toEqual({
      before: "First sentence. ",
      match: "Target sentence.",
      after: "",
    });
  });

  it("falls back to the whole context unbolded when the sentence isn't found", () => {
    const context = "First sentence. Second sentence.";
    const result = splitAroundSentence(context, "Not present anywhere.");
    expect(result).toEqual({ before: context, match: "", after: "" });
  });

  it("matches the first occurrence when the sentence repeats in the context", () => {
    const context = "Repeated bit. Repeated bit. Trailing text.";
    const result = splitAroundSentence(context, "Repeated bit.");
    expect(result).toEqual({
      before: "",
      match: "Repeated bit.",
      after: " Repeated bit. Trailing text.",
    });
  });
});
