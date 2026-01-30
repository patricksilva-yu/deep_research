"""
Redis client management for Flask and FastAPI.

For Flask: Creates a new client per request to avoid event loop conflicts
For FastAPI: Uses a singleton client for efficiency (FastAPI has stable event loops)

The Upstash Redis client is HTTP-based but uses aiohttp internally, which binds
to the event loop at creation time. Flask creates new event loops per request,
so we need to create new clients. FastAPI reuses the same event loop, so a
singleton is safe.
"""
import logging
import os
from typing import Optional
from upstash_redis.asyncio import Redis

logger = logging.getLogger(__name__)

# Global Redis client instance (singleton) - used only by FastAPI
_redis_client: Optional[Redis] = None


def _create_redis_client() -> Redis:
    """
    Create a new Redis client instance.

    Returns:
        A new Redis client

    Raises:
        ValueError: If Redis credentials not set in environment
    """
    redis_url = os.getenv("UPSTASH_REDIS_REST_URL")
    redis_token = os.getenv("UPSTASH_REDIS_REST_TOKEN")

    if not redis_url or not redis_token:
        raise ValueError(
            "UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN environment variables must be set"
        )

    return Redis(url=redis_url, token=redis_token)


async def init_redis() -> None:
    """
    Initialize the global Redis client for FastAPI.

    For Flask, this is a no-op since Flask creates clients per request.

    Raises:
        ValueError: If Redis credentials not configured
    """
    global _redis_client

    if _redis_client is not None:
        logger.warning("Redis client already initialized")
        return

    logger.info("Initializing Redis client")
    _redis_client = _create_redis_client()
    logger.info("Redis client initialized successfully")


async def close_redis() -> None:
    """
    Close the global Redis client during application shutdown.
    """
    global _redis_client

    if _redis_client is None:
        logger.warning("Redis client not initialized, nothing to close")
        return

    logger.info("Closing Redis client")
    _redis_client = None
    logger.info("Redis client closed")


def get_redis_client() -> Redis:
    """
    Get a Redis client instance.

    For FastAPI: Returns the singleton client
    For Flask: Creates a new client (call this in request context)

    Usage as FastAPI dependency:
        from typing import Annotated
        from fastapi import Depends
        from upstash_redis.asyncio import Redis
        from auth.redis_client import get_redis_client

        @router.post("/example")
        async def example(redis: Annotated[Redis, Depends(get_redis_client)]):
            await redis.set("key", "value")
            return {"status": "ok"}

    Usage in Flask request handlers:
        redis = get_redis_client()
        await redis.set("key", "value")

    Returns:
        A Redis client instance

    Raises:
        RuntimeError: If FastAPI singleton not initialized
        ValueError: If Redis credentials not configured
    """
    # For FastAPI (singleton pattern)
    if _redis_client is not None:
        return _redis_client

    # For Flask (per-request pattern) - create a new client
    # This avoids event loop binding issues since Flask creates new loops per request
    return _create_redis_client()
