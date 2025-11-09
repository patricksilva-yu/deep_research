from fastapi import APIRouter
from pydantic import BaseModel

from .agents import verification_agent
from .models import VerificationOutput

router = APIRouter(prefix="/verification", tags=["verification"])


class VerificationRequest(BaseModel):
    content: str


@router.post("/verify", response_model=VerificationOutput)
async def verify_research(request: VerificationRequest) -> VerificationOutput:
    """Verify research content for source credibility, factual consistency, and reasoning quality."""
    result = await verification_agent.run(request.content)
    return result.output
