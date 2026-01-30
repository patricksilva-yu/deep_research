"""
Flask authentication integration.
Provides before_request hook, login_required decorator, and g.user object.
Uses Upstash Redis for session management (same as FastAPI).

Note: Flask 2.0+ provides native async support for before_request hooks and views.
This eliminates the need for creating new event loops on every request.
"""
import logging
import os
from functools import wraps
from typing import Optional
from flask import g, request
from auth.sessions import get_session_manager
from auth import queries
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# API Configuration
API_BASE_URL = os.getenv("API_BASE_URL")


async def _get_user_from_session_async(session_id: str, csrf_token: str = None):
    if not session_id:
        return None

    # First, try local session manager
    session_manager = get_session_manager()
    session_data = await session_manager.get_session(session_id)

    if session_data:
        user_id = session_data.get("user_id")
        if user_id:
            # For Flask, we store just the user_id in g
            return {"user_id": user_id}

    # If not in local session, try FastAPI backend
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            headers = {}
            if csrf_token:
                headers["X-CSRF-Token"] = csrf_token

            response = await client.get(
                f"{API_BASE_URL}/auth/me",
                cookies={"session_id": session_id, "csrf_token": csrf_token or ""},
                headers=headers,
                timeout=5
            )
            if response.status_code == 200:
                user_data = response.json()
                return {"user_id": user_data.get("id")}
    except Exception as e:
        logger.warning(f"Failed to verify session with FastAPI backend: {e}")

    return None


async def _refresh_session_async(session_id: str):
    """Refresh session TTL. Called after successful session verification."""
    session_manager = get_session_manager()
    try:
        await session_manager.refresh_session(session_id)
    except Exception as e:
        logger.warning(f"Failed to refresh session: {e}")


def init_auth(app):

    @app.before_request
    async def check_session():
        """
        Async before_request hook for Flask 2.0+.

        Flask automatically manages the event loop for async before_request hooks.
        Redis client and session manager are created per-request to avoid event loop conflicts.
        """
        g.user = None
        session_id = request.cookies.get("session_id")
        csrf_token = request.cookies.get("csrf_token")

        if session_id:
            try:
                # Directly await the async function - Flask handles the event loop
                user = await _get_user_from_session_async(session_id, csrf_token)

                if user:
                    g.user = user
                    g.session_id = session_id

                    # Refresh session TTL - also awaited directly
                    await _refresh_session_async(session_id)
            except Exception as e:
                logger.warning(f"Session check failed: {e}")
                g.user = None


def login_required(f):

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not g.get("user"):
            # Redirect to login page
            from flask import redirect, url_for
            return redirect(url_for("sign_in") if hasattr(__builtins__, "sign_in") else "/sign-in")
        return f(*args, **kwargs)

    return decorated_function


def optional_login(f):

    @wraps(f)
    def decorated_function(*args, **kwargs):
        # g.user is already set by before_request hook
        return f(*args, **kwargs)

    return decorated_function
