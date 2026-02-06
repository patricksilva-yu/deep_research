"""
FastAPI dependencies for authentication and authorization.
Provides get_current_user dependency with proper Annotated syntax.
"""
from typing import Optional, Annotated
from fastapi import Depends, Cookie, HTTPException
import logging

from auth.sessions import get_session_manager
from auth.database import get_db
from auth import queries

logger = logging.getLogger(__name__)


class CurrentUser:
    """User object with session and database information."""

    def __init__(self, user_id: int, email: str):
        self.user_id = user_id
        self.email = email


async def get_current_user(
    session_id: Annotated[Optional[str], Cookie()] = None,
    db = Depends(get_db),
) -> CurrentUser:
    if not session_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    session_manager = get_session_manager()
    session_data = await session_manager.get_session(session_id)

    if not session_data:
        raise HTTPException(status_code=401, detail="Session expired")

    user_id = session_data.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid session")

    # Refresh session TTL (sliding window)
    await session_manager.refresh_session(session_id)

    # Fetch user from database
    user = await queries.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    if not user.get("is_active"):
        raise HTTPException(status_code=403, detail="User account is inactive")

    return CurrentUser(user_id=user["id"], email=user["email"])


async def get_current_user_optional(
    session_id: Annotated[Optional[str], Cookie()] = None,
    db = Depends(get_db),
) -> Optional[CurrentUser]:
    if not session_id:
        return None

    try:
        return await get_current_user(session_id=session_id, db=db)
    except HTTPException:
        return None
