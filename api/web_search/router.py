from fastapi import APIRouter, HTTPException
from pydantic_ai.exceptions import ModelHTTPError
from .agents import web_search_agent
from .models import SearchAgentOutput

router = APIRouter(prefix="/web-search", tags=["web-search"])

@router.post("/search", response_model=SearchAgentOutput)
async def search_web(query: str):
    """Execute web search using the research agent."""
    try:
        result = await web_search_agent.run(query)
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