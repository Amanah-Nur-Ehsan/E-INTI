"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type { components } from "./schema";

type ProjectRead = components["schemas"]["ProjectRead"];
type ProjectCreate = components["schemas"]["ProjectCreate"];
type DraftRead = components["schemas"]["DraftRead"];
type ImportResult = components["schemas"]["ImportResult"];
type ReferenceCounts = components["schemas"]["ReferenceCounts"];
type AnalysisRunStatus = components["schemas"]["AnalysisRunStatus"];
type ClaimRead = components["schemas"]["ClaimRead"];
type RecommendationRead = components["schemas"]["RecommendationRead"];
type ProjectSummary = components["schemas"]["ProjectSummary"];
type ExportRead = components["schemas"]["ExportRead"];
type ExportRequest = components["schemas"]["ExportRequest"];

const RUNNING_STATUSES = new Set(["PENDING", "RUNNING"]);

export function useProjects() {
  return useQuery({
    queryKey: ["projects"],
    queryFn: () => api.get("/api/v1/projects"),
  });
}

export function useProject(projectId: string) {
  return useQuery({
    queryKey: ["projects", projectId],
    queryFn: () => api.get("/api/v1/projects/{project_id}", { params: { project_id: projectId } }),
    enabled: Boolean(projectId),
  });
}

export function useCreateProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: ProjectCreate) => api.post("/api/v1/projects", { body }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}

export function useProjectSummary(projectId: string) {
  return useQuery({
    queryKey: ["projects", projectId, "summary"],
    queryFn: () =>
      api.get("/api/v1/projects/{project_id}/summary", { params: { project_id: projectId } }),
    enabled: Boolean(projectId),
    refetchInterval: (query) => {
      const data = query.state.data as ProjectSummary | undefined;
      return data?.latest_run && RUNNING_STATUSES.has(data.latest_run.status) ? 3000 : false;
    },
  });
}

export function useDrafts(projectId: string) {
  return useQuery({
    queryKey: ["projects", projectId, "drafts"],
    queryFn: () =>
      api.get("/api/v1/projects/{project_id}/drafts", { params: { project_id: projectId } }),
    enabled: Boolean(projectId),
  });
}

export function useUploadDraft(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (file: File) => {
      const { postFormData } = await import("./client");
      return postFormData(`/api/v1/projects/{project_id}/drafts/upload`, file, {
        project_id: projectId,
      }) as Promise<DraftRead>;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects", projectId, "drafts"] });
      queryClient.invalidateQueries({ queryKey: ["projects", projectId, "summary"] });
    },
  });
}

export function useReferenceStatus(projectId: string) {
  return useQuery({
    queryKey: ["projects", projectId, "references", "status"],
    queryFn: () =>
      api.get("/api/v1/projects/{project_id}/references/status", {
        params: { project_id: projectId },
      }),
    enabled: Boolean(projectId),
  });
}

export function useImportReferences(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (file: File) => {
      const { postFormData } = await import("./client");
      return postFormData(`/api/v1/projects/{project_id}/references/import`, file, {
        project_id: projectId,
      }) as Promise<ImportResult>;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects", projectId, "references"] });
      queryClient.invalidateQueries({ queryKey: ["projects", projectId, "summary"] });
    },
  });
}

export function useRunAnalysis(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (draftId?: string) =>
      api.post("/api/v1/projects/{project_id}/analysis/run", {
        params: { project_id: projectId },
        body: draftId ? { draft_id: draftId } : {},
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects", projectId, "analysis-status"] });
      queryClient.invalidateQueries({ queryKey: ["projects", projectId, "summary"] });
    },
  });
}

export function useAnalysisStatus(projectId: string) {
  return useQuery({
    queryKey: ["projects", projectId, "analysis-status"],
    queryFn: () =>
      api.get("/api/v1/projects/{project_id}/analysis/status", {
        params: { project_id: projectId },
      }),
    enabled: Boolean(projectId),
    retry: false,
    refetchInterval: (query) => {
      const data = query.state.data as AnalysisRunStatus | undefined;
      return data && RUNNING_STATUSES.has(data.status) ? 3000 : false;
    },
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

export function useDraft(draftId: string) {
  return useQuery({
    queryKey: ["drafts", draftId],
    queryFn: () => api.get("/api/v1/drafts/{draft_id}", { params: { draft_id: draftId } }),
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
    // Optimistic update: flip the recommendation's user_decision in the
    // cached batch immediately, so the highlight/ghost text reacts without
    // waiting on the round trip.
    onMutate: async ({ recommendationId, decision }) => {
      const queryKey = ["drafts", draftId, "recommendations"];
      await queryClient.cancelQueries({ queryKey });
      const previous = queryClient.getQueryData<Record<string, RecommendationRead[]>>(queryKey);

      if (previous) {
        const next: Record<string, RecommendationRead[]> = {};
        for (const [claimId, recs] of Object.entries(previous)) {
          next[claimId] = recs.map((rec) =>
            rec.id === recommendationId ? { ...rec, user_decision: decision } : rec,
          );
        }
        queryClient.setQueryData(queryKey, next);
      }
      return { previous };
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) {
        queryClient.setQueryData(["drafts", draftId, "recommendations"], context.previous);
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["drafts", draftId, "recommendations"] });
      queryClient.invalidateQueries({ queryKey: ["drafts", draftId, "accepted-citations"] });
      queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}

export function useCreateExport(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: ExportRequest) =>
      api.post("/api/v1/projects/{project_id}/exports", { params: { project_id: projectId }, body }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects", projectId, "exports"] });
    },
  });
}

export function useExports(projectId: string) {
  return useQuery({
    queryKey: ["projects", projectId, "exports"],
    queryFn: () =>
      api.get("/api/v1/projects/{project_id}/exports", { params: { project_id: projectId } }),
    enabled: Boolean(projectId),
  });
}

export type {
  ProjectRead,
  DraftRead,
  ImportResult,
  ReferenceCounts,
  AnalysisRunStatus,
  ClaimRead,
  RecommendationRead,
  ProjectSummary,
  ExportRead,
  ExportRequest,
};
