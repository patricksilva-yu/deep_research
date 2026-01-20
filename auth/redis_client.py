"""
Redis client singleton for application-wide connection reuse.

The Upstash Redis client is HTTP-based and connectionless (uses aiohttp internally).
While it doesn't require traditional connection pooling, the documentation recommends
creating the client once and reusing it to avoid initialization overhead.

Reference: https://github.com/upstash/redis-py
"If you are in a serverless environment that allows it, it's recommended to
initialise the client outside the request handler to be reused while your
function is still hot."

This module provides:
- Singleton Redis client initialization during app startup
- FastAPI dependency for dependency injection
- Proper startup/shutdown lifecycle management
"""
import logging
from typing import Optional
from upstash_redis.asyncio import Redis
from auth.redis_utils import get_redis_with_retry

logger = logging.getLogger(__name__)

# Global Redis client instance (singleton)
_redis_client: Optional[Redis] = None


async def init_redis() -> None:
    """
    Initialize the global Redis client during application startup.

    This should be called from the FastAPI lifespan context manager.
    Uses exponential backoff retry logic for resilient connection.

    The client is created once and reused for all subsequent requests,
    which is more efficient than creating a new instance per request.

    Raises:
        RedisConnectionError: If connection fails after retries
    """
    global _redis_client

    if _redis_client is not None:
        logger.warning("Redis client already initialized")
        return

    logger.info("Initializing Redis client")
    _redis_client = await get_redis_with_retry()
    logger.info("Redis client initialized successfully")


async def close_redis() -> None:
    """
    Close the global Redis client during application shutdown.

    This should be called from the FastAPI lifespan context manager.

    Note: The Upstash Redis client uses aiohttp internally. While it doesn't
    require explicit connection cleanup (HTTP is stateless), we clean up
    the reference for proper resource management.
    """
    global _redis_client

    if _redis_client is None:
        logger.warning("Redis client not initialized, nothing to close")
        return

    logger.info("Closing Redis client")
    # Upstash Redis client is HTTP-based and doesn't require explicit close,
    # but we reset the reference for cleanup
    _redis_client = None
    logger.info("Redis client closed")


def get_redis_client() -> Redis:
    """
    Get the singleton Redis client instance.

    This can be used as a FastAPI dependency or called directly.
    The Redis client is initialized once during app startup and reused.

    Usage as FastAPI dependency:
        from typing import Annotated
        from fastapi import Depends
        from upstash_redis.asyncio import Redis
        from auth.redis_client import get_redis_client

        @router.post("/example")
        async def example(redis: Annotated[Redis, Depends(get_redis_client)]):
            await redis.set("key", "value")
            return {"status": "ok"}

    Usage in initialization code:
        from auth.redis_client import get_redis_client

        session_manager = UpstashSessionManager(redis=get_redis_client())

    Returns:
        The global Redis client instance

    Raises:
        RuntimeError: If Redis client not initialized (app startup failed)
    """
    if _redis_client is None:
        logger.error("Redis client not initialized - did application startup fail?")
        raise RuntimeError(
            "Redis client not initialized. Ensure init_redis() is called during application startup."
        )

    return _redis_client
