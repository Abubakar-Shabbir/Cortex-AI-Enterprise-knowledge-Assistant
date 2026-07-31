from django.conf import settings
from django.db.models import F
from pgvector.django import L2Distance

from ..models import ChunkEmbedding
from .embedding_service import generate_embedding
from .bm25_service import bm25_search


def vector_search(question):
    """
    Semantic Vector Search
    """

    query_embedding = generate_embedding(question)

    similar_chunks = (

        ChunkEmbedding.objects

        .annotate(

            distance=L2Distance(
                "embedding",
                query_embedding
            )

        )

        .order_by("distance")[:settings.TOP_K]

    )

    results = []

    for item in similar_chunks:

        results.append(

            {

                "content": item.chunk.content,

                "document": item.chunk.document.title,

                "chunk_number": item.chunk.chunk_number,

                "score": round(item.distance, 4),

                "search_type": "vector",

            }

        )

    return results


def retrieve_chunks(question):
    """
    Hybrid Retrieval
    Vector Search + BM25
    """

    vector_results = vector_search(question)

    bm25_results = bm25_search(

        question,

        settings.TOP_K

    )

    merged = {}

    for item in vector_results + bm25_results:

        key = (

            item["document"],

            item["chunk_number"]

        )

        if key not in merged:

            merged[key] = item

    return list(

        merged.values()

    )[:settings.TOP_K]