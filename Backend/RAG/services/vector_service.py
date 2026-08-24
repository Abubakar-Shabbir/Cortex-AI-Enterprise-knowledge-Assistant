from ..models import ChunkEmbedding


def save_embedding(
    chunk,
    embedding,
    model_name,
):
    """
    Save embedding into PostgreSQL.
    """

    ChunkEmbedding.objects.update_or_create(
        chunk=chunk,
        defaults={
            "embedding": embedding.tolist(),
            "embedding_model": model_name,
        },
    )