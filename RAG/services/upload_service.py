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
    Upload Pipeline

    Steps
    -----
    1. Validate uploaded file
    2. Check duplicate document
    3. Extract metadata
    4. Save document (processing_status=PENDING)

    Deliberately stops there - upload only saves the file and creates
    the Document row, so the request returns fast regardless of file
    size. Steps 5-9 (extract/chunk/embed/graph-enrich, see
    process_uploaded_document()) only run when the user clicks Embed
    on that document (documents_view.document_embed), not
    automatically here. That view is what checks
    settings.ENABLE_ASYNC_PROCESSING to decide whether to dispatch to
    a Celery worker or run inline.
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

    return document


def process_uploaded_document(document):
    """
    Steps 5-9 of the upload pipeline: extract/chunk, embed, and
    knowledge-graph-enrich `document`, then update its chunk count.

    Split out from upload_document() (Sprint 10) so the exact same
    processing logic runs whether it's called inline (settings.
    ENABLE_ASYNC_PROCESSING off) or from RAG.tasks.process_document_task
    in a Celery worker (when it's on) - the caller decides *when* this
    runs, never *what* it does. Takes `document` (not a separate
    `user`) so a Celery task only needs to pass a document_id and
    re-fetch it - the graph-enrichment owner is always document.user.

    Nothing calls this automatically at upload time anymore (see
    upload_document() below) - it only runs when a user clicks Embed
    on a still-PENDING document (documents_view.document_embed), or
    when that dispatches it to a Celery worker.

    document.chunk_count is written right after chunking, not at the
    very end - so a document_status poll during the embed loop can
    compute a real percentage (embedded chunks / chunk_count) instead
    of only learning the total once everything is already done.
    """

    user = document.user

    document.processing_status = Document.ProcessingStatus.PROCESSING
    document.save(update_fields=["processing_status"])

    try:

        # ==================================================
        # Step 5 : Process Document
        # ==================================================

        chunks = process_document(
            document.file.path
        )

        document.chunk_count = len(chunks)

        document.save(update_fields=["chunk_count"])

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

    except Exception:

        document.processing_status = Document.ProcessingStatus.FAILED
        document.save(update_fields=["processing_status"])

        logger.exception("Processing failed for document %s", document.id)

        raise

    # ==================================================
    # Step 9 : Update Document Metadata
    # ==================================================

    document.processing_status = Document.ProcessingStatus.COMPLETED

    document.save(
        update_fields=[
            "processing_status",
        ]
    )

    return document