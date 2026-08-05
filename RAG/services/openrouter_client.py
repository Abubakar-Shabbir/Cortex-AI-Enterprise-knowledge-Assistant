import requests

class OpenRouterClient:

    def generate(self, prompt):

        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization":
                f"Bearer {settings.OPENROUTER_API_KEY}"
            },
            json={
                "model": settings.OPENROUTER_MODEL,
                "messages":[
                    {
                        "role":"user",
                        "content":prompt
                    }
                ]
            }
        )

        return response.json()["choices"][0]["message"]["content"]