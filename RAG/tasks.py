"""
Background task bodies (free-tier refactor - previously Celery tasks,
Sprint 10, extended for AI Tasks).

Two plain functions, both dispatched via RAG.services.task_runner.submit()
onto the in-process thread pool instead of a Celery worker:
- process_document_task: the async counterpart to
  upload_service.upload_document()'s inline processing path, gated by
  settings.ENABLE_ASYNC_PROCESSING.
- run_ai_task: executes one AITaskRun. Unlike process_document_task, this
  has no inline/sync fallback branch - AI Task runs always dispatch here
  regardless of settings.ENABLE_ASYNC_PROCESSING (see RAG.views.
  ai_task_create). That used to mean a Celery worker had to be running for
  AI Tasks to work at all; now the thread pool is always available in this
  same process, so there's no missing-worker failure mode to worry about.

Both tasks call apply_config_to_settings_cached() first - a background pool
thread never goes through RAG.middleware.SystemConfigSyncMiddleware (that
only runs for web requests), so without this a pool thread would only ever
see the SystemConfiguration values that happened to be live the moment this
process started, never picking up a later admin Settings change. Cheap due
to the existing 15s cache TTL (see system_config_service.py) - this is the
same TTL-recheck philosophy already used everywhere else in this codebase,
not a one-time process-start hook. (RAG/apps.py's AppConfig.ready() used to
call this too, at process start - removed from there since it queried the
DB during Django app initialization; web requests already get it from the
middleware, and this covers background thread tasks.)

See RAG/services/task_runner.py for how these get dispatched.
"""

import logging
import random
import time

from .models import AIRequestTrace, AITaskRun, Document
from .services.ai_tasks_engine_service import execute_run
from .services.observability_service import save_trace
from .services.system_config_service import apply_config_to_settings_cached
from .services.trace import bind_trace_id
from .services.upload_service import process_uploaded_document

logger = logging.getLogger(__name__)

MAX_PROCESSING_RETRIES = 3
RETRY_BASE_DELAY_SECONDS = 30
RETRY_MAX_DELAY_SECONDS = 600


def process_document_task(document_id):
    """
    Run steps 5-9 of the upload pipeline (extract/chunk, embed,
    graph-enrich, update chunk_count) for `document_id` on a background
    thread, instead of the request/response cycle.

    Retries up to MAX_PROCESSING_RETRIES times on unexpected failure (e.g.
    a transient DB hiccup), with exponential backoff + jitter (capped at
    RETRY_MAX_DELAY_SECONDS) rather than a flat delay every time - a
    transient blip recovers fast, a sustained outage backs off instead of
    hammering the same failing dependency repeatedly. Safe to block this
    pool thread with time.sleep() between attempts - unlike the old Celery
    self.retry(), which re-queued the task and returned the worker slot
    immediately, this just occupies one thread pool slot for the
    (bounded) duration of the backoff, which is an acceptable trade for
    not needing a broker/re-queue mechanism at all.

    Never raises - after exhausting retries, logs and returns. Nothing
    downstream calls .result() on this task's Future, so a raised
    exception would otherwise vanish silently rather than surface
    anywhere.

    Not retried when the Document itself is gone (deleted before the task
    ran), which is logged and treated as a no-op instead.
    """

    apply_config_to_settings_cached()

    try:
        document = Document.objects.get(id=document_id)

    except Document.DoesNotExist:
        logger.error(
            "process_document_task: Document %s no longer exists", document_id
        )
        return

    for attempt in range(1, MAX_PROCESSING_RETRIES + 1):
        try:
            process_uploaded_document(document)
            return

        except Exception:
            if attempt >= MAX_PROCESSING_RETRIES:
                logger.exception(
                    "process_document_task: giving up on document %s after %s attempts",
                    document_id, attempt,
                )
                return

            delay = min(
                RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1)),
                RETRY_MAX_DELAY_SECONDS,
            ) + random.uniform(0, 5)

            logger.exception(
                "process_document_task: attempt %s/%s failed for document %s, retrying in %.1fs",
                attempt, MAX_PROCESSING_RETRIES, document_id, delay,
            )

            time.sleep(delay)


def run_ai_task(run_id):
    """
    Executes one AITaskRun end-to-end. Always dispatched via
    task_runner.submit() regardless of settings.ENABLE_ASYNC_PROCESSING -
    unlike process_document_task, there is no inline fallback branch, but
    unlike the old Celery design this has no missing-worker failure mode
    either: the thread pool lives in this same process.

    Not retried, deliberately, unlike process_document_task:
    ai_tasks_engine_service.execute_run() writes AITaskResult rows
    incrementally as it goes and is not idempotent against a full re-run -
    a retry would duplicate every row already written before the failure.
    A failed run surfaces as AITaskRun.status=FAILED with error_message
    set; the user re-runs manually (a new AITaskRun) rather than this
    silently retrying a partially-written one.

    Binds one trace id for the whole run and saves it as an
    AIRequestTrace (RAG.services.observability_service.save_trace()) after
    execute_run() returns - the same shared trace Ask AI saves, so both
    features show up in the same AI Logs / Analytics Performance views.
    One row per RUN, not per per-document LLM call (see the trace model's
    own docstring for why).
    """

    apply_config_to_settings_cached()

    try:
        run = AITaskRun.objects.get(id=run_id)

    except AITaskRun.DoesNotExist:
        logger.error(
            "run_ai_task: AITaskRun %s no longer exists", run_id
        )
        return

    with bind_trace_id() as trace_id:
        execute_run(run)  # never raises - sets status itself (see its own docstring)

        total_duration_ms = None
        if run.started_at and run.completed_at:
            total_duration_ms = round((run.completed_at - run.started_at).total_seconds() * 1000)

        citation_count = sum(len(result.citations or []) for result in run.results.all())

        # A 1:1 status mapping (not "COMPLETED or else FAILED") - a
        # user-stopped run is neither: lumping it into FAILED would
        # both mislabel it in the AI Logs / Analytics Performance views
        # and inflate the failure rate those compute from this same
        # status field, for an outcome the user asked for.
        trace_status = {
            AITaskRun.Status.COMPLETED: AIRequestTrace.Status.COMPLETED,
            AITaskRun.Status.CANCELLED: AIRequestTrace.Status.CANCELLED,
        }.get(run.status, AIRequestTrace.Status.FAILED)

        save_trace(
            trace_id,
            AIRequestTrace.Source.AI_TASK,
            run.user,
            ai_task_run=run,
            status=trace_status,
            total_duration_ms=total_duration_ms,
            citation_count=citation_count,
            error=Exception(run.error_message) if run.status == AITaskRun.Status.FAILED and run.error_message else None,
        )
