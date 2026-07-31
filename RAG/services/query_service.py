from .llm_service import generate_answer
from .retrieval_service import retrieve_chunks


def answer_question(question):
    """
    Answer the user's question using
    PostgreSQL + pgvector retrieval.
    """

    # -------------------------
    # Retrieve Relevant Chunks
    # -------------------------

    retrieved_chunks = retrieve_chunks(
        question
    )

    # -------------------------
    # Build Context
    # -------------------------

    context = "\n\n".join(

        chunk["content"]

        for chunk in retrieved_chunks

    )

    # -------------------------
    # Generate LLM Answer
    # -------------------------

    answer = generate_answer(

        context,

        question

    )

    # -------------------------
    # Return Response
    # -------------------------

    return {

        "question": question,

        "answer": answer,

        "sources": retrieved_chunks

    }