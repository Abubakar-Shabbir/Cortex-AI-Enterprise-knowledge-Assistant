import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, getApiBaseUrl, getCsrfToken, setCsrfToken } from './client';

// ── Dashboard ────────────────────────────────────────────────────────
export function useDashboard() {
  return useQuery({ queryKey: ['dashboard'], queryFn: () => api.get('/dashboard/') });
}

export function useAdminOverview(range = 7) {
  return useQuery({
    queryKey: ['dashboard', 'admin', range],
    queryFn: () => api.get(`/dashboard/admin/?range=${range}`),
  });
}

// ── Documents ────────────────────────────────────────────────────────
// Documents list is keyed by its filter params, so switching filters
// (or navigating away and back with the same filters) reuses cached
// data instead of always refetching - staleTime keeps a just-fetched
// page from refetching again on quick re-navigation, while a
// processing-status poll (below) still invalidates it on its own.
export function useDocuments(params) {
  const search = new URLSearchParams(
    Object.fromEntries(Object.entries(params || {}).filter(([, v]) => v !== '' && v != null)),
  ).toString();
  return useQuery({
    queryKey: ['documents', params],
    queryFn: () => api.get(`/documents/${search ? `?${search}` : ''}`),
    staleTime: 10_000,
    placeholderData: (prev) => prev,
  });
}

export function useDocumentsMeta() {
  return useQuery({ queryKey: ['documents', 'meta'], queryFn: () => api.get('/documents/meta/'), staleTime: 60_000 });
}

export function useUploadDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (formData) => api.postForm('/documents/upload/', formData),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['documents'] }),
  });
}

export function useDeleteDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id) => api.delete(`/documents/${id}/`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['documents'] }),
  });
}

export function useEmbedDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id) => api.post(`/documents/${id}/embed/`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['documents'] }),
  });
}

export function useToggleFavorite() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id) => api.post(`/documents/${id}/favorite/`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['documents'] }),
  });
}

export function useToggleArchive() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id) => api.post(`/documents/${id}/archive/`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['documents'] }),
  });
}

export function useFavoriteDocuments(params) {
  return useQuery({
    queryKey: ['documents', 'favorites', params],
    queryFn: () => api.get(`/documents/favorites/${qs(params)}`),
    placeholderData: (prev) => prev,
  });
}

export function useSharedWithMe(params) {
  return useQuery({
    queryKey: ['documents', 'shared-with-me', params],
    queryFn: () => api.get(`/documents/shared-with-me/${qs(params)}`),
    placeholderData: (prev) => prev,
  });
}

export function useOrgLibrary(params) {
  return useQuery({
    queryKey: ['documents', 'org-library', params],
    queryFn: () => api.get(`/documents/org-library/${qs(params)}`),
    placeholderData: (prev) => prev,
  });
}

export function useCollections() {
  return useQuery({ queryKey: ['collections'], queryFn: () => api.get('/documents/collections/') });
}

export function useCollectionAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload) => api.post('/documents/collections/', payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['collections'] }),
  });
}

export function useCollectionDetail(collectionId, params) {
  return useQuery({
    queryKey: ['collections', collectionId, params],
    queryFn: () => api.get(`/documents/collections/${collectionId}/${qs(params)}`),
    enabled: !!collectionId,
    placeholderData: (prev) => prev,
  });
}

export function useCollectionDetailAction(collectionId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload) => api.post(`/documents/collections/${collectionId}/`, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['collections', collectionId] }),
  });
}

export function useToggleOrgLibrary() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id) => api.post(`/documents/org-library/${id}/toggle/`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['documents', 'org-library'] }),
  });
}

export function useBulkDocumentAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload) => api.post('/documents/bulk/', payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['documents'] }),
  });
}

export async function fetchDocumentShares(docId) {
  return api.get(`/documents/${docId}/share/`);
}

export async function createDocumentShare(docId, payload) {
  return api.post(`/documents/${docId}/share/`, payload);
}

export async function revokeDocumentShare(shareId) {
  return api.post(`/documents/shares/${shareId}/revoke/`);
}

export async function fetchDocumentVersions(docId) {
  return api.get(`/documents/${docId}/versions/`);
}

export function useUploadDocumentVersion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ docId, formData }) => api.postForm(`/documents/${docId}/versions/upload/`, formData),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['documents'] }),
  });
}

export async function fetchDocumentStatus(id) {
  return api.get(`/documents/${id}/status/`);
}

export async function fetchDocumentPreview(id) {
  return api.get(`/documents/${id}/preview/`);
}

// ── Ask AI ───────────────────────────────────────────────────────────
export function useAskContext() {
  return useQuery({ queryKey: ['ask', 'context'], queryFn: () => api.get('/ask/context/') });
}

export function useAskLog(logId) {
  return useQuery({
    queryKey: ['ask', 'log', logId],
    queryFn: () => api.get(`/ask/log/${logId}/`),
    enabled: !!logId,
  });
}

export function useAsk() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload) => api.post('/ask/', payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['ask', 'context'] }),
  });
}

// Streaming isn't a TanStack Query mutation (it needs incremental
// partial state as tokens arrive, not one final value) - a small
// hand-rolled async generator consumer instead, mirroring
// ask_ai.html's streamAnswer() exactly (same SSE framing, same
// AbortController stop/retry semantics), just returning structured
// JSON on 'done' instead of swapping in server-rendered HTML.
export async function streamAsk(payload, { onToken, onDone, onError, signal }) {
  const response = await fetch(`${getApiBaseUrl()}/api/ask/stream/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() || '' },
    credentials: 'include',
    body: JSON.stringify(payload),
    signal,
  });

  if (!response.ok || !response.body) {
    onError(new Error('stream unavailable'));
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let boundary;
    while ((boundary = buffer.indexOf('\n\n')) !== -1) {
      const frame = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      if (!frame.startsWith('data: ')) continue;

      const payloadEvent = JSON.parse(frame.slice(6));
      if (payloadEvent.type === 'token') onToken(payloadEvent.text);
      else if (payloadEvent.type === 'done') onDone(payloadEvent.result);
      else if (payloadEvent.type === 'error') onError(new Error('stream error'));
    }
  }
}

// ── Knowledge Base ───────────────────────────────────────────────────
function qs(params) {
  const search = new URLSearchParams(
    Object.fromEntries(Object.entries(params || {}).filter(([, v]) => v !== '' && v != null)),
  ).toString();
  return search ? `?${search}` : '';
}

export function useKnowledgeBrowse(params) {
  return useQuery({
    queryKey: ['knowledge', 'browse', params],
    queryFn: () => api.get(`/knowledge/browse/${qs(params)}`),
    placeholderData: (prev) => prev,
  });
}

export function useEntityDetail(entityId) {
  return useQuery({
    queryKey: ['knowledge', 'entity', entityId],
    queryFn: () => api.get(`/knowledge/entities/${entityId}/`),
    enabled: !!entityId,
  });
}

export function useRelationships(params) {
  return useQuery({
    queryKey: ['knowledge', 'relationships', params],
    queryFn: () => api.get(`/knowledge/relationships/${qs(params)}`),
    placeholderData: (prev) => prev,
  });
}

export function useKnowledgeGraph() {
  return useQuery({ queryKey: ['knowledge', 'graph'], queryFn: () => api.get('/knowledge/graph/') });
}

export function useGraphNodeDetail(entityId) {
  return useQuery({
    queryKey: ['knowledge', 'graph', 'node', entityId],
    queryFn: () => api.get(`/knowledge/graph/nodes/${entityId}/`),
    enabled: !!entityId,
  });
}

export async function fetchGraphEdgeDetail(a, b) {
  return api.get(`/knowledge/graph/edge/?a=${a}&b=${b}`);
}

export function useCitationExplorer() {
  return useQuery({ queryKey: ['knowledge', 'citations'], queryFn: () => api.get('/knowledge/citations/') });
}

export function useKnowledgeInsights() {
  return useQuery({ queryKey: ['knowledge', 'insights'], queryFn: () => api.get('/knowledge/insights/') });
}

export function useDocumentKnowledge(docId) {
  return useQuery({
    queryKey: ['knowledge', 'document', docId],
    queryFn: () => api.get(`/knowledge/documents/${docId}/`),
    enabled: !!docId,
  });
}

// ── AI Tasks ─────────────────────────────────────────────────────────
export function useAiTasksConfig() {
  return useQuery({ queryKey: ['ai-tasks', 'config'], queryFn: () => api.get('/ai-tasks/config/'), staleTime: Infinity });
}

export function useCreateAiTask() {
  return useMutation({ mutationFn: (payload) => api.post('/ai-tasks/create/', payload) });
}

export function useAiTaskStatus(runId, { enabled = true } = {}) {
  return useQuery({
    queryKey: ['ai-tasks', 'status', runId],
    queryFn: () => api.get(`/ai-tasks/${runId}/status/`),
    enabled: !!runId && enabled,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === 'pending' || status === 'running' ? 2000 : false;
    },
  });
}

export function useCancelAiTask() {
  return useMutation({ mutationFn: (runId) => api.post(`/ai-tasks/${runId}/cancel/`) });
}

export function useDeleteAiTask() {
  return useMutation({ mutationFn: (runId) => api.post(`/ai-tasks/${runId}/delete/`) });
}

export function useAiTaskResults(runId) {
  return useQuery({
    queryKey: ['ai-tasks', 'results', runId],
    queryFn: () => api.get(`/ai-tasks/${runId}/results/`),
    enabled: !!runId,
  });
}

export function useAiTaskHistory(params) {
  return useQuery({
    queryKey: ['ai-tasks', 'history', params],
    queryFn: () => api.get(`/ai-tasks/history/${qs(params)}`),
    placeholderData: (prev) => prev,
  });
}

// ── Analytics ────────────────────────────────────────────────────────
export function useAnalytics() {
  return useQuery({ queryKey: ['analytics'], queryFn: () => api.get('/analytics/') });
}

// ── Reports ──────────────────────────────────────────────────────────
export function useReports() {
  return useQuery({ queryKey: ['reports'], queryFn: () => api.get('/reports/') });
}

// ── Search History ───────────────────────────────────────────────────
export function useSearchHistory(params) {
  return useQuery({
    queryKey: ['search-history', params],
    queryFn: () => api.get(`/history/${qs(params)}`),
    placeholderData: (prev) => prev,
  });
}

// ── Monitoring ───────────────────────────────────────────────────────
export function useMonitoring() {
  return useQuery({
    queryKey: ['monitoring'],
    queryFn: () => api.get('/monitoring/'),
    refetchInterval: 15_000,
  });
}

export async function fetchMonitoringLive() {
  return api.get('/monitoring/?live=1');
}

// ── Admin: Users ─────────────────────────────────────────────────────
export function useAdminUsers() {
  return useQuery({ queryKey: ['admin', 'users'], queryFn: () => api.get('/admin/users/') });
}

export function useAdminUserAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload) => api.post('/admin/users/action/', payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'users'] }),
  });
}

export function useAdminUserProfile(userId) {
  return useQuery({
    queryKey: ['admin', 'users', userId, 'profile'],
    queryFn: () => api.get(`/admin/users/${userId}/profile/`),
    enabled: !!userId,
  });
}

// ── Admin: Roles ─────────────────────────────────────────────────────
export function useAdminRoles() {
  return useQuery({ queryKey: ['admin', 'roles'], queryFn: () => api.get('/admin/roles/') });
}

export function useCreateAdminRole() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload) => api.post('/admin/roles/create/', payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'roles'] }),
  });
}

export function useUpdateRolePermissions() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ roleId, permissions }) => api.post(`/admin/roles/${roleId}/permissions/`, { permissions }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'roles'] }),
  });
}

export function useDeleteAdminRole() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (roleId) => api.post(`/admin/roles/${roleId}/delete/`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'roles'] }),
  });
}

// ── Admin: Queries ───────────────────────────────────────────────────
export function useAdminQueries(params) {
  return useQuery({
    queryKey: ['admin', 'queries', params],
    queryFn: () => api.get(`/admin/queries/${qs(params)}`),
    placeholderData: (prev) => prev,
  });
}

export async function fetchAdminQueryDetail(logId) {
  return api.get(`/admin/queries/${logId}/detail/`);
}

export function useToggleQueryFlag() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (logId) => api.post(`/admin/queries/${logId}/toggle-flag/`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'queries'] }),
  });
}

// ── Admin: System Logs ───────────────────────────────────────────────
export function useAdminSystemLogs(params) {
  return useQuery({
    queryKey: ['admin', 'system-logs', params],
    queryFn: () => api.get(`/admin/system-logs/${qs(params)}`),
    placeholderData: (prev) => prev,
  });
}

export async function fetchAdminTraceDetail(traceId) {
  return api.get(`/admin/system-logs/traces/${traceId}/`);
}

export async function fetchAdminErrorGroupDetail(groupId) {
  return api.get(`/admin/system-logs/errors/${groupId}/`);
}

// ── Admin: Settings ──────────────────────────────────────────────────
export function useAdminSettings() {
  return useQuery({ queryKey: ['admin', 'settings'], queryFn: () => api.get('/admin/settings/') });
}

export function useSaveAdminSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload) => api.post('/admin/settings/', payload),
    onSuccess: (data) => qc.setQueryData(['admin', 'settings'], data),
  });
}

export function useTestLlmProvider() {
  return useMutation({ mutationFn: (provider) => api.post('/admin/settings/health-check/', { provider }) });
}

// ── Notifications ────────────────────────────────────────────────────
export function useNotificationUnreadCount() {
  return useQuery({
    queryKey: ['notifications', 'unread-count'],
    queryFn: () => api.get('/notifications/unread-count/'),
    refetchInterval: 25_000,
    staleTime: 0,
  });
}

export function useNotificationList(limit = 10) {
  return useQuery({
    queryKey: ['notifications', 'list', limit],
    queryFn: () => api.get(`/notifications/list/?limit=${limit}`),
    enabled: false, // lazy-fetched on first dropdown open, matching the classic bell
    staleTime: 0,
  });
}

export function useNotifications(params) {
  const search = new URLSearchParams(
    Object.fromEntries(Object.entries(params || {}).filter(([, v]) => v !== '' && v != null)),
  ).toString();
  return useQuery({
    queryKey: ['notifications', 'center', params],
    queryFn: () => api.get(`/notifications/${search ? `?${search}` : ''}`),
    placeholderData: (prev) => prev,
  });
}

export function useMarkNotificationRead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id) => api.post(`/notifications/${id}/read/`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['notifications'] }),
  });
}

export function useMarkAllNotificationsRead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post('/notifications/mark-all-read/'),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['notifications'] }),
  });
}

// ── Profile ──────────────────────────────────────────────────────────
export function useProfile() {
  return useQuery({ queryKey: ['profile'], queryFn: () => api.get('/profile/') });
}

export function useUpdatePersonal() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload) => api.post('/profile/personal/', payload),
    onSuccess: (data) => qc.setQueryData(['profile'], data),
  });
}

export function useUpdateExtendedProfile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload) => api.post('/profile/extended/', payload),
    onSuccess: (data) => qc.setQueryData(['profile'], data),
  });
}

export function useUploadAvatar() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (file) => {
      const formData = new FormData();
      formData.append('avatar', file);
      return api.postForm('/profile/avatar/', formData);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['profile'] }),
  });
}

export function useUpdateNotificationPreferences() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (emailCategories) => api.post('/profile/notifications/', { email_categories: emailCategories }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['profile'] }),
  });
}

export function useChangePassword() {
  return useMutation({ mutationFn: (payload) => api.post('/profile/password/', payload) });
}

// ── Auth (signup / OTP / password reset) ────────────────────────────
export function useSignup() {
  return useMutation({ mutationFn: (payload) => api.post('/auth/signup/', payload) });
}

export function useVerifyOtpStatus() {
  return useQuery({ queryKey: ['auth', 'verify-otp', 'status'], queryFn: () => api.get('/auth/verify-otp/status/') });
}

export function useVerifyOtp() {
  return useMutation({ mutationFn: (code) => api.post('/auth/verify-otp/', { code }) });
}

export function useResendOtp() {
  return useMutation({ mutationFn: () => api.post('/auth/verify-otp/resend/') });
}

export function usePasswordResetRequest() {
  return useMutation({ mutationFn: (email) => api.post('/auth/password-reset/', { email }) });
}

export function usePasswordResetValidate(uidb64, token) {
  return useQuery({
    queryKey: ['auth', 'password-reset', 'validate', uidb64, token],
    queryFn: () => api.get(`/auth/password-reset/validate/${uidb64}/${token}/`),
    enabled: !!uidb64 && !!token,
    retry: false,
  });
}

export function usePasswordResetConfirm(uidb64, token) {
  return useMutation({
    mutationFn: (payload) => api.post(`/auth/password-reset/confirm/${uidb64}/${token}/`, payload),
  });
}

export { setCsrfToken };
