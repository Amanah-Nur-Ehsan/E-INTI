"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type { components } from "./schema";

type DraftRead = components["schemas"]["DraftRead"];
type DraftDetail = components["schemas"]["DraftDetail"];
type ImportResult = components["schemas"]["ImportResult"];
type ReferenceCounts = components["schemas"]["ReferenceCounts"];
type AnalysisRunStatus = components["schemas"]["AnalysisRunStatus"];
type AnalysisRunAccepted = components["schemas"]["AnalysisRunAccepted"];
type ClaimRead = components["schemas"]["ClaimRead"];
type RecommendationRead = components["schemas"]["RecommendationRead"];
type ExportRead = components["schemas"]["ExportRead"];
type ExportRequest = components["schemas"]["ExportRequest"];

const RUNNING_STATUSES = new Set(["PENDING", "RUNNING"]);

export function useLibraryStatus() {
  return useQuery({
    queryKey: ["library", "status"],
    queryFn: () => api.get("/api/v1/library/status"),
    refetchInterval: (query) => {
      const data = query.state.data as ReferenceCounts | undefined;
      return data && data.pending > 0 ? 3000 : false;
    },
  });
}

export function useImportLibrary() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (file: File) => {
      const { postFormData } = await import("./client");
      return postFormData("/api/v1/library/import", file) as Promise<ImportResult>;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["library", "status"] });
    },
  });
}

export function useRefreshLibrary() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.post("/api/v1/library/refresh"),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["library", "status"] });
    },
  });
}

export function useUploadDraft() {
  return useMutation({
    mutationFn: async (file: File) => {
      const { postFormData } = await import("./client");
      return postFormData("/api/v1/drafts/upload", file) as Promise<DraftRead>;
    },
  });
}

export function useRunAnalysis(draftId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      api.post("/api/v1/drafts/{draft_id}/analysis/run", {
        params: { draft_id: draftId },
      }) as Promise<AnalysisRunAccepted>,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["drafts", draftId, "analysis-status"] });
    },
  });
}

export function useAnalysisStatus(draftId: string) {
  return useQuery({
    queryKey: ["drafts", draftId, "analysis-status"],
    queryFn: () =>
      api.get("/api/v1/drafts/{draft_id}/analysis/status", {
        params: { draft_id: draftId },
      }),
    enabled: Boolean(draftId),
    retry: false,
    refetchInterval: (query) => {
      const data = query.state.data as AnalysisRunStatus | undefined;
      return data && RUNNING_STATUSES.has(data.status) ? 3000 : false;
    },
  });
}

export function useDraft(draftId: string) {
  return useQuery({
    queryKey: ["drafts", draftId],
    queryFn: () => api.get("/api/v1/drafts/{draft_id}", { params: { draft_id: draftId } }),
    enabled: Boolean(draftId),
  });
}

export function useClaims(draftId: string, needsCitation?: boolean) {
  return useQuery({
    queryKey: ["drafts", draftId, "claims", { needsCitation }],
    queryFn: () =>
      api.get("/api/v1/drafts/{draft_id}/claims", {
        params: { draft_id: draftId },
        query: needsCitation === undefined ? undefined : { needs_citation: needsCitation },
      }),
    enabled: Boolean(draftId),
  });
}

export function useRecommendationsByDraft(draftId: string) {
  return useQuery({
    queryKey: ["drafts", draftId, "recommendations"],
    queryFn: () =>
      api.get("/api/v1/drafts/{draft_id}/recommendations", { params: { draft_id: draftId } }),
    enabled: Boolean(draftId),
  });
}

export function useAcceptedCitations(draftId: string) {
  return useQuery({
    queryKey: ["drafts", draftId, "accepted-citations"],
    queryFn: () =>
      api.get("/api/v1/drafts/{draft_id}/accepted-citations", { params: { draft_id: draftId } }),
    enabled: Boolean(draftId),
  });
}

export function useSetDecision(draftId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      recommendationId,
      decision,
      note,
    }: {
      recommendationId: string;
      decision: "ACCEPTED" | "REJECTED" | "IRRELEVANT";
      note?: string;
    }) =>
      api.post("/api/v1/recommendations/{recommendation_id}/decision", {
        params: { recommendation_id: recommendationId },
        body: { decision, note },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["drafts", draftId, "recommendations"] });
      queryClient.invalidateQueries({ queryKey: ["drafts", draftId, "accepted-citations"] });
    },
  });
}

export function useCreateExport(draftId: string) {
  return useMutation({
    mutationFn: (body: ExportRequest) =>
      api.post("/api/v1/drafts/{draft_id}/exports", {
        params: { draft_id: draftId },
        body,
      }) as Promise<ExportRead>,
  });
}

export type {
  DraftRead,
  DraftDetail,
  ImportResult,
  ReferenceCounts,
  AnalysisRunStatus,
  AnalysisRunAccepted,
  ClaimRead,
  RecommendationRead,
  ExportRead,
  ExportRequest,
};
