from typing import List, Optional
from pydantic import BaseModel, Field

from api.web_search.models import SearchAgentFinding
from api.verification.models import SourceAssessment, ConsistencyIssue


class CompletedTaskSummary(BaseModel):
    """Result of a completed research task."""
    task_id: str = Field(description="Identifier of the completed task")
    description: str = Field(description="What the task attempted to accomplish")
    summary: str = Field(description="Short narrative of the findings for this task")
    findings: List[SearchAgentFinding] = Field(
        description="Structured findings returned by the web search agent"
    )
    gaps: Optional[List[str]] = Field(
        default=None,
        description="Any remaining gaps or follow-up questions from the task"
    )


class VerificationSummary(BaseModel):
    """Digest of verification output to guide the summarizer."""
    overall_quality_rating: str = Field(description="Overall quality rating from verification")
    approved_for_use: bool = Field(description="Whether the research is approved for use")
    source_assessments: List[SourceAssessment] = Field(
        default_factory=list,
        description="Per-source credibility assessments"
    )
    consistency_issues: List[ConsistencyIssue] = Field(
        default_factory=list,
        description="Issues that should be acknowledged in the final report"
    )
    critical_flags: Optional[List[str]] = Field(
        default=None,
        description="Critical problems that require immediate attention"
    )
    improvement_priority: List[str] = Field(
        default_factory=list,
        description="Suggested follow-up actions from verification"
    )


class FinalReportInput(BaseModel):
    """Information the summarizer agent receives."""
    mission: str = Field(description="Overall mission statement from the research plan")
    tasks: List[CompletedTaskSummary] = Field(
        description="Completed task outputs from the orchestrator"
    )
    verification: Optional[VerificationSummary] = Field(
        default=None,
        description="Verification summary if quality checks were completed"
    )


class ReportSection(BaseModel):
    """Section within the synthesized final report."""
    title: str = Field(description="Heading for this section")
    summary: str = Field(description="Brief paragraph summarizing this section")
    supporting_points: List[str] = Field(
        default_factory=list,
        description="Bulleted supporting points derived from the findings"
    )


class FinalReport(BaseModel):
    """Structured final report produced by the summarizer agent."""
    mission: str = Field(description="Restated mission to anchor the report")
    executive_summary: str = Field(description="Top-level synthesis of the research")
    sections: List[ReportSection] = Field(
        description="Detailed sections covering major themes"
    )
    recommended_actions: Optional[List[str]] = Field(
        default=None,
        description="Optional action items or recommendations"
    )
    quality_notes: Optional[str] = Field(
        default=None,
        description="Notes about research quality, limitations, or verification outcomes"
    )
    sources: List[str] = Field(
        default_factory=list,
        description="List of deduplicated citation strings or URLs referenced in the report"
    )
