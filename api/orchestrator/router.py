from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pydantic_ai.exceptions import ModelHTTPError

from .agents import orchestrator_agent
from .models import OrchestratorOutput

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])


class PlanRequest(BaseModel):
    """Simple request for creating a research plan."""
    query: str


@router.post("/plan", response_model=OrchestratorOutput)
async def create_plan(request: PlanRequest) -> OrchestratorOutput:
    """Generate a research plan using the orchestrator agent."""
    try:
        result = await orchestrator_agent.run(request.query)
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
        raise HTTPException(status_code=500, detail=f"Internal server error: {exc}")
