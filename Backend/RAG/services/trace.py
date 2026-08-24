"""
Per-request trace ID.

Ask AI's pipeline (query processing -> retrieval -> LLM call -> citation
validation) spans several services, each already logging its own timing
via RAG.services.perf.timed_stage() / the RAG.perf logger. None of those
log lines are correlatable back to one specific request today - reading
"was this slow response caused by retrieval, the LLM provider, or
something else" means guessing from timestamps.

new_trace_id() + bind_trace_id() let RAG.views.ask_ai / ask_ai_stream
stamp one short id per request; settings.LOGGING's "verbose" formatter
(via TraceIdLogFilter) then includes it on every log line for the
duration of that request, with zero changes needed at any individual
logger.info()/logger.exception() call site.

A contextvars.ContextVar (not a global/threading.local) so it stays
correct if this process ever serves requests via async views or the
ThreadPoolExecutor fan-out in retrieval_service.py - each context gets
its own value rather than one shared mutable slot.
"""

import logging
import uuid
from contextlib import contextmanager
from contextvars import ContextVar

_trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")

# Holds the current request/run's stage list (or None when nothing is
# bound - e.g. a management command). bind_trace_id() sets this to a
# fresh list; record_stage() appends to it in place (never re-assigns),
# which is what makes it work correctly across
# retrieval_service.py's ThreadPoolExecutor fan-out: contextvars.copy_
# context() (see retrieval_service._run_timed's submission wrapper)
# copies the *binding*, not a deep copy of the list, so an append() from
# a worker thread lands in the exact same list object the main thread
# will read back via get_stages().
_stages_var: ContextVar[list] = ContextVar("stages", default=None)


def new_trace_id() -> str:
    """A short (8 hex char) id - enough to grep/correlate logs for one request, short enough to show a user as a support reference."""

    return uuid.uuid4().hex[:8]


def get_trace_id() -> str:
    """The current context's trace id, or "" if none is bound (e.g. a management command, a background task, a test)."""

    return _trace_id_var.get()


@contextmanager
def bind_trace_id(trace_id: str = None):
    """
    Binds `trace_id` (or a freshly generated one) for the duration of the
    wrapped block, and starts a fresh stage-recording list alongside it
    (see record_stage()/get_stages()) - one trace_id, one stage list, one
    scope. Returns the id so the caller can attach it to a response/
    result without a second lookup.
    """

    trace_id = trace_id or new_trace_id()
    id_token = _trace_id_var.set(trace_id)
    stages_token = _stages_var.set([])

    try:
        yield trace_id
    finally:
        _trace_id_var.reset(id_token)
        _stages_var.reset(stages_token)


def record_stage(name: str, duration_ms: float, **context):
    """
    Appends one stage entry to the current request/run's stage list, if
    one is bound (bind_trace_id() started it) - a no-op otherwise (e.g. a
    perf.timed_stage() call from a management command or a test with no
    bound trace). Called from perf.timed_stage() itself, not by
    individual call sites - every existing/future timed_stage() call
    gets recorded automatically with zero changes at the call site.
    """

    stages = _stages_var.get()

    if stages is not None:
        stages.append({"name": name, "duration_ms": duration_ms, **context})


def get_stages() -> list:
    """The current context's recorded stage list, or [] if none is bound."""

    return _stages_var.get() or []


class TraceIdLogFilter(logging.Filter):
    """Stamps every log record with the current context's trace id (or "-" when none is bound) - wired in settings.LOGGING so the "verbose" formatter can include %(trace_id)s."""

    def filter(self, record):
        record.trace_id = get_trace_id() or "-"
        return True
