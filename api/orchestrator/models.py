from pydantic import BaseModel, Field
from typing import List


class ResearchTask(BaseModel):
    """A single research task to be executed."""
    task_id: str = Field(description="Unique identifier for this task")
    description: str = Field(description="What needs to be researched")
    search_query: str = Field(description="Query to pass to the web search agent")


class ResearchPlan(BaseModel):
    """Simple research plan with ordered tasks."""
    mission: str = Field(description="What we're trying to research")
    tasks: List[ResearchTask] = Field(description="Ordered list of search tasks")
    next_steps: List[str] = Field(description="What to do after planning")


class OrchestratorOutput(BaseModel):
    """Output from the orchestrator agent."""
    plan: ResearchPlan = Field(description="The research plan")
