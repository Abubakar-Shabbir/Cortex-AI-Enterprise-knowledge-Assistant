"""
Celery tasks (Sprint 10).

Currently one task: the async counterpart to
upload_service.upload_document()'s inline processing path. See
myproject/celery.py for how this module is discovered, and
settings.ENABLE_ASYNC_PROCESSING for the flag that decides whether
upload_document() dispatches here at all.
"""

import logging

from celery import shared_task

from .models import Document
from .services.upload_service import process_uploaded_document

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def process_document_task(self, document_id):
    """
    Run steps 5-9 of the upload pipeline (extract/chunk, embed,
    graph-enrich, update chunk_count) for `document_id` in a Celery
    worker, instead of the request/response cycle.

    Retries up to 3 times, 30s apart, on unexpected failure (e.g. a
    transient DB hiccup) - but not when the Document itself is gone
    (deleted before the task ran), which is logged and treated as a
    no-op rather than retried.
    """

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
