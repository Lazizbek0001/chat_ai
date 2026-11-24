import secrets
import time
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.ai import ask_ai, list_models
from src.ai_errors import AIError
from src.auth import current_active_user, current_superuser, validate_api_key
from src.db import (
    ApiKey,
    User,
    create_db_and_tables,
    get_async_session,
    hash_password,
    hash_secret,
    verify_password,
)
from src.logging_config import logger
from src.models.chat import Chat, ChatMessage
from src.schemas import ChatRequest, LoginRequest, PasswordChange, UserCreate

@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_db_and_tables()
    yield

app = FastAPI(lifespan=lifespan)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    response = await call_next(request)

    logger.info(
        "%s %s %d",
        request.method,
        request.url.path,
        response.status_code,
    )

    return response


async def _new_token(session: AsyncSession, user: User) -> dict:
    """Creates a login token (stored like an API key, only its hash) valid for 30 days."""
    raw_token = secrets.token_urlsafe(32)
    key = ApiKey(user_id=user.id, key_hash=hash_secret(raw_token))
    session.add(key)
    await session.commit()
    return {
        "access_token": raw_token,
        "header": "X-API-Key",
        "valid_until": key.valid_until.isoformat(),
        "user": {"id": str(user.id), "username": user.username, "email": user.email},
    }


async def _find_user(session: AsyncSession, login: str) -> User | None:
    """Finds a user by username or email (case-insensitive)."""
    login = login.strip().lower()
    result = await session.execute(
        select(User).where(or_(func.lower(User.username) == login, func.lower(User.email) == login))
    )
    return result.scalars().first()


@app.post("/auth/login", tags=["auth"])
async def login(data: LoginRequest, session: AsyncSession = Depends(get_async_session)):
    """Returns a token. Send it as the X-API-Key header on every other request."""
    user = await _find_user(session, data.username)
    if user is None or not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Wrong username or password.")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="This account is disabled.")
    return await _new_token(session, user)


@app.post("/auth/token", tags=["auth"])
async def login_form(
    form: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(get_async_session),
):
    """Username (or email) + password as a form. Used by the "Authorize" button in /docs."""
    user = await _find_user(session, form.username)
    if user is None or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Wrong username or password.")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="This account is disabled.")
    token = await _new_token(session, user)
    return {**token, "token_type": "bearer"}


@app.post("/auth/logout", tags=["auth"])
async def logout(
    api_key_record: ApiKey = Depends(validate_api_key),
    session: AsyncSession = Depends(get_async_session),
):
    """Ends this login: the token sent in X-API-Key stops working."""
    await session.execute(delete(ApiKey).where(ApiKey.id == api_key_record.id))
    await session.commit()
    return {"detail": "Logged out."}


@app.post("/auth/change-password", tags=["auth"])
async def change_password(
    data: PasswordChange,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Changes the logged-in user's password. The current password is required."""
    if not verify_password(data.old_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="The current password is wrong.")
    if data.new_password == data.old_password:
        raise HTTPException(status_code=400, detail="The new password must be different.")
    user.hashed_password = hash_password(data.new_password)
    await session.commit()
    return {"detail": "Password changed."}


@app.post("/users", tags=["users"], status_code=201)
async def create_user(
    data: UserCreate,
    admin: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session),
):
    """Superuser only. Creates an account; give the user its username and password to log in."""
    username = data.username.strip().lower()
    email = data.email.strip().lower() if data.email else None
    if await _find_user(session, username) is not None:
        raise HTTPException(status_code=400, detail="This username is already taken.")
    if email and await _find_user(session, email) is not None:
        raise HTTPException(status_code=400, detail="This email is already registered.")
    user = User(
        username=username,
        email=email,
        hashed_password=hash_password(data.password),
        is_superuser=data.is_superuser,
        is_verified=True,
    )
    session.add(user)
    await session.commit()
    logger.info("User %s created by %s", user.username, admin.username)
    return {
        "id": str(user.id),
        "username": user.username,
        "email": user.email,
        "is_superuser": user.is_superuser,
    }


@app.get("/users/me", tags=["users"])
async def read_me(user: User = Depends(current_active_user)):
    return {
        "id": str(user.id),
        "username": user.username,
        "email": user.email,
        "is_active": user.is_active,
        "is_verified": user.is_verified,
    }


@app.post("/apikeys/generate", tags=["API Keys"])
async def generate_api_key(
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Generates a new API key for the logged-in user, valid for 30 days.

    The key is returned only here. Only its hash is stored, so it cannot be shown again.
    """
    raw_key = secrets.token_urlsafe(32)
    new_key = ApiKey(user_id=user.id, key_hash=hash_secret(raw_key))
    db.add(new_key)
    await db.commit()
    return {
        "id": str(new_key.id),
        "api_key": raw_key,
        "valid_until": new_key.valid_until.isoformat(),
    }


@app.get("/apikeys/list", tags=["API Keys"])
async def get_apikeys(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
    ):
    """Lists the user's keys without the keys themselves: only their ids and dates."""
    result = await session.execute(
        select(ApiKey).filter_by(user_id=user.id).order_by(ApiKey.created_at.desc())
    )
    keys_data = [
        {
            "id": str(key.id),
            "user_id": str(key.user_id),
            "created_at": key.created_at,
            "valid_until": key.valid_until,
            "username": user.username,
            "email": user.email,
        }
        for key in result.scalars().all()
    ]
    return {"api_keys": keys_data}


@app.post("/chat/new", tags=["AI Chat"])
async def create_chat(
    title: str,
    api_key_record: ApiKey = Depends(validate_api_key),
    session: AsyncSession = Depends(get_async_session)
):

    new_chat = Chat(
        user_id=api_key_record.user_id,
        title=title
    )


    session.add(new_chat)

    await session.commit()

    await session.refresh(new_chat)


    return {
        "chat_id": str(new_chat.id),
        "title": new_chat.title
    }

@app.get("/chat/list", tags=["AI Chat"])
async def get_chats(
    api_key_record: ApiKey = Depends(validate_api_key),
    session: AsyncSession = Depends(get_async_session)
    ):
    # selectinload fetches every chat's messages in one extra query, not one query per chat.
    result = await session.execute(
        select(Chat)
        .filter_by(user_id=api_key_record.user_id)
        .options(selectinload(Chat.messages))
    )
    chats = result.scalars().all()

    chats_data = []

    for chat in chats:
        messages = sorted(chat.messages, key=lambda m: m.created_at)
        chats_data.append(
            {
                "id": chat.id,
                "user_id": chat.user_id,
                "title": chat.title,
                "created_at": chat.created_at,
                "messages": [
                    {
                        "id": m.id,
                        "chat_id":m.chat_id,
                        "role":m.role,
                        "content": m.content,
                        "created_at":m.created_at,
                    }if m.role == 'user' else 
                    {
                        "id": m.id,
                        "chat_id":m.chat_id,
                        "role":m.role,
                        "duration": m.duration,
                        "content": m.content,
                        "created_at":m.created_at,
                    } for m in messages 
                ]

            }
        )
        
    return {"chat_list":chats_data}

@app.get("/chat/ai/models", tags=["AI Chat"])
async def get_models(
    api_key_record: ApiKey = Depends(validate_api_key),
):
    """Models from Groq and Ollama Cloud. Send an entry's "provider" and "id" as "provider"
    and "model" in POST /chat/{chat_id}. "available" is false when that provider has no key."""
    return await list_models()


# Kept so existing clients that use POST keep working. New code should use GET.
@app.post("/chat/ai/models", tags=["AI Chat"], deprecated=True)
async def list_models_post(
    api_key_record: ApiKey = Depends(validate_api_key),
):
    return await list_models()

@app.post("/chat/{chat_id}", tags=["AI Chat"])
async def send_message(
    chat_id: UUID,
    data: ChatRequest,
    api_key_record: ApiKey = Depends(validate_api_key),
    session: AsyncSession = Depends(get_async_session),
):
    result = await session.execute(
        select(Chat).where(
            Chat.id == chat_id,
            Chat.user_id == api_key_record.user_id,
        )
    )

    chat = result.scalars().first()

    if not chat:
        raise HTTPException(
            status_code=404,
            detail="Chat not found",
        )

    # Save user's message
    user_message = ChatMessage(
        chat_id=chat.id,
        role="user",
        content=data.message,
    )

    session.add(user_message)
    await session.flush()

    # Fetch conversation history
    result = await session.execute(
        select(ChatMessage)
        .where(ChatMessage.chat_id == chat.id)
        .order_by(ChatMessage.created_at)
    )

    history = result.scalars().all()

    messages = [
        {
            "role": msg.role,
            "content": msg.content,
        }
        for msg in history
    ]

    # Generate AI response
    start = time.perf_counter()

    try:
        ai_response, provider, model = await ask_ai(messages, provider=data.provider, model=data.model)
    except AIError as e:
        # Tracebacks only for outages; 4xx (no credits, unknown model, rate limit) are expected.
        logger.warning(
            "AI request failed for chat %s: %s",
            chat.id,
            e.detail,
            exc_info=e.__cause__ if e.status_code >= 500 else None,
        )
        raise HTTPException(status_code=e.status_code, detail=e.detail)

    duration = time.perf_counter() - start

    logger.info(
        "AI response generated in %.3f seconds for chat %s",
        duration,
        chat.id,
    )

    # Save assistant response
    assistant_message = ChatMessage(
        chat_id=chat.id,
        role="assistant",
        content=ai_response,
        duration=round(duration, 3),
    )

    session.add(assistant_message)
    await session.commit()

    return {
        "chat_id": str(chat.id),
        "user_message_id": str(user_message.id),
        "message_id": str(assistant_message.id),
        "provider": provider,
        "model": model,
        "response": ai_response,
        "duration": round(duration, 3),
    }
