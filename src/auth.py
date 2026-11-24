"""Login with API keys.

Every request sends "X-API-Key: <key>". Only the key's SHA-256 hash is stored.
Create the first user and key with:  python main.py create-user you@example.com
"""
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import ApiKey, User, get_async_session, hash_secret

# Also gives the /docs page an "Authorize" button for the key.
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def validate_api_key(
    x_api_key: str | None = Security(api_key_header),
    session: AsyncSession = Depends(get_async_session),
) -> ApiKey:
    if not x_api_key:
        raise HTTPException(status_code=401, detail="X-API-Key header missing.")

    result = await session.execute(select(ApiKey).where(ApiKey.key_hash == hash_secret(x_api_key)))
    api_key = result.scalars().first()
    if api_key is None:
        raise HTTPException(status_code=401, detail="Unauthorized API Key.")

    if api_key.valid_until.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=403, detail="API Key has expired.")

    return api_key


async def current_active_user(
    api_key: ApiKey = Depends(validate_api_key),
    session: AsyncSession = Depends(get_async_session),
) -> User:
    user = await session.get(User, api_key.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=403, detail="This account is disabled.")
    return user
