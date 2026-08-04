from rank_bm25 import BM25Okapi

from ..models import DocumentChunk
from .retrieval_filters import apply_document_filters


def bm25_search(
    question,
    top_k,
    filters=None,
):
    """
    Perform BM25 keyword search
    on all document chunks.
    """

    # -------------------------
    # Load All Chunks
    # -------------------------

    chunks_queryset = DocumentChunk.objects.select_related(
        "document"
    )

    chunks_queryset = apply_document_filters(
        chunks_queryset, filters, document_field="document"
    )

    chunks = list(chunks_queryset)

    if not chunks:

        return []

    # -------------------------
    # Tokenize Documents
    # -------------------------

    corpus = [

        chunk.content.lower().split()

        for chunk in chunks

    ]

    # -------------------------
    # Build BM25 Index
    # -------------------------

    bm25 = BM25Okapi(
        corpus
    )

    # -------------------------
    # Tokenize Query
    # -------------------------

    query = question.lower().split()

    # -------------------------
    # Calculate Scores
    # -------------------------

    scores = bm25.get_scores(
        query
    )

    # -------------------------
    # Sort Results
    # -------------------------

    ranked = sorted(

        zip(chunks, scores),

        key=lambda x: x[1],

        reverse=True

    )

    # -------------------------
    # Build Response
    # -------------------------

    results = []

    for chunk, score in ranked[:top_k]:

        results.append(

            {

                "content": chunk.content,

                "document": chunk.document.title,

                "chunk_number": chunk.chunk_number,

                "score": round(float(score), 4),

                "search_type": "bm25",

            }

        )

    return results