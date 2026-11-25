"""Groq cloud models (https://console.groq.com). Groq's API is OpenAI-compatible."""
import os

import httpx
from dotenv import load_dotenv

from src.ai_errors import AIError, provider_status

load_dotenv()

# From https://console.groq.com/keys. Only needed to chat with Groq models.
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_DEFAULT_MODEL = os.getenv("GROQ_DEFAULT_MODEL", "openai/gpt-oss-120b")

# Shown only when Groq's model list cannot be fetched.
GROQ_MODELS = [
    {"id": "openai/gpt-oss-120b", "name": "openai/gpt-oss-120b"},
    {"id": "openai/gpt-oss-20b", "name": "openai/gpt-oss-20b"},
    {"id": "qwen/qwen3.8-27b", "name": "qwen/qwen3.8-27b"},
]

# Not chat models: speech-to-text, text-to-speech and safety classifiers.
_NOT_CHAT = ("whisper", "tts", "guard", "prompt-guard", "orpheus")


def _headers() -> dict:
    return {"Authorization": f"Bearer {GROQ_API_KEY}"}


def _error_detail(response: httpx.Response) -> str:
    try:
        return response.json()["error"]["message"]
    except Exception:
        return response.text[:300] or response.reason_phrase


async def ask_groq(messages: list[dict], model: str = GROQ_DEFAULT_MODEL) -> str:
    if not GROQ_API_KEY:
        raise AIError(503, "Set GROQ_API_KEY in .env to chat with Groq models.")
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{GROQ_BASE_URL}/chat/completions",
                headers=_headers(),
                json={"model": model, "messages": messages},
            )
    except httpx.HTTPError as e:
        raise AIError(503, "Groq is temporarily unavailable.") from e
    if response.status_code != 200:
        raise AIError(provider_status(response.status_code), f"Groq: {_error_detail(response)}")
    return response.json()["choices"][0]["message"]["content"] or ""


async def list_groq_models() -> list[dict]:
    """The chat models Groq offers right now. Falls back to GROQ_MODELS if it cannot be reached."""
    if not GROQ_API_KEY:
        return GROQ_MODELS
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(f"{GROQ_BASE_URL}/models", headers=_headers())
        response.raise_for_status()
        models = response.json()["data"]
    except Exception:
        return GROQ_MODELS
    return sorted(
        (
            {"id": m["id"], "name": m["id"]}
            for m in models
            if m.get("active", True) and not any(word in m["id"] for word in _NOT_CHAT)
        ),
        key=lambda m: m["id"],
    )
