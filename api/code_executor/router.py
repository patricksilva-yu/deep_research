import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pydantic_ai.exceptions import ModelHTTPError

from .agents import code_execution_agent
from .models import CodeExecutorOutput

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/code_executor", tags=["code_executor"])


class ExecutionRequest(BaseModel):
    """Simple request for executing code."""
    task: str


@router.post("/execute", response_model=CodeExecutorOutput)
async def execute_code(request: ExecutionRequest) -> CodeExecutorOutput:
    """Execute code based on the user's task description."""
    try:
        result = await code_execution_agent.run(request.task)
        return result.output
    except ModelHTTPError as exc:
        if exc.status_code == 429:
            raise HTTPException(
                status_code=429,
                detail=(
                    "Rate limit exceeded. Try again shortly. "
                    f"Details: {exc.body.get('message', 'Rate limit error')}"
                ),
            )
        raise HTTPException(status_code=exc.status_code, detail=str(exc.body))
    except Exception as exc:
        # Log full exception details server-side for debugging
        logger.exception("Unexpected error in code execution endpoint")
        # Return generic error message to client (no sensitive info)
        raise HTTPException(status_code=500, detail="Internal server error")
