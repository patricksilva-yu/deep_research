import os
from typing import List, Optional

from dotenv import load_dotenv
from pydantic_ai import Agent, RunContext
from pydantic_ai.builtin_tools import FileSearchTool
from pydantic_ai.models.openai import OpenAIResponsesModelSettings

from api.orchestrator.models import OrchestratorOutput
from api.mcp_tools.execution_service import execute_python_task
from api.mcp_tools.report_service import build_final_report

from .compaction_service import build_fallback_memory
from .models import (
    CompletedTaskSummary,
    FinalReportInput,
    ResearchFindingArtifact,
    ResearchSessionState,
    SourceAssessment,
    SupportOverview,
    VerificationSummary,
)
from .mcp_client import (
    browse_page_via_mcp_or_local,
    compact_research_state_via_mcp_or_local,
    fetch_page_via_mcp_or_local,
    list_skills_via_mcp_or_local,
    load_skill_via_mcp_or_local,
    search_web_via_mcp_or_local,
    summarize_claim_support_via_mcp_or_local,
    verify_claim_via_mcp_or_local,
)
from .prompts import RESEARCH_AGENT_INSTRUCTIONS

load_dotenv()

MODEL_NAME = "openai-responses:gpt-5.4"
RESEARCH_REASONING_EFFORT = os.getenv("RESEARCH_REASONING_EFFORT", "low")
RESEARCH_REASONING_SUMMARY = os.getenv("RESEARCH_REASONING_SUMMARY", "auto")
MAX_SEARCH_CALLS = 2
MAX_FETCH_CALLS = 2
MAX_BROWSE_CALLS = 1
AUTO_COMPACT_AFTER_TOOL_CALLS = 4
MAX_REPORT_FINDINGS = 3
MAX_REPORT_SUPPORT_POINTS = 3
MAX_REPORT_SOURCE_ASSESSMENTS = 4
MAX_REPORT_CLAIM_CHECKS = 4

model_settings = OpenAIResponsesModelSettings(
    openai_reasoning_effort=RESEARCH_REASONING_EFFORT,
    openai_reasoning_summary=RESEARCH_REASONING_SUMMARY,
    openai_previous_response_id="auto",
)


def create_research_agent(vector_store_id: Optional[str] = None) -> Agent:
    builtin_tools = []
    if vector_store_id:
        builtin_tools.append(FileSearchTool(file_store_ids=[vector_store_id]))

    agent = Agent(
        MODEL_NAME,
        deps_type=ResearchSessionState,
        instructions=RESEARCH_AGENT_INSTRUCTIONS,
        output_type=OrchestratorOutput,
        retries=3,
        model_settings=model_settings,
        builtin_tools=builtin_tools,
    )

    def _should_auto_compact(state: ResearchSessionState) -> bool:
        total_tool_calls = state.search_call_count + state.fetch_call_count + state.browse_call_count
        if total_tool_calls == 0:
            return False
        if total_tool_calls % AUTO_COMPACT_AFTER_TOOL_CALLS != 0:
            return False
        return state.compaction_call_count < max(1, total_tool_calls // AUTO_COMPACT_AFTER_TOOL_CALLS)

    async def _refresh_memory(state: ResearchSessionState) -> None:
        state.ledger = await compact_research_state_via_mcp_or_local(
            mission=state.mission,
            search_queries=state.search_queries,
            fetched_pages=list(state.fetched_pages.values()),
            verification_results=state.verification_results,
            existing_ledger=state.ledger,
        )
        state.compacted_memory = build_fallback_memory(
            mission=state.ledger.mission,
            search_queries=state.ledger.search_queries,
            fetched_pages=list(state.fetched_pages.values()),
            verification_results=state.verification_results,
            existing_ledger=state.ledger,
        )
        state.compaction_call_count += 1

    async def _maybe_auto_compact(state: ResearchSessionState) -> Optional[dict]:
        if not _should_auto_compact(state):
            return None
        await _refresh_memory(state)
        return {
            "auto_compacted": True,
            "memory": state.compacted_memory.model_dump(mode="json") if state.compacted_memory else None,
            "ledger": state.ledger.model_dump(mode="json") if state.ledger else None,
        }

    @agent.tool
    async def search_web_sources(
        ctx: RunContext[ResearchSessionState],
        query: str,
        max_results: int = 5,
    ) -> dict:
        normalized_query = " ".join(query.lower().split())
        if normalized_query in {" ".join(existing.lower().split()) for existing in ctx.deps.search_queries}:
            return {
                "query": query,
                "results": [],
                "budget": {
                    "search_calls_used": ctx.deps.search_call_count,
                    "search_calls_remaining": max(0, MAX_SEARCH_CALLS - ctx.deps.search_call_count),
                },
                "note": "Skipped duplicate search query. Use existing results or synthesize.",
            }
        if normalized_query in ctx.deps.active_search_queries:
            return {
                "query": query,
                "results": [],
                "budget": {
                    "search_calls_used": ctx.deps.search_call_count,
                    "search_calls_remaining": max(0, MAX_SEARCH_CALLS - ctx.deps.search_call_count),
                },
                "note": "This search is already in progress. Wait for its results instead of duplicating it.",
            }
        if ctx.deps.search_call_count >= MAX_SEARCH_CALLS:
            return {
                "query": query,
                "results": [],
                "budget": {
                    "search_calls_used": ctx.deps.search_call_count,
                    "search_calls_remaining": 0,
                },
                "note": "Search budget exhausted. Fetch from known sources or synthesize.",
            }

        ctx.deps.search_call_count += 1
        ctx.deps.active_search_queries.add(normalized_query)
        try:
            results = await search_web_via_mcp_or_local(query=query, max_results=min(max_results, 2))
            ctx.deps.search_queries.append(query)
            payload = {
                "query": query,
                "results": [result.model_dump(mode="json") for result in results],
                "budget": {
                    "search_calls_used": ctx.deps.search_call_count,
                    "search_calls_remaining": max(0, MAX_SEARCH_CALLS - ctx.deps.search_call_count),
                },
            }
        finally:
            ctx.deps.active_search_queries.discard(normalized_query)
        auto_compact = await _maybe_auto_compact(ctx.deps)
        if auto_compact:
            payload["auto_compact"] = auto_compact
        return payload

    @agent.tool
    async def fetch_page(
        ctx: RunContext[ResearchSessionState],
        url: str,
    ) -> dict:
        if url in ctx.deps.fetched_pages:
            cached_page = ctx.deps.fetched_pages[url]
            return {
                **cached_page.to_agent_payload(),
                "cached": True,
                "budget": {
                    "fetch_calls_used": ctx.deps.fetch_call_count,
                    "fetch_calls_remaining": max(0, MAX_FETCH_CALLS - ctx.deps.fetch_call_count),
                },
            }
        if url in ctx.deps.active_fetch_urls:
            return {
                "url": url,
                "fetch_status": "in_progress",
                "note": "This page is already being fetched. Use the pending result instead of issuing another fetch.",
                "budget": {
                    "fetch_calls_used": ctx.deps.fetch_call_count,
                    "fetch_calls_remaining": max(0, MAX_FETCH_CALLS - ctx.deps.fetch_call_count),
                },
            }
        if ctx.deps.fetch_call_count >= MAX_FETCH_CALLS:
            return {
                "url": url,
                "fetch_status": "budget_exhausted",
                "note": "Fetch budget exhausted. Verify or synthesize from existing evidence.",
                "budget": {
                    "fetch_calls_used": ctx.deps.fetch_call_count,
                    "fetch_calls_remaining": 0,
                },
            }
        ctx.deps.fetch_call_count += 1
        ctx.deps.active_fetch_urls.add(url)
        try:
            page = await fetch_page_via_mcp_or_local(url)
            ctx.deps.fetched_pages[str(page.url)] = page
            payload = {
                **page.to_agent_payload(),
                "budget": {
                    "fetch_calls_used": ctx.deps.fetch_call_count,
                    "fetch_calls_remaining": max(0, MAX_FETCH_CALLS - ctx.deps.fetch_call_count),
                },
            }
        finally:
            ctx.deps.active_fetch_urls.discard(url)
        auto_compact = await _maybe_auto_compact(ctx.deps)
        if auto_compact:
            payload["auto_compact"] = auto_compact
        return payload

    @agent.tool
    async def browse_page_tool(
        ctx: RunContext[ResearchSessionState],
        url: str,
        goal: Optional[str] = None,
    ) -> dict:
        concise_mission = (ctx.deps.mission or "").lower()
        if ctx.deps.fetch_call_count >= MAX_FETCH_CALLS or "concise" in concise_mission:
            return {
                "url": url,
                "fetch_status": "budget_exhausted",
                "note": "Browse is disabled for this bounded run. Continue with fetched evidence and synthesize.",
                "budget": {
                    "browse_calls_used": ctx.deps.browse_call_count,
                    "browse_calls_remaining": 0,
                },
            }
        if url in ctx.deps.fetched_pages:
            cached_page = ctx.deps.fetched_pages[url]
            if cached_page.fetch_status == "ok":
                return {
                    **cached_page.to_agent_payload(),
                    "cached": True,
                    "note": "A fetched copy already exists. Browse only if you need interactive content not captured by fetch.",
                    "budget": {
                        "browse_calls_used": ctx.deps.browse_call_count,
                        "browse_calls_remaining": max(0, MAX_BROWSE_CALLS - ctx.deps.browse_call_count),
                    },
                }
        if url in ctx.deps.active_browse_urls:
            return {
                "url": url,
                "fetch_status": "in_progress",
                "note": "This page is already being browsed. Wait for that result instead of opening it again.",
                "budget": {
                    "browse_calls_used": ctx.deps.browse_call_count,
                    "browse_calls_remaining": max(0, MAX_BROWSE_CALLS - ctx.deps.browse_call_count),
                },
            }
        if ctx.deps.browse_call_count >= MAX_BROWSE_CALLS:
            return {
                "url": url,
                "fetch_status": "budget_exhausted",
                "note": "Browse budget exhausted. Continue with existing fetched evidence.",
                "budget": {
                    "browse_calls_used": ctx.deps.browse_call_count,
                    "browse_calls_remaining": 0,
                },
            }

        ctx.deps.browse_call_count += 1
        ctx.deps.active_browse_urls.add(url)
        try:
            page = await browse_page_via_mcp_or_local(url=url, goal=goal)
            ctx.deps.fetched_pages[str(page.url)] = page
            payload = {
                **page.to_agent_payload(),
                "budget": {
                    "browse_calls_used": ctx.deps.browse_call_count,
                    "browse_calls_remaining": max(0, MAX_BROWSE_CALLS - ctx.deps.browse_call_count),
                },
            }
        finally:
            ctx.deps.active_browse_urls.discard(url)
        auto_compact = await _maybe_auto_compact(ctx.deps)
        if auto_compact:
            payload["auto_compact"] = auto_compact
        return payload

    @agent.tool
    async def compact_research_state_tool(
        ctx: RunContext[ResearchSessionState],
    ) -> dict:
        await _refresh_memory(ctx.deps)
        return {
            "ledger": ctx.deps.ledger.model_dump(mode="json") if ctx.deps.ledger else None,
            "memory": ctx.deps.compacted_memory.model_dump(mode="json"),
            "budget": {
                "search_calls_used": ctx.deps.search_call_count,
                "fetch_calls_used": ctx.deps.fetch_call_count,
                "browse_calls_used": ctx.deps.browse_call_count,
                "compactions_used": ctx.deps.compaction_call_count,
            },
        }

    @agent.tool
    async def verify_claim(
        ctx: RunContext[ResearchSessionState],
        claim: str,
        source_urls: List[str],
    ) -> dict:
        result = await verify_claim_via_mcp_or_local(
            claim=claim,
            source_urls=source_urls,
            prefetched_pages=list(ctx.deps.fetched_pages.values()),
        )
        ctx.deps.verification_results.append(result)
        ctx.deps.artifacts.setdefault("verified_claims", []).append(result.model_dump(mode="json"))
        return result.model_dump(mode="json")

    @agent.tool
    async def summarize_claim_support(
        ctx: RunContext[ResearchSessionState],
    ) -> dict:
        payload = await summarize_claim_support_via_mcp_or_local(ctx.deps.verification_results)
        overview = SupportOverview.model_validate(payload)
        ctx.deps.artifacts["support_overview"] = overview.model_dump()
        return overview.model_dump()

    @agent.tool_plain
    async def run_data_analysis(task: str) -> dict:
        result = await execute_python_task(task)
        return result.model_dump()

    @agent.tool_plain
    async def list_available_skills() -> dict:
        return await list_skills_via_mcp_or_local()

    @agent.tool_plain
    async def load_skill(skill_name: str) -> dict:
        return await load_skill_via_mcp_or_local(skill_name)

    @agent.tool
    async def record_research_finding(
        ctx: RunContext[ResearchSessionState],
        title: str,
        summary: str,
        supporting_points: List[str],
        source_urls: List[str],
    ) -> dict:
        artifact = ResearchFindingArtifact(
            title=title,
            summary=summary,
            supporting_points=supporting_points,
            source_urls=source_urls,
        )
        ctx.deps.finding_artifacts.append(artifact)
        ctx.deps.artifacts.setdefault("finding_artifacts", []).append(artifact.model_dump(mode="json"))
        return artifact.model_dump(mode="json")

    @agent.tool
    async def generate_final_report_from_state(
        ctx: RunContext[ResearchSessionState],
        mission: Optional[str] = None,
    ) -> dict:
        completed_tasks = []
        artifact_candidates = ctx.deps.finding_artifacts[-MAX_REPORT_FINDINGS:]
        for index, artifact in enumerate(artifact_candidates, start=1):
            trimmed_artifact = ResearchFindingArtifact(
                title=artifact.title,
                summary=artifact.summary[:500],
                supporting_points=artifact.supporting_points[:MAX_REPORT_SUPPORT_POINTS],
                source_urls=artifact.source_urls[:MAX_REPORT_SUPPORT_POINTS],
            )
            completed_tasks.append(
                CompletedTaskSummary(
                    task_id=f"finding_{index}",
                    description=trimmed_artifact.title,
                    summary=trimmed_artifact.summary,
                    findings=trimmed_artifact.to_search_findings()[:MAX_REPORT_SUPPORT_POINTS],
                    gaps=None,
                )
            )

        source_assessments = []
        seen_titles = set()
        for page in ctx.deps.fetched_pages.values():
            title = page.title or str(page.url)
            if title in seen_titles:
                continue
            seen_titles.add(title)
            source_assessments.append(
                SourceAssessment(
                    source_title=title,
                    credibility_rating="Medium",
                    reasoning=f"Fetched via {page.retrieval_method}; formal scoring still needs stronger heuristics.",
                )
            )
            if len(source_assessments) >= MAX_REPORT_SOURCE_ASSESSMENTS:
                break

        verification_summary = None
        if ctx.deps.verification_results or source_assessments:
            support_counts = {
                "supported": 0,
                "partial": 0,
                "unsupported": 0,
                "conflicting": 0,
            }
            for result in ctx.deps.verification_results:
                support_counts[result.status] = support_counts.get(result.status, 0) + 1

            approved_for_use = support_counts["unsupported"] == 0 and support_counts["conflicting"] == 0
            overall_quality = "high" if approved_for_use else "medium"
            if support_counts["conflicting"]:
                overall_quality = "low"

            selected_claim_checks = sorted(
                ctx.deps.verification_results,
                key=lambda result: {"conflicting": 0, "unsupported": 1, "partial": 2, "supported": 3}.get(result.status, 4),
            )[:MAX_REPORT_CLAIM_CHECKS]

            verification_summary = VerificationSummary(
                overall_quality_rating=overall_quality,
                approved_for_use=approved_for_use,
                source_assessments=source_assessments,
                consistency_issues=[],
                critical_flags=None,
                improvement_priority=(ctx.deps.compacted_memory.next_actions[:3] if ctx.deps.compacted_memory else []),
                claim_support_results=selected_claim_checks,
            )

        report_input = FinalReportInput(
            mission=mission or ctx.deps.mission or "Research request",
            tasks=completed_tasks,
            verification=verification_summary,
        )
        final_report = build_final_report(report_input).model_dump(mode="json")
        ctx.deps.artifacts["generated_report"] = final_report
        return final_report

    return agent


research_agent = create_research_agent()
