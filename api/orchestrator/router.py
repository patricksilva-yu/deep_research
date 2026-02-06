from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from typing import Optional, Annotated, List
from pydantic_ai.messages import BinaryContent

from .agents import orchestrator_agent, OrchestratorState, create_orchestrator_agent
from .models import OrchestratorOutput
from auth.dependencies import get_current_user, CurrentUser
from auth.conversation_db import (
    create_conversation, get_conversation, add_message,
    update_conversation_title
)
from api.files.validation import validate_upload_file
from api.files.service import save_file, load_file_content
from api.files.db import insert_file, update_file_status, insert_vector_store
from api.files.vector_store_service import upload_file_to_openai, create_vector_store
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])


class PlanRequest(BaseModel):
    """Request for creating a research plan."""
    query: str
    conversation_id: Optional[int] = None


@router.post("/plan", response_model=OrchestratorOutput)
async def create_plan(
    query: Annotated[str, Form()],
    conversation_id: Annotated[Optional[int], Form()] = None,
    files: List[UploadFile] = File(default=[]),
    current_user: Annotated[CurrentUser, Depends(get_current_user)] = None
) -> OrchestratorOutput:
    """Generate a research plan with optional file uploads and save to conversation history."""
    try:
        # 1. Create or use existing conversation
        if conversation_id:
            conversation = await get_conversation(conversation_id, current_user.user_id)
            if not conversation:
                raise HTTPException(status_code=404, detail="Conversation not found")
            conv_id = conversation_id
        else:
            # Create new conversation with first 100 chars of query as title
            conversation = await create_conversation(current_user.user_id, query[:100])
            conv_id = conversation.id

        # 2. Process uploaded files
        image_contents = []
        document_file_ids = []
        vector_store_id = None

        logger.info(f"Processing {len(files)} uploaded files")
        for file in files:
            try:
                # Validate file
                safe_filename, mime_type, file_type = await validate_upload_file(file)

                # Save file to local storage
                file_path, stored_filename, file_size = await save_file(
                    file, conv_id, safe_filename
                )

                # Insert file metadata into database
                file_id = await insert_file(
                    conversation_id=conv_id,
                    filename=stored_filename,
                    original_filename=safe_filename,
                    file_path=file_path,
                    file_size=file_size,
                    mime_type=mime_type,
                    file_type=file_type,
                    status="uploaded"
                )

                # Process based on file type
                if file_type == "image":
                    # Load image content for BinaryContent
                    content = await load_file_content(file_path)
                    image_contents.append(BinaryContent(data=content, media_type=mime_type))
                    await update_file_status(file_id, "processed")
                    logger.info(f"Processed image file: {safe_filename}")

                elif file_type == "document":
                    # Upload to OpenAI for vector store
                    openai_file_id = await upload_file_to_openai(file_path, purpose="assistants")
                    document_file_ids.append(openai_file_id)
                    await update_file_status(file_id, "processed", openai_file_id)
                    logger.info(f"Uploaded document to OpenAI: {safe_filename}")

            except Exception as e:
                logger.error(f"Error processing file {file.filename}: {e}")
                # Continue with other files

        # 3. Create vector store if documents were uploaded
        logger.info(f"Document file IDs collected: {len(document_file_ids)}")
        if document_file_ids:
            logger.info(f"Attempting to create vector store with {len(document_file_ids)} document(s)")
            try:
                vector_store_openai_id, file_count = await create_vector_store(
                    name=f"Conversation {conv_id} Documents",
                    file_ids=document_file_ids,
                    expires_after_days=7
                )
                logger.info(f"Vector store creation result: ID={vector_store_openai_id}, files={file_count}")

                # Only save if vector store was successfully created
                if vector_store_openai_id:
                    vector_store_id = vector_store_openai_id

                    # Save vector store to database
                    await insert_vector_store(
                        conversation_id=conv_id,
                        openai_vector_store_id=vector_store_openai_id,
                        name=f"Conversation {conv_id} Documents",
                        file_count=file_count
                    )
                    logger.info(f"✓ Vector store created successfully: {vector_store_openai_id} with {file_count} documents")
                else:
                    logger.warning(f"Vector store creation returned None, continuing without file search")

            except Exception as e:
                logger.error(f"✗ Error creating vector store: {e}", exc_info=True)
                # Continue without vector store
        else:
            logger.info("No document files to upload, skipping vector store creation")

        logger.info(f"Vector store ID for agent: {vector_store_id}")

        # 4. Save user message
        await add_message(conv_id, role="user", content=query)

        # 5. Build prompt with images
        user_prompt = [query]
        if image_contents:
            user_prompt.extend(image_contents)
            logger.info(f"Added {len(image_contents)} images to prompt")

        # 6. Run orchestrator agent with optional file search for documents
        state = OrchestratorState()

        if vector_store_id:
            # Create agent with FileSearchTool for document search
            logger.info(f"Running orchestrator agent with FileSearchTool for vector store {vector_store_id}")
            agent = create_orchestrator_agent(vector_store_id)
            result = await agent.run(user_prompt, deps=state)
        else:
            logger.info("Running orchestrator agent without file search")
            result = await orchestrator_agent.run(user_prompt, deps=state)

        output = result.output  # OrchestratorOutput with plan and final_report

        # 7. Save assistant response with full metadata
        display_content = (
            output.final_report.executive_summary
            if output.final_report
            else f"Plan created with {len(output.plan.tasks)} tasks"
        )

        await add_message(
            conv_id,
            role="assistant",
            content=display_content,
            metadata={
                "plan": output.plan.model_dump(),
                "final_report": output.final_report.model_dump() if output.final_report else None,
                "files_uploaded": len(files),
                "vector_store_id": vector_store_id
            }
        )

        # 8. Update conversation title to mission (more descriptive)
        await update_conversation_title(
            conv_id,
            current_user.user_id,
            output.plan.mission[:100]
        )

        return output
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in create_plan: {e}")
        raise HTTPException(status_code=500, detail="Failed to create research plan")
