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
    5. Process document
    6. Save document chunks
    7. Generate embeddings
    8. Store embeddings in PostgreSQL (pgvector)
    9. Update document metadata
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
    # Step 8 : Update Document Metadata
    # ==================================================

    document.chunk_count = len(chunks)

    document.save(
        update_fields=[
            "chunk_count",
        ]
    )

    # ==================================================
    # Step 9 : Return Document
    # ==================================================

    return document