"""
Redis-based rate limiting and account lockout for authentication.
Implements sliding window counters for login attempts.
"""
import logging
from datetime import datetime, timedelta
from upstash_redis.asyncio import Redis

logger = logging.getLogger(__name__)

# Rate limit thresholds
LOGIN_ATTEMPTS_PER_MINUTE = 5  # Per IP
LOGIN_ATTEMPTS_PER_5_MIN = 10  # Per email
FAILED_ATTEMPTS_LOCKOUT = 10  # Account lockout threshold
LOCKOUT_DURATION_MINUTES = 15


class RateLimiter:
    """
    Rate limiting and account lockout using Redis.
    """

    def __init__(self, redis: Redis):
        self.redis = redis

    async def check_ip_rate_limit(self, ip: str) -> bool:

        key = f"ratelimit:ip:{ip}:1m"
        count = await self.redis.incr(key)

        # Set expiry on first increment
        if count == 1:
            await self.redis.expire(key, 60)

        if count > LOGIN_ATTEMPTS_PER_MINUTE:
            logger.warning(f"IP rate limit exceeded: {ip}")
            return True

        return False

    async def check_email_rate_limit(self, email: str) -> bool:
        """
        Check if email has exceeded login attempts per 5 minutes.

        Args:
            email: User email address

        Returns:
            True if rate limited (exceeded limit), False otherwise
        """
        key = f"ratelimit:email:{email}:5m"
        count = await self.redis.incr(key)

        # Set expiry on first increment
        if count == 1:
            await self.redis.expire(key, 300)

        if count > LOGIN_ATTEMPTS_PER_5_MIN:
            logger.warning(f"Email rate limit exceeded: {email}")
            return True

        return False

    async def increment_failed_attempts(self, email: str) -> int:
        """
        Increment failed login attempt counter for an email.

        Args:
            email: User email address

        Returns:
            New failure count
        """
        key = f"failed_attempts:{email}"
        count = await self.redis.incr(key)

        # Expire after 1 hour (resets failed attempts after 1 hour)
        await self.redis.expire(key, 3600)

        return count

    async def reset_failed_attempts(self, email: str) -> None:
        """
        Reset failed attempts counter (after successful login).

        Args:
            email: User email address
        """
        key = f"failed_attempts:{email}"
        await self.redis.delete(key)

    async def should_lockout_account(self, email: str) -> bool:
        """
        Check if account should be locked out based on failed attempts.

        Args:
            email: User email address

        Returns:
            True if account has exceeded failure threshold, False otherwise
        """
        key = f"failed_attempts:{email}"
        count = await self.redis.get(key)

        if count and int(count) >= FAILED_ATTEMPTS_LOCKOUT:
            logger.warning(f"Account lockout triggered: {email}")
            return True

        return False

    async def lock_account(self, user_id: int) -> None:
        """
        Lock an account in Redis (in addition to database update).

        Args:
            user_id: User ID
        """
        key = f"account_locked:{user_id}"
        locked_until = (datetime.utcnow() + timedelta(minutes=LOCKOUT_DURATION_MINUTES)).isoformat()
        await self.redis.setex(
            key,
            LOCKOUT_DURATION_MINUTES * 60,
            locked_until
        )
        logger.info(f"Account locked: user {user_id}")

    async def is_account_locked(self, user_id: int) -> bool:
        """
        Check if account is locked.

        Args:
            user_id: User ID

        Returns:
            True if account is locked, False otherwise
        """
        key = f"account_locked:{user_id}"
        result = await self.redis.get(key)
        return bool(result)

    async def unlock_account(self, user_id: int) -> None:
        """
        Unlock an account.

        Args:
            user_id: User ID
        """
        key = f"account_locked:{user_id}"
        await self.redis.delete(key)
        logger.info(f"Account unlocked: user {user_id}")


def get_rate_limiter(redis: Redis) -> RateLimiter:
    """
    Create a RateLimiter instance with the provided Redis client.

    This function can be used as a FastAPI dependency or called directly.
    The RateLimiter is lightweight and stateless - it only wraps the Redis client.

    Args:
        redis: Upstash Redis client (should be singleton from app startup)

    Returns:
        RateLimiter instance
    """
    return RateLimiter(redis)
