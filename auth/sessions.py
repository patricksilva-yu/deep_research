"""
Upstash Redis session management using the official Python SDK.
Handles server-side sessions stored in Upstash Redis with REST API.
"""
import os
import json
import secrets
from typing import Optional, Dict, Any
from datetime import datetime
import logging
from upstash_redis.asyncio import Redis
from auth.redis_utils import redis_retry, exponential_backoff_retry

logger = logging.getLogger(__name__)


class UpstashSessionManager:
    """
    Manages user sessions using Upstash Redis REST API.
    Sessions store user_id and metadata with configurable TTL.
    """

    def __init__(self, redis: Redis):
        """
        Initialize session manager with a Redis client.

        Args:
            redis: Upstash Redis client instance (should be singleton from app startup)
        """
        self.redis = redis
        self.session_ttl = int(os.getenv("SESSION_TTL", "86400"))  # 24 hours default

    @redis_retry(max_retries=3, initial_delay=0.5)
    async def _setex_with_retry(self, key: str, ttl: int, value: str) -> None:
        """Helper for setex with retry."""
        await self.redis.setex(key, ttl, value)

    async def create_session(self, user_id: int) -> str:
        """
        Create a new session for a user.

        Args:
            user_id: User ID

        Returns:
            Session ID (random hex string)
        """
        session_id = secrets.token_hex(32)  # 64-character hex string

        session_data = {
            "user_id": user_id,
            "created_at": datetime.utcnow().isoformat(),
        }

        # Store in Redis with TTL (EX = expire in seconds) with retry logic
        try:
            await self._setex_with_retry(
                f"session:{session_id}",
                self.session_ttl,
                json.dumps(session_data),
            )
        except Exception as e:
            logger.error(f"Failed to create session for user {user_id}: {e}")
            raise

        logger.info(f"Created session {session_id} for user {user_id}")
        return session_id

    @redis_retry(max_retries=3, initial_delay=0.5)
    async def _get_with_retry(self, key: str) -> Optional[str]:
        """Helper for get with retry."""
        return await self.redis.get(key)

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve session data.

        Args:
            session_id: Session ID

        Returns:
            Session dict with user_id and created_at, or None if not found
        """
        try:
            result = await self._get_with_retry(f"session:{session_id}")
        except Exception as e:
            logger.error(f"Failed to retrieve session {session_id}: {e}")
            return None

        if not result:
            return None

        try:
            return json.loads(result)
        except json.JSONDecodeError:
            logger.error(f"Failed to decode session data for {session_id}")
            return None

    @redis_retry(max_retries=3, initial_delay=0.5)
    async def _delete_with_retry(self, key: str) -> None:
        """Helper for delete with retry."""
        await self.redis.delete(key)

    async def delete_session(self, session_id: str) -> None:
        """
        Delete a session (logout).

        Args:
            session_id: Session ID
        """
        try:
            await self._delete_with_retry(f"session:{session_id}")
        except Exception as e:
            logger.error(f"Failed to delete session {session_id}: {e}")
            raise
        logger.info(f"Deleted session {session_id}")

    @redis_retry(max_retries=3, initial_delay=0.5)
    async def _expire_with_retry(self, key: str, ttl: int) -> int:
        """Helper for expire with retry."""
        return await self.redis.expire(key, ttl)

    async def refresh_session(self, session_id: str) -> bool:
        """
        Refresh session TTL (sliding window).
        Used on every authenticated request to keep active sessions alive.

        Args:
            session_id: Session ID

        Returns:
            True if session existed and was refreshed, False otherwise
        """
        try:
            # EXPIRE returns 1 if key exists, 0 if not
            result = await self._expire_with_retry(f"session:{session_id}", self.session_ttl)
            return bool(result)
        except Exception as e:
            logger.error(f"Failed to refresh session {session_id}: {e}")
            return False


# Global session manager instance
_session_manager: Optional[UpstashSessionManager] = None


def get_session_manager() -> UpstashSessionManager:
    """
    Get the global session manager instance.

    Returns:
        The global session manager instance

    Raises:
        RuntimeError: If session manager not initialized (app startup failed)
    """
    global _session_manager
    if _session_manager is None:
        raise RuntimeError(
            "Session manager not initialized. Ensure init_sessions() is called during application startup."
        )
    return _session_manager


async def init_sessions() -> None:
    """
    Initialize the session manager (called at app startup).

    This must be called after init_redis() since it depends on the Redis client.
    """
    global _session_manager
    from auth.redis_client import get_redis_client

    redis = get_redis_client()
    _session_manager = UpstashSessionManager(redis=redis)
    logger.info("Session manager initialized")


async def close_sessions() -> None:
    """Close the session manager (called at app shutdown)."""
    global _session_manager
    if _session_manager:
        _session_manager = None
        logger.info("Session manager closed")
