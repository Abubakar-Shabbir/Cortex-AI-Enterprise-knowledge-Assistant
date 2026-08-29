import logging

from django.conf import settings

from ..models import (
    Document,
    DocumentChunk,
    DocumentVersion,
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
    the background thread pool or run inline.
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


def upload_new_version(document, file):
    """
    Replaces `document`'s active file with `file`, snapshotting the
    outgoing file into a new DocumentVersion row first (history only -
    there's no "restore as current" action, so this table only ever
    grows). Re-processing (chunk/embed/graph-enrich) is the caller's
    responsibility, same split as upload_document()/
    process_uploaded_document() above - documents_view's
    document_version_upload calls this then triggers processing
    exactly like document_embed does for a fresh upload.

    Deliberately does not re-check ownership - the view is responsible
    for that (get_object_or_404(..., user=request.user)), the same
    pattern every other mutating document view already uses.
    """

    validate_document(file)

    duplicate, file_hash = check_duplicate(user=document.user, file=file)

    if duplicate:
        raise ValueError("This file is identical to one you've already uploaded.")

    metadata = extract_metadata(file)

    DocumentVersion.objects.create(
        document=document,
        version_number=document.version_number,
        file=document.file,
        file_hash=document.file_hash,
        file_size=document.file_size,
        file_type=document.file_type,
    )

    # Existing chunks/embeddings/graph mentions describe the OUTGOING
    # file - delete them so re-processing below rebuilds retrieval data
    # from scratch instead of leaving stale rows that would duplicate
    # search results. Cascades ChunkEmbedding (OneToOne) and
    # EntityMention (FK to chunk) automatically.
    document.chunks.all().delete()

    document.file = file
    document.file_hash = file_hash
    document.file_type = metadata["file_type"]
    document.file_size = metadata["file_size"]
    document.version_number += 1
    document.processing_status = Document.ProcessingStatus.PENDING
    document.chunk_count = 0

    document.save(update_fields=[
        "file", "file_hash", "file_type", "file_size", "version_number",
        "processing_status", "chunk_count",
    ])

    return document


def process_uploaded_document(document):
    """
    Steps 5-9 of the upload pipeline: extract/chunk, embed, and
    knowledge-graph-enrich `document`, then update its chunk count.

    Split out from upload_document() (Sprint 10) so the exact same
    processing logic runs whether it's called inline (settings.
    ENABLE_ASYNC_PROCESSING off) or from RAG.tasks.process_document_task
    on the background thread pool (when it's on) - the caller decides
    *when* this runs, never *what* it does. Takes `document` (not a
    separate `user`) so a background task only needs to pass a
    document_id and re-fetch it - the graph-enrichment owner is always
    document.user.

    Nothing calls this automatically at upload time anymore (see
    upload_document() below) - it only runs when a user clicks Embed
    on a still-PENDING document (documents_view.document_embed), or
    when that dispatches it to the background thread pool.

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