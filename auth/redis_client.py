"""
Redis client management for Flask and FastAPI.

Supports either:
- Local/standard Redis via `REDIS_URL`
- Upstash Redis REST via `UPSTASH_REDIS_REST_URL` + `UPSTASH_REDIS_REST_TOKEN`
"""
import logging
import os
from typing import Any, Optional

from redis.asyncio import Redis as AsyncRedis
from upstash_redis.asyncio import Redis as UpstashRedis

logger = logging.getLogger(__name__)

# Global Redis client instance (singleton) - used only by FastAPI
_redis_client: Optional[Any] = None


def _create_redis_client() -> Any:
    """
    Create a new Redis client instance.

    Returns:
        A new Redis client

    Raises:
        ValueError: If Redis credentials not set in environment
    """
    local_redis_url = os.getenv("REDIS_URL")
    if local_redis_url:
        logger.info("Using local Redis client")
        return AsyncRedis.from_url(local_redis_url, decode_responses=True)

    redis_url = os.getenv("UPSTASH_REDIS_REST_URL")
    redis_token = os.getenv("UPSTASH_REDIS_REST_TOKEN")
    if redis_url and redis_token:
        logger.info("Using Upstash Redis client")
        return UpstashRedis(url=redis_url, token=redis_token)

    raise ValueError(
        "Set REDIS_URL for local Redis or UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN for Upstash"
    )


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


def get_redis_client() -> Any:
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

    # For Flask and fallback code paths, create a client on demand.
    return _create_redis_client()
