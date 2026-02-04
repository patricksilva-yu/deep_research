"""Database operations for files and vector stores."""
from typing import Optional, List, Literal
from datetime import datetime
import logging

from auth.database import get_pool

logger = logging.getLogger(__name__)


async def insert_file(
    conversation_id: int,
    filename: str,
    original_filename: str,
    file_path: str,
    file_size: int,
    mime_type: str,
    file_type: Literal["image", "document", "other"],
    openai_file_id: Optional[str] = None,
    status: Literal["pending", "uploaded", "processed", "error"] = "pending"
) -> int:
    """Insert file metadata into database."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO files (
                conversation_id, filename, original_filename, file_path,
                file_size, mime_type, file_type, openai_file_id, status
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING id
            """,
            conversation_id, filename, original_filename, file_path,
            file_size, mime_type, file_type, openai_file_id, status
        )
        return row['id']


async def update_file_status(
    file_id: int,
    status: Literal["pending", "uploaded", "processed", "error"],
    openai_file_id: Optional[str] = None
) -> None:
    """Update file status and OpenAI file ID."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        if openai_file_id:
            await conn.execute(
                """
                UPDATE files
                SET status = $1, openai_file_id = $2
                WHERE id = $3
                """,
                status, openai_file_id, file_id
            )
        else:
            await conn.execute(
                """
                UPDATE files
                SET status = $1
                WHERE id = $2
                """,
                status, file_id
            )


async def get_files_for_conversation(conversation_id: int) -> List[dict]:
    """Get all files for a conversation."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, conversation_id, filename, original_filename, file_path,
                   file_size, mime_type, file_type, openai_file_id, status, created_at
            FROM files
            WHERE conversation_id = $1
            ORDER BY created_at DESC
            """,
            conversation_id
        )
        return [dict(row) for row in rows]


async def get_file_by_id(file_id: int) -> Optional[dict]:
    """Get file metadata by ID."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, conversation_id, filename, original_filename, file_path,
                   file_size, mime_type, file_type, openai_file_id, status, created_at
            FROM files
            WHERE id = $1
            """,
            file_id
        )
        return dict(row) if row else None


async def delete_files_for_conversation(conversation_id: int) -> None:
    """Delete all file records for a conversation."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM files WHERE conversation_id = $1",
            conversation_id
        )


# Vector store operations

async def insert_vector_store(
    conversation_id: int,
    openai_vector_store_id: str,
    name: Optional[str] = None,
    file_count: int = 0,
    expires_at: Optional[datetime] = None
) -> int:
    """Insert vector store metadata into database."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO vector_stores (
                conversation_id, openai_vector_store_id, name, file_count, expires_at
            )
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id
            """,
            conversation_id, openai_vector_store_id, name, file_count, expires_at
        )
        return row['id']


async def get_vector_stores_for_conversation(conversation_id: int) -> List[dict]:
    """Get all vector stores for a conversation."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, conversation_id, openai_vector_store_id, name,
                   file_count, status, created_at, expires_at
            FROM vector_stores
            WHERE conversation_id = $1 AND status = 'active'
            ORDER BY created_at DESC
            """,
            conversation_id
        )
        return [dict(row) for row in rows]


async def update_vector_store_status(
    vector_store_id: int,
    status: Literal["active", "expired", "deleted"]
) -> None:
    """Update vector store status."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE vector_stores
            SET status = $1
            WHERE id = $2
            """,
            status, vector_store_id
        )


async def delete_vector_stores_for_conversation(conversation_id: int) -> List[str]:
    """
    Mark vector stores as deleted and return their OpenAI IDs.

    Returns:
        List of OpenAI vector store IDs to delete from OpenAI API
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            UPDATE vector_stores
            SET status = 'deleted'
            WHERE conversation_id = $1 AND status = 'active'
            RETURNING openai_vector_store_id
            """,
            conversation_id
        )
        return [row['openai_vector_store_id'] for row in rows]
