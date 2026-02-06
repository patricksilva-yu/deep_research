"""Files API router for standalone file management endpoints."""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from typing import Annotated, List
import logging

from .models import FileUploadResponse, FileMetadata
from .validation import validate_upload_file
from .service import save_file, load_file_content
from .db import insert_file, get_files_for_conversation, get_file_by_id, update_file_status
from .vector_store_service import upload_file_to_openai
from auth.dependencies import get_current_user, CurrentUser
from auth.conversation_db import get_conversation

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/files", tags=["files"])


@router.post("/upload", response_model=FileUploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    conversation_id: int = None,
    current_user: Annotated[CurrentUser, Depends(get_current_user)] = None
) -> FileUploadResponse:
    """
    Upload a file and associate it with a conversation.

    This endpoint handles:
    - File validation (size, type, security)
    - Saving to local storage
    - Optional upload to OpenAI (for documents)
    - Recording metadata in database
    """
    try:
        # Verify conversation ownership
        if conversation_id:
            conversation = await get_conversation(conversation_id, current_user.user_id)
            if not conversation:
                raise HTTPException(status_code=404, detail="Conversation not found")

        # Validate file
        safe_filename, mime_type, file_type = await validate_upload_file(file)

        # Save file to local storage
        file_path, stored_filename, file_size = await save_file(
            file, conversation_id, safe_filename
        )

        # Insert file metadata into database
        file_id = await insert_file(
            conversation_id=conversation_id,
            filename=stored_filename,
            original_filename=safe_filename,
            file_path=file_path,
            file_size=file_size,
            mime_type=mime_type,
            file_type=file_type,
            status="uploaded"
        )

        # For documents, optionally upload to OpenAI for vector store
        openai_file_id = None
        if file_type == "document":
            try:
                openai_file_id = await upload_file_to_openai(file_path)
                await update_file_status(file_id, "processed", openai_file_id)
            except Exception as e:
                logger.warning(f"Failed to upload to OpenAI: {e}")
                # Continue anyway, file is saved locally

        return FileUploadResponse(
            file_id=file_id,
            filename=stored_filename,
            file_type=file_type,
            status="processed" if openai_file_id else "uploaded",
            openai_file_id=openai_file_id,
            message=f"File uploaded successfully as {file_type}"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading file: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload file")


@router.get("/conversation/{conversation_id}", response_model=List[FileMetadata])
async def list_conversation_files(
    conversation_id: int,
    current_user: Annotated[CurrentUser, Depends(get_current_user)]
) -> List[FileMetadata]:
    """List all files for a conversation."""
    try:
        # Verify conversation ownership
        conversation = await get_conversation(conversation_id, current_user.user_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        # Get files
        files = await get_files_for_conversation(conversation_id)
        return [FileMetadata(**file) for file in files]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing files: {e}")
        raise HTTPException(status_code=500, detail="Failed to list files")


@router.get("/{file_id}")
async def get_file(
    file_id: int,
    current_user: Annotated[CurrentUser, Depends(get_current_user)]
):
    """Get file metadata by ID."""
    try:
        file_data = await get_file_by_id(file_id)
        if not file_data:
            raise HTTPException(status_code=404, detail="File not found")

        # Verify user owns the conversation
        conversation = await get_conversation(file_data['conversation_id'], current_user.user_id)
        if not conversation:
            raise HTTPException(status_code=403, detail="Access denied")

        return FileMetadata(**file_data)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting file: {e}")
        raise HTTPException(status_code=500, detail="Failed to get file")
