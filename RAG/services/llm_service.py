import google.generativeai as genai
from django.conf import settings


# Configure Gemini API
genai.configure(
    api_key=settings.GEMINI_API_KEY
)


def generate_answer(context, question):

    try:

        # Initialize Gemini model
        model = genai.GenerativeModel(
            "gemini-2.0-flash"
        )


        prompt = f"""
You are a helpful AI assistant.

Your task is to answer the user's question
ONLY using the provided context.

Rules:
1. Do not use your own knowledge.
2. If the answer is not available in the context,
   reply exactly:

"I couldn't find the answer in the uploaded document."

3. Keep the answer clear and concise.


Context:
----------------
{context}
----------------


Question:
{question}


Answer:
"""


        # Generate response
        response = model.generate_content(
            prompt
        )


        # Check response
        if response.text:

            return response.text


        else:

            return (
                "I couldn't find the answer "
                "in the uploaded document."
            )


    except Exception as e:
        import traceback
        traceback.print_exc()

        return f"Gemini Error: {e}"