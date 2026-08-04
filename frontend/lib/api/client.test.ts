import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, postFormData } from "./client";

/** A real regression: response.json() consumes the body stream even when
 * JSON.parse throws, so a `catch { response.text() }` fallback on the same
 * response always throws "body stream already read" -- this surfaced live
 * whenever the backend (or a reverse proxy in front of it) returned a
 * non-JSON error body, e.g. an HTML error page or plain text. */
describe("error body parsing", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function stubFetch(status: number, body: string, contentType = "text/plain") {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(body, {
            status,
            headers: { "Content-Type": contentType },
          }),
      ),
    );
  }

  it("request() surfaces a non-JSON error body instead of crashing", async () => {
    stubFetch(502, "<html><body>Bad Gateway</body></html>", "text/html");

    await expect(api.get("/api/v1/library/status")).rejects.toMatchObject({
      status: 502,
      body: "<html><body>Bad Gateway</body></html>",
    });
  });

  it("request() still parses a real JSON error body correctly", async () => {
    stubFetch(422, JSON.stringify({ detail: "Dataset is missing required column(s): title" }));

    await expect(api.get("/api/v1/library/status")).rejects.toBeInstanceOf(ApiError);
    try {
      await api.get("/api/v1/library/status");
    } catch (err) {
      expect((err as ApiError).message).toBe(
        "Dataset is missing required column(s): title",
      );
    }
  });

  it("postFormData() surfaces a non-JSON error body instead of crashing", async () => {
    stubFetch(504, "Gateway Timeout");

    const file = new File(["x"], "sample.xlsx");
    await expect(postFormData("/api/v1/library/import", file)).rejects.toMatchObject({
      status: 504,
      body: "Gateway Timeout",
    });
  });
});
