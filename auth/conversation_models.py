"""
Pydantic models for conversation history functionality.
Defines request/response schemas for conversations and messages.
"""
from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Any


class ConversationCreate(BaseModel):
    """Request model for creating a new conversation."""
    title: str


class ConversationResponse(BaseModel):
    """Response model for conversation data."""
    id: int
    user_id: int
    title: str
    created_at: datetime
    updated_at: datetime


class MessageCreate(BaseModel):
    """Request model for adding a message to a conversation."""
    role: str  # 'user' or 'assistant'
    content: str
    metadata: Optional[dict[str, Any]] = None


class MessageResponse(BaseModel):
    """Response model for message data."""
    id: int
    conversation_id: int
    role: str
    content: str
    metadata: Optional[dict[str, Any]]
    created_at: datetime
