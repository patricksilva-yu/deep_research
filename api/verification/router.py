from fastapi import APIRouter, HTTPException
from pydantic_ai.exceptions import ModelHTTPError

from .agents import verification_agent
from .models import VerificationOutput

router = APIRouter(prefix="/verification", tags=["verification"])


@router.post("/verify", response_model=VerificationOutput)
async def verify_research(content: str) -> VerificationOutput:
    """Verify research content for source credibility, factual consistency, and reasoning quality."""
    try:
        result = await verification_agent.run(content)
        return result.output
    except ModelHTTPError as e:
        if e.status_code == 429:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Please try again in a few seconds. Details: {e.body.get('message', 'Rate limit error')}"
            )
        raise HTTPException(status_code=e.status_code, detail=str(e.body))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
