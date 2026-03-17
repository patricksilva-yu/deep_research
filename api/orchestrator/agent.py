import os
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
import re

from dotenv import load_dotenv
import logfire
from pydantic_ai import Agent, RunContext
from pydantic_ai.builtin_tools import FileSearchTool
from pydantic_ai.models.openai import OpenAIResponsesModelSettings

try:
    from pydantic_ai import MCPServerTool
except ImportError:  # pragma: no cover - depends on installed PydanticAI version
    MCPServerTool = None

from api.orchestrator.models import OrchestratorOutput
from api.research_runtime.compaction_service import build_fallback_memory
from api.research_runtime.evidence_service import chunk_page
from api.research_runtime.execution_service import execute_python_task
from api.research_runtime.mcp_client import (
    call_runtime_tool_via_mcp_or_local,
    compact_research_state_via_mcp_or_local,
    search_runtime_tools_via_mcp_or_local,
)
from api.research_runtime.models import (
    ClaimSupportResult,
    CompletedTaskSummary,
    EvidenceChunk,
    ExtractedPage,
    FinalReportInput,
    ResearchFindingArtifact,
    ResearchSessionState,
    SourceAssessment,
    SupportOverview,
    VerificationSummary,
)
from api.research_runtime.report_service import build_final_report
from api.research_runtime.verification_service import (
    retrieve_evidence_chunks as retrieve_evidence_candidates,
    verify_claim_support as verify_claim_with_sources,
)

from .prompts import RESEARCH_AGENT_INSTRUCTIONS

load_dotenv()

MODEL_NAME = "openai-responses:gpt-5.4"
RESEARCH_REASONING_EFFORT = os.getenv("RESEARCH_REASONING_EFFORT", "low")
RESEARCH_REASONING_SUMMARY = os.getenv("RESEARCH_REASONING_SUMMARY", "auto")
MAX_SEARCH_CALLS = 6
MAX_FETCH_CALLS = 3
MAX_BROWSE_CALLS = 1
AUTO_COMPACT_AFTER_TOOL_CALLS = 4
MAX_REPORT_FINDINGS = 3
MAX_REPORT_SUPPORT_POINTS = 3
MAX_REPORT_SOURCE_ASSESSMENTS = 4
MAX_REPORT_CLAIM_CHECKS = 4
PROVIDER_MCP_SERVER_URL = os.getenv("PROVIDER_MCP_SERVER_URL")
ENABLE_PROVIDER_MCP_TOOL_SEARCH = os.getenv("ENABLE_PROVIDER_MCP_TOOL_SEARCH", "false").lower() == "true"

model_settings = OpenAIResponsesModelSettings(
    openai_reasoning_effort=RESEARCH_REASONING_EFFORT,
    openai_reasoning_summary=RESEARCH_REASONING_SUMMARY,
    openai_previous_response_id="auto",
)


def create_research_agent(vector_store_id: Optional[str] = None) -> Agent:
    builtin_tools = []
    if vector_store_id:
        builtin_tools.append(FileSearchTool(file_store_ids=[vector_store_id]))
    # This only works if the MCP server is reachable by the provider.
    if ENABLE_PROVIDER_MCP_TOOL_SEARCH and PROVIDER_MCP_SERVER_URL and MCPServerTool is not None:
        builtin_tools.append(
            MCPServerTool(
                id="research-hub",
                url=PROVIDER_MCP_SERVER_URL,
                description=(
                    "Use this remote MCP server when provider-side tool search is enabled and the server "
                    "is publicly reachable. It exposes search, fetch, browse, evidence retrieval, verification, "
                    "compaction, and skill tools."
                ),
                allowed_tools=[
                    "search_web_sources",
                    "fetch_page",
                    "browse_page_tool",
                    "retrieve_evidence_chunks",
                    "verify_claim",
                    "compact_research_state_tool",
                    "summarize_claim_support",
                    "list_available_skills",
                    "load_skill",
                ],
            )
        )

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
        if os.getenv("ENABLE_AUTO_COMPACTION", "false").lower() != "true":
            return False
        total_tool_calls = state.search_call_count + state.fetch_call_count + state.browse_call_count
        if total_tool_calls == 0:
            return False
        if total_tool_calls % AUTO_COMPACT_AFTER_TOOL_CALLS != 0:
            return False
        has_substantive_state = bool(
            state.finding_artifacts
            or state.verification_results
            or any(page.fetch_status == "ok" for page in state.fetched_pages.values())
        )
        if not has_substantive_state:
            return False
        return state.compaction_call_count < max(1, total_tool_calls // AUTO_COMPACT_AFTER_TOOL_CALLS)

    async def _refresh_memory(state: ResearchSessionState) -> None:
        state.ledger = await compact_research_state_via_mcp_or_local(
            mission=state.mission,
            search_queries=state.search_queries,
            fetched_pages=list(state.fetched_pages.values()),
            verification_results=state.verification_results,
            finding_artifacts=state.finding_artifacts,
            existing_ledger=state.ledger,
        )
        state.compacted_memory = build_fallback_memory(
            mission=state.ledger.mission,
            search_queries=state.ledger.search_queries,
            fetched_pages=list(state.fetched_pages.values()),
            verification_results=state.verification_results,
            finding_artifacts=state.finding_artifacts,
            existing_ledger=state.ledger,
        )
        state.compaction_call_count += 1

    def _search_budget(state: ResearchSessionState) -> int:
        return MAX_SEARCH_CALLS

    def _fetch_budget(state: ResearchSessionState) -> int:
        return MAX_FETCH_CALLS

    def _domain(url: str) -> str:
        return urlparse(url).netloc.lower()

    def _is_social_or_ugc_domain(domain: str) -> bool:
        return any(host in domain for host in ("reddit.com", "facebook.com", "instagram.com", "tiktok.com", "x.com"))

    def _is_officialish_domain(domain: str) -> bool:
        return domain.endswith(".gov") or domain.endswith(".org") or ".gov." in domain

    def _record_domain_outcome(state: ResearchSessionState, url: str, fetch_status: str) -> None:
        domain = _domain(url)
        if not domain:
            return
        domain_stats = state.artifacts.setdefault("domain_fetch_stats", {})
        stats = domain_stats.setdefault(domain, {"ok": 0, "blocked": 0, "error": 0})
        if fetch_status == "ok":
            stats["ok"] += 1
        elif fetch_status.startswith("blocked_"):
            stats["blocked"] += 1
        else:
            stats["error"] += 1

    def _rank_search_results(state: ResearchSessionState, payload: dict) -> dict:
        results = payload.get("results")
        if not isinstance(results, list):
            return payload
        domain_stats = state.artifacts.get("domain_fetch_stats", {})

        def sort_key(result: dict) -> tuple[float, float, str]:
            url = str(result.get("url", ""))
            domain = _domain(url)
            stats = domain_stats.get(domain, {})
            domain_score = float(stats.get("ok", 0)) - float(stats.get("blocked", 0)) - (0.5 * float(stats.get("error", 0)))
            provider_score = float(result.get("score") or 0.0)
            if _is_social_or_ugc_domain(domain):
                domain_score -= 3.0
            elif _is_officialish_domain(domain):
                domain_score += 1.5
            return (-domain_score, -provider_score, url)

        ranked_results = sorted(results, key=sort_key)
        return {**payload, "results": ranked_results}

    async def _maybe_auto_compact(state: ResearchSessionState) -> Optional[dict]:
        if not _should_auto_compact(state):
            return None
        await _refresh_memory(state)
        return {
            "auto_compacted": True,
            "memory": state.compacted_memory.model_dump(mode="json") if state.compacted_memory else None,
            "ledger": state.ledger.model_dump(mode="json") if state.ledger else None,
        }

    def _store_page(state: ResearchSessionState, page: ExtractedPage) -> dict:
        state.fetched_pages[str(page.url)] = page
        _record_domain_outcome(state, str(page.url), page.fetch_status)
        if page.fetch_status == "ok":
            for chunk in chunk_page(page):
                state.evidence_chunks[chunk.chunk_id] = chunk
        return page.to_agent_payload()

    def _store_search_result_snippets(state: ResearchSessionState, payload: dict) -> None:
        results = payload.get("results")
        if not isinstance(results, list):
            return
        snippet_payloads = state.artifacts.setdefault("search_result_pages", {})
        for result in results:
            url = str(result.get("url", "")).strip()
            snippet = (result.get("content") or "").strip()
            if not url or not snippet:
                continue
            page = ExtractedPage(
                url=url,
                title=result.get("title"),
                extracted_text=snippet,
                excerpt=snippet[:500],
                retrieval_method="search-result-snippet",
                fetch_status="ok",
            )
            state.search_snippet_pages.setdefault(url, []).append(page)
            snippet_payloads.setdefault(url, [])
            snippet_payload = page.model_dump(mode="json")
            if snippet_payload not in snippet_payloads[url]:
                snippet_payloads[url].append(snippet_payload)

    def _prefetched_pages_for_sources(state: ResearchSessionState, source_urls: List[str]) -> List[ExtractedPage]:
        pages: List[ExtractedPage] = []
        for url in source_urls:
            if url in state.fetched_pages:
                pages.append(state.fetched_pages[url])
            pages.extend(state.search_snippet_pages.get(url, []))
        return pages

    def _analysis_artifacts(state: ResearchSessionState) -> List[ResearchFindingArtifact]:
        artifacts: List[ResearchFindingArtifact] = []
        for index, analysis_run in enumerate(state.artifacts.get("analysis_runs", [])[-2:], start=1):
            executions = analysis_run.get("executions") or []
            if not executions:
                continue
            latest = executions[-1]
            output = (latest.get("output") or "").strip()
            if not output:
                continue
            lines = [line.strip() for line in output.splitlines() if line.strip()]
            summary = lines[0][:240]
            supporting_points = lines[:4]
            artifacts.append(
                ResearchFindingArtifact(
                    title=f"Calculated analysis {index}",
                    summary=summary,
                    supporting_points=supporting_points,
                    source_urls=[],
                )
            )
        return artifacts

    async def _derive_claim_checks(
        state: ResearchSessionState,
        artifacts: List[ResearchFindingArtifact],
    ) -> List[ClaimSupportResult]:
        existing_by_claim = {result.claim: result for result in state.verification_results}
        derived: List[ClaimSupportResult] = []
        for artifact in artifacts:
            source_urls = artifact.external_source_urls()
            if not source_urls:
                continue
            claim = artifact.summary
            if claim in existing_by_claim:
                derived.append(existing_by_claim[claim])
                continue
            result = await verify_claim_with_sources(
                claim=claim,
                source_urls=source_urls,
                prefetched_pages=_prefetched_pages_for_sources(state, source_urls),
            )
            state.verification_results.append(result)
            derived.append(result)
            if len(derived) >= MAX_REPORT_CLAIM_CHECKS:
                break
        return derived[:MAX_REPORT_CLAIM_CHECKS]

    def _store_claim_result(state: ResearchSessionState, result: ClaimSupportResult) -> dict:
        state.verification_results.append(result)
        state.artifacts.setdefault("verified_claims", []).append(result.model_dump(mode="json"))
        for match in result.evidence_matches:
            if match.chunk_id in state.evidence_chunks:
                continue
            state.evidence_chunks[match.chunk_id] = EvidenceChunk(
                chunk_id=match.chunk_id,
                url=match.url,
                title=match.title,
                text=match.snippet,
                char_start=match.char_start,
                char_end=match.char_end,
                retrieval_method="verification-evidence",
                lexical_score=match.retrieval_score,
                rerank_score=match.rerank_score,
            )
        return result.model_dump(mode="json")

    @agent.tool
    async def discover_runtime_tools(
        ctx: RunContext[ResearchSessionState],
        query: str,
    ) -> dict:
        """Use this tool when you need to discover which MCP runtime tools are relevant to the next step."""
        with logfire.span("agent.discover_runtime_tools", query=query):
            return await search_runtime_tools_via_mcp_or_local(query)

    @agent.tool
    async def call_runtime_tool(
        ctx: RunContext[ResearchSessionState],
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> dict:
        """Use this tool when you want to invoke a discovered MCP runtime tool by name."""
        state = ctx.deps
        with logfire.span(
            "agent.call_runtime_tool",
            tool_name=tool_name,
            argument_keys=sorted(arguments.keys()),
        ):

            if tool_name == "search_web_sources":
                query = arguments.get("query", "")
                normalized_query = " ".join(query.lower().split())
                if normalized_query in {" ".join(existing.lower().split()) for existing in state.search_queries}:
                    return {
                        "tool_name": tool_name,
                        "note": "Skipped duplicate search query. Use existing results or synthesize.",
                        "budget": {
                            "search_calls_used": state.search_call_count,
                            "search_calls_remaining": max(0, _search_budget(state) - state.search_call_count),
                        },
                    }
                if normalized_query in state.active_search_queries:
                    return {
                        "tool_name": tool_name,
                        "note": "This search is already in progress. Wait for its results instead of duplicating it.",
                        "budget": {
                            "search_calls_used": state.search_call_count,
                            "search_calls_remaining": max(0, _search_budget(state) - state.search_call_count),
                        },
                    }
                if state.search_call_count >= _search_budget(state):
                    return {
                        "tool_name": tool_name,
                        "note": "Search budget exhausted. Fetch from known sources or synthesize.",
                        "budget": {
                            "search_calls_used": state.search_call_count,
                            "search_calls_remaining": 0,
                        },
                    }
                state.search_call_count += 1
                state.active_search_queries.add(normalized_query)
                try:
                    payload = await call_runtime_tool_via_mcp_or_local(
                        tool_name,
                        {"query": query, "max_results": min(arguments.get("max_results", 5), 5)},
                    )
                    payload = _rank_search_results(state, payload)
                    _store_search_result_snippets(state, payload)
                    state.search_queries.append(query)
                finally:
                    state.active_search_queries.discard(normalized_query)
                payload["budget"] = {
                    "search_calls_used": state.search_call_count,
                    "search_calls_remaining": max(0, _search_budget(state) - state.search_call_count),
                }
                payload.setdefault(
                    "note",
                    "Search snippets are stored as usable evidence. Fetch a page only if you need stronger or more detailed support.",
                )
                auto_compact = await _maybe_auto_compact(state)
                if auto_compact:
                    payload["auto_compact"] = auto_compact
                return payload

            if tool_name == "fetch_page":
                url = arguments["url"]
                if url in state.fetched_pages:
                    cached_page = state.fetched_pages[url]
                    return {
                        **cached_page.to_agent_payload(),
                        "cached": True,
                        "budget": {
                            "fetch_calls_used": state.fetch_call_count,
                            "fetch_calls_remaining": max(0, _fetch_budget(state) - state.fetch_call_count),
                        },
                    }
                if url in state.active_fetch_urls:
                    return {
                        "url": url,
                        "fetch_status": "in_progress",
                        "note": "This page is already being fetched. Use the pending result instead of issuing another fetch.",
                        "budget": {
                            "fetch_calls_used": state.fetch_call_count,
                            "fetch_calls_remaining": max(0, _fetch_budget(state) - state.fetch_call_count),
                        },
                    }
                if state.fetch_call_count >= _fetch_budget(state):
                    return {
                        "url": url,
                        "fetch_status": "budget_exhausted",
                        "note": "Fetch budget exhausted. Verify or synthesize from existing evidence.",
                        "budget": {
                            "fetch_calls_used": state.fetch_call_count,
                            "fetch_calls_remaining": 0,
                        },
                    }
                state.fetch_call_count += 1
                state.active_fetch_urls.add(url)
                try:
                    payload = await call_runtime_tool_via_mcp_or_local(tool_name, {"url": url})
                finally:
                    state.active_fetch_urls.discard(url)
                page = ExtractedPage.model_validate(payload)
                result = {
                    **_store_page(state, page),
                    "budget": {
                        "fetch_calls_used": state.fetch_call_count,
                        "fetch_calls_remaining": max(0, _fetch_budget(state) - state.fetch_call_count),
                    },
                }
                if page.fetch_status.startswith("blocked_"):
                    result["note"] = (
                        "Direct fetch was blocked for this source. Prefer another source or use browse_page_tool "
                        "only if this page is essential."
                    )
                auto_compact = await _maybe_auto_compact(state)
                if auto_compact:
                    result["auto_compact"] = auto_compact
                return result

            if tool_name == "browse_page_tool":
                url = arguments["url"]
                concise_mission = (state.mission or "").lower()
                if "concise" in concise_mission:
                    return {
                        "url": url,
                        "fetch_status": "budget_exhausted",
                        "note": "Browse is disabled for this bounded run. Continue with fetched evidence and synthesize.",
                        "budget": {
                            "browse_calls_used": state.browse_call_count,
                            "browse_calls_remaining": 0,
                        },
                    }
                if url in state.fetched_pages and state.fetched_pages[url].fetch_status == "ok":
                    cached_page = state.fetched_pages[url]
                    return {
                        **cached_page.to_agent_payload(),
                        "cached": True,
                        "note": "A fetched copy already exists. Browse only if you need interactive content not captured by fetch.",
                        "budget": {
                            "browse_calls_used": state.browse_call_count,
                            "browse_calls_remaining": max(0, MAX_BROWSE_CALLS - state.browse_call_count),
                        },
                    }
                if url in state.active_browse_urls:
                    return {
                        "url": url,
                        "fetch_status": "in_progress",
                        "note": "This page is already being browsed. Wait for that result instead of opening it again.",
                        "budget": {
                            "browse_calls_used": state.browse_call_count,
                            "browse_calls_remaining": max(0, MAX_BROWSE_CALLS - state.browse_call_count),
                        },
                    }
                if state.browse_call_count >= MAX_BROWSE_CALLS:
                    return {
                        "url": url,
                        "fetch_status": "budget_exhausted",
                        "note": "Browse budget exhausted. Continue with existing fetched evidence.",
                        "budget": {
                            "browse_calls_used": state.browse_call_count,
                            "browse_calls_remaining": 0,
                        },
                    }
                state.browse_call_count += 1
                state.active_browse_urls.add(url)
                try:
                    payload = await call_runtime_tool_via_mcp_or_local(
                        tool_name,
                        {"url": url, "goal": arguments.get("goal")},
                    )
                finally:
                    state.active_browse_urls.discard(url)
                page = ExtractedPage.model_validate(payload)
                result = {
                    **_store_page(state, page),
                    "budget": {
                        "browse_calls_used": state.browse_call_count,
                        "browse_calls_remaining": max(0, MAX_BROWSE_CALLS - state.browse_call_count),
                    },
                }
                auto_compact = await _maybe_auto_compact(state)
                if auto_compact:
                    result["auto_compact"] = auto_compact
                return result

            if tool_name == "compact_research_state_tool":
                if state.artifacts.get("generated_report"):
                    return {
                        "note": "Compaction skipped because a final report has already been generated for this run.",
                        "ledger": state.ledger.model_dump(mode="json") if state.ledger else None,
                        "memory": state.compacted_memory.model_dump(mode="json") if state.compacted_memory else None,
                        "budget": {
                            "search_calls_used": state.search_call_count,
                            "fetch_calls_used": state.fetch_call_count,
                            "browse_calls_used": state.browse_call_count,
                            "compactions_used": state.compaction_call_count,
                        },
                    }
                payload = await call_runtime_tool_via_mcp_or_local(
                    tool_name,
                    {
                        "mission": state.mission,
                        "search_queries": state.search_queries,
                        "fetched_pages": [page.model_dump(mode="json") for page in state.fetched_pages.values()],
                        "verification_results": [result.model_dump(mode="json") for result in state.verification_results],
                        "finding_artifacts": [artifact.model_dump(mode="json") for artifact in state.finding_artifacts],
                        "existing_ledger": state.ledger.model_dump(mode="json") if state.ledger else None,
                    },
                )
                await _refresh_memory(state)
                return {
                    "ledger": payload,
                    "memory": state.compacted_memory.model_dump(mode="json") if state.compacted_memory else None,
                    "budget": {
                        "search_calls_used": state.search_call_count,
                        "fetch_calls_used": state.fetch_call_count,
                        "browse_calls_used": state.browse_call_count,
                        "compactions_used": state.compaction_call_count,
                    },
                }

            if tool_name == "retrieve_evidence_chunks":
                source_urls = arguments.get("source_urls")
                if not source_urls and arguments.get("source_url"):
                    source_urls = [arguments["source_url"]]
                if not source_urls:
                    return {
                        "claim": arguments.get("claim"),
                        "chunks": [],
                        "note": "retrieve_evidence_chunks requires source_urls. Discover or supply source URLs before requesting evidence chunks.",
                    }
                chunks = await retrieve_evidence_candidates(
                    claim=arguments["claim"],
                    source_urls=source_urls,
                    prefetched_pages=_prefetched_pages_for_sources(state, source_urls),
                )
                for chunk in chunks:
                    state.evidence_chunks[chunk.chunk_id] = chunk
                return {"claim": arguments["claim"], "chunks": [chunk.model_dump(mode="json") for chunk in chunks]}

            if tool_name == "verify_claim":
                source_urls = arguments.get("source_urls")
                if not source_urls and arguments.get("source_url"):
                    source_urls = [arguments["source_url"]]
                if not source_urls:
                    return {
                        "claim": arguments.get("claim"),
                        "status": "unsupported",
                        "supporting_urls": [],
                        "evidence_snippets": [],
                        "reasoning": "verify_claim requires source_urls. No source URLs were supplied for verification.",
                        "evidence_matches": [],
                    }
                result = await verify_claim_with_sources(
                    claim=arguments["claim"],
                    source_urls=source_urls,
                    prefetched_pages=_prefetched_pages_for_sources(state, source_urls),
                )
                return _store_claim_result(state, result)

            if tool_name == "summarize_claim_support":
                payload = await call_runtime_tool_via_mcp_or_local(
                    tool_name,
                    {"verification_results": [result.model_dump(mode="json") for result in state.verification_results]},
                )
                overview = SupportOverview.model_validate(payload)
                state.artifacts["support_overview"] = overview.model_dump()
                return overview.model_dump()

            if tool_name in {"list_available_skills", "load_skill"}:
                logfire.info(
                    "agent skill tool selected",
                    tool_name=tool_name,
                    skill_name=arguments.get("skill_name"),
                )
                return await call_runtime_tool_via_mcp_or_local(tool_name, arguments)

            return {"tool_name": tool_name, "note": "Unsupported runtime tool name."}

    @agent.tool
    async def run_data_analysis(ctx: RunContext[ResearchSessionState], task: str) -> dict:
        """Use this tool when calculations, tabular analysis, or small code execution are needed."""
        result = await execute_python_task(task)
        payload = result.model_dump()
        ctx.deps.artifacts.setdefault("analysis_runs", []).append(payload)
        return payload

    @agent.tool
    async def record_research_finding(
        ctx: RunContext[ResearchSessionState],
        title: str,
        summary: str,
        supporting_points: List[str],
        source_urls: List[str],
    ) -> dict:
        """Use this tool when you want to save a grounded finding for later synthesis into the final report."""
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
        """Use this tool when you are ready to assemble the final report from recorded findings and verification state."""
        completed_tasks = []
        artifact_candidates = ctx.deps.finding_artifacts[-MAX_REPORT_FINDINGS:] + _analysis_artifacts(ctx.deps)
        artifact_candidates = artifact_candidates[-MAX_REPORT_FINDINGS:]
        for index, artifact in enumerate(artifact_candidates, start=1):
            completed_tasks.append(
                CompletedTaskSummary(
                    task_id=f"finding_{index}",
                    description=artifact.title,
                    summary=artifact.summary,
                    findings=artifact.to_search_findings()[:MAX_REPORT_SUPPORT_POINTS],
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
                    reasoning=f"Fetched via {page.retrieval_method}; credibility scoring can be improved later.",
                )
            )
            if len(source_assessments) >= MAX_REPORT_SOURCE_ASSESSMENTS:
                break
        if len(source_assessments) < MAX_REPORT_SOURCE_ASSESSMENTS:
            for pages in ctx.deps.search_snippet_pages.values():
                for page in pages:
                    title = page.title or str(page.url)
                    if title in seen_titles:
                        continue
                    seen_titles.add(title)
                    source_assessments.append(
                        SourceAssessment(
                            source_title=title,
                            credibility_rating="Medium",
                            reasoning="Available as a metasearch/result snippet rather than a fully fetched page.",
                        )
                    )
                    if len(source_assessments) >= MAX_REPORT_SOURCE_ASSESSMENTS:
                        break
                if len(source_assessments) >= MAX_REPORT_SOURCE_ASSESSMENTS:
                    break

        derived_claim_checks = await _derive_claim_checks(ctx.deps, artifact_candidates)
        verification_results = ctx.deps.verification_results or derived_claim_checks
        verification_summary = None
        if verification_results or source_assessments:
            support_counts = {
                "supported": 0,
                "partial": 0,
                "unsupported": 0,
                "conflicting": 0,
            }
            for result in verification_results:
                support_counts[result.status] = support_counts.get(result.status, 0) + 1

            approved_for_use = support_counts["unsupported"] == 0 and support_counts["conflicting"] == 0
            overall_quality = "high" if approved_for_use else "medium"
            if support_counts["conflicting"]:
                overall_quality = "low"

            selected_claim_checks = sorted(
                verification_results,
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
            finding_artifacts=artifact_candidates,
            verification=verification_summary,
        )
        final_report = (await build_final_report(report_input)).model_dump(mode="json")
        ctx.deps.artifacts["generated_report"] = final_report
        return final_report

    return agent


research_agent = create_research_agent()
