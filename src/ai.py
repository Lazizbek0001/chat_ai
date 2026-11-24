"""Picks the AI provider for a chat request: Ollama Cloud or Groq."""
import asyncio
import os

from src.ai_errors import AIError
from src.ai_groq import GROQ_API_KEY, GROQ_DEFAULT_MODEL, ask_groq, list_groq_models
from src.ai_ollama import OLLAMA_API_KEY, ask_ai_cloud, list_cloud_models
from src.ai_ollama import DEFAULT_MODEL as OLLAMA_DEFAULT_MODEL

PROVIDERS = ("ollama", "groq")

# Used when a request names no provider. Defaults to whichever provider has a key, Groq first.
DEFAULT_PROVIDER = os.getenv("DEFAULT_AI_PROVIDER") or ("groq" if GROQ_API_KEY else "ollama")


async def ask_ai(messages: list[dict], provider: str | None = None, model: str | None = None) -> tuple[str, str, str]:
    """Returns (reply, provider, model) so the caller can report what answered."""
    provider = provider or DEFAULT_PROVIDER
    if provider == "groq":
        model = model or GROQ_DEFAULT_MODEL
        return await ask_groq(messages, model=model), provider, model
    if provider == "ollama":
        model = model or OLLAMA_DEFAULT_MODEL
        return await ask_ai_cloud(messages, model=model), provider, model
    raise AIError(400, f"Unknown provider {provider!r}. Use one of: {', '.join(PROVIDERS)}.")


async def list_models() -> list[dict]:
    """Every provider's models, each tagged with its provider and whether its key is set."""
    ollama, groq = await asyncio.gather(list_cloud_models(), list_groq_models())
    return [
        {**m, "provider": "groq", "available": bool(GROQ_API_KEY)} for m in groq
    ] + [
        {**m, "provider": "ollama", "available": bool(OLLAMA_API_KEY)} for m in ollama
    ]
