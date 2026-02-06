"""
CSRF token generation and verification.
Uses signed session-bound tokens (Double-Submit Cookie pattern).
"""
import hmac
import hashlib
import secrets
import logging

logger = logging.getLogger(__name__)


def generate_csrf_token(session_id: str, secret: str) -> str:
    nonce = secrets.token_hex(16)  # 32-character hex string
    message = f"{session_id}:{nonce}"
    signature = hmac.new(
        secret.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()
    token = f"{nonce}.{signature}"
    return token


def verify_csrf_token(token: str, session_id: str, secret: str) -> bool:
    try:
        # Split token into nonce and signature
        nonce, signature = token.split(".", 1)

        # Reconstruct expected signature
        message = f"{session_id}:{nonce}"
        expected_signature = hmac.new(
            secret.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()

        # Use constant-time comparison to prevent timing attacks
        return hmac.compare_digest(signature, expected_signature)
    except (ValueError, AttributeError):
        logger.warning(f"Invalid CSRF token format")
        return False
    except Exception as e:
        logger.error(f"CSRF verification error: {e}")
        return False
