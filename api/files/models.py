"""Models for file upload and vector store management."""
from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime


class FileStatus(str):
    """File processing status."""
    PENDING = "pending"
    UPLOADED = "uploaded"
    PROCESSED = "processed"
    ERROR = "error"


class FileType(str):
    """File type categories."""
    IMAGE = "image"
    DOCUMENT = "document"
    OTHER = "other"


class FileMetadata(BaseModel):
    """Metadata for an uploaded file."""
    id: int
    conversation_id: int
    filename: str
    original_filename: str
    file_path: str
    file_size: int
    mime_type: str
    file_type: Literal["image", "document", "other"]
    openai_file_id: Optional[str] = None
    status: Literal["pending", "uploaded", "processed", "error"]
    created_at: datetime


class FileUploadResponse(BaseModel):
    """Response after file upload."""
    file_id: int
    filename: str
    file_type: Literal["image", "document", "other"]
    status: Literal["pending", "uploaded", "processed", "error"]
    openai_file_id: Optional[str] = None
    message: str = Field(description="Status message")


class VectorStoreMetadata(BaseModel):
    """Metadata for a vector store."""
    id: int
    conversation_id: int
    openai_vector_store_id: str
    name: Optional[str] = None
    file_count: int = 0
    status: Literal["active", "expired", "deleted"]
    created_at: datetime
    expires_at: Optional[datetime] = None
