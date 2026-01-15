"""
FastAPI authentication router.
Implements /auth/login, /auth/register, /auth/logout, /auth/me endpoints.
"""
import os
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr
import logging

from auth.database import get_db
from auth import queries
from auth.security import hash_password, verify_password
from auth.sessions import get_session_manager
from auth.csrf import generate_csrf_token
from auth.rate_limit import get_rate_limiter
from auth.dependencies import get_current_user, CurrentUser
from upstash_redis.asyncio import Redis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    message: str
    user: dict


@router.post("/register")
async def register(
    req: RegisterRequest,
    db = Depends(get_db),
):
    """
    Register a new user account.

    Args:
        req: Registration request with email and password
        db: Database connection

    Returns:
        Success message with user info

    Raises:
        HTTPException: 400 if email already exists
    """
    # Validate password strength (minimum 8 chars, should be enforced client-side too)
    if len(req.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    # Check if email already exists
    existing_user = await queries.get_user_by_email(db, req.email)
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    # Hash password and create user
    try:
        password_hash = hash_password(req.password)
        user = await queries.create_user(db, req.email, password_hash)
        logger.info(f"New user registered: {req.email}")

        return {
            "message": "User registered successfully",
            "user": {
                "id": user["id"],
                "email": user["email"],
                "created_at": user["created_at"],
            }
        }
    except Exception as e:
        logger.error(f"Registration failed: {e}")
        raise HTTPException(status_code=500, detail="Registration failed")


@router.post("/login")
async def login(
    req: LoginRequest,
    request: Request,
    db = Depends(get_db),
):
    """
    Authenticate user and create session.

    Args:
        req: Login request with email and password
        request: FastAPI request object (for client IP)
        db: Database connection

    Returns:
        JSONResponse with session and CSRF cookies

    Raises:
        HTTPException: 401 if credentials invalid, 429 if rate limited, 403 if account locked
    """
    client_ip = request.client.host

    # Initialize Redis and rate limiter
    redis = Redis.from_env()
    rate_limiter = await get_rate_limiter(redis)

    # Check rate limits
    if await rate_limiter.check_ip_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Too many login attempts from this IP")

    if await rate_limiter.check_email_rate_limit(req.email):
        raise HTTPException(status_code=429, detail="Too many login attempts for this email")

    # Get user from database
    user = await queries.get_user_by_email(db, req.email)
    if not user:
        logger.warning(f"Login attempt for non-existent email: {req.email}")
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Check if account is locked
    if await rate_limiter.is_account_locked(user["id"]):
        raise HTTPException(status_code=403, detail="Account locked due to too many failed attempts")

    if user.get("locked_until"):
        from datetime import datetime
        if user["locked_until"] > datetime.now(user["locked_until"].tzinfo):
            raise HTTPException(status_code=403, detail="Account locked")

    if not user.get("is_active"):
        raise HTTPException(status_code=403, detail="User account is inactive")

    # Verify password
    if not verify_password(req.password, user["password_hash"]):
        # Increment failed attempts
        attempts = await rate_limiter.increment_failed_attempts(req.email)

        # Lock account if threshold reached
        if attempts >= 10:
            from datetime import datetime, timedelta
            locked_until = datetime.now() + timedelta(minutes=15)
            await queries.lock_account(db, user["id"], locked_until)
            await rate_limiter.lock_account(user["id"])
            raise HTTPException(status_code=403, detail="Account locked due to too many failed attempts")

        logger.warning(f"Failed login attempt: {req.email} (attempt {attempts})")
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Successful login - reset failed attempts
    await rate_limiter.reset_failed_attempts(req.email)
    await queries.reset_failed_login_attempts(db, user["id"])

    # Create session
    session_manager = get_session_manager()
    session_id = await session_manager.create_session(user["id"])

    # Generate CSRF token
    csrf_secret = os.getenv("CSRF_SECRET")
    csrf_token = generate_csrf_token(session_id, csrf_secret)

    # Create response with cookies
    response = JSONResponse(
        content={
            "message": "Logged in successfully",
            "user": {
                "id": user["id"],
                "email": user["email"],
            }
        },
        status_code=200
    )

    # Set session cookie (HttpOnly)
    response.set_cookie(
        key="session_id",
        value=session_id,
        max_age=86400,  # 24 hours
        httponly=True,
        secure=False,
        samesite="lax",
        path="/",
    )

    # Set CSRF cookie (readable by JS)
    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        max_age=86400,
        httponly=False,
        secure=False,
        samesite="lax",
        path="/",
    )

    logger.info(f"User logged in: {req.email}")
    return response


@router.post("/logout")
async def logout(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    request: Request,
):
    """
    Logout user and delete session from Redis.

    Args:
        current_user: Current authenticated user
        request: FastAPI request object (for accessing cookies)

    Returns:
        JSONResponse with cleared cookies
    """
    # Get session_id from cookies
    session_id = request.cookies.get("session_id")

    # Delete session from Redis
    if session_id:
        session_manager = get_session_manager()
        await session_manager.delete_session(session_id)
        logger.info(f"Session deleted for user: {current_user.email}")

    response = JSONResponse(content={"message": "Logged out successfully"})

    # Clear cookies
    response.delete_cookie("session_id", path="/")
    response.delete_cookie("csrf_token", path="/")

    logger.info(f"User logged out: {current_user.email}")
    return response


@router.get("/me")
async def get_me(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    db = Depends(get_db),
):
    """
    Get current user information.

    Args:
        current_user: Current authenticated user
        db: Database connection

    Returns:
        User information
    """
    user = await queries.get_user_by_id(db, current_user.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "id": user["id"],
        "email": user["email"],
        "is_active": user["is_active"],
        "created_at": user["created_at"],
    }
