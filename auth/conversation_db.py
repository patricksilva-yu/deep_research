"""
Database operations for conversation history.
Handles CRUD operations for conversations and messages using asyncpg.
"""
from typing import List, Optional
from datetime import datetime
from auth.database import get_pool
from auth.conversation_models import ConversationResponse, MessageResponse
import json
import logging

logger = logging.getLogger(__name__)


async def create_conversation(user_id: int, title: str) -> ConversationResponse:
    """Create a new conversation."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO conversations (user_id, title)
            VALUES ($1, $2)
            RETURNING id, user_id, title, created_at, updated_at
            """,
            user_id, title
        )
        if not row:
            raise RuntimeError("Failed to create conversation")
        return ConversationResponse(**dict(row))


async def get_user_conversations(user_id: int, limit: int = 50) -> List[ConversationResponse]:
    """Get all conversations for a user, ordered by most recent."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, user_id, title, created_at, updated_at
            FROM conversations
            WHERE user_id = $1
            ORDER BY updated_at DESC
            LIMIT $2
            """,
            user_id, limit
        )
        return [ConversationResponse(**dict(row)) for row in rows]


async def get_conversation(conversation_id: int, user_id: int) -> Optional[ConversationResponse]:
    """Get a specific conversation (with user ownership check)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, user_id, title, created_at, updated_at
            FROM conversations
            WHERE id = $1 AND user_id = $2
            """,
            conversation_id, user_id
        )
        return ConversationResponse(**dict(row)) if row else None


async def add_message(
    conversation_id: int,
    role: str,
    content: str,
    metadata: Optional[dict] = None
) -> MessageResponse:
    """Add a message to a conversation and update conversation timestamp."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Insert message - asyncpg handles JSONB serialization automatically
            metadata_json = json.dumps(metadata) if metadata else None
            row = await conn.fetchrow(
                """
                INSERT INTO messages (conversation_id, role, content, metadata)
                VALUES ($1, $2, $3, $4)
                RETURNING id, conversation_id, role, content, metadata, created_at
                """,
                conversation_id, role, content, metadata_json
            )

            if not row:
                raise RuntimeError("Failed to add message")

            # Update conversation updated_at
            await conn.execute(
                """
                UPDATE conversations
                SET updated_at = CURRENT_TIMESTAMP
                WHERE id = $1
                """,
                conversation_id
            )

            # Convert row to dict and parse metadata back from JSON string
            row_dict = dict(row)
            if row_dict['metadata'] is not None:
                if isinstance(row_dict['metadata'], str):
                    row_dict['metadata'] = json.loads(row_dict['metadata'])

            return MessageResponse(**row_dict)


async def get_conversation_messages(conversation_id: int, user_id: int) -> List[MessageResponse]:
    """Get all messages for a conversation (with user ownership check)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Verify ownership
        owner_check = await conn.fetchval(
            "SELECT user_id FROM conversations WHERE id = $1",
            conversation_id
        )
        if owner_check != user_id:
            return []

        # Fetch messages
        rows = await conn.fetch(
            """
            SELECT id, conversation_id, role, content, metadata, created_at
            FROM messages
            WHERE conversation_id = $1
            ORDER BY created_at ASC
            """,
            conversation_id
        )

        messages = []
        for row in rows:
            row_dict = dict(row)
            # Parse metadata from JSON string
            if row_dict['metadata'] is not None:
                if isinstance(row_dict['metadata'], str):
                    row_dict['metadata'] = json.loads(row_dict['metadata'])
            messages.append(MessageResponse(**row_dict))

        return messages


async def delete_conversation(conversation_id: int, user_id: int) -> bool:
    """Delete a conversation (with user ownership check)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            DELETE FROM conversations
            WHERE id = $1 AND user_id = $2
            """,
            conversation_id, user_id
        )
        # Result is a string like "DELETE 1", extract the count
        return "1" in result


async def update_conversation_title(conversation_id: int, user_id: int, title: str) -> bool:
    """Update conversation title (with user ownership check)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE conversations
            SET title = $1, updated_at = CURRENT_TIMESTAMP
            WHERE id = $2 AND user_id = $3
            """,
            title, conversation_id, user_id
        )
        # Result is a string like "UPDATE 1", extract the count
        return "1" in result
