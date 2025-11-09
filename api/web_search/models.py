from pydantic import BaseModel, HttpUrl, Field
from typing import Optional, List
from enum import Enum


class RelevanceScore(str, Enum):
    """Relevance score for search findings."""
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class SearchAgentFinding(BaseModel):
    """Individual finding from web search with citation."""
    topic_subtopic: str = Field(
        description="The topic or subtopic this finding relates to"
    )
    key_finding: str = Field(
        description="The specific information or insight discovered"
    )
    source_title: str = Field(
        description="Title of the source document/article"
    )
    source_url: HttpUrl = Field(
        description="URL of the source"
    )
    publication_date: Optional[str] = Field(
        default=None,
        description="Publication date of the source (if available)"
    )
    relevance_score: RelevanceScore = Field(
        description="How relevant this finding is to the research query"
    )


class SearchAgentOutput(BaseModel):
    """Output from the web search agent."""
    findings: List[SearchAgentFinding] = Field(
        description="List of research findings with citations"
    )
    summary: str = Field(
        description="Brief synthesis of what was found"
    )
    gaps: Optional[List[str]] = Field(
        default=None,
        description="Areas where more research is needed or information is limited"
    )
