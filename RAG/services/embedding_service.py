from sentence_transformers import SentenceTransformer


model = SentenceTransformer(
    "all-MiniLM-L6-v2"
)



def generate_embedding(text):

    embedding = model.encode(
        text
    )

    return embedding