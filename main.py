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

#@app.get("/start_interview")
#def start_interview():
#    TODO: Read candidate profile and generate greeting message
#    return {"message": "Welcome to the interview!"}

#@app.get("/start_questions")
#def start_questions():
#   TODO: Generate 3 questions with question bank
#    return {"questions": ["Question 1", "Question 2", "Question 3"]}

#@app.get("/cv_based_questions")
#def cv_based_questions():
#    TODO: Generate question based on candidate's CV
#    return {"question": "Based on your CV, can you tell us about your experience with X?"}

#@app.get("/follow_up_questions")
#def follow_up_questions(answer: str, ended: bool):
#    TODO: Generate follow-up questions based on candidate's answers (Handling end of interview and 0 answer cases)
#    return {"question": "Can you elaborate on that?"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

