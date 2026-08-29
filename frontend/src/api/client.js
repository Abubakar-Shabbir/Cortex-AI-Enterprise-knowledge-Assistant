// Centralized API client — React talks directly to Django.
//
// Architecture (dev and prod):
//   React/Vite  →  Django /api/...  →  DB / services
// Vite never proxies API traffic.
//
// Dev default:  http://localhost:8000  (must match the browser hostname;
//   open the SPA at http://localhost:5173 — not 127.0.0.1 — so SameSite=Lax
//   session cookies are sent on cross-origin fetches to Django).
// Prod: set VITE_API_BASE_URL to the Django origin, or leave unset when the
//   SPA is served from the same Django host (relative /api/... still hits Django).
//
// credentials: "include" sends the HttpOnly session cookie.
// CSRF token is read from GET /api/auth/session/ and sent as X-CSRFToken.

const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL ||
  (import.meta.env.DEV ? "http://localhost:8000" : "")
).replace(/\/$/, "");

let csrfToken = null;

export function setCsrfToken(token) {
  csrfToken = token;
}

export function getCsrfToken() {
  return csrfToken;
}

function buildUrl(path) {
  if (!path.startsWith("/")) {
    path = `/${path}`;
  }
  return `${API_BASE_URL}/api${path}`;
}

async function parseResponse(response) {
  const contentType = response.headers.get("content-type") || "";

  if (contentType.includes("application/json")) {
    try {
      return await response.json();
    } catch {
      return null;
    }
  }

  try {
    return await response.text();
  } catch {
    return null;
  }
}

async function request(
  path,
  {
    method = "GET",
    body = undefined,
    isFormData = false,
  } = {}
) {
  const headers = {};
  const verb = method.toUpperCase();

  if (!isFormData && body !== undefined) {
    headers["Content-Type"] = "application/json";
  }

  if (csrfToken && !["GET", "HEAD", "OPTIONS"].includes(verb)) {
    headers["X-CSRFToken"] = csrfToken;
  }

  const url = buildUrl(path);

  let response;
  try {
    response = await fetch(url, {
      method: verb,
      headers,
      // Required for cross-origin SPA → Django session cookies.
      credentials: "include",
      body:
        body === undefined
          ? undefined
          : isFormData
          ? body
          : JSON.stringify(body),
    });
  } catch (error) {
    const networkError = new Error(
      `Unable to connect to backend API: ${url}`
    );
    networkError.status = 0;
    networkError.originalError = error;
    throw networkError;
  }

  const data = await parseResponse(response);

  if (!response.ok) {
    let message = `Request failed (${response.status})`;

    if (data && typeof data === "object") {
      message = data.error || data.detail || data.message || message;
    } else if (typeof data === "string" && data.trim()) {
      message = data;
    }

    const error = new Error(message);
    error.status = response.status;
    error.data = data;
    error.url = url;
    throw error;
  }

  // Keep CSRF in sync when Django returns a fresh token on any response.
  if (data && typeof data === "object" && data.csrf_token) {
    setCsrfToken(data.csrf_token);
  }

  return data;
}

export function get(path) {
  return request(path, { method: "GET" });
}

export function post(path, body = {}) {
  return request(path, { method: "POST", body });
}

export function put(path, body = {}) {
  return request(path, { method: "PUT", body });
}

export function patch(path, body = {}) {
  return request(path, { method: "PATCH", body });
}

export function del(path) {
  return request(path, { method: "DELETE" });
}

export function postForm(path, formData) {
  return request(path, { method: "POST", body: formData, isFormData: true });
}

export function putForm(path, formData) {
  return request(path, { method: "PUT", body: formData, isFormData: true });
}

export function patchForm(path, formData) {
  return request(path, { method: "PATCH", body: formData, isFormData: true });
}

export const api = {
  get,
  post,
  put,
  patch,
  delete: del,
  postForm,
  putForm,
  patchForm,
};

export function getApiBaseUrl() {
  return API_BASE_URL;
}
