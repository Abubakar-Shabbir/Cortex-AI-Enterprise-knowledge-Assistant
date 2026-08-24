// Centralized API client - every request goes through here so CSRF
// handling and error shaping live in exactly one place. The Django
// session cookie rides along automatically (same-origin in prod, Vite
// dev-proxy in dev - see vite.config.js), so this never sets an
// Authorization header; the only thing it manages itself is the CSRF
// token, which JS can't read off the cookie (CSRF_COOKIE_HTTPONLY=True,
// see myproject/settings.py) - the backend hands it to us explicitly
// instead (RAG/api/auth_views.py's session/login/logout responses).

let csrfToken = null;

export function setCsrfToken(token) {
  csrfToken = token;
}

export function getCsrfToken() {
  return csrfToken;
}

async function request(path, { method = 'GET', body, isFormData = false } = {}) {
  const headers = {};
  if (!isFormData) headers['Content-Type'] = 'application/json';
  if (csrfToken && method !== 'GET') headers['X-CSRFToken'] = csrfToken;

  const response = await fetch(`/api${path}`, {
    method,
    headers,
    credentials: 'same-origin',
    body: body === undefined ? undefined : isFormData ? body : JSON.stringify(body),
  });

  const contentType = response.headers.get('content-type') || '';
  const data = contentType.includes('application/json') ? await response.json() : null;

  if (!response.ok) {
    const error = new Error((data && (data.error || data.detail)) || `Request failed (${response.status})`);
    error.status = response.status;
    error.data = data;
    throw error;
  }

  return data;
}

export const api = {
  get: (path) => request(path),
  post: (path, body) => request(path, { method: 'POST', body }),
  postForm: (path, formData) => request(path, { method: 'POST', body: formData, isFormData: true }),
  delete: (path) => request(path, { method: 'DELETE' }),
};
