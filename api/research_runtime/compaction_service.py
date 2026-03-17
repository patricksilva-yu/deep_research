import os
from typing import List, Optional

from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIResponsesModelSettings

from .models import ClaimSupportResult, ExtractedPage, ResearchFindingArtifact, ResearchLedger, ResearchMemory

load_dotenv()

COMPACTOR_MODEL = os.getenv("RESEARCH_COMPACTOR_MODEL", "openai-responses:gpt-5-mini")

compactor_settings = OpenAIResponsesModelSettings(
    openai_reasoning_effort="low",
    openai_reasoning_summary="auto",
    openai_previous_response_id="auto",
)

compactor_agent = Agent(
    COMPACTOR_MODEL,
    instructions=(
        "You compress stale working context into a structured research ledger. "
        "Keep source URLs and evidence references, preserve open questions and next actions, "
        "and avoid copying long excerpts. Return only structured ledger data."
    ),
    output_type=ResearchLedger,
    model_settings=compactor_settings,
    retries=2,
)


def build_fallback_memory(
    mission: Optional[str],
    search_queries: List[str],
    fetched_pages: List[ExtractedPage],
    verification_results: List[ClaimSupportResult],
    finding_artifacts: List[ResearchFindingArtifact],
    existing_ledger: Optional[ResearchLedger] = None,
) -> ResearchMemory:
    high_value_sources = [page.url for page in fetched_pages[-8:] if page.fetch_status == "ok"]
    confirmed_findings = [artifact.summary for artifact in finding_artifacts[-8:] if artifact.summary]

    if not confirmed_findings:
        for result in verification_results[-8:]:
            if result.status in {"supported", "partial"} and result.reasoning:
                confirmed_findings.append(f"{result.claim}: {result.reasoning}")

    if not confirmed_findings:
        for page in fetched_pages[-8:]:
            if page.fetch_status == "ok":
                confirmed_findings.append(f"Fetched {page.title or page.url} via {page.retrieval_method}.")

    open_questions = [
        verification.claim
        for verification in verification_results
        if verification.status != "supported"
    ][:6]

    next_actions = []
    if open_questions:
        next_actions.append("Resolve unsupported or partial claims with stronger evidence.")
    if len(high_value_sources) < 3:
        next_actions.append("Fetch more primary sources before final synthesis.")
    if not next_actions:
        next_actions.append("Draft the final report and verify material claims.")

    if existing_ledger:
        confirmed_findings = (existing_ledger.confirmed_findings + confirmed_findings)[:10]
        open_questions = (existing_ledger.open_questions + open_questions)[:10]
        next_actions = (existing_ledger.next_actions + next_actions)[:10]
        high_value_sources = (existing_ledger.source_urls + high_value_sources)[:10]

    return ResearchMemory(
        mission=mission,
        search_queries=search_queries[-8:],
        fetched_urls=high_value_sources[:8],
        confirmed_findings=confirmed_findings[:8],
        open_questions=open_questions[:8],
        high_value_sources=high_value_sources[:8],
        next_actions=next_actions[:8],
    )


async def compact_research_state(
    mission: Optional[str],
    search_queries: List[str],
    fetched_pages: List[ExtractedPage],
    verification_results: List[ClaimSupportResult],
    finding_artifacts: List[ResearchFindingArtifact],
    existing_ledger: Optional[ResearchLedger] = None,
) -> ResearchLedger:
    fallback_memory = build_fallback_memory(
        mission=mission,
        search_queries=search_queries,
        fetched_pages=fetched_pages,
        verification_results=verification_results,
        finding_artifacts=finding_artifacts,
        existing_ledger=existing_ledger,
    )

    prompt = {
        "mission": mission,
        "existing_ledger": existing_ledger.model_dump(mode="json") if existing_ledger else None,
        "search_queries": search_queries[-12:],
        "finding_artifacts": [artifact.model_dump(mode="json") for artifact in finding_artifacts[-8:]],
        "fetched_pages": [
            {
                "url": str(page.url),
                "title": page.title,
                "fetch_status": page.fetch_status,
                "retrieval_method": page.retrieval_method,
            }
            for page in fetched_pages[-10:]
        ],
        "verification_results": [result.model_dump(mode="json") for result in verification_results[-10:]],
        "fallback_memory": fallback_memory.model_dump(mode="json"),
    }

    try:
        result = await compactor_agent.run(prompt)
        return result.output
    except Exception:
        return ResearchLedger(
            mission=fallback_memory.mission,
            search_queries=fallback_memory.search_queries,
            confirmed_findings=fallback_memory.confirmed_findings,
            open_questions=fallback_memory.open_questions,
            next_actions=fallback_memory.next_actions,
            source_urls=fallback_memory.high_value_sources,
            compaction_notes="Fallback ledger used because model compaction was unavailable.",
        )
