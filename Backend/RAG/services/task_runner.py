"""
In-process background task execution (replaces Celery, free-tier refactor).

Celery + a separate worker process required a second always-on process
alongside the web server - a hard requirement most free-tier hosts (Render
free, Railway, Fly.io free allowance, PythonAnywhere) don't offer. This
module replaces that with a `concurrent.futures.ThreadPoolExecutor` living
inside the same process as the web server: `submit()` hands a callable to a
pool thread instead of a Celery broker, `cancel()` replaces
`AsyncResult.revoke()`, and `get_status()` replaces the Celery
`inspect().ping()` worker check.

Unlike a Celery worker, there is no "is it running" question here - the
pool is created lazily on first use and lives for the lifetime of this
process, so `get_status()["available"]` is always True once this module has
been imported successfully. This is what lets RAG.tasks.run_ai_task drop
its old "no inline fallback, a Celery worker must be running" caveat
entirely - the pool is always there.

Each pool thread is reused across submissions (this is the whole point of
a thread *pool*), so - unlike a fresh Celery worker process per task - a
stale/broken DB connection left open by a previous task must be dropped
explicitly at the start and end of every task, the same way Django's own
request_started/request_finished signals do for the request/response
cycle.
"""

import logging
import threading
from concurrent.futures import Future, ThreadPoolExecutor

from django.conf import settings
from django.db import close_old_connections

logger = logging.getLogger(__name__)

_executor = None
_executor_lock = threading.Lock()

_futures: dict = {}
_futures_lock = threading.Lock()

_active_count = 0
_active_lock = threading.Lock()


def _get_executor() -> ThreadPoolExecutor:
    global _executor

    if _executor is None:
        with _executor_lock:
            if _executor is None:
                _executor = ThreadPoolExecutor(
                    max_workers=settings.BACKGROUND_WORKER_THREADS,
                    thread_name_prefix="rag-bg",
                )

    return _executor


def _run(func, args, kwargs):
    global _active_count

    close_old_connections()

    with _active_lock:
        _active_count += 1

    try:
        func(*args, **kwargs)

    except Exception:
        # A pool thread's exception has nowhere else to go - nothing
        # downstream calls future.result(), so it would otherwise vanish
        # silently. Log it explicitly instead, same never-lose-an-error
        # contract as the rest of RAG/services/*.py.
        logger.exception("Background task %r failed", getattr(func, "__name__", func))

    finally:
        close_old_connections()

        with _active_lock:
            _active_count -= 1


def submit(func, *args, key=None, **kwargs) -> Future:
    """
    Runs `func(*args, **kwargs)` on the background thread pool.

    `key` (e.g. an AITaskRun id) registers the resulting Future so a later
    cancel(key) can best-effort stop it before it starts - pass the same
    key value cancel() will be called with.
    """

    executor = _get_executor()
    future = executor.submit(_run, func, args, kwargs)

    if key is not None:
        with _futures_lock:
            _futures[key] = future

        future.add_done_callback(lambda f, k=key: _futures.pop(k, None))

    return future


def cancel(key) -> bool:
    """
    Best-effort cancel of a still-queued (not yet started) task submitted
    with the same `key`. Once a task has actually started running,
    Future.cancel() can't interrupt it - same real-world limitation the old
    Celery revoke(terminate=True) had without a prefork worker pool. Never
    raises; returns False if there's nothing to cancel or it already
    started.
    """

    with _futures_lock:
        future = _futures.get(key)

    if future is None:
        return False

    try:
        return future.cancel()

    except Exception:
        logger.exception("task_runner.cancel: unexpected error cancelling %r", key)
        return False


def get_status() -> dict:
    """
    {"available": True, "max_workers": N, "active": <running>, "pending": <queued>}.

    `available` is always True once this module is importable - the pool
    lives in this same process, so unlike a separate Celery worker there's
    no reachability question. Never raises.
    """

    try:
        executor = _get_executor()

        with _active_lock:
            active = _active_count

        try:
            pending = executor._work_queue.qsize()
        except Exception:
            pending = 0

        return {
            "available": True,
            "max_workers": settings.BACKGROUND_WORKER_THREADS,
            "active": active,
            "pending": pending,
        }

    except Exception:
        logger.warning("task_runner.get_status: unavailable", exc_info=True)
        return {"available": False, "max_workers": None, "active": None, "pending": None}
