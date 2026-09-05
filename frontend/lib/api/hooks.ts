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
type BestReferenceRead = components["schemas"]["BestReferenceRead"];
type ParagraphRewriteRead = components["schemas"]["ParagraphRewriteRead"];
type MissingAbstractsByYear = components["schemas"]["MissingAbstractsByYear"];
type AuthSessionStatus = components["schemas"]["AuthSessionStatus"];
type RegisterRequest = components["schemas"]["RegisterRequest"];
type LoginRequest = components["schemas"]["LoginRequest"];
type ActivateRequest = components["schemas"]["ActivateRequest"];
type ForgotPasswordRequest = components["schemas"]["ForgotPasswordRequest"];
type ResetPasswordRequest = components["schemas"]["ResetPasswordRequest"];
type UpdateProfileRequest = components["schemas"]["UpdateProfileRequest"];
type UserAdminRead = components["schemas"]["UserAdminRead"];
type UpdateUserAdminRequest = components["schemas"]["UpdateUserAdminRequest"];
type ResetPasswordAdminRequest = components["schemas"]["ResetPasswordAdminRequest"];
type AdminOverview = components["schemas"]["AdminOverview"];
type AnalysisHistoryItem = components["schemas"]["AnalysisHistoryItem"];

// The stored analysis-result snapshot (result_json). Hand-typed because the
// backend returns it as a raw dict.
export interface AnalysisReference {
  title: string;
  authors: string[] | null;
  year: number | null;
  source: string | null;
  doi: string | null;
  scopus_url: string | null;
  citation_count: number | null;
}

export interface AnalysisRecommendation {
  id: string;
  rank: number;
  score: number;
  label: string | null;
  verdict: string;
  usage: string | null;
  evidence: string | null;
  limitations: string | null;
  decision: string;
  note: string | null;
  reference: AnalysisReference;
}

export interface AnalysisClaimSnapshot {
  id: string;
  sentence: string;
  claim_text: string | null;
  claim_type: string | null;
  needs_citation: boolean;
  section: string | null;
  recommendations: AnalysisRecommendation[];
}

export interface AnalysisSnapshot {
  run: {
    id: string;
    status: string;
    stage: string | null;
    error: string | null;
    started_at: string | null;
    finished_at: string | null;
    created_at: string | null;
  };
  draft: {
    id: string;
    filename: string;
    mime_type: string;
    language_code: string | null;
    raw_text: string | null;
    created_at: string | null;
  };
  sdg: {
    number: number | null;
    name: string | null;
    keyword: string | null;
    rationale: string | null;
    closest_number: number | null;
    closest_name: string | null;
  };
  summary: {
    claims_total: number;
    claims_needing_citation: number;
    recommendations: number;
    accepted: number;
  };
  claims: AnalysisClaimSnapshot[];
  accepted_citations: {
    claim_id: string;
    citation_text: string | null;
    reference: AnalysisReference;
  }[];
}

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

export function useMissingAbstractsByYear(enabled = true) {
  return useQuery({
    queryKey: ["library", "missing-abstracts-by-year"],
    queryFn: () => api.get("/api/v1/library/missing-abstracts-by-year"),
    enabled,
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

export function useAnalysisStatus(draftId: string, enabled = true) {
  return useQuery({
    queryKey: ["drafts", draftId, "analysis-status"],
    queryFn: () =>
      api.get("/api/v1/drafts/{draft_id}/analysis/status", {
        params: { draft_id: draftId },
      }),
    // No analysis run exists until the user clicks "Run analysis" -- polling
    // before that always 404s (expected, not an error), so callers gate this
    // on having actually triggered a run instead of just having a draft id.
    enabled: Boolean(draftId) && enabled,
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

export function useDrafts() {
  return useQuery({
    queryKey: ["drafts"],
    queryFn: () => api.get("/api/v1/drafts") as Promise<DraftRead[]>,
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
      // ReferenceCard reads its accepted/"Used" state from
      // recommendation.user_decision on *this* query (best-reference and
      // best-references, both keyed by this prefix) -- without
      // invalidating it too, a refetch or remount after "Use this" would
      // silently show stale (pre-accept) state.
      queryClient.invalidateQueries({ queryKey: ["drafts", draftId, "best-reference"] });
      queryClient.invalidateQueries({ queryKey: ["drafts", draftId, "best-references"] });
    },
  });
}

export function useBestReference(draftId: string, enabled = true) {
  return useQuery({
    queryKey: ["drafts", draftId, "best-reference"],
    queryFn: () =>
      api.get("/api/v1/drafts/{draft_id}/best-reference", {
        params: { draft_id: draftId },
      }),
    // Same reasoning as useAnalysisStatus: nothing to fetch until analysis
    // has actually produced recommendations, so callers gate this rather
    // than let it 404 the instant a draft exists.
    enabled: Boolean(draftId) && enabled,
    retry: false,
  });
}

export function useBestReferences(draftId: string, enabled = true, limit = 5) {
  return useQuery({
    queryKey: ["drafts", draftId, "best-references", { limit }],
    queryFn: () =>
      api.get("/api/v1/drafts/{draft_id}/best-references", {
        params: { draft_id: draftId },
        query: { limit },
      }),
    // Same reasoning as useBestReference: nothing to fetch until analysis
    // has actually produced recommendations.
    enabled: Boolean(draftId) && enabled,
    retry: false,
  });
}

export function useRewriteParagraph() {
  return useMutation({
    mutationFn: ({ recommendationId, style }: { recommendationId: string; style: string }) =>
      api.post("/api/v1/recommendations/{recommendation_id}/rewrite-paragraph", {
        params: { recommendation_id: recommendationId },
        body: { style },
      }) as Promise<ParagraphRewriteRead>,
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

// -- User auth ------------------------------------------------------------

/** 401 means "not logged in", not a real error -- retry: false so pages
 * can render their login prompt on the first failed check without a
 * loading flicker or a retry backoff delay first. */
export function useSession() {
  return useQuery({
    queryKey: ["auth", "session"],
    queryFn: () => api.get("/api/v1/auth/session") as Promise<AuthSessionStatus>,
    retry: false,
  });
}

export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: LoginRequest) => api.post("/api/v1/auth/login", { body }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["auth", "session"] });
    },
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.post("/api/v1/auth/logout"),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["auth", "session"] });
    },
  });
}

export function useRegister() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: RegisterRequest) => api.post("/api/v1/auth/register", { body }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["auth", "session"] });
    },
  });
}

export function useActivate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: ActivateRequest) => api.post("/api/v1/auth/activate", { body }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["auth", "session"] });
    },
  });
}

export function useForgotPassword() {
  return useMutation({
    mutationFn: (body: ForgotPasswordRequest) =>
      api.post("/api/v1/auth/forgot-password", { body }),
  });
}

export function useResendActivation() {
  return useMutation({
    mutationFn: (body: ForgotPasswordRequest) =>
      api.post("/api/v1/auth/resend-activation", { body }),
  });
}

export function useResetPassword() {
  return useMutation({
    mutationFn: (body: ResetPasswordRequest) => api.post("/api/v1/auth/reset-password", { body }),
  });
}

export function useUpdateProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: UpdateProfileRequest) => api.patch("/api/v1/auth/me", { body }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["auth", "session"] });
    },
  });
}

// -- Admin user management -------------------------------------------------

export function useAdminUsers() {
  return useQuery({
    queryKey: ["admin", "users"],
    queryFn: () => api.get("/api/v1/admin/users") as Promise<UserAdminRead[]>,
  });
}

export function useAdminOverview() {
  return useQuery({
    queryKey: ["admin", "overview"],
    queryFn: () => api.get("/api/v1/admin/overview") as Promise<AdminOverview>,
  });
}

export function useAnalysisHistory() {
  return useQuery({
    queryKey: ["analysis", "history"],
    queryFn: () => api.get("/api/v1/analysis/history") as Promise<AnalysisHistoryItem[]>,
  });
}

export function useAnalysisHistoryDetail(runId: string) {
  return useQuery({
    queryKey: ["analysis", "history", runId],
    queryFn: () =>
      api.get("/api/v1/analysis/history/{run_id}", {
        params: { run_id: runId },
      }) as unknown as Promise<AnalysisSnapshot>,
    enabled: Boolean(runId),
  });
}

export function useUpdateUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ userId, body }: { userId: string; body: UpdateUserAdminRequest }) =>
      api.patch("/api/v1/admin/users/{user_id}", { params: { user_id: userId }, body }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
    },
  });
}

export function useResetUserPassword() {
  return useMutation({
    mutationFn: ({ userId, newPassword }: { userId: string; newPassword: string }) =>
      api.post("/api/v1/admin/users/{user_id}/reset-password", {
        params: { user_id: userId },
        body: { new_password: newPassword } satisfies ResetPasswordAdminRequest,
      }),
  });
}

export function useDeleteUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (userId: string) => api.delete("/api/v1/admin/users/{user_id}", { params: { user_id: userId } }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
    },
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
  BestReferenceRead,
  ParagraphRewriteRead,
  MissingAbstractsByYear,
  AuthSessionStatus,
  RegisterRequest,
  LoginRequest,
  ActivateRequest,
  ForgotPasswordRequest,
  ResetPasswordRequest,
  UpdateProfileRequest,
  UserAdminRead,
  UpdateUserAdminRequest,
  ResetPasswordAdminRequest,
  AdminOverview,
  AnalysisHistoryItem,
};
