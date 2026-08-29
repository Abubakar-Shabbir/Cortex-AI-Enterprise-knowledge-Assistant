from langchain_experimental.text_splitter import (
    SemanticChunker
)

from .embedding_service import shared_embeddings


# Reuses the single SentenceTransformer already loaded in
# embedding_service.py (via the shared_embeddings adapter) instead of
# loading a second, independent embedding model here - see
# embedding_service.SharedSentenceTransformerEmbeddings.
semantic_splitter = SemanticChunker(
    embeddings=shared_embeddings,
    breakpoint_threshold_type="percentile"
)


def semantic_chunk(text):
    """
    Split document into semantic chunks
    using embedding similarity.
    """

    chunks = semantic_splitter.create_documents(
        [text]
    )

    return [
        chunk.page_content
        for chunk in chunks
    ]