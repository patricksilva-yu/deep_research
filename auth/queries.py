"""
Raw SQL queries for user CRUD operations.
All queries use parameterized statements to prevent SQL injection.
"""
from typing import Optional, Dict, Any
import asyncpg
from datetime import datetime


async def create_user(
    db: asyncpg.Connection,
    email: str,
    password_hash: str
) -> Dict[str, Any]:
    query = """
        INSERT INTO users (email, password_hash)
        VALUES (LOWER($1), $2)
        RETURNING id, email, is_active, failed_login_attempts, locked_until, created_at, updated_at
    """
    row = await db.fetchrow(query, email, password_hash)
    return dict(row)


async def get_user_by_email(
    db: asyncpg.Connection,
    email: str
) -> Optional[Dict[str, Any]]:
    query = """
        SELECT id, email, password_hash, is_active, failed_login_attempts, locked_until, created_at, updated_at
        FROM users
        WHERE LOWER(email) = LOWER($1)
    """
    row = await db.fetchrow(query, email)
    return dict(row) if row else None


async def get_user_by_id(
    db: asyncpg.Connection,
    user_id: int
) -> Optional[Dict[str, Any]]:
    query = """
        SELECT id, email, is_active, failed_login_attempts, locked_until, created_at, updated_at
        FROM users
        WHERE id = $1
    """
    row = await db.fetchrow(query, user_id)
    return dict(row) if row else None


async def increment_failed_login_attempts(
    db: asyncpg.Connection,
    user_id: int
) -> int:
    query = """
        UPDATE users
        SET failed_login_attempts = failed_login_attempts + 1
        WHERE id = $1
        RETURNING failed_login_attempts
    """
    row = await db.fetchrow(query, user_id)
    return row["failed_login_attempts"] if row else 0


async def reset_failed_login_attempts(
    db: asyncpg.Connection,
    user_id: int
) -> None:
    query = """
        UPDATE users
        SET failed_login_attempts = 0, locked_until = NULL
        WHERE id = $1
    """
    await db.execute(query, user_id)


async def lock_account(
    db: asyncpg.Connection,
    user_id: int,
    locked_until: datetime
) -> None:
    """
    Lock user account until specified timestamp.

    Args:
        db: Database connection
        user_id: User ID
        locked_until: Timestamp when account should be unlocked
    """
    query = """
        UPDATE users
        SET locked_until = $2
        WHERE id = $1
    """
    await db.execute(query, user_id, locked_until)


async def is_account_locked(
    db: asyncpg.Connection,
    user_id: int
) -> bool:
    query = """
        SELECT locked_until
        FROM users
        WHERE id = $1
    """
    row = await db.fetchrow(query, user_id)
    if not row or not row["locked_until"]:
        return False

    # Account is locked if locked_until is in the future
    return row["locked_until"] > datetime.now(row["locked_until"].tzinfo)


async def update_user_email(
    db: asyncpg.Connection,
    user_id: int,
    new_email: str
) -> None:
    query = """
        UPDATE users
        SET email = LOWER($2)
        WHERE id = $1
    """
    await db.execute(query, user_id, new_email)


async def update_user_password(
    db: asyncpg.Connection,
    user_id: int,
    new_password_hash: str
) -> None:
    query = """
        UPDATE users
        SET password_hash = $2
        WHERE id = $1
    """
    await db.execute(query, user_id, new_password_hash)


async def deactivate_user(
    db: asyncpg.Connection,
    user_id: int
) -> None:
    query = """
        UPDATE users
        SET is_active = FALSE
        WHERE id = $1
    """
    await db.execute(query, user_id)


async def activate_user(
    db: asyncpg.Connection,
    user_id: int
) -> None:
    query = """
        UPDATE users
        SET is_active = TRUE
        WHERE id = $1
    """
    await db.execute(query, user_id)
