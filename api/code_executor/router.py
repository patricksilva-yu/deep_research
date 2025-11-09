from fastapi import APIRouter
from pydantic import BaseModel

from .agents import code_execution_agent
from .models import CodeExecutorOutput

router = APIRouter(prefix="/code_executor", tags=["code_executor"])


class ExecutionRequest(BaseModel):
    """Simple request for executing code."""
    task: str


@router.post("/execute", response_model=CodeExecutorOutput)
async def execute_code(request: ExecutionRequest) -> CodeExecutorOutput:
    """Execute code based on the user's task description."""
    result = await code_execution_agent.run(request.task)
    return result.output
