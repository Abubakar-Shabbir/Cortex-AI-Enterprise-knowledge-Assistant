import faiss
import numpy as np

from .embedding_service import generate_embedding



VECTOR_PATH="vector_db/index.faiss"



def search_vectors(question,texts):


    index = faiss.read_index(
        VECTOR_PATH
    )


    query_embedding = generate_embedding(
        question
    )


    query_embedding = np.array(
        [query_embedding]
    ).astype("float32")



    distances, indexes = index.search(
        query_embedding,
        3
    )


    results=[]


    for i in indexes[0]:

        results.append(
            texts[i]
        )


    return results