import logging
from fastapi import APIRouter, HTTPException
from pydantic_ai.exceptions import ModelHTTPError

from .agents import summarizer_agent
from .models import FinalReport, FinalReportInput

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/summarizer", tags=["summarizer"])


@router.post("/report", response_model=FinalReport)
async def generate_report(request: FinalReportInput) -> FinalReport:
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
        # Log full exception details server-side for debugging
        logger.exception("Unexpected error in summarizer endpoint")
        # Return generic error message to client (no sensitive info)
        raise HTTPException(status_code=500, detail="Internal server error")
