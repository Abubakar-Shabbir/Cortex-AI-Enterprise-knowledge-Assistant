# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Django-based RAG (Retrieval-Augmented Generation) document assistant. Users upload documents (PDF/DOCX/TXT), the app extracts, cleans, and chunks the text, embeds each chunk, stores vectors in PostgreSQL (via `pgvector`), extracts entities/relationships into a per-user knowledge graph, and answers questions using hybrid (vector + BM25 + graph) retrieval passed as context to Google Gemini.

Django project name is `myproject`; the single app is `RAG` (note the uppercase app label — imports/migrations reference `RAG`, not `rag`).

## Commands

Run all commands from the repo root (where `manage.py` lives).

```
python manage.py runserver          # start dev server
python manage.py makemigrations RAG # create migrations after model changes
python manage.py migrate            # apply migrations
python manage.py test RAG           # run tests
python manage.py createsuperuser    # for /admin access
pip install -r requirements.txt     # install deps
celery -A myproject worker --loglevel=info  # run a worker (only does anything once ENABLE_ASYNC_PROCESSING=True)
```

There is no configured linter/formatter in the repo.

`RAG/tests.py` deliberately mixes two base classes: plain `unittest.TestCase` for pure-logic tests (normalization, JSON parsing, mocked-LLM extraction) that need no database, and `django.test.TestCase` for tests that touch models. This matters because `django.test.TestCase.setUpClass` opens a DB transaction unconditionally, even for a test body that never queries anything — so *any* `django.test.TestCase` in the suite requires a reachable Postgres (with the `vector` extension available to the ephemeral test DB) for `manage.py test` to run at all. If you only need to check the pure-logic tests without a DB, load Django (`django.setup()`) and run those specific `unittest.TestCase` classes directly instead of through `manage.py test`.

**`requirements.txt` was rewritten (Sprint 10)** to a curated, UTF-8, top-level-only list (it was previously UTF-16-encoded and missing several packages the code actually imports). It's still worth knowing the `fitz` import is fragile — a same-named but unrelated `fitz` package (a neuroimaging workflow tool, unrelated to PyMuPDF) can end up on `sys.path` in a shared/global Python environment and shadow PyMuPDF, breaking the import with `ModuleNotFoundError: No module named 'frontend'`; if that happens, `pip uninstall fitz frontend && pip install pymupdf`. If you regenerate this file with a raw `pip freeze`, check the environment isn't polluted with unrelated packages first (a global/shared env can easily accumulate dozens of packages this project never imports) — prefer curating top-level direct imports over dumping a freeze verbatim.

## Environment configuration

Settings load from a `.env` file at the repo root via `django-environ` / `python-dotenv` (`myproject/settings.py`). Required variables:

- `SECRET_KEY`, `DEBUG`
- `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` — PostgreSQL connection (the only supported DB backend; `ENGINE` is hardcoded to `django.db.backends.postgresql`)
- `GEMINI_API_KEY` — used by `RAG/services/llm_service.py`
- Optional, with defaults in `settings.py`: `TOP_K` (3), `EMBEDDING_MODEL` (`all-MiniLM-L6-v2`), `LLM_MODEL` (`gemini-2.0-flash`)
- Optional Advanced Retrieval flags (Sprint 6), all with defaults in `settings.py`: `ENABLE_QUERY_EXPANSION` (`False`), `ENABLE_HYDE` (`False`), `ENABLE_MULTI_QUERY` (`False`), `ENABLE_DYNAMIC_TOP_K` (`True`), `DYNAMIC_TOP_K_MAX` (10), `MULTI_QUERY_VARIANTS` (3) — see the Advanced Retrieval section below for why the LLM-cost features default off
- Optional Reranking flags (Sprint 7): `ENABLE_RERANKER` (`False`), `RERANKER_MODEL` (`BAAI/bge-reranker-base`), `RERANKER_CANDIDATE_MULTIPLIER` (3) — see the Reranking section below
- Optional Context Compression flags (Sprint 8): `ENABLE_CONTEXT_COMPRESSION` (`False`), `CONTEXT_COMPRESSION_THRESHOLD` (`0.92`) — see the Context Compression section below
- Answer Generation (Sprint 9): `ANSWER_TEMPERATURE` (`0.2`) — see the Answer Generation section below
- Celery + Redis (Sprint 10): `REDIS_URL` (`redis://localhost:6379/0`), `CELERY_BROKER_URL`/`CELERY_RESULT_BACKEND` (both default to `REDIS_URL`), `ENABLE_ASYNC_PROCESSING` (`False`), `USE_REDIS_CACHE` (`False`), `DJANGO_LOG_LEVEL` (`INFO`) — see the Celery + Redis and Monitoring sections below

**The PostgreSQL database must have the `vector` extension enabled manually** (`CREATE EXTENSION IF NOT EXISTS vector;`) — no migration does this, it's a prerequisite the migrations assume is already in place. `settings_view` / `get_system_status()` checks this live and surfaces it on the Settings page.

**Settings.py gotchas** (non-obvious, easy to trip over when touching chunking/embeddings):
- `CHUNK_SIZE` is read from the environment near the top of `settings.py`, then unconditionally **overwritten to the literal `800`** near the bottom of the same file. The env var currently has no effect; `CHUNK_OVERLAP` (150) is a plain hardcoded constant, not env-driven at all.
- `EMBEDDING_DIMENSION` is a hardcoded `1024`, independent of `EMBEDDING_MODEL`. The default `EMBEDDING_MODEL` (`all-MiniLM-L6-v2`) actually produces 384-dim vectors — mismatched with the `VectorField(dimensions=settings.EMBEDDING_DIMENSION)` on `ChunkEmbedding`. If you change `EMBEDDING_MODEL`, you must also update `EMBEDDING_DIMENSION` and the migration for `ChunkEmbedding.embedding` to match the real output dimension of that model, or embedding inserts will fail.
- `LLM_MODEL` **is now live** (Sprint 9) — `llm_service.py` calls `gemini_client.get_model()` (`settings.LLM_MODEL`, defaulting to `"gemini-2.0-flash"`, same default as before) instead of its own inline `genai.configure()`/`GenerativeModel("gemini-2.0-flash")` call. This is the one exception to the "llm_service.py stays untouched" rule other sprints followed — Sprint 9 *is* the answer-generation sprint, so its prompt/model plumbing was the point.

## Architecture

### Upload pipeline — `upload_service.upload_document()`

1. `validation_service.validate_document()` — extension allowlist (`ALLOWED_FILE_EXTENSIONS`), max size (`MAX_FILE_SIZE`, 20 MB), non-empty, readable, non-blank filename.
2. `duplicate_service.check_duplicate()` — SHA-256 hash of the file contents, checked against `Document.file_hash` scoped to the current user; raises if already uploaded.
3. `metadata_service.extract_metadata()` — file name/extension/size.
4. Creates the `Document` row (file saved to `media/documents/`).
5. `document_processor.process_document()`:
   - `text_extractor.extract_text()` dispatches on extension: `.pdf` via PyMuPDF (`fitz`), `.docx` via `python-docx`, `.txt` via plain read.
   - Whitespace-normalizes the text.
   - `RecursiveCharacterTextSplitter` (langchain) splits it by `CHUNK_SIZE`/`CHUNK_OVERLAP` (characters, not words).
   - Each recursive chunk is further split by `semantic_chunk_service.semantic_chunk()` (langchain's `SemanticChunker`, percentile breakpoint, backed by a `HuggingFaceEmbeddings(EMBEDDING_MODEL)` instance separate from the one in `embedding_service.py`).
6. Each final chunk is saved as a `DocumentChunk` row (ordered by `chunk_number`).
7. `embedding_service.generate_embedding()` (SentenceTransformer, model = `settings.EMBEDDING_MODEL`, loaded once at import time) embeds each chunk.
8. `vector_service.save_embedding()` upserts a `ChunkEmbedding` row (one-to-one with `DocumentChunk`).
9. `graph_service.build_graph_for_chunk()` extracts entities/relationships from the chunk and merges them into the knowledge graph — see the Knowledge Graph section below. Wrapped in its own `try`/`except` in `upload_service.py`; a failure here is logged and swallowed, never fails the upload.
10. `Document.chunk_count` is updated to the final chunk total.

`RAG/utils/chunking.py`, `RAG/utils/file_parser.py`, and `RAG/utils/text_cleaner.py` are **dead code** — not imported anywhere in the current pipeline (extraction and chunking now live in `RAG/services/`). Only `RAG/utils/formatting.py` (`format_bytes`, `format_ms`) is actually used, by `stats_service.py` and `views.py`.

### Query pipeline — `query_service.answer_question()`

1. `retrieval_service.retrieve_chunks(question, user=None, filters=None, top_k=None)` runs **hybrid retrieval** across up to five sources, merged by `(document, chunk_number)`, optionally reranked (Sprint 7, see below), and capped to the effective `top_k`:
   - `vector_search()` — pgvector `L2Distance` similarity search over `ChunkEmbedding`.
   - `bm25_service.bm25_search()` — rank-bm25 `BM25Okapi`.
   - `graph_retrieval_service.graph_search()` — knowledge-graph lookup (see the Knowledge Graph section).
   - `hyde_search()` — Sprint 6, off by default (`settings.ENABLE_HYDE`). See Advanced Retrieval below.
   - `multi_query_service.multi_query_search()` — Sprint 6, off by default (`settings.ENABLE_MULTI_QUERY`). Imported *inside* `retrieve_chunks()`, not at module level, to break a circular import (`multi_query_service` reuses `retrieval_service.vector_search()` directly).
   - **Vector and BM25 are not scoped to the requesting user** — they search every user's chunks. Graph search *is* user-scoped (Entity/Relationship both carry a `user` FK). This is an intentional, pre-existing inconsistency that neither graph retrieval nor Sprint 6 attempts to fix — `user` is an optional parameter (defaults to `None`) so it stays backward compatible with any caller that omits it.
2. `query_service.answer_question()` optionally runs `context_compression_service.compress_context()` on the retrieved chunks (Sprint 8, off by default — `settings.ENABLE_CONTEXT_COMPRESSION`). This happens before anything downstream, so context, confidence, the search-method label, and the logged `QueryLog.sources` all reflect exactly what the LLM saw. See Context Compression below.
3. Retrieved (and, if enabled, compressed) chunks are rendered into a single numbered context string by `citation_service.build_cited_context()` (Sprint 9) — `"[1] (Document, chunk N):\n<content>"` blocks, in retrieval order — so the LLM has something concrete to cite.
4. `llm_service.generate_answer()` sends that numbered context + question to Gemini via `prompt_templates.build_answer_prompt()`, which instructs the model to answer only from the numbered sources, cite every claim inline as `[n]`, and reply with the fixed fallback (`prompt_templates.NOT_FOUND_ANSWER`) when unanswerable. Runs at `settings.ANSWER_TEMPERATURE` (default `0.2`, well below the provider default) as an additional hallucination-reduction lever. See Answer Generation below.
5. `citation_service.extract_citations()` parses which `[n]` markers actually appear in the answer, maps them back to the cited chunks, and annotates each cited entry in `retrieved_chunks` in place with `citation_number` (read by `ask_ai.html` to badge cited source cards).
6. `calculate_confidence(retrieved_chunks, answer=None, citation_count=None)` derives a 0–100 score from the L2 distances of `"vector"` and `"hyde"` chunks (both are genuine embedding-space distances; no distance evidence at all falls back to `40`), then two Sprint 9 adjustments layer on top when `answer`/`citation_count` are passed (as `answer_question()` does): the fixed fallback answer forces confidence to `0` outright, and an answer that cited none of the retrieved sources discounts the distance-based score by 30%. Both parameters default to `None`/inert, so any caller passing only `retrieved_chunks` keeps the pre-Sprint-9 score.
7. `describe_search_method()` builds the `search_method` label (e.g. `"Hybrid (Vector + BM25)"`, `"Hybrid (Vector + BM25 + Graph + HyDE + Multi-query)"`) from whichever `search_type` values actually appear in the retrieved chunks, via the `SEARCH_TYPE_LABELS` list — extend that list alongside any new retrieval source rather than hardcoding a new fixed string.
8. Every question (when `user` is set) is persisted as a `QueryLog` row — question, answer, `sources` (JSON list of retrieved chunk dicts, now including `citation_number` on cited entries), `search_method`, `response_time_ms`, `confidence`. This is what powers Search History and Analytics; `source.search_type` and `stats_service`'s search-type breakdown are read generically from whatever strings appear, so a new retrieval source needs no template/analytics changes. `views.search_history`'s answered/unanswered classification now calls `prompt_templates.is_not_found_answer()` rather than keeping its own copy of the fallback substring.

### Advanced Retrieval (Sprint 6) (`RAG/services/{query_transform,query_expansion,hyde,retrieval_filters,dynamic_topk,multi_query}_service.py`)

Five composable retrieval enhancements, all reusing the existing `vector_search()`/`bm25_search()`/embedding/Gemini plumbing rather than duplicating it. **Design choice:** the three that cost an extra Gemini call per question (query expansion, HyDE, multi-query) default to **off** (`ENABLE_QUERY_EXPANSION` / `ENABLE_HYDE` / `ENABLE_MULTI_QUERY` = `False`), so the out-of-the-box request path and its latency/cost are unchanged from Sprint 5. Metadata filtering and dynamic top-k are local/free and are effectively always available (filtering is opt-in per call via `filters=None`; dynamic top-k defaults **on**, `ENABLE_DYNAMIC_TOP_K = True`). All five are fully implemented and unit-tested regardless of their default flag state — flip the relevant `.env` flag to activate one, no code changes needed.

- **Query Expansion** (`query_expansion_service.expand_query()`) — asks Gemini for alternate phrasings via the shared `query_transform_service.generate_query_variants()`, then folds their distinct *words* into one enriched string appended to the original question. Used only to enrich the **BM25** query (`retrieve_chunks()`'s `lexical_query`) — vector search keeps embedding the raw question, since a keyword-stuffed sentence doesn't embed more accurately, only lexical matching benefits.
- **HyDE** (`hyde_service.generate_hypothetical_document()` + `retrieval_service.hyde_search()`) — asks Gemini to write a short hypothetical passage that would answer the question, embeds *that* instead of the question, and runs it through the same nearest-neighbor lookup as `vector_search()`. Both now share `retrieval_service._vector_similarity_search()` (extracted in this sprint) rather than duplicating the pgvector query. Tagged `search_type: "hyde"`.
- **Metadata Filtering** (`retrieval_filters.RetrievalFilters` / `apply_document_filters()`) — a frozen dataclass (`document_ids`, `file_types`, `uploaded_after`, `uploaded_before`) applied as Django queryset filters. Every retrieval function (`vector_search`, `hyde_search`, `bm25_search`, `graph_search`) takes the same `filters=None` keyword and calls `apply_document_filters(queryset, filters, document_field=...)` before slicing to `top_k` — a no-op when `filters` is `None`/empty. `RetrievalFilters.from_request()` builds one from loosely-typed request input (e.g. a POSTed `document_id` string) and degrades invalid input to "no filter" rather than raising. Exposed end-to-end via a "Search in" document dropdown on the Ask AI page (`views.ask_ai`, `templates/ask_ai.html`) — the only new UI surface Sprint 6 adds.
- **Dynamic Top-K** (`dynamic_topk_service.compute_dynamic_top_k()`) — a deliberately non-LLM, word-count-and-conjunction heuristic (see module docstring for why: retrieval depth is decided on *every* query, and this sprint already risks stacking multiple LLM calls per question). Replaces the fixed `settings.TOP_K` as `retrieve_chunks()`'s default depth unless a caller passes `top_k=` explicitly or `ENABLE_DYNAMIC_TOP_K` is `False`. Capped at `settings.DYNAMIC_TOP_K_MAX`.
- **Multi-query Retrieval** (`multi_query_service.multi_query_search()`) — RAG-Fusion style: reuses `generate_query_variants()` for `settings.MULTI_QUERY_VARIANTS` alternate phrasings, runs `vector_search()` + `bm25_search()` per *additional* variant (the original question is already covered by the primary hybrid search), and fuses the ranked lists with Reciprocal Rank Fusion (`_reciprocal_rank_fusion()`, standard `RRF_K = 60`). A failure on one variant's search is caught per-variant so it doesn't discard the others. Tagged `search_type: "multi_query"`.

`generate_query_variants()` (`query_transform_service.py`) is the one shared LLM-rewriting primitive behind both query expansion and multi-query retrieval — it's the only place that prompts Gemini for alternate phrasings, so the two features can't drift into duplicate prompt/parsing logic. It always returns the original question as `variants[0]`, and falls back to `[question]` on any failure.

Every new LLM-backed function in this section follows the same never-raise contract as `graph_extraction_service.extract_graph()` (Sprint 5): on any failure (missing API key, network/model error, malformed JSON) it logs and returns an empty/unchanged result, never propagates the exception. No new third-party dependencies were introduced.

### Reranking (Sprint 7) (`RAG/services/reranker_service.py`)

A BGE cross-encoder reranker re-scores the merged candidate list right before `retrieve_chunks()` returns, off by default (`settings.ENABLE_RERANKER`). Unlike the hybrid retrievers, which score each chunk independently (a pgvector distance, a BM25 score, an entity match), a cross-encoder scores each `(question, chunk)` pair jointly — a stronger relevance signal, at the cost of one local model inference pass per candidate chunk.

- `reranker_service.rerank_chunks(question, chunks, top_k=None)` runs `sentence_transformers.CrossEncoder(settings.RERANKER_MODEL)` (default `BAAI/bge-reranker-base`) over every candidate, sorts descending by score, and tags each result with an added `rerank_score` key — every existing key (including `search_type`) is preserved unchanged, so `calculate_confidence()`, `describe_search_method()`, `QueryLog.sources`, and the templates all keep working with zero modification. Never raises: any failure (model load error, inference error) logs and falls back to the original, unranked `chunks` list, same contract as the Sprint 5/6 services.
- **The cross-encoder model is lazily loaded on first call** (`_get_reranker_model()`), not at import time — unlike `embedding_service.py`'s eager `SentenceTransformer(...)` load at module import. `retrieval_service.py` imports `reranker_service` unconditionally, so an eager load there would pay the model download/load cost on every process start regardless of the flag; the lazy singleton keeps `ENABLE_RERANKER=False` completely free.
- When reranking is enabled, `retrieve_chunks()` over-fetches each source by `settings.RERANKER_CANDIDATE_MULTIPLIER` (default 3× the effective `top_k`) before merging, so the reranker has a real candidate pool to reorder instead of just re-scoring an already-truncated list; the final result is then reranked back down to the effective `top_k`. When the flag is off, retrieval depth and behavior are byte-for-byte unchanged from Sprint 6.
- No new third-party dependency — `CrossEncoder` ships inside `sentence-transformers`, already a dependency via `embedding_service.py`.

### Context Compression (Sprint 8) (`RAG/services/context_compression_service.py`)

Removes chunks from the retrieved set that are semantically redundant with one already kept, right before `answer_question()` builds the LLM context — off by default (`settings.ENABLE_CONTEXT_COMPRESSION`).

- `compress_context(chunks, similarity_threshold=None)` embeds each chunk's content with the existing `embedding_service.generate_embedding()` (no new dependency, no LLM call), walks the list in order, and drops a chunk only when its cosine similarity to an **already-kept** chunk is `>= similarity_threshold` (default `settings.CONTEXT_COMPRESSION_THRESHOLD`, `0.92`). The first occurrence of an idea always survives — only later duplicates are dropped — so no distinct fact is ever removed, just repetition. Fewer than 2 chunks is a no-op (nothing to compare). Never raises: an embedding failure logs and returns `chunks` unchanged, same never-raise contract as the rest of Sprints 5–7.
- Called from `query_service.answer_question()` immediately after `retrieve_chunks()` and before context/confidence/search-method/`QueryLog` are built, so every downstream consumer — the answer's context, `calculate_confidence()`, `describe_search_method()`, and the logged `sources` — reflects exactly what was compressed, never the pre-compression set.
- Threshold is deliberately conservative and opt-in: a too-aggressive value risks dropping a chunk that genuinely mattered, which is why this defaults off rather than joining Dynamic Top-K/Metadata Filtering as always-on despite also being local/free (no LLM call).

### Answer Generation (Sprint 9) (`RAG/services/{prompt_templates,citation_service}.py`, `llm_service.py`)

Prompt templates, grounding, citations, confidence, and hallucination reduction are one connected change to how the final answer is produced — unlike Sprints 6–8, all always active (no feature flag), since these are correctness/quality improvements to the core answer step rather than opt-in extras with a cost/risk tradeoff.

- **Prompt Templates** (`prompt_templates.py`) — `ANSWER_PROMPT_TEMPLATE` and `build_answer_prompt(context, question)` replace the inline f-string `llm_service.py` used to build itself. `NOT_FOUND_ANSWER` is the single canonical copy of the fixed fallback sentence, and `is_not_found_answer(answer)` is the one place that checks for it (a substring check, tolerant of minor whitespace variation) — `views.search_history` and `query_service.calculate_confidence()` both call it instead of keeping their own copy of the fallback text, closing the "keep them in sync" gotcha earlier CLAUDE.md revisions flagged.
- **Grounded Answers** — the template's rules restrict the model to the numbered sources only ("never use outside knowledge, even if you are confident it is correct"), require it to say what's missing rather than fill gaps itself when sources only partially answer, and require the exact fallback sentence, nothing else, when they don't answer at all.
- **Source Citations** (`citation_service.py`) — `build_cited_context(chunks)` numbers the (already retrieved/compressed) chunks `[1]..[N]` in order and renders each as a `(Document, chunk N)` labeled block; this numbered string *is* the `context` passed into `generate_answer()`, so the prompt's citation rule ("cite every claim as `[n]`") has something concrete to reference. `extract_citations(answer, chunks)` parses `[n]` markers back out of the generated answer, drops any out-of-range/invented number, dedupes repeats, and — for template convenience, the same "enrich the dict as it flows through" pattern `reranker_service.py` uses for `rerank_score` — annotates each cited chunk *in place* with `citation_number`. `ask_ai.html` reads that to badge cited source cards ("Cited [n]") and shows a citation count alongside confidence/response time/chunk count.
- **Confidence Score** — unchanged distance-based scoring (see the query pipeline steps above) plus two new signals folded into `calculate_confidence()`: the fallback answer forces `0`; zero citations despite retrieved sources discounts the score by 30% (not to `0` — short factual answers can legitimately cite sparsely). Both signals are opt-in via optional parameters, so the function's original one-argument call shape still behaves exactly as before.
- **Hallucination Reduction** is the combination of the above rather than one component: grounding rules + mandatory inline citations + `settings.ANSWER_TEMPERATURE` (default `0.2`, well below the Gemini default) to reduce improvisation + a confidence score that actually reflects whether the model grounded its answer in a citation, rather than only how strong retrieval looked.
- `llm_service.generate_answer(context, question)` keeps its exact pre-Sprint-9 signature and never-raise/error-string contract (`f"Gemini Error: {e}"` on failure, an unusual but long-standing behavior other code doesn't currently branch on) — only its internals changed: it now calls `gemini_client.get_model()` instead of configuring `genai` itself (see the `LLM_MODEL` gotcha above), builds the prompt via `prompt_templates.build_answer_prompt()`, and passes `generation_config={"temperature": settings.ANSWER_TEMPERATURE}`.

### Celery + Redis (Sprint 10) (`myproject/celery.py`, `RAG/tasks.py`)

Async document processing, off by default — `settings.ENABLE_ASYNC_PROCESSING` (`False`), so out-of-the-box behavior is unchanged from every sprint before this one: `upload_service.upload_document()` still processes a document inline, in the request/response cycle.

- **Wiring**: `myproject/celery.py` defines the Celery app (`Celery("myproject")`, configured from Django settings under the `CELERY_` namespace); `myproject/__init__.py` imports it as `celery_app` so `@shared_task` anywhere in the project binds correctly as soon as Django starts. `app.autodiscover_tasks()` picks up `RAG/tasks.py` automatically since `"RAG"` is in `INSTALLED_APPS` — no explicit task registration needed.
- **The split**: `upload_service.py` was refactored into `upload_document()` (steps 1-4: validate, dedupe, extract metadata, create the `Document` row) and `process_uploaded_document(document)` (steps 5-9: extract/chunk, embed, graph-enrich, update `chunk_count` — the expensive part). `upload_document()` calls `process_uploaded_document()` directly when `ENABLE_ASYNC_PROCESSING` is off, or dispatches `RAG.tasks.process_document_task.delay(document.id)` when it's on — imported with `from ..tasks import process_document_task` *inside* the branch, not at module top level, so `upload_service.py` (in `RAG/services/`) doesn't have to import Celery machinery on every request when async processing is disabled.
- **Why this needed no UI/status-logic changes**: `Document.chunk_count` already defaults to `0` until `process_uploaded_document()` finishes, and `documents_view` already reads `chunk_count == 0` as `"Processing"` status. Dispatching the same work to a worker instead of running it inline doesn't change that contract at all — a document just shows "Processing" for longer if there's no worker consuming the queue yet, rather than the request hanging.
- **`RAG/tasks.py`**: one task, `process_document_task(document_id)` — re-fetches the `Document` (a Celery task only gets serializable arguments, not the live object `upload_document()` already had), calls `process_uploaded_document()`, and retries up to 3 times (30s apart) on unexpected failure via `self.retry()`. A `Document.DoesNotExist` (deleted before the task ran) is logged and treated as a no-op, not retried.
- **Redis** backs the Celery broker/result store (`REDIS_URL`, defaulted by `CELERY_BROKER_URL`/`CELERY_RESULT_BACKEND`) unconditionally once Celery is configured, and *optionally* backs Django's cache (`USE_REDIS_CACHE`, default `False` → plain `LocMemCache`, Django's implicit default) — `context_processors.sidebar_status()`'s `cache.get_or_set()` call is the one existing cache consumer this affects, and needed no code change since it goes through the same `django.core.cache.cache` either way.
- Running a worker locally: `celery -A myproject worker --loglevel=info` (needs a reachable Redis; `ENABLE_ASYNC_PROCESSING=True` in `.env` to actually route uploads to it).

### Monitoring (Sprint 10) (`RAG/services/health_service.py`)

- **Logging**: `settings.py` now has an explicit `LOGGING` dict (console handler, `%(asctime)s %(levelname)s %(name)s: %(message)s`), so the `logger.info()`/`logger.exception()` calls already present throughout `RAG/services/*.py` actually surface — previously they relied on Django's implicit default, which only shows `WARNING`+ on the root logger. `DJANGO_LOG_LEVEL` controls the root level (default `INFO`); `httpx`/`httpcore`/`urllib3` are pinned to `WARNING` since the embedding/reranker model libraries' Hugging Face requests would otherwise log a line per HTTP call and drown out everything else.
- **`GET /health/`** (`views.health_check`, public — no `@login_required`, since a health check has to work before anything else does) returns JSON via `health_service.get_health_status()`: `200` with `{"status": "ok", ...}` or `503` with `{"status": "degraded", ...}`. Reuses `stats_service.get_system_status()` for the DB/pgvector checks rather than duplicating that `SELECT 1`/`pg_extension` lookup, but wraps the whole call — `get_system_status()`'s own unguarded ORM `.count()`/`.aggregate()` calls (below its `SELECT 1` try/except) will raise on a fully-down database, which is fine for `settings_view` (an authenticated page) but not acceptable for a public health endpoint that has to stay up precisely when the database might not be. Adds one new check, `_check_redis()` (a 1s-timeout `PING` against `REDIS_URL`), which is only load-bearing to the overall `ok`/`degraded` verdict when `USE_REDIS_CACHE` or `ENABLE_ASYNC_PROCESSING` is actually turned on — an unreachable Redis shouldn't fail the health check for a deployment that never enabled either.

### Data model (`RAG/models.py`)

`Document` (owned by `User`, holds `file_hash` for dedup, `file_size`, `file_type`, denormalized `chunk_count`) → `DocumentChunk` (ordered by `chunk_number`) → `ChunkEmbedding` (1:1 with a chunk, `VectorField(dimensions=settings.EMBEDDING_DIMENSION)` plus which model produced it — see the dimension-mismatch gotcha above). `QueryLog` is independent of the document graph and records every Q&A interaction per user. `Entity`, `EntityMention`, and `Relationship` form the knowledge graph — see below.

### Knowledge Graph (`RAG/services/graph_*.py`)

Built during upload, read during query answering. All three models are scoped per `User`.

- **`Entity`** — a deduplicated entity, keyed by `(user, name, entity_type)` where `name` is the lowercased/whitespace-normalized form (`display_name` keeps original casing for UI). `entity_type` is a free-form string (not Django `choices`), so new types need no migration; `graph_extraction_service.SUGGESTED_ENTITY_TYPES` is prompt guidance only. `mention_count` is denormalized, incremented on each new `EntityMention`.
- **`EntityMention`** — links an `Entity` to the `DocumentChunk` it was found in (`unique_together`, so re-processing a chunk is a no-op). This is what graph retrieval joins through to get back to chunk content.
- **`Relationship`** — a directed edge `(user, source, target, relation_type)`. Re-extracting the same triple from another chunk doesn't create a duplicate row — it increments `weight` via `get_or_create` + `F("weight") + 1`. `context` stores the first supporting chunk snippet (up to 500 chars) for reference.

**Extraction** (`graph_extraction_service.extract_graph()`) is a single Gemini call per chunk (JSON-mode response, `response_mime_type: "application/json"`) that returns both entities and relationships together, rather than two calls — the prompt requires relationship endpoints to reuse the exact entity names given, and `_parse_response()` drops any relationship referencing a name outside the extracted entity list. Chunks under `MIN_CHUNK_LENGTH` (20 chars) are skipped without an API call. **Never raises** — any failure (missing API key, network error, malformed JSON) logs and returns an empty result, by design, so graph enrichment can never break ingestion or query answering. It reuses `gemini_client.get_model()`, the same shared factory `llm_service.py` was moved onto in Sprint 9 (see the `LLM_MODEL` gotcha above).

**Construction** (`graph_service.build_graph_for_chunk()`) calls `extract_graph()` *outside* any DB transaction (it's a slow network call), then writes the results inside a separate `@transaction.atomic` block (`_persist_graph()`) so a DB transaction is never held open across the LLM round-trip. Called once per chunk from `upload_service.upload_document()`, right after that chunk's embedding is saved.

**Retrieval** (`graph_retrieval_service.graph_search()`) does *not* run a second LLM extraction per query (cost/latency). Instead it lexically matches the question against the user's already-known `Entity.name` values (same "load everything into Python, score it" style as `bm25_service.py`), expands one relationship hop via `Relationship`, then returns the `EntityMention`-linked chunks — shaped identically to `vector_search()`/`bm25_search()` results (`search_type: "graph"`) so `retrieval_service.retrieve_chunks()` merges them with zero special-casing.

No new third-party dependencies were introduced — extraction reuses `google-generativeai`, already a dependency for `llm_service.py`.

### Views (`RAG/views.py`)

Function-based, one view per page (not a single multiplexed dashboard):

- `dashboard` — aggregate stats (`stats_service.get_dashboard_stats`), a 7-day activity/search-mix/chunk chart snapshot (`get_analytics_data`), and (Enterprise Dashboard rebuild) real Smart Insights / Recommendations (`get_dashboard_insights`) plus a Quick Actions row.
- `ask_ai` — dedicated Q&A page ("AI Search" in the nav); POSTs a question (plus an optional `document_id` from a "Search in" dropdown, parsed into `RetrievalFilters` — Sprint 6 metadata filtering), shows answer/sources/confidence/timing, plus Suggested Questions derived from the user's own top knowledge-graph entities.
- `documents_view` — upload (via `upload_service`) + document library, with a per-document status computed on the fly (`Processing` / `Partial` / `Embedded`) by comparing `chunk_count` against the count of chunks that actually have an embedding.
- `document_delete`, `search_history` (paginated, 15/page), `analytics_view` (14-day charts, now including confidence/response-time trends), `profile_view` (profile + password-change forms + current-session info).
- `knowledge_base_view`, `entity_detail_view`, `relationships_view`, `knowledge_graph_view`, `citation_explorer_view` — the Knowledge Base section (new UI surface for Sprint 5's Entity/Relationship graph — see below).
- `reports_view`, `export_documents_report`, `export_usage_report` — real CSV exports (`reports_service.py`, stdlib `csv`, no new dependency).
- `monitoring_view` — **replaces the old `settings_view`/`/settings/` route.** Same RAG-pipeline-config + DB/pgvector content as before, now also showing Sprint 10's Redis/Celery health, and gated behind `request.user.is_staff` (a real, pre-existing Django field — not a new RBAC system; see Role-based navigation below). Any authenticated user could reach the old settings page; that was never intentional, just never tightened until this rebuild.
- `health_check` (Sprint 10) — the one view in this list that's public (no `@login_required`); see the Monitoring section above.

`stats_service.py` centralizes all aggregate/chart-data queries (`get_dashboard_stats`, `get_recent_activity`, `get_analytics_data`, `get_dashboard_insights`, `get_system_status`) — reuse it rather than writing new aggregate queries directly in views. `knowledge_service.py` does the same for Knowledge Base queries (Entity/Relationship/EntityMention), and `reports_service.py` for CSV row-building.

`context_processors.py` runs two context processors on every authenticated page render (registered in `TEMPLATES.OPTIONS.context_processors`): `sidebar_status` (merged recent-activity feed + `get_system_status()`, cached 30s) and `breadcrumbs` (a static `BREADCRUMB_MAP`/`NAV_GROUP_MAP` keyed off `request.resolver_match.url_name` — see below). Neither needs any individual view to build its own trail/status for the common case.

### Information architecture & role-based navigation

The nav is a grouped, multi-page sidebar (`templates/partials/sidebar.html`), not a single dashboard: Dashboard → Workspace (Documents, Knowledge Base, AI Search) → Insights (Analytics, Reports) → Profile, plus an **Administration** group (currently just Monitoring) that only renders for `request.user.is_staff`. This uses Django's built-in `is_staff` field as the User/Admin distinction — there is no separate RBAC/permissions system in this project; if one gets built later, `is_staff` is the natural seam to hang it off.

- **Breadcrumbs** (`partials/_breadcrumbs.html`) come from `context_processors.breadcrumbs()`'s `BREADCRUMB_MAP` (`{url_name: [(label, url_name_or_None), ...]}`). A view with a dynamic final segment (e.g. `entity_detail_view` showing the entity's actual name) sets `breadcrumb_leaf` in its own context instead of trying to fit a dynamic value into the static map.
- **Active nav highlighting** for a section with more than one URL (e.g. every Knowledge Base sub-page) goes through `NAV_GROUP_MAP` in the same context processor, producing `active_nav` — `_nav_item.html` compares against that, not the raw `url_name`, so `entity_detail`/`relationships`/`knowledge_graph`/`citation_explorer` all highlight "Knowledge Base".
- **Command palette** (`partials/_command_palette.html`, included globally in `base.html` for authenticated users) — Cmd/Ctrl+K, a client-side Alpine component listing the exact same `{% url %}`-resolved destinations as the sidebar. No new backend, no search index — it's keyboard navigation, not a search feature.
- Sections requested but with no backing data model yet (Collections/Tags/Favorites on Documents; Saved Searches on AI Search; scheduled/comparative Reports; multi-device session listing on Profile; a centralized log viewer on Monitoring) render `partials/_coming_soon.html` instead of fabricated data — check that partial before building the real feature so the placeholder can just be deleted, not reconciled with fake content.

### Knowledge Base (new UI, Sprint 5 backend) (`RAG/services/knowledge_service.py`, `templates/knowledge/`)

The Knowledge Graph (`Entity`/`EntityMention`/`Relationship`, built during upload since Sprint 5) had no UI at all until this rebuild — `knowledge_service.py` is read-only, user-scoped, and is the first thing that surfaces it. Four sub-pages share one tab bar (`partials/_kb_tabs.html`) under a single "Knowledge Base" sidebar entry rather than four separate top-level nav items:

- **Browse** (`knowledge_base_view`) — category/search-filterable entity grid (`search_entities()`), overview counts (`get_knowledge_overview()`).
- **Relationship Explorer** (`relationships_view`) — paginated table of `Relationship` rows, most-reinforced (`weight`) first, filterable by `relation_type`.
- **Graph** (`knowledge_graph_view`) — a `vis-network` (CDN, loaded only on this page — see Performance below) force-directed visualization. `get_graph_data()` caps at `GRAPH_NODE_LIMIT` (120) entities by mention count; this is a visualization, not an export, so the Relationship Explorer table is the place for the full unfiltered list. `get_graph_insights()` (most-mentioned entity, most-connected entity by relationship degree, top category/relation type) backs the stat cards above the graph.
- **Citation Explorer** (`citation_explorer_view`) — built from `QueryLog.sources` entries with a `citation_number` (Sprint 9's per-answer citations), *not* a separate citations table — citations are already fully captured there.

`entity_detail_view` (reached by clicking an entity, not from the sidebar) shows its mentions (linking back to source chunks) and one-hop outgoing/incoming relationships.

### Reports (`RAG/services/reports_service.py`)

Two real CSV exports (`export_documents_report`, `export_usage_report`) writing straight into the `HttpResponse` via the stdlib `csv` module — no new dependency, no intermediate file. `reports_service.py` only builds the row lists (easy to unit test); the views own the `HttpResponse`/`csv.writer` plumbing.

### Templates & frontend

Templates live in `templates/` (`base.html` + `templates/partials/`, plus `templates/knowledge/` for the Knowledge Base sub-pages), configured via `TEMPLATES.DIRS` rather than per-app template dirs. Tailwind, Alpine.js, Lucide icons, and Chart.js are all loaded via CDN `<script>` tags in `base.html` / per-page `extra_scripts` blocks — there is no npm/node build step for frontend assets. `vis-network` (Knowledge Graph visualization) follows the same CDN pattern but is loaded *only* from `knowledge/graph.html`'s own `extra_scripts` block, not globally — the closest equivalent this architecture has to route-based code splitting. Chart data is passed from views as Python lists/dicts and serialized into the page with Django's `json_script` filter, then read by inline Chart.js setup code (see `dashboard.html`, `analytics.html`).

Reusable partials worth knowing about beyond the obvious (`_nav_item`, `_stat_card`): `_page_header.html` (title/subtitle/optional CTA), `_empty_state.html`, `_coming_soon.html` (see above), `_logo.html` (the brand mark — a three-node network glyph, `currentColor`-driven so it doubles as a monochrome mark; used in the sidebar, topbar mobile view, login/signup, and baked into the favicon data URIs since those can't use `currentColor`). `_stat_card.html` takes an optional `numeric=True` to animate the value counting up from 0 on page load (Alpine `requestAnimationFrame`, ~700ms) — only pass it for genuinely numeric values, not formatted strings like "4.2 MB".
