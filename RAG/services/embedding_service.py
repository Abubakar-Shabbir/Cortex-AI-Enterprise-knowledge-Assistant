from sentence_transformers import SentenceTransformer
from django.conf import settings

# Load Model Once
model = SentenceTransformer(
    settings.EMBEDDING_MODEL
)


def generate_embedding(text):
    """
    Generate multilingual embedding using BGE-M3.
    """

    embedding = model.encode(
        text,
        normalize_embeddings=True
    )

    return embedding