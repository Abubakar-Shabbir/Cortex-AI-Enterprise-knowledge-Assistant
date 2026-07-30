import faiss
import pickle
import os
import numpy as np

from .embedding_service import generate_embedding

VECTOR_PATH = "vector_db"

INDEX_PATH = os.path.join(
    VECTOR_PATH,
    "index.faiss"
)

CHUNKS_PATH = os.path.join(
    VECTOR_PATH,
    "chunks.pkl"
)


def retrieve_chunks(question, top_k=3):

    # Load FAISS Index
    index = faiss.read_index(
        INDEX_PATH
    )

    # Load Stored Chunks
    with open(
        CHUNKS_PATH,
        "rb"
    ) as f:

        chunks = pickle.load(f)

    # Generate Question Embedding
    embedding = generate_embedding(
        question
    )

    embedding = np.array(
        [embedding],
        dtype=np.float32
    )

    # Search Similar Chunks
    distances, indices = index.search(
        embedding,
        top_k
    )

    results = []

    for idx in indices[0]:

        if idx != -1:

            results.append(
                chunks[idx]
            )

    return results