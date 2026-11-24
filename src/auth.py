"""Authentication.

Log in with POST /auth/login (username or email + password) to get a token, then send it on
every request as "X-API-Key: <token>" or "Authorization: Bearer <token>". POST /auth/logout
ends that login. Long-lived API keys from POST /apikeys/generate or `python main.py create-user`
work the same way. In Swagger (/docs), "Authorize" logs in with username and password
through POST /auth/token.
Only the SHA-256 hash of a token or key is stored.
"""
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import ApiKey, User, get_async_session, hash_secret

# Both show up under "Authorize" on the /docs page: username + password, or a raw API key.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token", auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def validate_api_key(
    bearer_token: str | None = Security(oauth2_scheme),
    header_key: str | None = Security(api_key_header),
    session: AsyncSession = Depends(get_async_session),
) -> ApiKey:
    x_api_key = header_key or bearer_token
    if not x_api_key:
        raise HTTPException(
            status_code=401,
            detail="Not logged in: send X-API-Key or Authorization: Bearer.",
            headers={"WWW-Authenticate": "Bearer"},
        )

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


async def current_superuser(user: User = Depends(current_active_user)) -> User:
    if not user.is_superuser:
        raise HTTPException(status_code=403, detail="Only a superuser can do this.")
    return user
