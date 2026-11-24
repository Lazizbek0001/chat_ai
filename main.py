"""Start the API:            python main.py
Create a user and API key: python main.py create-user <username> [days]
Create the first superuser: python main.py create-superuser <username>
Reset a user's password:   python main.py set-password <username>

Other users are created by a superuser with POST /users."""
import asyncio
import sys
from datetime import datetime, timedelta, timezone

import uvicorn


async def create_user(username: str, days: int) -> None:
    import secrets

    from sqlalchemy import func, select

    from src.db import ApiKey, User, async_session_maker, create_db_and_tables, hash_secret

    username = username.strip().lower()
    await create_db_and_tables()
    async with async_session_maker() as session:
        user = (
            await session.execute(select(User).where(func.lower(User.username) == username))
        ).scalars().first()
        if user is None:
            user = User(username=username, hashed_password="", is_verified=True)
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

    print(f"User:  {username}")
    print(f"Key:   {raw_key}")
    print(f"Valid: {days} days. It is shown only now; save it.")


def ask_password() -> str:
    from getpass import getpass

    password = getpass("New password: ")
    if len(password) < 8:
        sys.exit("The password must be at least 8 characters.")
    if getpass("Repeat it: ") != password:
        sys.exit("The passwords do not match.")
    return password


async def set_password(username: str, make_superuser: bool = False) -> None:
    """Sets a user's password. With make_superuser, also creates the user if missing
    and makes them a superuser."""
    from sqlalchemy import func, select

    from src.db import User, async_session_maker, create_db_and_tables, hash_password

    password = ask_password()

    username = username.strip().lower()
    await create_db_and_tables()
    async with async_session_maker() as session:
        user = (
            await session.execute(select(User).where(func.lower(User.username) == username))
        ).scalars().first()
        if user is None:
            if not make_superuser:
                sys.exit(f"No user {username}.")
            user = User(username=username, is_verified=True)
            session.add(user)
        user.hashed_password = hash_password(password)
        if make_superuser:
            user.is_superuser = True
        await session.commit()
    role = "Superuser" if make_superuser else "Password set for"
    print(f"{role} {username}. Log in with POST /auth/login.")


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "create-user":
        days = int(sys.argv[3]) if len(sys.argv) > 3 else 365
        asyncio.run(create_user(sys.argv[2], days))
    elif len(sys.argv) >= 3 and sys.argv[1] == "create-superuser":
        asyncio.run(set_password(sys.argv[2], make_superuser=True))
    elif len(sys.argv) >= 3 and sys.argv[1] == "set-password":
        asyncio.run(set_password(sys.argv[2]))
    else:
        uvicorn.run(app="src.app:app", host="0.0.0.0", port=8000, reload=True)
