import logging

from django.conf import settings

from ..models import (
    Document,
    DocumentChunk,
)

from .validation_service import validate_document
from .duplicate_service import check_duplicate
from .metadata_service import extract_metadata
from .document_processor import process_document
from .embedding_service import generate_embedding
from .vector_service import save_embedding
from .graph_service import build_graph_for_chunk

logger = logging.getLogger(__name__)


def upload_document(
    user,
    title,
    file,
):
    """
    Enterprise Upload Pipeline

    Steps
    -----
    1. Validate uploaded file
    2. Check duplicate document
    3. Extract metadata
    4. Save document
    5-9. Process document (see process_uploaded_document()) - run
         inline, or dispatched to a Celery worker (Sprint 10), per
         settings.ENABLE_ASYNC_PROCESSING.
    """

    # ==================================================
    # Step 1 : Validate File
    # ==================================================

    validate_document(file)

    # ==================================================
    # Step 2 : Duplicate Detection
    # ==================================================

    duplicate, file_hash = check_duplicate(
        user=user,
        file=file,
    )

    if duplicate:

        raise ValueError(
            "This document has already been uploaded."
        )

    # ==================================================
    # Step 3 : Metadata Extraction
    # ==================================================

    metadata = extract_metadata(
        file
    )

    # ==================================================
    # Step 4 : Save Document
    # ==================================================

    document = Document.objects.create(

        user=user,

        title=title,

        file=file,

        file_hash=file_hash,

        file_type=metadata["file_type"],

        file_size=metadata["file_size"],

    )

    # ==================================================
    # Steps 5-9 : Process Document
    # ==================================================
    # `document.chunk_count` stays at its default (0) until this
    # completes - documents_view already reads that as "Processing"
    # status, so dispatching this asynchronously needs no UI change:
    # the document simply shows "Processing" until the worker (or, if
    # ENABLE_ASYNC_PROCESSING is off, this same request) finishes it.

    if settings.ENABLE_ASYNC_PROCESSING:

        from ..tasks import process_document_task

        process_document_task.delay(document.id)

    else:

        process_uploaded_document(document)

    return document


def process_uploaded_document(document):
    """
    Steps 5-9 of the upload pipeline: extract/chunk, embed, and
    knowledge-graph-enrich `document`, then update its chunk count.

    Split out from upload_document() (Sprint 10) so the exact same
    processing logic runs whether it's called inline (the historical
    behavior, settings.ENABLE_ASYNC_PROCESSING off) or from
    RAG.tasks.process_document_task in a Celery worker (when it's on)
    - the caller decides *when* this runs, never *what* it does. Takes
    `document` (not a separate `user`) so a Celery task only needs to
    pass a document_id and re-fetch it - the graph-enrichment owner is
    always document.user.
    """

    user = document.user

    # ==================================================
    # Step 5 : Process Document
    # ==================================================

    chunks = process_document(
        document.file.path
    )

    # ==================================================
    # Step 6 & 7 :
    # Save Chunks + Generate Embeddings
    # ==================================================

    for index, chunk_text in enumerate(chunks):

        document_chunk = DocumentChunk.objects.create(

            document=document,

            content=chunk_text,

            chunk_number=index,

        )

        embedding = generate_embedding(
            chunk_text
        )

        save_embedding(

            chunk=document_chunk,

            embedding=embedding,

            model_name=settings.EMBEDDING_MODEL,

        )

        # ==================================================
        # Step 8 : Knowledge Graph Extraction
        # ==================================================
        # Best-effort: a failed extraction should never fail
        # the upload, since the document/chunks/embeddings it
        # would enrich are already saved.

        try:

            build_graph_for_chunk(
                document_chunk,
                user,
            )

        except Exception:

            logger.exception(
                "Graph enrichment failed for document %s chunk %s",
                document.id,
                document_chunk.chunk_number,
            )

    # ==================================================
    # Step 9 : Update Document Metadata
    # ==================================================

    document.chunk_count = len(chunks)

    document.save(
        update_fields=[
            "chunk_count",
        ]
    )

    return document