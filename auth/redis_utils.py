"""
Redis utilities with exponential backoff retry logic.
Provides resilient Redis connection handling with configurable retries.
"""
import asyncio
import logging
import os
from typing import Optional, Callable, Any, TypeVar
from functools import wraps
from upstash_redis.asyncio import Redis

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Configuration
DEFAULT_MAX_RETRIES = 3
DEFAULT_INITIAL_DELAY = 0.5  # seconds
DEFAULT_MAX_DELAY = 10  # seconds
DEFAULT_EXPONENTIAL_BASE = 2.0


class RedisConnectionError(Exception):
    """Raised when Redis connection fails after retries."""
    pass


async def exponential_backoff_retry(
    func: Callable[..., Any],
    *args,
    max_retries: int = DEFAULT_MAX_RETRIES,
    initial_delay: float = DEFAULT_INITIAL_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    exponential_base: float = DEFAULT_EXPONENTIAL_BASE,
    **kwargs
) -> Any:
    """
    Execute a function with exponential backoff retry logic.

    Args:
        func: Async function to call
        *args: Positional arguments to pass to func
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds before first retry
        max_delay: Maximum delay in seconds between retries
        exponential_base: Base for exponential calculation (delay = initial_delay * (base ** attempt))
        **kwargs: Keyword arguments to pass to func

    Returns:
        Result from func

    Raises:
        RedisConnectionError: If all retries fail
    """
    last_exception = None
    delay = initial_delay

    for attempt in range(max_retries + 1):
        try:
            logger.debug(f"Executing {func.__name__} (attempt {attempt + 1}/{max_retries + 1})")
            return await func(*args, **kwargs)
        except Exception as e:
            last_exception = e
            if attempt < max_retries:
                logger.warning(
                    f"Error in {func.__name__} (attempt {attempt + 1}/{max_retries + 1}): {e}. "
                    f"Retrying in {delay:.2f}s..."
                )
                await asyncio.sleep(delay)
                # Calculate next delay with exponential backoff
                delay = min(delay * exponential_base, max_delay)
            else:
                logger.error(
                    f"Failed to execute {func.__name__} after {max_retries + 1} attempts: {e}"
                )

    raise RedisConnectionError(
        f"Redis operation failed after {max_retries + 1} attempts: {last_exception}"
    )


def redis_retry(
    max_retries: int = DEFAULT_MAX_RETRIES,
    initial_delay: float = DEFAULT_INITIAL_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    exponential_base: float = DEFAULT_EXPONENTIAL_BASE,
):
    """
    Decorator for async functions that should retry on failure with exponential backoff.

    Usage:
        @redis_retry(max_retries=3, initial_delay=0.5)
        async def my_redis_operation():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            return await exponential_backoff_retry(
                func,
                *args,
                max_retries=max_retries,
                initial_delay=initial_delay,
                max_delay=max_delay,
                exponential_base=exponential_base,
                **kwargs
            )
        return wrapper
    return decorator


async def get_redis_with_retry(
    url: Optional[str] = None,
    token: Optional[str] = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
    initial_delay: float = DEFAULT_INITIAL_DELAY,
) -> Redis:
    """
    Create a Redis client with connection retry logic.

    Args:
        url: Redis URL (defaults to UPSTASH_REDIS_REST_URL env var)
        token: Redis token (defaults to UPSTASH_REDIS_REST_TOKEN env var)
        max_retries: Maximum connection retry attempts
        initial_delay: Initial delay before first retry

    Returns:
        Configured Redis client

    Raises:
        RedisConnectionError: If connection fails after retries
    """
    redis_url = url or os.getenv("UPSTASH_REDIS_REST_URL")
    redis_token = token or os.getenv("UPSTASH_REDIS_REST_TOKEN")

    if not redis_url or not redis_token:
        raise ValueError(
            "UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN environment variables must be set"
        )

    async def _create_redis() -> Redis:
        # Test the connection by creating and immediately testing the client
        redis = Redis(url=redis_url, token=redis_token)
        # Verify connection works
        await redis.ping()
        return redis

    try:
        return await exponential_backoff_retry(
            _create_redis,
            max_retries=max_retries,
            initial_delay=initial_delay,
        )
    except RedisConnectionError as e:
        logger.error(f"Failed to establish Redis connection: {e}")
        raise
