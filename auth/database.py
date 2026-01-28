"""
Database connection management using asyncpg.
Provides connection pool and database initialization.
"""
import os
import asyncpg
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Global connection pool
_pool: Optional[asyncpg.Pool] = None


async def get_pool() -> asyncpg.Pool:
    """Get the database connection pool."""
    global _pool
    if _pool is None:
        raise RuntimeError("Database pool not initialized. Call init_db() first.")
    return _pool


async def init_db() -> None:
    global _pool

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")

    logger.info("Initializing database connection pool")

    _pool = await asyncpg.create_pool(
        database_url,
        min_size=2,
        max_size=10,
        command_timeout=60,
        max_queries=50000,
        max_inactive_connection_lifetime=300,
    )

    logger.info("Database connection pool initialized successfully")


async def close_db() -> None:
    global _pool
    if _pool:
        logger.info("Closing database connection pool")
        await _pool.close()
        _pool = None


async def get_db():
    pool = await get_pool()
    async with pool.acquire() as connection:
        yield connection
