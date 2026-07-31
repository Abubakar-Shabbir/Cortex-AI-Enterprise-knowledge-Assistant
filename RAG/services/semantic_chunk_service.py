from langchain_experimental.text_splitter import (
    SemanticChunker
)

from langchain_community.embeddings import (
    HuggingFaceEmbeddings
)

from django.conf import settings


embedding_model = HuggingFaceEmbeddings(
    model_name=settings.EMBEDDING_MODEL
)


semantic_splitter = SemanticChunker(
    embeddings=embedding_model,
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