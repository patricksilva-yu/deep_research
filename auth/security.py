"""
Password hashing and verification using Argon2id.
OWASP-recommended parameters for password hashing.
"""
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHash
import logging

logger = logging.getLogger(__name__)

# Create password hasher with OWASP baseline parameters for Argon2id
# https://owasp.org/www-community/vulnerabilities/Insufficient_Password_Management
_password_hasher = PasswordHasher(
    time_cost=2,        # iterations (low but acceptable for async context)
    memory_cost=19456,  # 19 MiB
    parallelism=1,      # 1 thread (serverless safe)
    hash_len=32,        # 32-byte output
    salt_len=16,        # 16-byte salt
)


def hash_password(password: str) -> str:
    """
    Hash a password using Argon2id.

    Args:
        password: Plain text password

    Returns:
        Argon2id hash string (includes salt and parameters)

    Raises:
        Exception: If hashing fails
    """
    try:
        return _password_hasher.hash(password)
    except Exception as e:
        logger.error(f"Password hashing failed: {e}")
        raise


def verify_password(password: str, hash_string: str) -> bool:
    """
    Verify a plain text password against an Argon2id hash.

    Args:
        password: Plain text password to verify
        hash_string: Argon2id hash from database

    Returns:
        True if password matches, False otherwise
    """
    try:
        _password_hasher.verify(hash_string, password)
        return True
    except VerifyMismatchError:
        return False
    except InvalidHash:
        logger.error(f"Invalid hash format in database")
        return False
    except Exception as e:
        logger.error(f"Password verification failed: {e}")
        return False


def needs_rehash(hash_string: str) -> bool:
    """
    Check if a hash needs to be rehashed with updated parameters.
    Used during login to update weak hashes.

    Args:
        hash_string: Argon2id hash from database

    Returns:
        True if hash should be regenerated with current parameters
    """
    try:
        return _password_hasher.check_needs_rehash(hash_string)
    except Exception as e:
        logger.error(f"Check rehash failed: {e}")
        return False
