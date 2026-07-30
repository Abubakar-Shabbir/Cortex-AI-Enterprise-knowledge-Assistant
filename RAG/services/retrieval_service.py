from django.conf import settings
from django.db.models import F
from pgvector.django import L2Distance

from ..models import ChunkEmbedding
from .embedding_service import generate_embedding


def retrieve_chunks(question):
    """
    Retrieve the most relevant chunks
    using PostgreSQL + pgvector.
    """

    # -------------------------
    # Generate Question Embedding
    # -------------------------

    query_embedding = generate_embedding(
        question
    )

    # -------------------------
    # Vector Search
    # -------------------------

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

    # -------------------------
    # Build Results
    # -------------------------

    results = []

    for item in similar_chunks:

        results.append(

            {

                "content": item.chunk.content,

                "document": item.chunk.document.title,

                "chunk_number": item.chunk.chunk_number,

                "distance": round(item.distance, 4)

            }

        )

    return results