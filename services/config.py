import dotenv

dotenv.load_dotenv()

OAI_API_KEY = dotenv.get_key(".env", "OAI_API_KEY")
MONGODB_URI = dotenv.get_key(".env", "MONGODB_URI")

EMBED_MODEL = "text-embedding-3-small"
GEN_MODEL = "openai/gpt-5.4-mini"
EMBED_DIMS = 1536
QUESTION_BANK_VECTOR_INDEX = "question_bank_vector_idx_v2"
