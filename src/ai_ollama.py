import os
from ollama import Client, ResponseError

from src.ai_errors import AIError, provider_status
from dotenv import load_dotenv
import asyncio
load_dotenv()

# Shown only when the cloud model list cannot be fetched. The live list comes from
# list_cloud_models(): Ollama retires cloud models, so a hard-coded list goes stale.
MODELS = [
    {"id": "gemma4:31b", "name": "gemma4:31b"},
]

DEFAULT_MODEL = os.getenv("OLLAMA_DEFAULT_MODEL", "gemma4:31b")

# Only chatting needs this key. The app (login, users, chat list) starts without it.
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY")

client = Client(
    host="https://ollama.com",
    headers={"Authorization": f"Bearer {OLLAMA_API_KEY}"} if OLLAMA_API_KEY else None,
)

def _cloud_model_name(model: str) -> str:
    # "-cloud" / ":cloud" suffixes are only for a local Ollama that forwards to the cloud.
    # https://ollama.com takes the plain name.
    return model.removesuffix("-cloud").removesuffix(":cloud")


async def ask_ai_cloud(messages, model=DEFAULT_MODEL):
    if not OLLAMA_API_KEY:
        raise AIError(503, "Set OLLAMA_API_KEY in .env to chat with the AI.")
    try:
        response = await asyncio.to_thread(
            client.chat,
            model=_cloud_model_name(model),
            messages=messages,
        )
    except ResponseError as e:
        # 401 bad key, 402/403 no credits, 404 unknown model, 410 retired model, 429 rate limit.
        raise AIError(provider_status(e.status_code), f"Ollama Cloud: {e.error}") from e
    except Exception as e:
        raise AIError(503, "AI service is temporarily unavailable.") from e
    return response["message"]["content"]


async def list_cloud_models() -> list[dict]:
    """The models Ollama Cloud offers right now. Falls back to MODELS if it cannot be reached."""
    try:
        result = await asyncio.to_thread(client.list)
    except Exception:
        return MODELS
    return [{"id": m.model, "name": m.model} for m in result.models]
