# Deploying Cortex at $0/month

This guide deploys the **entire existing application** — the same Django project you run locally with `manage.py runserver`, unmodified in behavior — to genuinely free infrastructure. No feature is removed, downgraded, or mocked to make this work; where a free tier has a real limitation, it's called out explicitly below along with how the app already handles it (or what you trade off).

## Architecture

```
                         User's browser
                               |
                               v
                    +----------------------+
                    |   Render (free)      |   Django + Gunicorn + WhiteNoise
                    |   web service          |   serves HTML, static files, and
                    |                       |   the /media/ URL directly - one
                    +----------------------+   process, no separate frontend
                         |            |
                         v            v
              +----------------+  +------------------------+
              | Supabase (free)|  | Supabase Storage (free) |
              | Postgres +     |  | S3-compatible - document|
              | pgvector       |  | uploads & avatars       |
              +----------------+  +------------------------+
                               |
                               v
                    +----------------------+
                    | OpenRouter / Groq /  |   free-tier LLM APIs
                    | Gemini (free tier)   |   (already provider-agnostic
                    +----------------------+    in this codebase)
```

**There is no separate frontend deployment (no Vercel).** This app is a server-rendered Django monolith — Tailwind/Alpine.js/Lucide load from CDN `<script>` tags directly in the HTML Django returns, there is no React/Vue build step and no JSON API for pages to call. Render's one free web service *is* both "frontend" (the HTML/CSS/JS the browser gets) and "backend" (the Django views/DB access) — there's nothing else to host on Vercel for this specific app. If a genuinely separate frontend is ever built later, Vercel remains a fine choice for it at that point; forcing a split today would mean rewriting working code for no functional benefit.

**There is no Redis or Celery**, and none is needed. An earlier pass on this codebase already replaced them with an in-process `concurrent.futures.ThreadPoolExecutor` (`RAG/services/task_runner.py`) specifically because most free-tier hosts (Render free included) only run one process and can't host a second always-on worker. AI Task progress/results/logs are written to the database as they run (`AITaskRun`), not held in memory, so status polling works correctly regardless of which request hits the app. See "Background jobs" below for the one thing worth tuning.

---

## 1. Supabase — database + pgvector + file storage

1. Create a free account at [supabase.com](https://supabase.com) (no credit card required) and a new project.
2. **Enable pgvector**: Database → Extensions → search "vector" → enable it. (Migrations assume this is already on — nothing in this repo runs `CREATE EXTENSION vector` for you.)
3. **Get your Postgres connection values**: Project Settings → Database → Connection info. Use the **direct connection** (port `5432`), not the pooler — this app keeps one Gunicorn worker on Render free (see below), so it never opens enough concurrent connections to need PgBouncer/Supavisor, and the direct connection is simpler for Django's `CONN_MAX_AGE` persistent-connection behavior. Set in Render's env vars:
   - `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`
   - `DB_SSLMODE=require` (Supabase's public endpoint requires SSL; local dev via docker-compose leaves this at `prefer` since that Postgres has no SSL configured)
4. **Create a Storage bucket for uploads**: Storage → New bucket → name it (e.g. `cortex-media`) → make it **Public** (documents/avatars are served back by URL; there's no signed-URL flow in this codebase, so a private bucket would 403 on every view/download). If you'd rather keep it private, that's a real code change (signed URLs), not just a config flag — out of scope for this pass.
5. **Get S3-compatible credentials for that bucket**: Project Settings → Storage → S3 Connection. Generate an Access Key ID + Secret Access Key there, and copy the **Endpoint** and **Region** shown on that same page. Set in Render's env vars:
   - `USE_S3_STORAGE=True`
   - `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` (the keys you just generated)
   - `AWS_STORAGE_BUCKET_NAME` (the bucket name from step 4)
   - `AWS_S3_ENDPOINT_URL` (from the S3 Connection page, looks like `https://<project-ref>.supabase.co/storage/v1/s3`)
   - `AWS_S3_REGION_NAME` (from the same page)

This is what actually solves the "Render's free web service has no persistent disk" problem (confirmed: free instances cannot attach a disk, and local filesystem changes are lost on every restart/redeploy/spin-down) — `Document.file`, `DocumentVersion.file`, and `UserProfile.avatar` are plain Django `FileField`/`ImageField`s, so this is a **pure settings.py change** (`STORAGES["default"]`, see that file's own comment) with zero changes to any view, service, or model. Uploads survive restarts and redeploys.

**Free-tier limits to know**: 500 MB database, 1 GB file storage, 5 GB egress/month, and — the one that actually matters operationally — **a free project pauses automatically after 7 days with no API activity**. If nobody uses the app for a week, the next visitor's request will fail to reach the database until you manually resume the project from the Supabase dashboard (Project → "Restore"/"Resume", ~60s cold start). This is a genuine free-tier limitation with no code-level workaround; if the app needs to stay reachable with no manual babysitting, that specifically is what a paid Supabase plan removes.

**Keeping this replaceable**: nothing about the DB config is Supabase-specific — it's the same `DB_*` env vars this app has always used, pointed at Postgres-with-pgvector wherever that runs. Moving to Neon, RDS, or a paid Supabase plan later is a connection-string change, not a code change. Storage is the same story: swap `AWS_S3_ENDPOINT_URL`/keys for real AWS S3, Cloudflare R2, or Backblaze B2 later with no code change — `django-storages`' `S3Storage` backend is provider-agnostic by design.

---

## 2. A free LLM provider

Already fully configured in this codebase (`RAG/services/llm_client.py`) — provider-agnostic, env-driven, nothing hardcoded. Pick **one** to start (all free-tier-capable):

| Provider | Env var | Notes |
|---|---|---|
| OpenRouter (default primary) | `OPENROUTER_API_KEY` | `OPENROUTER_MODEL` defaults to a free model; check Admin → Settings if it's ever retired |
| Groq | `GROQ_API_KEY` | Fast free-tier inference; good fallback |
| Gemini | `GEMINI_API_KEY` | Also has a free tier |

Set `LLM_PROVIDER` to whichever is primary. `LLM_FALLBACK_ENABLED=True` lets the app fall through to the others (in priority order) if the primary fails — set keys for more than one provider if you want that resilience; leave it `False` for strict "this provider or a clear error." Both behaviors are also editable at runtime from Admin → Settings without a redeploy.

---

## 3. Free SMTP (OTP/password-reset/notification emails)

`EMAIL_BACKEND` already branches on whether `EMAIL_HOST` is set (`myproject/settings.py`) — leave it blank and email prints to Render's log instead of sending, which is enough to smoke-test the OTP flow but not to actually run the app. For real delivery, **Brevo's free plan** is the most generous genuinely-free option verified for this guide: 300 emails/day, no credit card. (Gmail SMTP via an app password also works and needs no signup, but caps around 500/day on a personal account and is easier to get flagged as spammy at any real volume.)

Brevo setup: create a free account → SMTP & API → generate SMTP credentials. Set:
```
EMAIL_HOST=smtp-relay.brevo.com
EMAIL_PORT=587
EMAIL_HOST_USER=<your Brevo SMTP login>
EMAIL_HOST_PASSWORD=<your Brevo SMTP key>
EMAIL_USE_TLS=True
DEFAULT_FROM_EMAIL=Cortex <no-reply@yourdomain-or-brevo-sender.com>
```

---

## 4. Render — the app itself

### Option A: Blueprint (`render.yaml`, infra-as-code)

This repo includes `render.yaml` with `plan: free` explicit on its one service. In the Render dashboard: **New → Blueprint** → point at this repo → Render reads `render.yaml` and creates the service, prompting you for every env var marked `sync: false` (the secrets — API keys, DB credentials, etc.). Fill those in from steps 1–3 above.

### Option B: Manual (New → Web Service)

1. **New → Web Service** → connect this repo. Render's sign-up flow has not consistently required a credit card in recent reports, but confirm at signup and make sure you explicitly select the **Free** instance type before creating the service.
2. Runtime: Python 3. Region: whichever is closest to you (affects Supabase latency too — ideally the same region as your Supabase project).
3. **Build command**: `bash build.sh` (installs dependencies, runs `collectstatic`, runs migrations, seeds RBAC roles/permissions — see that file, every step is safe to re-run on every deploy).
4. **Start command**:
   ```
   gunicorn myproject.wsgi:application --workers 1 --threads 2 --timeout 120 --bind 0.0.0.0:$PORT
   ```
   `--workers 1`: Render free gives **512 MB RAM / 0.1 CPU** — a second worker process would roughly double the app's baseline memory (Python + Django + the embedding model loaded at import time) for no benefit on a 0.1-CPU instance, and would also split the in-process background thread pool and its in-memory cancel-tracking across two unsynchronized processes. `--threads 2` gives a bit of real concurrency within that one process. `--timeout 120`: embedding a large document or a slow LLM provider response can take well past Gunicorn's 30s default, which would otherwise kill the worker mid-request.
5. **Health check path**: `/health/` (already implemented, public, no login required — see "Monitoring" below).
6. Add every env var from `.env.example` (fill in real values for the blanks; the file documents what each one does and where it comes from). At minimum: `SECRET_KEY` (generate one — see the comment in `.env.example`), `DEBUG=False`, `ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS` (your `*.onrender.com` URL, with `https://` scheme for the CSRF one), the `DB_*` vars, the storage vars, at least one LLM provider key, and the email vars if you want real delivery.

### CORS / CSRF / "API URL" — why these are simpler here than the target architecture implies

Because there's one origin (Render serves both the pages and everything they call), **CORS doesn't apply at all** — no `django-cors-headers` is needed or installed, since the browser never makes a cross-origin request. CSRF is exactly the existing Django session-cookie CSRF this app already has (`{% csrf_token %}` in every form, already env-driven `CSRF_TRUSTED_ORIGINS`) — just add your real Render URL to it. There's no "API base URL" to configure client-side, because the browser is never told to call anywhere except the page it's already on.

### Free-tier resource limits — what's genuinely constrained, and how this app already handles it

- **Cold starts**: a free web service spins down after 15 minutes with no traffic and takes up to ~60s to wake on the next request (confirmed current Render behavior). The first visitor after idle time waits; this is inherent to the free tier, not something app code can avoid. If you want the service to stay warm, a free uptime pinger (e.g. a free-tier cron/monitoring service hitting `/health/` every ~10 minutes) keeps it awake — but note Render's free plan grants 750 instance-hours/workspace/month, and keeping one service awake 24/7 uses ~720–744 of those, leaving little headroom for a second always-on free service in the same workspace. Letting it sleep when unused is the more free-tier-friendly default; only force-keep-alive if you specifically need to avoid the wake-up delay.
- **512 MB RAM / 0.1 CPU**: the embedding model (`all-MiniLM-L6-v2`, the default `EMBEDDING_MODEL`) loads once at process start and is small enough to fit comfortably. **The reranker (`ENABLE_RERANKER`) is a much larger cross-encoder model and defaults off for exactly this reason** — enabling it on a 512 MB instance risks an out-of-memory restart. Leave it off unless you've upgraded past the free tier, or point `RERANKER_MODEL` at a genuinely small cross-encoder and watch Render's memory graph closely after enabling it. Query expansion/HyDE/multi-query don't cost local RAM (they're extra LLM API calls, not local models) and are safe to enable resource-wise — they just add latency/provider-quota cost, which is why they also default off.
- **Background jobs**: `BACKGROUND_WORKER_THREADS` is set to `1` in `.env.example`'s production guidance for the same 0.1-CPU reason — more threads context-switch against each other rather than doing more real work on a fractional core, and each one that's actively running an embedding/LLM call holds real RAM. `ENABLE_ASYNC_PROCESSING=True` in production so a large document's processing happens on that background thread instead of blocking the request (and risking a platform-level request timeout) — the Documents page already shows "Processing" for a document with `chunk_count == 0`, so this needed no UI change.
- **AI Tasks always run in the background** regardless of `ENABLE_ASYNC_PROCESSING` (unchanged from local dev) — they start, write progress to `AITaskRun` as they go, and the AI Tasks UI polls that DB row, so this works identically on Render.

---

## 5. Static files

`STATIC_ROOT` + WhiteNoise (`whitenoise.middleware.WhiteNoiseMiddleware`, added right after `SecurityMiddleware`) serve CSS/JS/images directly from the Gunicorn process with far-future cache headers and gzip/brotli compression — no separate CDN or static hosting service, genuinely free, and it's what `build.sh`'s `collectstatic` step populates. Nothing here is Django-app-specific to touch; Tailwind/Alpine/Lucide themselves still load from their own CDNs exactly as before (unrelated to `STATIC_ROOT`, which only covers this app's own `static/` files).

---

## 6. Monitoring — no paid service needed

- **`GET /health/`** — already implemented (`RAG.views.health_check`), public, returns `200`/`{"status": "ok", ...}` or `503`/`{"status": "degraded", ...}`. This is what Render's own health check (step 4.4) polls, and it's also a valid target for any free external uptime monitor if you want one.
- **Admin → System Health** (in-app, for a logged-in Admin) — the same checks, human-readable: Postgres, pgvector, the background thread pool (replacing the old Redis/Celery-worker check with "is the pool available", which — unlike a separate worker process — is trivially true whenever this process is up), every configured LLM provider (a live reachability check via the same call the "Check Now" button uses), and storage (now reports "Remote (S3)" instead of a local disk-usage figure once `USE_S3_STORAGE=True`, since the free-tier host's own ephemeral disk no longer has anything to do with where documents live — see `health_service._check_storage()`'s own comment).
- **Logs**: Django already has an explicit `LOGGING` config (console handler, structured `%(asctime)s %(levelname)s [%(trace_id)s] %(name)s: %(message)s` format) plus automatic error grouping/dedup into the `ErrorGroup` model from every existing `logger.warning()/error()/exception()` call across the codebase — visible in Admin → System Logs. Render's dashboard captures and displays this process's stdout/stderr for free, with no separate log-shipping service needed.
- **`python manage.py check_infra`** — a CLI wrapper around the exact same health checks, exits non-zero on failure; run it via Render's shell (or locally against production env vars) any time you want a one-shot readiness check.

---

## 7. First deploy — verification checklist

After the first successful deploy:

1. `python manage.py check_infra` (via Render's Shell tab) — confirms Postgres, pgvector, the background pool, and every configured LLM provider are all reachable.
2. Visit `/health/` directly — should return `200`.
3. Visit the app root — should redirect to `/login/`.
4. **Signup → OTP**: create an account, confirm the OTP email arrives (or appears in Render's logs if `EMAIL_HOST` is still blank), verify, confirm you land on the dashboard.
5. **Documents**: upload a PDF/DOCX/TXT, confirm it processes (status moves from "Processing" to "Embedded"), open Admin → System Health → Storage and confirm it shows "Remote (S3)", then check the Supabase Storage bucket directly to confirm the file is actually there.
6. **Redeploy** (trigger a manual deploy with no changes) and re-check that document is still downloadable — this is the concrete test that storage survives Render's ephemeral filesystem.
7. **Ask AI**: ask a question about the uploaded document, confirm a grounded, cited answer comes back (exercises hybrid retrieval — vector + BM25 + knowledge graph — end to end).
8. **AI Tasks**: run one from the wizard, confirm it starts, shows progress, completes, and its results/logs are visible afterward.
9. **Knowledge Base / Knowledge Graph**: confirm entities/relationships extracted from the uploaded document appear.
10. **RBAC**: confirm a non-admin account can't reach `/admin/*` pages (403), and an Admin account can.
11. **Analytics / Reports / Search History / Notifications / Profile**: each already reads from the same DB models the rest of this checklist already exercised — a quick visual check each renders without error is enough.

---

## What's intentionally *not* changed

Per the deployment brief's own instruction not to rewrite working components: authentication, RBAC, the entire retrieval pipeline (vector/BM25/graph/HyDE/multi-query/reranking/compression), citation rendering, the AI Tasks engine, analytics/reports queries, and every existing Django view/service/model are untouched. Every setting introduced here (`USE_S3_STORAGE`, `DB_SSLMODE`, WhiteNoise) is additive and defaults to the exact previous local-dev behavior when unset.
