# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

AI-powered document assistant (RAG): users upload documents, the app extracts/chunks/embeds them into PostgreSQL (`pgvector`), builds a per-user knowledge graph, and answers questions via hybrid (vector + BM25 + graph) retrieval passed to an LLM. Two top-level pieces:

- **`Backend/`** — the Django project (`myproject`) and single app (`RAG`, uppercase — imports/migrations reference `RAG`, not `rag`). Has its own detailed **`Backend/CLAUDE.md`** — read it before working on anything under `Backend/`; it covers the full RAG pipeline, every sprint-numbered feature, RBAC, background tasks, observability, etc. This file does not repeat that content.
- **`frontend/`** — a React (Vite) SPA that is **actively replacing** the classic Django server-rendered UI, one page at a time. Currently covers only Login, Dashboard, Documents, and Ask AI (`frontend/src/App.jsx`); every other page (`Backend/CLAUDE.md`'s Views/Knowledge Base/AI Tasks/Admin sections) is still the Django-template version and hasn't been ported yet.

## Commands

**Backend** (from `Backend/`, where `manage.py` lives):
```
python manage.py runserver          # dev server, http://localhost:8000
python manage.py makemigrations RAG # after model changes
python manage.py migrate
python manage.py test RAG
pip install -r requirements.txt
```
See `Backend/CLAUDE.md` for the DB test-suite caveat (needs a reachable Postgres with `pgvector`) and other gotchas.

**Frontend** (from `frontend/`):
```
npm install
npm run dev       # Vite dev server, http://localhost:5173 (not 127.0.0.1 — see below)
npm run build     # outputs frontend/dist/
npm run lint      # oxlint
npm run preview
```
No test runner is configured in `frontend/package.json`.

## How the two halves connect

This is a two-server split during local dev, not a proxy setup — there is no Vite `/api` proxy:

- React (`:5173`) talks **directly** to Django (`:8000`) via `frontend/src/api/client.js`, which prefixes every call with `/api` and sends `credentials: "include"` (session cookie auth, not tokens).
- The API surface React uses lives entirely under `Backend/RAG/api/` (`ask_views.py`, `auth_views.py`, `dashboard_views.py`, `documents_views.py`, mounted at `/api/` in `myproject/urls.py`), deliberately separate from `Backend/RAG/views.py` (the classic template views mounted at `/`). Adding a page to the SPA generally means adding a matching endpoint under `RAG/api/` rather than reusing the template view.
- **Hostname matters**: always browse the SPA at `http://localhost:5173`, never `127.0.0.1` — `SESSION_COOKIE_SAMESITE = "Lax"` means a hostname mismatch between the two origins silently drops the session cookie on cross-origin fetches, and login will appear to work while every subsequent `/api/...` call 403s. `vite.config.js` pins `host: 'localhost'` for this reason.
- CSRF: Django issues the CSRF token via `GET /api/auth/session/`; the client stores it in memory (`setCsrfToken`/`getCsrfToken` in `client.js`) and sends it back as `X-CSRFToken` on mutating requests. `CSRF_TRUSTED_ORIGINS` / CORS in `Backend/myproject/settings.py` must include the Vite origin for this to work.
- In production, Django serves the built SPA itself: `RAG/spa_views.py`'s `spa_view` returns `frontend/dist/index.html` for `/app/` and every client-side sub-route (`myproject/urls.py`'s catch-all `re_path(r'^app/.*$', ...)`) so a hard refresh on a deep route like `/app/documents` resolves correctly instead of 404ing. Without a build present, `DEBUG=True` redirects to the Vite dev server instead of failing outright.
- When extending the SPA to a page that already exists as a Django template, check whether the underlying data/service layer already exists in `Backend/RAG/services/` (see `Backend/CLAUDE.md`'s Architecture section) — the service functions are reused; only a new thin `RAG/api/*_views.py` view plus a new React page/route is usually needed.
