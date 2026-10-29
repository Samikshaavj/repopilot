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