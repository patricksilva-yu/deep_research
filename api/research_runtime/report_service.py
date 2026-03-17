import os
import re
from typing import List

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIResponsesModelSettings

from .models import FinalReport, FinalReportInput, SupportOverview

load_dotenv()

REPORT_MODEL = os.getenv("RESEARCH_REPORT_MODEL", "openai-responses:gpt-5-mini")


class _ReportValidation(BaseModel):
    is_valid: bool = Field(description="Whether the report is aligned with the mission and supplied findings")
    reason: str = Field(description="Short explanation of the validation decision")


_INTERNAL_ACTION_PHRASES = (
    "ledger",
    "populate fetched_pages",
    "verification criteria",
    "source types",
    "clarify scope and priorities",
)

report_agent = Agent(
    REPORT_MODEL,
    instructions=(
        "You write the final research report from structured findings and verification state. "
        "Synthesize across findings instead of copying them. "
        "Use only the supplied evidence and verification results. "
        "Keep the executive summary concise, preserve uncertainty, and include only grounded claims. "
        "Separate direct evidence from inference whenever support is partial. "
        "If verification shows weak support, qualify the claim rather than overstating it."
    ),
    output_type=FinalReport,
    model_settings=OpenAIResponsesModelSettings(
        openai_reasoning_effort="low",
        openai_reasoning_summary="auto",
    ),
    retries=2,
)

report_validator_agent = Agent(
    REPORT_MODEL,
    instructions=(
        "You validate whether a synthesized report is aligned with the mission and supplied findings. "
        "Mark invalid if the report drifts to another topic, ignores the mission, invents an unrelated framework, "
        "or includes internal workflow recommendations instead of user-facing next actions. "
        "Be strict."
    ),
    output_type=_ReportValidation,
    model_settings=OpenAIResponsesModelSettings(
        openai_reasoning_effort="minimal",
        openai_reasoning_summary="auto",
    ),
    retries=2,
)


def _dedupe_sources(items: List[str]) -> List[str]:
    seen = set()
    output: List[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        output.append(item)
    return output


def _support_overview_from_request(request: FinalReportInput) -> SupportOverview | None:
    if not request.verification:
        return None
    results = request.verification.claim_support_results
    return SupportOverview.model_validate({
        "supported_claims": sum(1 for result in results if result.status == "supported"),
        "partial_claims": sum(1 for result in results if result.status == "partial"),
        "unsupported_claims": sum(1 for result in results if result.status == "unsupported"),
        "conflicting_claims": sum(1 for result in results if result.status == "conflicting"),
        "notes": "Derived from recorded verification results.",
    })


def _is_user_facing_action(action: str) -> bool:
    normalized = action.lower()
    return not any(phrase in normalized for phrase in _INTERNAL_ACTION_PHRASES)


def _tokenize(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) > 2}


def _is_mission_aligned(report: FinalReport, mission: str) -> bool:
    mission_tokens = _tokenize(mission)
    report_tokens = _tokenize(report.mission)
    if not mission_tokens or not report_tokens:
        return False
    overlap = len(mission_tokens & report_tokens) / len(mission_tokens)
    return overlap >= 0.5


def _post_process_report(report: FinalReport, request: FinalReportInput) -> FinalReport:
    report.sources = _dedupe_sources(report.sources)
    if request.verification and not report.support_overview:
        report.support_overview = _support_overview_from_request(request)

    if report.recommended_actions:
        report.recommended_actions = [action for action in report.recommended_actions if _is_user_facing_action(action)][:3] or None

    if request.verification:
        partial_or_worse = any(
            result.status in {"partial", "unsupported", "conflicting"}
            for result in request.verification.claim_support_results
        )
        if partial_or_worse:
            note = "Some conclusions include inference beyond directly retrieved evidence; confidence is stated where support is partial."
            report.quality_notes = f"{report.quality_notes} {note}".strip() if report.quality_notes else note

    return report


def _report_is_too_thin(report: FinalReport, request: FinalReportInput) -> bool:
    expected_sections = max(1, min(len(request.finding_artifacts) or len(request.tasks), 3))
    if len(report.sections) < expected_sections:
        return True
    if request.finding_artifacts and not report.sources:
        return True
    return False


def _fallback_report(request: FinalReportInput) -> FinalReport:
    sources: List[str] = []
    sections = []
    artifact_sections = []
    for artifact in request.finding_artifacts[:4]:
        for source_url in artifact.source_urls:
            sources.append(source_url)
        artifact_sections.append(
            {
                "title": artifact.title,
                "summary": artifact.summary,
                "supporting_points": artifact.supporting_points[:4],
            }
        )
    for task in request.tasks:
        supporting_points = []
        for finding in task.findings:
            source_url = str(finding.source_url)
            supporting_points.append(f"{finding.key_finding} ({source_url})")
            sources.append(source_url)
        sections.append(
            {
                "title": task.description,
                "summary": task.summary,
                "supporting_points": supporting_points[:4],
            }
        )
    if artifact_sections:
        sections = artifact_sections

    quality_notes = None
    recommended_actions = None
    support_overview = None
    claim_support = []

    if request.verification:
        verification = request.verification
        claim_support = verification.claim_support_results[:4]
        supported = sum(1 for result in verification.claim_support_results if result.status == "supported")
        partial = sum(1 for result in verification.claim_support_results if result.status == "partial")
        unsupported = sum(1 for result in verification.claim_support_results if result.status == "unsupported")
        conflicting = sum(1 for result in verification.claim_support_results if result.status == "conflicting")
        support_overview = {
            "supported_claims": supported,
            "partial_claims": partial,
            "unsupported_claims": unsupported,
            "conflicting_claims": conflicting,
            "notes": "Fallback report used after report synthesis was unavailable.",
        }
        if verification.improvement_priority:
            recommended_actions = verification.improvement_priority[:3]
        quality_notes = (
            f"Quality rating: {verification.overall_quality_rating}. "
            f"Approved for use: {'yes' if verification.approved_for_use else 'no'}."
        )

    executive_summary = (
        request.finding_artifacts[0].summary
        if request.finding_artifacts
        else request.tasks[0].summary
        if request.tasks
        else f"Research completed for: {request.mission}"
    )

    return FinalReport.model_validate(
        {
            "mission": request.mission,
            "executive_summary": executive_summary,
            "sections": sections[:4],
            "recommended_actions": recommended_actions,
            "quality_notes": quality_notes,
            "support_overview": support_overview or _support_overview_from_request(request),
            "claim_support": [result.model_dump(mode="json") for result in claim_support],
            "sources": _dedupe_sources(sources),
        }
    )


async def build_final_report(request: FinalReportInput) -> FinalReport:
    prompt = {
        "mission": request.mission,
        "completed_tasks": [task.model_dump(mode="json") for task in request.tasks],
        "finding_artifacts": [artifact.model_dump(mode="json") for artifact in request.finding_artifacts],
        "verification": request.verification.model_dump(mode="json") if request.verification else None,
    }

    try:
        result = await report_agent.run(prompt)
        report = _post_process_report(result.output, request)
        if not _is_mission_aligned(report, request.mission):
            raise ValueError("Generated report drifted off mission.")
        if _report_is_too_thin(report, request):
            raise ValueError("Generated report was too thin for the available findings.")
        validation = await report_validator_agent.run(
            {
                "mission": request.mission,
                "finding_artifacts": [artifact.model_dump(mode="json") for artifact in request.finding_artifacts],
                "verification": request.verification.model_dump(mode="json") if request.verification else None,
                "report": report.model_dump(mode="json"),
            }
        )
        if validation.output.is_valid:
            return report
    except Exception:
        pass

    return _post_process_report(_fallback_report(request), request)
