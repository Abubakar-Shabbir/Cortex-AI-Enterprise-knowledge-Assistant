from transformers import pipeline



# Load Model

generator = pipeline(
    "text-generation",
    model="google/flan-t5-base"
)



def generate_answer(question, context):


    prompt = f"""

You are an AI assistant.

Answer the question using only the given context.

Context:
{context}


Question:
{question}


Answer:

"""


    response = generator(
        prompt,
        max_length=200
    )


    return response[0]["generated_text"]