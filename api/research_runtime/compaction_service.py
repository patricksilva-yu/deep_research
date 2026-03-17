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
        "and avoid copying long excerpts. "
        "Do not copy wrapper field names, schema labels, or prompt keys into ledger contents. "
        "Return only structured ledger data."
    ),
    output_type=ResearchLedger,
    model_settings=compactor_settings,
    retries=2,
)

_SCHEMA_FIELD_NAMES = {
    "mission",
    "existing_ledger",
    "search_queries",
    "finding_artifacts",
    "fetched_pages",
    "verification_results",
    "fallback_memory",
    "confirmed_findings",
    "open_questions",
    "next_actions",
    "source_urls",
    "compaction_notes",
}


def _clean_list(items: List[str]) -> List[str]:
    cleaned: List[str] = []
    seen = set()
    for item in items:
        normalized = " ".join(str(item).split())
        if not normalized:
            continue
        if normalized in _SCHEMA_FIELD_NAMES:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        cleaned.append(normalized)
    return cleaned


def _sanitize_ledger(ledger: ResearchLedger) -> ResearchLedger:
    mission = " ".join((ledger.mission or "").split()) or None
    if mission in _SCHEMA_FIELD_NAMES:
        mission = None

    source_urls = []
    seen_urls = set()
    for url in ledger.source_urls:
        if url in seen_urls:
            continue
        seen_urls.add(url)
        source_urls.append(url)

    return ResearchLedger(
        mission=mission,
        search_queries=_clean_list(ledger.search_queries),
        confirmed_findings=_clean_list(ledger.confirmed_findings),
        open_questions=_clean_list(ledger.open_questions),
        next_actions=_clean_list(ledger.next_actions),
        source_urls=source_urls,
        compaction_notes=ledger.compaction_notes,
    )


def _ledger_is_suspicious(ledger: ResearchLedger) -> bool:
    content_items = (
        ledger.search_queries
        + ledger.confirmed_findings
        + ledger.open_questions
        + ledger.next_actions
    )
    if not content_items and not ledger.source_urls:
        return True
    schema_hits = sum(1 for item in content_items if item in _SCHEMA_FIELD_NAMES)
    return schema_hits >= max(1, len(content_items) // 3)


def _deterministic_ledger_from_memory(memory: ResearchMemory) -> ResearchLedger:
    return ResearchLedger(
        mission=memory.mission,
        search_queries=_clean_list(memory.search_queries),
        confirmed_findings=_clean_list(memory.confirmed_findings),
        open_questions=_clean_list(memory.open_questions),
        next_actions=_clean_list(memory.next_actions),
        source_urls=memory.high_value_sources,
        compaction_notes="Deterministic compaction used from current research memory.",
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

    ledger = _deterministic_ledger_from_memory(fallback_memory)
    ledger.compaction_notes = "Deterministic compaction used; model compaction is disabled for reliability."
    return ledger
