from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, Annotated

from .agents import orchestrator_agent, OrchestratorState
from .models import OrchestratorOutput
from auth.dependencies import get_current_user, CurrentUser
from auth.conversation_db import (
    create_conversation, get_conversation, add_message,
    update_conversation_title
)
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])


class PlanRequest(BaseModel):
    """Request for creating a research plan."""
    query: str
    conversation_id: Optional[int] = None


@router.post("/plan", response_model=OrchestratorOutput)
async def create_plan(
    request: PlanRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)]
) -> OrchestratorOutput:
    """Generate a research plan and save to conversation history."""
    try:
        # 1. Create or use existing conversation
        if request.conversation_id:
            conversation = await get_conversation(request.conversation_id, current_user.user_id)
            if not conversation:
                raise HTTPException(status_code=404, detail="Conversation not found")
            conversation_id = request.conversation_id
        else:
            # Create new conversation with first 100 chars of query as title
            conversation = await create_conversation(current_user.user_id, request.query[:100])
            conversation_id = conversation.id

        # 2. Save user message
        await add_message(conversation_id, role="user", content=request.query)

        # 3. Run orchestrator agent
        state = OrchestratorState()
        result = await orchestrator_agent.run(request.query, deps=state)
        output = result.output  # OrchestratorOutput with plan and final_report

        # 4. Save assistant response with full metadata
        display_content = (
            output.final_report.executive_summary
            if output.final_report
            else f"Plan created with {len(output.plan.tasks)} tasks"
        )

        await add_message(
            conversation_id,
            role="assistant",
            content=display_content,
            metadata={
                "plan": output.plan.model_dump(),
                "final_report": output.final_report.model_dump() if output.final_report else None,
            }
        )

        # 5. Update conversation title to mission (more descriptive)
        await update_conversation_title(
            conversation_id,
            current_user.user_id,
            output.plan.mission[:100]
        )

        return output
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in create_plan: {e}")
        raise HTTPException(status_code=500, detail="Failed to create research plan")
