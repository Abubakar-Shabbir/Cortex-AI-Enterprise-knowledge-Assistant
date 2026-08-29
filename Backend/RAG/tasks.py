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

from django.contrib.auth.models import User
from django.utils import timezone

from .models import AIRequestTrace, AITaskRun, Document, Notification
from .services.ai_tasks_engine_service import execute_run
from .services.observability_service import save_trace
from .services.system_config_service import apply_config_to_settings_cached
from .services.trace import bind_trace_id
from .services.upload_service import process_uploaded_document

logger = logging.getLogger(__name__)

MAX_PROCESSING_RETRIES = 3
RETRY_BASE_DELAY_SECONDS = 30
RETRY_MAX_DELAY_SECONDS = 600


def send_notification_email_task(notification_id):
    """
    Backgrounded email delivery for one Notification row, dispatched by
    RAG.services.notification_service.create_notification() via
    task_runner.submit() - same re-fetch-by-id-on-a-pool-thread pattern
    as process_document_task re-fetching Document. Writes
    email_sent/email_sent_at/email_error back onto the row so delivery
    status is inspectable without a separate log lookup. Never raises
    further - a missing Notification (deleted before this ran) is
    logged and treated as a no-op, matching process_document_task's own
    DoesNotExist handling.
    """

    apply_config_to_settings_cached()

    from .services.email_service import send_templated_email

    try:
        notification = Notification.objects.select_related("recipient", "actor").get(id=notification_id)
    except Notification.DoesNotExist:
        logger.error("send_notification_email_task: Notification %s no longer exists", notification_id)
        return

    success, error = send_templated_email(
        to_email=notification.recipient.email,
        subject=notification.title,
        template_base="notification_email",
        context={
            "site_name": _site_name(),
            "title": notification.title,
            "message": notification.message,
            "action_url": _absolute_url(notification.action_url),
            "actor_name": notification.actor.username if notification.actor_id else None,
        },
    )

    notification.email_sent = success
    notification.email_sent_at = timezone.now() if success else None
    notification.email_error = "" if success else error[:255]
    notification.save(update_fields=["email_sent", "email_sent_at", "email_error"])


def _site_name():
    from django.conf import settings
    return settings.SITE_NAME


def _absolute_url(path):
    """Joins a relative path (e.g. from reverse()) onto settings.SITE_URL for use inside an email body, where a relative link would be meaningless. Falls back to the bare path if SITE_URL isn't configured (local dev without it set)."""

    from django.conf import settings

    if not path:
        return ""
    if not settings.SITE_URL:
        return path
    return settings.SITE_URL.rstrip("/") + path


def send_otp_email_task(user_id, raw_code, expires_at_iso):
    """
    Backgrounded OTP email send, dispatched by
    RAG.services.otp_service.generate_and_send_otp() via
    task_runner.submit(). `raw_code` is only ever held here, as a
    function argument on a pool thread - never logged (task_runner's
    own exception logging logs only this function's name, never its
    arguments - see task_runner._run()) and never written to the
    database (EmailOTP only stores make_password(code)).
    """

    apply_config_to_settings_cached()

    from .services.email_service import send_templated_email

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        logger.error("send_otp_email_task: User %s no longer exists", user_id)
        return

    from .utils.formatting import mask_email

    success, error = send_templated_email(
        to_email=user.email,
        subject="Verify your email",
        template_base="otp_email",
        context={
            "site_name": _site_name(),
            "code": raw_code,
            "expiry_minutes": otp_expiry_minutes(),
            "masked_email": mask_email(user.email),
        },
    )

    if not success:
        logger.error("send_otp_email_task: delivery failed for user %s: %s", user_id, error)


def otp_expiry_minutes():
    from .services.otp_service import OTP_EXPIRY_MINUTES
    return OTP_EXPIRY_MINUTES


def send_password_reset_email_task(user_id, uidb64, token, to_email):
    """
    Backgrounded delivery for RAG.auth_views.RAGPasswordResetForm -
    reconstructs the reset link from primitives (user id, uid, token)
    rather than receiving a pre-built URL, so this task is the one
    place that has to know the password_reset_confirm URL shape.

    Points at the React SPA's /app/reset/<uidb64>/<token>/ route (see
    frontend/src/pages/auth/PasswordResetConfirm.jsx + RAG/api/auth_views.py's
    password_reset_confirm_validate_view/password_reset_confirm_view),
    not the classic Django `password_reset_confirm` URL - the SPA is
    the primary UI now. The classic route/view/template still exist
    and still work for anyone who reaches them directly.
    """

    apply_config_to_settings_cached()

    from .services.email_service import send_templated_email

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        logger.error("send_password_reset_email_task: User %s no longer exists", user_id)
        return

    reset_url = _absolute_url(f"/app/reset/{uidb64}/{token}/")

    success, error = send_templated_email(
        to_email=to_email,
        subject="Reset your password",
        template_base="password_reset_email",
        context={"site_name": _site_name(), "reset_url": reset_url, "username": user.username},
    )

    if not success:
        logger.error("send_password_reset_email_task: delivery failed for user %s: %s", user_id, error)


def send_share_invite_email_task(document_id, invited_email, sharer_username):
    """
    Sent directly via email_service (not notification_service - there's
    no User row yet for `invited_email`, and Notification.recipient is
    a required FK). RAG.services.otp_service.verify_otp() converts the
    pending DocumentShare row and fires the real in-app notification
    once this address actually signs up and verifies - see that
    function's docstring.
    """

    apply_config_to_settings_cached()

    from .services.email_service import send_templated_email

    try:
        document = Document.objects.get(id=document_id)
    except Document.DoesNotExist:
        logger.error("send_share_invite_email_task: Document %s no longer exists", document_id)
        return

    signup_url = _absolute_url(f"/app/signup?invited_email={invited_email}")

    success, error = send_templated_email(
        to_email=invited_email,
        subject=f"{sharer_username} shared a document with you",
        template_base="document_share_invite",
        context={
            "site_name": _site_name(),
            "sharer_username": sharer_username,
            "document_title": document.title,
            "signup_url": signup_url,
        },
    )

    if not success:
        logger.error("send_share_invite_email_task: delivery failed for %s: %s", invited_email, error)


def send_account_deleted_email_task(email, username):
    """
    Sent directly via email_service (not notification_service) - by
    the time this runs the User row is already gone (Notification.
    recipient is a required FK, so there's nothing to attach an
    in-app notification to), same reasoning as
    send_share_invite_email_task for a not-yet-existing account.
    """

    apply_config_to_settings_cached()

    from .services.email_service import send_templated_email

    success, error = send_templated_email(
        to_email=email,
        subject="Your account has been deleted",
        template_base="account_deleted",
        context={"site_name": _site_name(), "username": username},
    )

    if not success:
        logger.error("send_account_deleted_email_task: delivery failed for %s: %s", email, error)


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

            # Only meaningful for the async path this task IS (see
            # module docstring) - a synchronous upload_document() call
            # already returns the finished document in the same
            # response, so notifying there would be redundant. The
            # user may well have navigated away by the time an async
            # embed finishes, which is exactly when this matters.
            from .services.notification_service import create_notification, document_open_url
            create_notification(
                recipient=document.user,
                notification_type="document.processing_completed",
                title="Document ready",
                message=f'"{document.title}" has finished processing and is ready to use.',
                data={"document_id": document.id},
                action_url=document_open_url(document.id),
            )

            return

        except Exception:
            if attempt >= MAX_PROCESSING_RETRIES:
                logger.exception(
                    "process_document_task: giving up on document %s after %s attempts",
                    document_id, attempt,
                )

                from .services.notification_service import create_notification
                create_notification(
                    recipient=document.user,
                    notification_type="document.processing_failed",
                    title="Document processing failed",
                    message=f'"{document.title}" could not be processed. Try re-uploading it.',
                    data={"document_id": document.id},
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
