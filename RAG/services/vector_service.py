import faiss
import os
import pickle
import numpy as np

VECTOR_PATH = "vector_db"


def save_vectors(embeddings, texts):

    os.makedirs(
        VECTOR_PATH,
        exist_ok=True
    )

    # Convert list to numpy array
    embeddings = np.array(
        embeddings,
        dtype=np.float32
    )

    # Create FAISS index
    dimension = embeddings.shape[1]

    index = faiss.IndexFlatL2(
        dimension
    )

    # Add embeddings
    index.add(
        embeddings
    )

    # Save FAISS index
    faiss.write_index(
        index,
        os.path.join(
            VECTOR_PATH,
            "index.faiss"
        )
    )

    # Save chunk texts
    with open(
        os.path.join(
            VECTOR_PATH,
            "chunks.pkl"
        ),
        "wb"
    ) as f:

        pickle.dump(
            texts,
            f
        )

    print("Vectors and chunks saved successfully")