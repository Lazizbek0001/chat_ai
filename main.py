"""Start the API:            python main.py
Create a user and API key: python main.py create-user you@example.com [days]"""
import asyncio
import sys
from datetime import datetime, timedelta, timezone

import uvicorn


async def create_user(email: str, days: int) -> None:
    import secrets

    from sqlalchemy import func, select

    from src.db import ApiKey, User, async_session_maker, create_db_and_tables, hash_secret

    await create_db_and_tables()
    async with async_session_maker() as session:
        user = (
            await session.execute(select(User).where(func.lower(User.email) == email.lower()))
        ).scalars().first()
        if user is None:
            user = User(email=email, hashed_password="", is_verified=True)
            session.add(user)
            await session.flush()

        raw_key = secrets.token_urlsafe(32)
        key = ApiKey(
            user_id=user.id,
            key_hash=hash_secret(raw_key),
            valid_until=datetime.now(timezone.utc) + timedelta(days=days),
        )
        session.add(key)
        await session.commit()

    print(f"User:  {email}")
    print(f"Key:   {raw_key}")
    print(f"Valid: {days} days. It is shown only now; save it.")


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "create-user":
        days = int(sys.argv[3]) if len(sys.argv) > 3 else 365
        asyncio.run(create_user(sys.argv[2], days))
    else:
        uvicorn.run(app="src.app:app", host="0.0.0.0", port=8000, reload=True)
