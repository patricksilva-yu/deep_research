"""OpenAI Vector Store service for managing file storage and retrieval."""
import os
import openai
from typing import List, Optional
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# Initialize OpenAI client
openai.api_key = os.getenv('OPENAI_API_KEY')
client = openai.AsyncOpenAI(api_key=os.getenv('OPENAI_API_KEY'))


async def upload_file_to_openai(
    file_path: str,
    purpose: str = "assistants"
) -> str:
    """
    Upload file to OpenAI Files API.

    Args:
        file_path: Path to the file to upload
        purpose: Purpose of the file (assistants, vision, etc.)

    Returns:
        OpenAI file ID
    """
    try:
        with open(file_path, 'rb') as f:
            file_response = await client.files.create(
                file=f,
                purpose=purpose
            )

        logger.info(f"Uploaded file to OpenAI: {file_response.id}")
        return file_response.id

    except Exception as e:
        logger.error(f"Error uploading file to OpenAI: {e}")
        raise


async def create_vector_store(
    name: str,
    file_ids: List[str],
    expires_after_days: int = 7
) -> tuple[str, int]:
    """
    Create a vector store in OpenAI with the given files.

    Args:
        name: Name for the vector store
        file_ids: List of OpenAI file IDs to add to the store
        expires_after_days: Number of days until vector store expires

    Returns:
        tuple: (vector_store_id, file_count)
    """
    try:
        vector_store = await client.vector_stores.create(
            name=name,
            file_ids=file_ids,
            expires_after={
                "anchor": "last_active_at",
                "days": expires_after_days
            }
        )

        logger.info(f"Created vector store: {vector_store.id} with {len(file_ids)} files")
        return vector_store.id, len(file_ids)

    except AttributeError as e:
        logger.warning(f"Vector stores API not available in this OpenAI client version - continuing without vector store: {e}")
        # Return a fallback ID to indicate vector store creation was skipped
        return None, len(file_ids)
    except Exception as e:
        logger.error(f"Error creating vector store: {e}")
        # Don't raise - allow the request to continue without vector store
        return None, len(file_ids)


async def add_files_to_vector_store(
    vector_store_id: str,
    file_ids: List[str]
) -> int:
    """
    Add files to an existing vector store.

    Args:
        vector_store_id: OpenAI vector store ID
        file_ids: List of OpenAI file IDs to add

    Returns:
        Number of files added
    """
    try:
        # Create a file batch
        file_batch = await client.vector_stores.file_batches.create(
            vector_store_id=vector_store_id,
            file_ids=file_ids
        )

        logger.info(f"Added {len(file_ids)} files to vector store {vector_store_id}")
        return len(file_ids)

    except Exception as e:
        logger.error(f"Error adding files to vector store: {e}")
        raise


async def delete_vector_store(vector_store_id: str) -> bool:
    """
    Delete a vector store from OpenAI.

    Args:
        vector_store_id: OpenAI vector store ID

    Returns:
        True if successful
    """
    try:
        await client.vector_stores.delete(vector_store_id)
        logger.info(f"Deleted vector store: {vector_store_id}")
        return True

    except Exception as e:
        logger.error(f"Error deleting vector store {vector_store_id}: {e}")
        return False


async def delete_file_from_openai(file_id: str) -> bool:
    """
    Delete a file from OpenAI Files API.

    Args:
        file_id: OpenAI file ID

    Returns:
        True if successful
    """
    try:
        await client.files.delete(file_id)
        logger.info(f"Deleted file from OpenAI: {file_id}")
        return True

    except Exception as e:
        logger.error(f"Error deleting file {file_id}: {e}")
        return False


async def get_vector_store_info(vector_store_id: str) -> Optional[dict]:
    """
    Get information about a vector store.

    Args:
        vector_store_id: OpenAI vector store ID

    Returns:
        Vector store information or None
    """
    try:
        vector_store = await client.vector_stores.retrieve(vector_store_id)
        return {
            'id': vector_store.id,
            'name': vector_store.name,
            'file_counts': vector_store.file_counts,
            'status': vector_store.status,
            'created_at': vector_store.created_at,
            'expires_at': vector_store.expires_at
        }

    except Exception as e:
        logger.error(f"Error retrieving vector store {vector_store_id}: {e}")
        return None
