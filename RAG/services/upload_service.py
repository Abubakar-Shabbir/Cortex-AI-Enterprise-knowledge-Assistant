from django.conf import settings

from ..models import (
    Document,
    DocumentChunk,
)

from .document_processor import process_document
from .embedding_service import generate_embedding
from .vector_service import save_embedding


def upload_document(
    user,
    title,
    file,
):
    """
    Upload a document and process it.

    Steps:
    1. Save document
    2. Extract and chunk text
    3. Save chunks
    4. Generate embeddings
    5. Save embeddings in PostgreSQL (pgvector)
    """

    # -------------------------
    # Save Document
    # -------------------------

    document = Document.objects.create(
        user=user,
        title=title,
        file=file,
    )

    # -------------------------
    # Process Document
    # -------------------------

    chunks = process_document(
        document.file.path
    )

    # -------------------------
    # Save Chunks + Embeddings
    # -------------------------

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

    return document