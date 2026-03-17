from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, HttpUrl


class RelevanceScore(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class SearchAgentFinding(BaseModel):
    topic_subtopic: str = Field(description="Topic or subtopic covered by the finding")
    key_finding: str = Field(description="Main claim or finding extracted from the source")
    source_title: str = Field(description="Source title")
    source_url: str = Field(description="Source URL")
    publication_date: Optional[str] = Field(default=None, description="Publication date if known")
    relevance_score: RelevanceScore = Field(description="Estimated relevance to the task")


class SearchResult(BaseModel):
    title: str = Field(description="Result title")
    url: HttpUrl = Field(description="Result URL")
    content: Optional[str] = Field(default=None, description="Snippet or summary")
    score: Optional[float] = Field(default=None, description="Provider relevance score")


class ExtractedPage(BaseModel):
    url: HttpUrl = Field(description="Fetched URL")
    title: Optional[str] = Field(default=None, description="Page title if discovered")
    extracted_text: str = Field(description="Cleaned textual content")
    excerpt: Optional[str] = Field(default=None, description="Short evidence excerpt")
    retrieval_method: str = Field(description="How the page was retrieved")
    fetch_status: str = Field(default="ok", description="Fetch result status")

    def to_agent_payload(self, max_chars: int = 1600) -> Dict[str, Any]:
        excerpt = self.excerpt or self.extracted_text[:max_chars]
        return {
            "url": str(self.url),
            "title": self.title,
            "excerpt": excerpt[:max_chars] if excerpt else None,
            "retrieval_method": self.retrieval_method,
            "fetch_status": self.fetch_status,
            "text_length": len(self.extracted_text),
        }


class ClaimSupportResult(BaseModel):
    claim: str = Field(description="Claim being checked")
    status: str = Field(description="supported, partial, unsupported, or conflicting")
    supporting_urls: List[HttpUrl] = Field(default_factory=list, description="Sources used for the check")
    evidence_snippets: List[str] = Field(default_factory=list, description="Supporting or conflicting excerpts")
    reasoning: str = Field(description="Short explanation of the judgment")
    evidence_matches: List["EvidenceMatch"] = Field(
        default_factory=list,
        description="Specific evidence chunks selected for this claim",
    )


class EvidenceChunk(BaseModel):
    chunk_id: str = Field(description="Stable identifier for the evidence chunk")
    url: HttpUrl = Field(description="Source URL for this chunk")
    title: Optional[str] = Field(default=None, description="Source title if known")
    text: str = Field(description="Chunk text")
    char_start: int = Field(description="Start offset in the source text")
    char_end: int = Field(description="End offset in the source text")
    retrieval_method: str = Field(description="How the source page was retrieved")
    lexical_score: float = Field(default=0.0, description="Initial retrieval score")
    rerank_score: Optional[float] = Field(default=None, description="Model reranker score")

    def preview(self, max_chars: int = 320) -> str:
        return self.text[:max_chars]


class EvidenceMatch(BaseModel):
    chunk_id: str = Field(description="Evidence chunk identifier")
    url: HttpUrl = Field(description="URL backing this evidence")
    title: Optional[str] = Field(default=None, description="Source title if known")
    snippet: str = Field(description="Short supporting or conflicting snippet")
    char_start: int = Field(description="Start offset in the source text")
    char_end: int = Field(description="End offset in the source text")
    retrieval_score: float = Field(default=0.0, description="Candidate retrieval score")
    rerank_score: Optional[float] = Field(default=None, description="Reranker score if available")


class EvidenceRetrievalResult(BaseModel):
    claim: str = Field(description="Claim used for retrieval")
    candidates: List[EvidenceChunk] = Field(default_factory=list, description="Top candidate chunks before support judgment")


class RerankedEvidenceResult(BaseModel):
    claim: str = Field(description="Claim being reranked")
    ranked_chunk_ids: List[str] = Field(default_factory=list, description="Chunk ids in ranked order")
    reasoning: Optional[str] = Field(default=None, description="Short reranking rationale")


class CredibilityRating(str, Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class IssueSeverity(str, Enum):
    CRITICAL = "Critical"
    MAJOR = "Major"
    MINOR = "Minor"


class SourceAssessment(BaseModel):
    source_title: str = Field(description="Title or name of the source")
    credibility_rating: CredibilityRating = Field(description="Overall credibility rating")
    reasoning: str = Field(description="Explanation of the credibility rating")


class ConsistencyIssue(BaseModel):
    severity: IssueSeverity = Field(description="How severe this issue is")
    description: str = Field(description="Detailed description of the issue")
    suggested_action: str = Field(description="Recommended action to address this issue")


class VerificationOutput(BaseModel):
    summary: str = Field(description="Executive summary of the verification assessment")
    overall_quality_rating: str = Field(description="Overall quality rating")
    source_assessments: List[SourceAssessment] = Field(description="Credibility assessment for each source")
    consistency_issues: List[ConsistencyIssue] = Field(description="List of identified consistency or factual issues")
    claim_support_results: List[ClaimSupportResult] = Field(
        default_factory=list,
        description="Claim-level support checks against fetched source text",
    )
    critical_flags: Optional[List[str]] = Field(default=None, description="Critical issues that require immediate attention")
    approved_for_use: bool = Field(description="Whether the research meets quality standards for use")
    improvement_priority: List[str] = Field(description="Prioritized list of improvements to make")


class ResearchMemory(BaseModel):
    mission: Optional[str] = Field(default=None, description="Current research mission")
    search_queries: List[str] = Field(default_factory=list, description="Queries already issued")
    fetched_urls: List[HttpUrl] = Field(default_factory=list, description="URLs fetched so far")
    confirmed_findings: List[str] = Field(default_factory=list, description="High-confidence findings")
    open_questions: List[str] = Field(default_factory=list, description="Still-unresolved questions")
    high_value_sources: List[HttpUrl] = Field(default_factory=list, description="Best supporting sources")
    next_actions: List[str] = Field(default_factory=list, description="Suggested next steps")


class ResearchLedger(BaseModel):
    mission: Optional[str] = Field(default=None, description="Current research mission")
    search_queries: List[str] = Field(default_factory=list, description="Recent searches worth retaining")
    confirmed_findings: List[str] = Field(default_factory=list, description="Durable findings preserved across compaction")
    open_questions: List[str] = Field(default_factory=list, description="Outstanding unknowns to revisit")
    next_actions: List[str] = Field(default_factory=list, description="Recommended next actions after compaction")
    source_urls: List[HttpUrl] = Field(default_factory=list, description="High-value sources retained by reference")
    compaction_notes: Optional[str] = Field(default=None, description="Notes about what was compressed or omitted")


class ResearchFindingArtifact(BaseModel):
    title: str = Field(description="Short heading for this finding group")
    summary: str = Field(description="Short synthesis of what was learned")
    supporting_points: List[str] = Field(default_factory=list, description="Grounded supporting details")
    source_urls: List[str] = Field(default_factory=list, description="Sources that support the finding")

    def external_source_urls(self) -> List[str]:
        return [
            source_url
            for source_url in self.source_urls
            if source_url.startswith("http://") or source_url.startswith("https://")
        ]

    def to_search_findings(self) -> List[SearchAgentFinding]:
        findings: List[SearchAgentFinding] = []
        for index, source_url in enumerate(self.external_source_urls(), start=1):
            findings.append(
                SearchAgentFinding(
                    topic_subtopic=self.title,
                    key_finding=self.summary,
                    source_title=f"{self.title} source {index}",
                    source_url=source_url,
                    publication_date=None,
                    relevance_score=RelevanceScore.HIGH,
                )
            )
        return findings


class CompletedTaskSummary(BaseModel):
    task_id: str = Field(description="Identifier of the completed task")
    description: str = Field(description="What the task attempted to accomplish")
    summary: str = Field(description="Short narrative of the findings for this task")
    findings: List[SearchAgentFinding] = Field(description="Structured findings returned by research tools")
    gaps: Optional[List[str]] = Field(default=None, description="Any remaining gaps or follow-up questions from the task")


class VerificationSummary(BaseModel):
    overall_quality_rating: str = Field(description="Overall quality rating from verification")
    approved_for_use: bool = Field(description="Whether the research is approved for use")
    source_assessments: List[SourceAssessment] = Field(default_factory=list, description="Per-source credibility assessments")
    consistency_issues: List[ConsistencyIssue] = Field(default_factory=list, description="Issues that should be acknowledged in the final report")
    critical_flags: Optional[List[str]] = Field(default=None, description="Critical problems that require immediate attention")
    improvement_priority: List[str] = Field(default_factory=list, description="Suggested follow-up actions from verification")
    claim_support_results: List[ClaimSupportResult] = Field(default_factory=list, description="Claim-level support checks run against fetched source text")


class FinalReportInput(BaseModel):
    mission: str = Field(description="Overall mission statement from the research plan")
    tasks: List[CompletedTaskSummary] = Field(description="Completed task outputs from the orchestrator")
    finding_artifacts: List[ResearchFindingArtifact] = Field(
        default_factory=list,
        description="Recorded grounded findings accumulated during the run",
    )
    verification: Optional[VerificationSummary] = Field(default=None, description="Verification summary if quality checks were completed")


class ReportSection(BaseModel):
    title: str = Field(description="Heading for this section")
    summary: str = Field(description="Brief paragraph summarizing this section")
    supporting_points: List[str] = Field(default_factory=list, description="Bulleted supporting points derived from the findings")


class SupportOverview(BaseModel):
    supported_claims: int = Field(description="Number of claims marked as supported")
    partial_claims: int = Field(description="Number of claims marked as partial")
    unsupported_claims: int = Field(description="Number of claims marked as unsupported")
    conflicting_claims: int = Field(description="Number of claims marked as conflicting")
    notes: Optional[str] = Field(default=None, description="Short narrative of what the support distribution means")


class FinalReport(BaseModel):
    mission: str = Field(description="Restated mission to anchor the report")
    executive_summary: str = Field(description="Top-level synthesis of the research")
    sections: List[ReportSection] = Field(description="Detailed sections covering major themes")
    recommended_actions: Optional[List[str]] = Field(default=None, description="Optional action items or recommendations")
    quality_notes: Optional[str] = Field(default=None, description="Notes about research quality, limitations, or verification outcomes")
    support_overview: Optional[SupportOverview] = Field(default=None, description="Aggregate claim support status for the final report")
    claim_support: List[ClaimSupportResult] = Field(default_factory=list, description="Claim-level verification outcomes for important report assertions")
    sources: List[str] = Field(default_factory=list, description="List of deduplicated citation strings or URLs referenced in the report")


class CodeExecutionResult(BaseModel):
    code: str = Field(description="The Python code that was executed")
    output: Optional[str] = Field(default=None, description="Standard output from the code execution")
    error: Optional[str] = Field(default=None, description="Error message if execution failed")
    execution_time: Optional[float] = Field(default=None, description="Execution time in seconds")


class CodeExecutorOutput(BaseModel):
    summary: str = Field(description="Brief explanation of what was accomplished")
    executions: List[CodeExecutionResult] = Field(description="List of code executions performed")
    next_steps: Optional[List[str]] = Field(default=None, description="Suggested next steps or follow-up actions")


ClaimSupportResult.model_rebuild()


@dataclass
class ResearchSessionState:
    mission: Optional[str] = None
    search_queries: List[str] = field(default_factory=list)
    fetched_pages: Dict[str, ExtractedPage] = field(default_factory=dict)
    search_snippet_pages: Dict[str, List[ExtractedPage]] = field(default_factory=dict)
    evidence_chunks: Dict[str, EvidenceChunk] = field(default_factory=dict)
    verification_results: List[ClaimSupportResult] = field(default_factory=list)
    finding_artifacts: List[ResearchFindingArtifact] = field(default_factory=list)
    ledger: Optional[ResearchLedger] = None
    compacted_memory: Optional[ResearchMemory] = None
    artifacts: Dict[str, Any] = field(default_factory=dict)
    search_call_count: int = 0
    fetch_call_count: int = 0
    browse_call_count: int = 0
    compaction_call_count: int = 0
    active_search_queries: set[str] = field(default_factory=set)
    active_fetch_urls: set[str] = field(default_factory=set)
    active_browse_urls: set[str] = field(default_factory=set)


class ResearchTask(BaseModel):
    """A single research task to be executed."""
    task_id: str = Field(description="Unique identifier for this task")
    description: str = Field(description="What needs to be researched")
    search_query: str = Field(description="Query to pass to the research search tool")


class ResearchPlan(BaseModel):
    """Simple research plan with ordered tasks."""
    mission: str = Field(description="What we're trying to research")
    tasks: List[ResearchTask] = Field(description="Ordered list of search tasks")
    next_steps: List[str] = Field(description="What to do after planning")


class OrchestratorOutput(BaseModel):
    """Output from the single research agent."""
    plan: ResearchPlan = Field(description="The research plan")
    final_report: FinalReport = Field(
        description="The final synthesized research report, generated after executing all tasks",
    )
