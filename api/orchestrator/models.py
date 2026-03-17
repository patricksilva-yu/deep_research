from typing import List, Optional

from pydantic import BaseModel, Field

from api.research_runtime.models import FinalReport


class ResearchTask(BaseModel):
    """A single research task to be executed."""
    task_id: str = Field(description="Unique identifier for this task")
    description: str = Field(description="What needs to be researched")
    search_query: str = Field(description="Query to pass to the research search tool")


class ResearchPlan(BaseModel):
    """Simple research plan with ordered tasks."""
    mission: str = Field(description="What we're trying to research")
    tasks: List[ResearchTask] = Field(description="Ordered list of research tasks")
    next_steps: List[str] = Field(description="What to do after planning")


class OrchestratorOutput(BaseModel):
    """Output from the single research agent."""
    plan: ResearchPlan = Field(description="The research plan")
    final_report: Optional[FinalReport] = Field(
        default=None,
        description="The final synthesized research report, generated after executing all tasks",
    )
