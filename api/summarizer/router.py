from fastapi import APIRouter, HTTPException
from pydantic_ai.exceptions import ModelHTTPError

from .agents import summarizer_agent
from .models import FinalReport, FinalReportInput

router = APIRouter(prefix="/summarizer", tags=["summarizer"])


class SummaryRequest(FinalReportInput):
    """Request payload for generating a final research report."""
    pass


@router.post("/report", response_model=FinalReport)
async def generate_report(request: SummaryRequest) -> FinalReport:
    """Create a final research report from completed tasks and verification feedback."""
    try:
        # Convert BaseModel to JSON string for the agent
        result = await summarizer_agent.run(request.model_dump_json(indent=2))
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
