import os
from typing import Any, Dict, List, Optional

import logfire

from .models import ClaimSupportResult, EvidenceChunk, ExtractedPage, ResearchFindingArtifact, ResearchLedger, ResearchMemory, SearchResult
from .skills import list_project_skills, load_project_skill
from .compaction_service import build_fallback_memory, compact_research_state
from .fetch_service import fetch_url
from .search_service import search_web
from .tooling_browser import browse_page
from .verification_service import retrieve_evidence_chunks, verify_claim_support

try:
    from fastmcp import Client
except ImportError:  # pragma: no cover - optional until dependency install
    Client = None


def _mcp_server_url() -> Optional[str]:
    return os.getenv("MCP_SERVER_URL")


def _extract_result_payload(result: Any) -> Any:
    if hasattr(result, "data"):
        return result.data
    return result


def _runtime_tool_catalog() -> List[Dict[str, str]]:
    return [
        {
            "name": "search_web_sources",
            "description": "Find candidate web sources for a topic or subtopic.",
        },
        {
            "name": "fetch_page",
            "description": "Fetch and extract the contents of a specific URL.",
        },
        {
            "name": "browse_page_tool",
            "description": "Open interactive pages when normal fetch is insufficient.",
        },
        {
            "name": "retrieve_evidence_chunks",
            "description": "Select candidate evidence chunks for a claim from cited sources.",
        },
        {
            "name": "verify_claim",
            "description": "Judge whether cited sources support a claim.",
        },
        {
            "name": "compact_research_state_tool",
            "description": "Compress current research progress into durable memory.",
        },
        {
            "name": "list_available_skills",
            "description": "List project skills available to the agent.",
        },
        {
            "name": "load_skill",
            "description": "Load the instructions for a named skill.",
        },
    ]


def _normalize_tool_entry(entry: Any) -> Optional[Dict[str, Any]]:
    if hasattr(entry, "model_dump"):
        entry = entry.model_dump(mode="json")
    elif hasattr(entry, "__dict__") and not isinstance(entry, dict):
        entry = {
            key: value
            for key, value in entry.__dict__.items()
            if not key.startswith("_")
        }

    if isinstance(entry, str):
        return {"name": entry, "description": ""}

    if not isinstance(entry, dict):
        return None

    name = entry.get("name") or entry.get("tool_name")
    description = entry.get("description") or entry.get("title") or entry.get("summary") or ""

    if not name:
        nested_tool = entry.get("tool")
        if isinstance(nested_tool, dict):
            name = nested_tool.get("name")
            description = description or nested_tool.get("description", "")

    if not name:
        return None

    normalized = {
        "name": name,
        "description": description,
    }
    if "inputSchema" in entry:
        normalized["input_schema"] = entry["inputSchema"]
    elif "input_schema" in entry:
        normalized["input_schema"] = entry["input_schema"]
    return normalized


def _normalize_tool_search_payload(payload: Any) -> List[Dict[str, Any]]:
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json")

    if isinstance(payload, dict):
        if "results" in payload and isinstance(payload["results"], list):
            payload = payload["results"]
        elif "tools" in payload and isinstance(payload["tools"], list):
            payload = payload["tools"]

    if not isinstance(payload, list):
        return []

    normalized: List[Dict[str, Any]] = []
    seen_names = set()
    for item in payload:
        entry = _normalize_tool_entry(item)
        if not entry:
            continue
        name = entry["name"]
        if name in seen_names:
            continue
        seen_names.add(name)
        normalized.append(entry)
    return normalized


async def _call_remote_tool(tool_name: str, arguments: Dict[str, Any]) -> Any:
    server_url = _mcp_server_url()
    if not server_url or Client is None:
        raise RuntimeError("Remote MCP client unavailable.")

    with logfire.span(
        "mcp.remote_tool_call",
        tool_name=tool_name,
        server_url=server_url,
        argument_keys=sorted(arguments.keys()),
    ):
        async with Client(server_url) as client:
            result = await client.call_tool(tool_name, arguments)
    return _extract_result_payload(result)


async def search_runtime_tools_via_mcp_or_local(query: str) -> Dict[str, Any]:
    try:
        with logfire.span("runtime_tool_discovery", query=query, transport="mcp"):
            payload = await _call_remote_tool("search_tools", {"query": query})
        normalized = _normalize_tool_search_payload(payload)
        if normalized:
            return {"query": query, "results": normalized}
    except Exception:
        with logfire.span("runtime_tool_discovery", query=query, transport="local-fallback"):
            pass
    return {"query": query, "results": _runtime_tool_catalog()}


async def call_runtime_tool_via_mcp_or_local(name: str, arguments: Dict[str, Any]) -> Any:
    normalized_arguments = dict(arguments)
    if name == "load_skill" and "skill_name" not in normalized_arguments:
        alias_value = normalized_arguments.get("name") or normalized_arguments.get("skill")
        if isinstance(alias_value, str) and alias_value:
            normalized_arguments["skill_name"] = alias_value
    if name == "load_skill":
        normalized_arguments = {
            "skill_name": normalized_arguments["skill_name"]
        }

    try:
        with logfire.span(
            "runtime_tool_call",
            tool_name=name,
            transport="mcp",
            argument_keys=sorted(normalized_arguments.keys()),
        ):
            return await _call_remote_tool("call_tool", {"name": name, "arguments": normalized_arguments})
    except Exception:
        with logfire.span(
            "runtime_tool_call",
            tool_name=name,
            transport="local-fallback",
            argument_keys=sorted(normalized_arguments.keys()),
        ):
            pass
        if name == "search_web_sources":
            results = search_web(query=normalized_arguments["query"], max_results=normalized_arguments.get("max_results", 5))
            return {
                "query": normalized_arguments["query"],
                "results": [result.model_dump(mode="json") for result in results],
            }
        if name == "fetch_page":
            return (await fetch_url(normalized_arguments["url"])).model_dump(mode="json")
        if name == "browse_page_tool":
            return (await browse_page(url=normalized_arguments["url"], goal=normalized_arguments.get("goal"))).model_dump(mode="json")
        if name == "retrieve_evidence_chunks":
            chunks = await retrieve_evidence_chunks(
                claim=normalized_arguments["claim"],
                source_urls=normalized_arguments["source_urls"],
            )
            return {"claim": normalized_arguments["claim"], "chunks": [chunk.model_dump(mode="json") for chunk in chunks]}
        if name == "verify_claim":
            return (
                await verify_claim_support(
                    claim=normalized_arguments["claim"],
                    source_urls=normalized_arguments["source_urls"],
                )
            ).model_dump(mode="json")
        if name == "compact_research_state_tool":
            ledger = await compact_research_state(
                mission=normalized_arguments.get("mission"),
                search_queries=normalized_arguments.get("search_queries", []),
                fetched_pages=[ExtractedPage.model_validate(page) for page in normalized_arguments.get("fetched_pages", [])],
                verification_results=[
                    ClaimSupportResult.model_validate(result)
                    for result in normalized_arguments.get("verification_results", [])
                ],
                finding_artifacts=[
                    ResearchFindingArtifact.model_validate(artifact)
                    for artifact in normalized_arguments.get("finding_artifacts", [])
                ],
                existing_ledger=(
                    ResearchLedger.model_validate(normalized_arguments["existing_ledger"])
                    if normalized_arguments.get("existing_ledger")
                    else None
                ),
            )
            return ledger.model_dump(mode="json")
        if name == "summarize_claim_support":
            return await summarize_claim_support_via_mcp_or_local(
                [ClaimSupportResult.model_validate(result) for result in normalized_arguments.get("verification_results", [])]
            )
        if name == "list_available_skills":
            logfire.info("runtime skill catalog requested", skill_count=len(list_project_skills()))
            return {"skills": list_project_skills()}
        if name == "load_skill":
            skill_name = normalized_arguments["skill_name"]
            logfire.info("runtime skill loaded", skill_name=skill_name)
            return {"skill_name": skill_name, "content": load_project_skill(skill_name)}
        raise RuntimeError(f"Unsupported runtime tool fallback: {name}")


async def search_web_via_mcp_or_local(query: str, max_results: int = 5) -> List[SearchResult]:
    try:
        payload = await _call_remote_tool(
            "search_web_sources",
            {"query": query, "max_results": max_results},
        )
        results = payload.get("results", []) if isinstance(payload, dict) else []
        return [SearchResult.model_validate(result) for result in results]
    except Exception:
        return search_web(query=query, max_results=max_results)


async def fetch_page_via_mcp_or_local(url: str) -> ExtractedPage:
    try:
        payload = await _call_remote_tool("fetch_page", {"url": url})
        return ExtractedPage.model_validate(payload)
    except Exception:
        return await fetch_url(url)


async def browse_page_via_mcp_or_local(url: str, goal: Optional[str] = None) -> ExtractedPage:
    try:
        payload = await _call_remote_tool("browse_page_tool", {"url": url, "goal": goal})
        return ExtractedPage.model_validate(payload)
    except Exception:
        return await browse_page(url=url, goal=goal)


async def verify_claim_via_mcp_or_local(
    claim: str,
    source_urls: List[str],
    prefetched_pages: Optional[List[ExtractedPage]] = None,
) -> ClaimSupportResult:
    try:
        payload = await _call_remote_tool(
            "verify_claim",
            {"claim": claim, "source_urls": source_urls},
        )
        return ClaimSupportResult.model_validate(payload)
    except Exception:
        return await verify_claim_support(
            claim=claim,
            source_urls=source_urls,
            prefetched_pages=prefetched_pages,
        )


async def retrieve_evidence_chunks_via_mcp_or_local(
    claim: str,
    source_urls: List[str],
    prefetched_pages: Optional[List[ExtractedPage]] = None,
) -> List[EvidenceChunk]:
    try:
        payload = await _call_remote_tool(
            "retrieve_evidence_chunks",
            {"claim": claim, "source_urls": source_urls},
        )
        chunks = payload.get("chunks", []) if isinstance(payload, dict) else []
        return [EvidenceChunk.model_validate(chunk) for chunk in chunks]
    except Exception:
        return await retrieve_evidence_chunks(
            claim=claim,
            source_urls=source_urls,
            prefetched_pages=prefetched_pages,
        )


async def compact_research_state_via_mcp_or_local(
    mission: Optional[str],
    search_queries: List[str],
    fetched_pages: List[ExtractedPage],
    verification_results: List[ClaimSupportResult],
    finding_artifacts: List[ResearchFindingArtifact],
    existing_ledger: Optional[ResearchLedger] = None,
) -> ResearchLedger:
    try:
        payload = await _call_remote_tool(
            "compact_research_state_tool",
            {
                "mission": mission,
                "search_queries": search_queries,
                "fetched_pages": [page.model_dump(mode="json") for page in fetched_pages],
                "verification_results": [result.model_dump(mode="json") for result in verification_results],
                "finding_artifacts": [artifact.model_dump(mode="json") for artifact in finding_artifacts],
                "existing_ledger": existing_ledger.model_dump(mode="json") if existing_ledger else None,
            },
        )
        return ResearchLedger.model_validate(payload)
    except Exception:
        return await compact_research_state(
            mission=mission,
            search_queries=search_queries,
            fetched_pages=fetched_pages,
            verification_results=verification_results,
            finding_artifacts=finding_artifacts,
            existing_ledger=existing_ledger,
        )


async def summarize_claim_support_via_mcp_or_local(
    verification_results: List[ClaimSupportResult],
) -> Dict[str, Any]:
    try:
        payload = await _call_remote_tool(
            "summarize_claim_support",
            {"verification_results": [result.model_dump() for result in verification_results]},
        )
        return payload if isinstance(payload, dict) else {}
    except Exception:
        counts = {
            "supported": 0,
            "partial": 0,
            "unsupported": 0,
            "conflicting": 0,
        }
        for result in verification_results:
            counts[result.status] = counts.get(result.status, 0) + 1

        notes = None
        if counts["unsupported"] or counts["conflicting"]:
            notes = "Some claims remain weak or contested and should be qualified in the final report."
        elif counts["partial"]:
            notes = "Several claims have partial support and should be phrased cautiously."
        elif sum(counts.values()) > 0:
            notes = "Verified claims are largely supported by fetched source text."

        return {
            "supported_claims": counts["supported"],
            "partial_claims": counts["partial"],
            "unsupported_claims": counts["unsupported"],
            "conflicting_claims": counts["conflicting"],
            "notes": notes,
        }


async def list_skills_via_mcp_or_local() -> Dict[str, Any]:
    try:
        payload = await _call_remote_tool("list_available_skills", {})
        return payload if isinstance(payload, dict) else {"skills": []}
    except Exception:
        return {"skills": list_project_skills()}


async def load_skill_via_mcp_or_local(skill_name: str) -> Dict[str, Any]:
    try:
        payload = await _call_remote_tool("load_skill", {"skill_name": skill_name})
        return payload if isinstance(payload, dict) else {"skill_name": skill_name, "content": ""}
    except Exception:
        return {
            "skill_name": skill_name,
            "content": load_project_skill(skill_name),
        }
