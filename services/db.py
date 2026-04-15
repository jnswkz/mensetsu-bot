from pymongo import MongoClient

from services.config import MONGODB_URI

client = MongoClient(MONGODB_URI)
db = client["SEeds"]

question_bank = db["question_banking"]
generated_questions = db["generated_questions"]
candidate_profiles = db["candidate_profiles"]
