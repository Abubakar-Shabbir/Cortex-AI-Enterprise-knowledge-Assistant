import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, getApiBaseUrl, getCsrfToken, setCsrfToken } from './client';

// ── Dashboard ────────────────────────────────────────────────────────
export function useDashboard() {
  return useQuery({ queryKey: ['dashboard'], queryFn: () => api.get('/dashboard/') });
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

export { setCsrfToken };
