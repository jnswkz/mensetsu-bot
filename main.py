# from openai import OpenAI
from fastapi import FastAPI
import uvicorn
import dotenv

# services
from services.bot.response import get_response

dotenv.load_dotenv()

OAI_API_KEY = dotenv.get_key(".env", "OAI_API_KEY")

app = FastAPI()

@app.get("/")
def read_root():
    return {"Hello": "World"}

@app.get("/response")
def get_bot_response(prompt: str):
    response = get_response(OAI_API_KEY, prompt)
    return {"response": response}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

