import os

from dotenv import load_dotenv

# Reads backend/.env and puts its values into environment variables
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set. Add it to backend/.env")

# Any OpenAI-compatible provider works here (Groq, Gemini, OpenRouter, Ollama...)
LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_BASE_URL = os.getenv("LLM_BASE_URL")
LLM_MODEL = os.getenv("LLM_MODEL")


def _number(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


# --- Settings for a public demo. Each can be overridden with an environment variable. ---
DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() in ("1", "true", "yes")
QUESTIONS_PER_IP_PER_HOUR = _number("QUESTIONS_PER_IP_PER_HOUR", 3)
QUESTIONS_PER_DAY = _number("QUESTIONS_PER_DAY", 10)
MAX_CONCURRENT_QUESTIONS = _number("MAX_CONCURRENT_QUESTIONS", 2)
MAX_REPO_KB = _number("MAX_REPO_KB", 30000)
MAX_SYMBOLS = _number("MAX_SYMBOLS", 4000)
IP_HASH_SALT = os.getenv("IP_HASH_SALT", "dev-only-salt")
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if origin.strip()
]