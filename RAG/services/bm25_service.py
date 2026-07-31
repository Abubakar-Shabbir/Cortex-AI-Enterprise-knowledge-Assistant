from rank_bm25 import BM25Okapi

from ..models import DocumentChunk


def bm25_search(
    question,
    top_k,
):
    """
    Perform BM25 keyword search
    on all document chunks.
    """

    # -------------------------
    # Load All Chunks
    # -------------------------

    chunks = list(

        DocumentChunk.objects.select_related(
            "document"
        )

    )

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