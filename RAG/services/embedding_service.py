from langchain_core.embeddings import Embeddings
from sentence_transformers import SentenceTransformer
from django.conf import settings

from .perf import timed_stage

# Load Model Once
model = SentenceTransformer(
    settings.EMBEDDING_MODEL
)


def generate_embedding(text):
    """
    Generate multilingual embedding using BGE-M3.
    """

    with timed_stage("embedding generation", chars=len(text or "")):
        embedding = model.encode(
            text,
            normalize_embeddings=True
        )

    return embedding


class SharedSentenceTransformerEmbeddings(Embeddings):
    """
    Thin langchain_core.embeddings.Embeddings adapter around the one
    SentenceTransformer instance loaded above, so any LangChain
    component that needs an `Embeddings` object (e.g.
    semantic_chunk_service.py's SemanticChunker) reuses it instead of
    loading a second copy of the same model under a different library.
    """

    def embed_documents(self, texts):
        return model.encode(texts, normalize_embeddings=True).tolist()

    def embed_query(self, text):
        return model.encode(text, normalize_embeddings=True).tolist()


shared_embeddings = SharedSentenceTransformerEmbeddings()