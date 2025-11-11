from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum


class CredibilityRating(str, Enum):
    """Credibility rating for sources."""
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class IssueSeverity(str, Enum):
    """Severity level for identified issues."""
    CRITICAL = "Critical"
    MAJOR = "Major"
    MINOR = "Minor"


class SourceAssessment(BaseModel):
    """Assessment of a single source's credibility."""
    source_title: str = Field(description="Title or name of the source")
    credibility_rating: CredibilityRating = Field(description="Overall credibility rating")
    reasoning: str = Field(description="Explanation of the credibility rating")


class ConsistencyIssue(BaseModel):
    """An identified inconsistency or factual issue."""
    severity: IssueSeverity = Field(description="How severe this issue is")
    description: str = Field(description="Detailed description of the issue")
    suggested_action: str = Field(description="Recommended action to address this issue")


class VerificationOutput(BaseModel):
    """Complete output from the verification agent."""
    summary: str = Field(description="Executive summary of the verification assessment")
    overall_quality_rating: str = Field(description="Overall quality rating")
    source_assessments: List[SourceAssessment] = Field(description="Credibility assessment for each source")
    consistency_issues: List[ConsistencyIssue] = Field(description="List of identified consistency or factual issues")
    critical_flags: Optional[List[str]] = Field(default=None, description="Critical issues that require immediate attention")
    approved_for_use: bool = Field(description="Whether the research meets quality standards for use")
    improvement_priority: List[str] = Field(description="Prioritized list of improvements to make")
