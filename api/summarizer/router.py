from fastapi import APIRouter

from .agents import summarizer_agent
from .models import FinalReport, FinalReportInput

router = APIRouter(prefix="/summarizer", tags=["summarizer"])


@router.post("/report", response_model=FinalReport)
async def generate_report(request: FinalReportInput) -> FinalReport:
    """Create a final research report from completed tasks and verification feedback."""
    # Convert BaseModel to JSON string for the agent
    result = await summarizer_agent.run(request.model_dump_json(indent=2))
    return result.output
