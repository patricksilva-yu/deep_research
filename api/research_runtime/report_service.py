import os
from typing import List

from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIResponsesModelSettings

from .models import FinalReport, FinalReportInput

load_dotenv()

REPORT_MODEL = os.getenv("RESEARCH_REPORT_MODEL", "openai-responses:gpt-5-mini")

report_agent = Agent(
    REPORT_MODEL,
    instructions=(
        "You write the final research report from structured findings and verification state. "
        "Synthesize across findings instead of copying them. "
        "Use only the supplied evidence and verification results. "
        "Keep the executive summary concise, preserve uncertainty, and include only grounded claims. "
        "If verification shows weak support, qualify the claim rather than overstating it."
    ),
    output_type=FinalReport,
    model_settings=OpenAIResponsesModelSettings(
        openai_reasoning_effort="low",
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


def _fallback_report(request: FinalReportInput) -> FinalReport:
    sources: List[str] = []
    sections = []
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
        request.tasks[0].summary
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
            "support_overview": support_overview,
            "claim_support": [result.model_dump(mode="json") for result in claim_support],
            "sources": _dedupe_sources(sources),
        }
    )


async def build_final_report(request: FinalReportInput) -> FinalReport:
    prompt = {
        "mission": request.mission,
        "completed_tasks": [task.model_dump(mode="json") for task in request.tasks],
        "verification": request.verification.model_dump(mode="json") if request.verification else None,
    }

    try:
        result = await report_agent.run(prompt)
        report = result.output
        report.sources = _dedupe_sources(report.sources)
        return report
    except Exception:
        return _fallback_report(request)
