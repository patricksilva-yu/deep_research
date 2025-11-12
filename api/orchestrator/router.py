from fastapi import APIRouter
from pydantic import BaseModel

from .agents import orchestrator_agent, OrchestratorState
from .models import OrchestratorOutput

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])


class PlanRequest(BaseModel):
    """Simple request for creating a research plan."""
    query: str


@router.post("/plan", response_model=OrchestratorOutput)
async def create_plan(request: PlanRequest) -> OrchestratorOutput:
    """Generate a research plan using the orchestrator agent."""
    # Create fresh state for this request
    state = OrchestratorState()
    result = await orchestrator_agent.run(request.query, deps=state)
    return result.output
