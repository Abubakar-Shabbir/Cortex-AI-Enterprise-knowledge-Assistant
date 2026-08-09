"""
Celery tasks (Sprint 10, extended for AI Tasks).

Two tasks:
- process_document_task: the async counterpart to
  upload_service.upload_document()'s inline processing path, gated by
  settings.ENABLE_ASYNC_PROCESSING.
- run_ai_task: executes one AITaskRun. Unlike process_document_task,
  this has no inline/sync fallback - AI Task runs always dispatch here
  regardless of settings.ENABLE_ASYNC_PROCESSING (see
  RAG.views.ai_task_create), since a run can span up to
  settings.AI_TASKS_MAX_DOCUMENTS documents.

Both tasks call apply_config_to_settings_cached() first - a Celery
worker process never goes through RAG.middleware.SystemConfigSyncMiddleware
(that only runs for web requests), so without this a worker would only
ever see the SystemConfiguration values that happened to be live the
moment the worker process started, never picking up a later admin
Settings change. Cheap due to the existing 15s cache TTL (see
system_config_service.py) - this is the same TTL-recheck philosophy
already used everywhere else in this codebase, not a one-time
worker-start hook. (RAG/apps.py's AppConfig.ready() used to call this
too, at process start - removed from there since it queried the DB
during Django app initialization; web requests already get it from the
middleware, and this covers Celery.)

See myproject/celery.py for how this module is discovered.
"""

import logging

from celery import shared_task

from .models import AIRequestTrace, AITaskRun, Document
from .services.ai_tasks_engine_service import execute_run
from .services.observability_service import save_trace
from .services.system_config_service import apply_config_to_settings_cached
from .services.trace import bind_trace_id
from .services.upload_service import process_uploaded_document

logger = logging.getLogger(__name__)


@shared_task(
    bind=True, max_retries=3, default_retry_delay=30,
    retry_backoff=True, retry_backoff_max=600, retry_jitter=True,
)
def process_document_task(self, document_id):
    """
    Run steps 5-9 of the upload pipeline (extract/chunk, embed,
    graph-enrich, update chunk_count) for `document_id` in a Celery
    worker, instead of the request/response cycle.

    Retries up to 3 times on unexpected failure (e.g. a transient DB
    hiccup), with exponential backoff + jitter (Celery's built-in
    retry_backoff, base default_retry_delay=30s, capped at
    retry_backoff_max=600s) rather than a flat 30s delay every time -
    a transient blip recovers fast, a sustained outage backs off
    instead of hammering the same failing dependency every 30s. Not
    retried when the Document itself is gone (deleted before the task
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

    try:
        process_uploaded_document(document)

    except Exception as exc:
        logger.exception(
            "process_document_task failed for document %s", document_id
        )
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=0)
def run_ai_task(self, run_id):
    """
    Executes one AITaskRun end-to-end. Always dispatched via .delay()
    regardless of settings.ENABLE_ASYNC_PROCESSING - unlike
    process_document_task, there is no inline fallback branch; a
    Celery worker must be running for the AI Tasks feature to work at
    all.

    max_retries=0, deliberately unlike process_document_task's 3:
    ai_tasks_engine_service.execute_run() writes AITaskResult rows
    incrementally as it goes and is not idempotent against a full
    re-run - a retry would duplicate every row already written before
    the failure. A failed run surfaces as AITaskRun.status=FAILED with
    error_message set; the user re-runs manually (a new AITaskRun)
    rather than Celery silently retrying a partially-written one.

    Binds one trace id for the whole run and saves it as an
    AIRequestTrace (RAG.services.observability_service.save_trace())
    after execute_run() returns - the same shared trace Ask AI saves,
    so both features show up in the same AI Logs / Analytics
    Performance views. One row per RUN, not per per-document LLM call
    (see the trace model's own docstring for why).
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

        save_trace(
            trace_id,
            AIRequestTrace.Source.AI_TASK,
            run.user,
            ai_task_run=run,
            status=(
                AIRequestTrace.Status.COMPLETED
                if run.status == AITaskRun.Status.COMPLETED
                else AIRequestTrace.Status.FAILED
            ),
            total_duration_ms=total_duration_ms,
            citation_count=citation_count,
            error=Exception(run.error_message) if run.status == AITaskRun.Status.FAILED and run.error_message else None,
        )
