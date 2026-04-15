import litellm
from fastapi.responses  import StreamingResponse

def get_response(OAI_API_KEY: str, prompt: str) -> str:
    try:
        response = litellm.completion(
            model="openai/gpt-5.4-mini",
            messages=[
                {"role": "user", "content": prompt}
            ],
            api_key=OAI_API_KEY
        )
    except litellm.AuthenticationError as e:
        print(f"Bad API key: {e}")
    except litellm.RateLimitError as e:
        print(f"Rate limited: {e}")
    except litellm.APIError as e:
        print(f"API error: {e}")
    return response.choices[0].message.content