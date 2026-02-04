"""File validation utilities."""
import magic
import os
from pathlib import Path
from fastapi import UploadFile, HTTPException
from typing import Literal


# Allowed file extensions
ALLOWED_EXTENSIONS = {
    'pdf', 'png', 'jpg', 'jpeg', 'gif', 'csv', 'txt', 'md', 'json', 'xlsx'
}

# MIME type to file type mapping
MIME_TYPE_MAPPING = {
    'image/png': 'image',
    'image/jpeg': 'image',
    'image/jpg': 'image',
    'image/gif': 'image',
    'application/pdf': 'document',
    'text/plain': 'document',
    'text/csv': 'document',
    'text/markdown': 'document',
    'application/json': 'document',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'document',
}

# Max file size (50MB default)
MAX_FILE_SIZE = int(os.getenv('MAX_FILE_SIZE', 52428800))


def get_file_extension(filename: str) -> str:
    """Extract file extension from filename."""
    return Path(filename).suffix.lstrip('.').lower()


def validate_file_extension(filename: str) -> None:
    """Validate file extension against allowed list."""
    ext = get_file_extension(filename)
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type .{ext} not allowed. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"
        )


def validate_file_size(file_size: int) -> None:
    """Validate file size is within limits."""
    if file_size > MAX_FILE_SIZE:
        max_mb = MAX_FILE_SIZE / (1024 * 1024)
        raise HTTPException(
            status_code=400,
            detail=f"File size exceeds maximum allowed size of {max_mb}MB"
        )


def detect_mime_type(file_content: bytes) -> str:
    """Detect MIME type from file content using python-magic."""
    try:
        mime = magic.Magic(mime=True)
        return mime.from_buffer(file_content)
    except Exception:
        return "application/octet-stream"


def categorize_file_type(mime_type: str) -> Literal["image", "document", "other"]:
    """Categorize file based on MIME type."""
    return MIME_TYPE_MAPPING.get(mime_type, "other")


def prevent_path_traversal(filename: str) -> str:
    """Sanitize filename to prevent path traversal attacks."""
    # Remove any path components, keep only the filename
    safe_filename = os.path.basename(filename)

    # Remove any potentially dangerous characters
    safe_filename = safe_filename.replace('..', '').replace('/', '').replace('\\', '')

    if not safe_filename:
        raise HTTPException(
            status_code=400,
            detail="Invalid filename"
        )

    return safe_filename


async def validate_upload_file(file: UploadFile) -> tuple[str, str, Literal["image", "document", "other"]]:
    """
    Validate uploaded file and return sanitized filename, MIME type, and file type.

    Returns:
        tuple: (sanitized_filename, mime_type, file_type)
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    # Validate extension
    validate_file_extension(file.filename)

    # Sanitize filename
    safe_filename = prevent_path_traversal(file.filename)

    # Read file content for validation
    content = await file.read()

    # Validate file size
    validate_file_size(len(content))

    # Detect MIME type
    mime_type = detect_mime_type(content)

    # Categorize file type
    file_type = categorize_file_type(mime_type)

    # Reset file pointer for later reading
    await file.seek(0)

    return safe_filename, mime_type, file_type
