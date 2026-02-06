"""File storage service for saving and loading files."""
import os
import uuid
import aiofiles
from pathlib import Path
from fastapi import UploadFile, HTTPException
from typing import Literal
import logging

logger = logging.getLogger(__name__)

# Upload directory
UPLOAD_DIR = Path(os.getenv('UPLOAD_DIR', '/app/uploads'))


def get_upload_path(conversation_id: int, filename: str) -> Path:
    """Generate storage path for uploaded file."""
    # Create subdirectory per conversation
    conversation_dir = UPLOAD_DIR / str(conversation_id)
    conversation_dir.mkdir(parents=True, exist_ok=True)

    # Generate unique filename to avoid collisions
    file_ext = Path(filename).suffix
    unique_filename = f"{uuid.uuid4()}{file_ext}"

    return conversation_dir / unique_filename


async def save_file(
    file: UploadFile,
    conversation_id: int,
    safe_filename: str
) -> tuple[str, str, int]:
    """
    Save uploaded file to disk.

    Args:
        file: FastAPI UploadFile object
        conversation_id: ID of the conversation
        safe_filename: Sanitized filename

    Returns:
        tuple: (storage_path, stored_filename, file_size)
    """
    try:
        # Generate storage path
        storage_path = get_upload_path(conversation_id, safe_filename)

        # Seek back to start in case file was already read (e.g., for validation)
        await file.seek(0)

        # Read file content
        content = await file.read()
        file_size = len(content)

        # Save file to disk
        async with aiofiles.open(storage_path, 'wb') as f:
            await f.write(content)

        logger.info(f"Saved file {safe_filename} to {storage_path} ({file_size} bytes)")

        return str(storage_path), storage_path.name, file_size

    except Exception as e:
        logger.error(f"Error saving file {safe_filename}: {e}")
        raise HTTPException(status_code=500, detail="Failed to save file")


async def load_file_content(file_path: str) -> bytes:
    """
    Load file content from disk.

    Args:
        file_path: Path to the file

    Returns:
        bytes: File content
    """
    try:
        path = Path(file_path)
        if not path.exists():
            raise HTTPException(status_code=404, detail="File not found")

        async with aiofiles.open(path, 'rb') as f:
            content = await f.read()

        return content

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error loading file {file_path}: {e}")
        raise HTTPException(status_code=500, detail="Failed to load file")


async def delete_file(file_path: str) -> None:
    """
    Delete file from disk.

    Args:
        file_path: Path to the file
    """
    try:
        path = Path(file_path)
        if path.exists():
            path.unlink()
            logger.info(f"Deleted file {file_path}")
        else:
            logger.warning(f"File not found for deletion: {file_path}")

    except Exception as e:
        logger.error(f"Error deleting file {file_path}: {e}")
        # Don't raise exception for delete failures
