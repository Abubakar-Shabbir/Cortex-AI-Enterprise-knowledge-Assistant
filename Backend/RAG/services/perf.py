"""
Performance instrumentation.

One small, reusable timer every stage of the RAG pipeline (retrieval,
context assembly, LLM calls, the request as a whole) wraps itself in,
so "where did the time go" is answerable by reading logs instead of
writing a one-off profiling script. Everything logs to the dedicated
"RAG.perf" logger at INFO, prefixed "[PERF]" so it's easy to grep/
filter out of the rest of the app's logs.

Usage
-----
    with timed_stage("vector search", top_k=5):
        results = vector_search(question, top_k=5, user=user)

    with timed_stage("retrieve_chunks TOTAL", vector="42ms", bm25="30ms"):
        ...
"""

import logging
import time
from contextlib import contextmanager

from .trace import record_stage

logger = logging.getLogger("RAG.perf")


@contextmanager
def timed_stage(label: str, **context):
    """
    Times the wrapped block and logs it on exit - including on
    exception, so a stage that fails still reports how long it ran
    before failing, rather than silently vanishing from the timing
    picture. Also records the same (label, duration, context) into the
    current request/run's trace (RAG.services.trace.record_stage()), if
    one is bound - every existing and future call site gets a queryable
    stage entry for free, with no call-site changes.
    """

    start = time.perf_counter()

    try:
        yield
    finally:
        elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
        extra = " ".join(f"{key}={value}" for key, value in context.items())
        logger.info("[PERF] %-28s %8.1fms %s", label, elapsed_ms, extra)
        record_stage(label, elapsed_ms, **context)


class Timer:
    """
    Non-context-manager alternative for a stage whose duration needs
    to be captured as a value (e.g. folded into a later summary line)
    rather than logged immediately on its own. Call .stop() once.
    """

    def __init__(self):
        self._start = time.perf_counter()

    def stop(self) -> float:
        """Returns elapsed milliseconds, rounded to 1 decimal place."""

        return round((time.perf_counter() - self._start) * 1000, 1)
