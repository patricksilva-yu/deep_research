from fastapi import APIRouter

from .agents import verification_agent
from .models import VerificationOutput

router = APIRouter(prefix="/verification", tags=["verification"])


@router.post("/verify", response_model=VerificationOutput)
async def verify_research(content: str) -> VerificationOutput:
    """Verify research content for source credibility, factual consistency, and reasoning quality."""
    result = await verification_agent.run(content)
    return result.output
