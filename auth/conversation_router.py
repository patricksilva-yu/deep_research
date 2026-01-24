"""
FastAPI router for conversation history endpoints.
Provides CRUD operations for conversations and messages.
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Annotated

from auth.conversation_models import (
    ConversationCreate, ConversationResponse,
    MessageCreate, MessageResponse
)
from auth.conversation_db import (
    create_conversation, get_user_conversations,
    get_conversation, add_message,
    get_conversation_messages, delete_conversation,
    update_conversation_title
)
from auth.dependencies import get_current_user, CurrentUser
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post("/", response_model=ConversationResponse)
async def create_new_conversation(
    conversation: ConversationCreate,
    current_user: Annotated[CurrentUser, Depends(get_current_user)]
) -> ConversationResponse:
    """Create a new conversation."""
    try:
        return await create_conversation(current_user.user_id, conversation.title)
    except Exception as e:
        logger.error(f"Error creating conversation: {e}")
        raise HTTPException(status_code=500, detail="Failed to create conversation")


@router.get("/", response_model=List[ConversationResponse])
async def list_conversations(
    limit: int = 50,
    current_user: Annotated[CurrentUser, Depends(get_current_user)] = None
) -> List[ConversationResponse]:
    """Get all conversations for the current user."""
    try:
        return await get_user_conversations(current_user.user_id, limit)
    except Exception as e:
        logger.error(f"Error listing conversations: {e}")
        raise HTTPException(status_code=500, detail="Failed to list conversations")


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation_by_id(
    conversation_id: int,
    current_user: Annotated[CurrentUser, Depends(get_current_user)]
) -> ConversationResponse:
    """Get a specific conversation."""
    try:
        conversation = await get_conversation(conversation_id, current_user.user_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return conversation
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting conversation: {e}")
        raise HTTPException(status_code=500, detail="Failed to get conversation")


@router.get("/{conversation_id}/messages", response_model=List[MessageResponse])
async def get_messages(
    conversation_id: int,
    current_user: Annotated[CurrentUser, Depends(get_current_user)]
) -> List[MessageResponse]:
    """Get all messages in a conversation."""
    try:
        # Verify conversation exists and belongs to user
        conversation = await get_conversation(conversation_id, current_user.user_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        messages = await get_conversation_messages(conversation_id, current_user.user_id)
        return messages
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting messages: {e}")
        raise HTTPException(status_code=500, detail="Failed to get messages")


@router.post("/{conversation_id}/messages", response_model=MessageResponse)
async def add_message_to_conversation(
    conversation_id: int,
    message: MessageCreate,
    current_user: Annotated[CurrentUser, Depends(get_current_user)]
) -> MessageResponse:
    """Add a message to a conversation."""
    try:
        # Verify conversation exists and belongs to user
        conversation = await get_conversation(conversation_id, current_user.user_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        return await add_message(
            conversation_id,
            message.role,
            message.content,
            message.metadata
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding message: {e}")
        raise HTTPException(status_code=500, detail="Failed to add message")


@router.delete("/{conversation_id}")
async def delete_conversation_by_id(
    conversation_id: int,
    current_user: Annotated[CurrentUser, Depends(get_current_user)]
):
    """Delete a conversation."""
    try:
        deleted = await delete_conversation(conversation_id, current_user.user_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return {"detail": "Conversation deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting conversation: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete conversation")


@router.patch("/{conversation_id}/title")
async def update_title(
    conversation_id: int,
    conversation: ConversationCreate,
    current_user: Annotated[CurrentUser, Depends(get_current_user)]
):
    """Update conversation title."""
    try:
        updated = await update_conversation_title(
            conversation_id,
            current_user.user_id,
            conversation.title
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return {"detail": "Title updated"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating conversation title: {e}")
        raise HTTPException(status_code=500, detail="Failed to update title")
