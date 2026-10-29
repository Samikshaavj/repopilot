from openai import OpenAI

from app.config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL


def get_client() -> OpenAI:
    """A client for whichever provider is set in .env."""
    if not (LLM_API_KEY and LLM_BASE_URL and LLM_MODEL):
        raise RuntimeError("Set LLM_API_KEY, LLM_BASE_URL and LLM_MODEL in backend/.env")
    return OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)