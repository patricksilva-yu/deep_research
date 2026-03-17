import os

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse
try:
    from fastmcp.server.transforms.tool_search import BM25SearchTransform
except ImportError:  # pragma: no cover - FastMCP versions may expose this elsewhere
    try:
        from fastmcp.server.transforms.search import BM25SearchTransform
    except ImportError:  # pragma: no cover
        BM25SearchTransform = None

from api.research_runtime.models import ClaimSupportResult, ExtractedPage, ResearchFindingArtifact, ResearchLedger, SupportOverview
from api.research_runtime.skills import list_project_skills, load_project_skill
from api.research_runtime.compaction_service import compact_research_state
from api.research_runtime.fetch_service import fetch_url
from api.research_runtime.search_service import search_web
from api.research_runtime.tooling_browser import browse_page
from api.research_runtime.verification_service import (
    retrieve_evidence_chunks as retrieve_evidence_candidates,
    verify_claim_support,
)

mcp = FastMCP("research-hub")

if BM25SearchTransform is not None and hasattr(mcp, "add_transform"):
    mcp.add_transform(
        BM25SearchTransform(
            max_results=5,
            always_visible=["list_available_skills"],
        )
    )


@mcp.custom_route("/health", methods=["GET"])
async def health_check(_request: Request) -> JSONResponse:
    return JSONResponse({"status": "healthy", "server": "research-hub"})


@mcp.tool
def search_web_sources(query: str, max_results: int = 5) -> dict:
    """Use this tool when you need to find candidate web sources for a topic or claim."""
    results = search_web(query=query, max_results=max_results)
    return {
        "query": query,
        "results": [result.model_dump(mode="json") for result in results],
    }


@mcp.tool
async def fetch_page(url: str) -> dict:
    """Use this tool when you need the extracted contents of a specific URL."""
    page = await fetch_url(url)
    return page.model_dump(mode="json")


@mcp.tool
async def browse_page_tool(url: str, goal: str | None = None) -> dict:
    """Use this tool when a page is interactive or standard fetching may miss important content."""
    page = await browse_page(url=url, goal=goal)
    return page.model_dump(mode="json")


@mcp.tool
async def verify_claim(claim: str, source_urls: list[str]) -> dict:
    """Use this tool when you need to judge whether cited sources support a claim."""
    result = await verify_claim_support(claim=claim, source_urls=source_urls)
    return result.model_dump(mode="json")


@mcp.tool
async def retrieve_evidence_chunks(claim: str, source_urls: list[str]) -> dict:
    """Use this tool when you need high-signal evidence chunks for a claim before verification or reporting."""
    chunks = await retrieve_evidence_candidates(claim=claim, source_urls=source_urls)
    return {
        "claim": claim,
        "chunks": [chunk.model_dump(mode="json") for chunk in chunks],
    }


@mcp.tool
async def compact_research_state_tool(
    mission: str | None,
    search_queries: list[str],
    fetched_pages: list[dict],
    verification_results: list[dict],
    finding_artifacts: list[dict],
    existing_ledger: dict | None = None,
) -> dict:
    """Use this tool when you want to compress research progress into a durable ledger."""
    parsed_pages = [ExtractedPage.model_validate(page) for page in fetched_pages]
    parsed_verifications = [
        ClaimSupportResult.model_validate(result)
        for result in verification_results
    ]
    parsed_findings = [
        ResearchFindingArtifact.model_validate(artifact)
        for artifact in finding_artifacts
    ]
    ledger = ResearchLedger.model_validate(existing_ledger) if existing_ledger else None
    compacted = await compact_research_state(
        mission=mission,
        search_queries=search_queries,
        fetched_pages=parsed_pages,
        verification_results=parsed_verifications,
        finding_artifacts=parsed_findings,
        existing_ledger=ledger,
    )
    return compacted.model_dump(mode="json")


@mcp.tool
def summarize_claim_support(verification_results: list[dict]) -> dict:
    """Use this tool when you want an aggregate summary of claim verification outcomes."""
    parsed_verifications = [
        ClaimSupportResult.model_validate(result)
        for result in verification_results
    ]
    counts = {
        "supported": 0,
        "partial": 0,
        "unsupported": 0,
        "conflicting": 0,
    }
    for result in parsed_verifications:
        counts[result.status] = counts.get(result.status, 0) + 1

    notes = None
    if counts["unsupported"] or counts["conflicting"]:
        notes = "Some claims remain weak or contested and should be qualified in the final report."
    elif counts["partial"]:
        notes = "Several claims have partial support and should be phrased cautiously."
    elif sum(counts.values()) > 0:
        notes = "Verified claims are largely supported by fetched source text."

    overview = SupportOverview(
        supported_claims=counts["supported"],
        partial_claims=counts["partial"],
        unsupported_claims=counts["unsupported"],
        conflicting_claims=counts["conflicting"],
        notes=notes,
    )
    return overview.model_dump(mode="json")


@mcp.tool
def list_available_skills() -> dict:
    """Use this tool when you need to see which project skills are available."""
    return {"skills": list_project_skills()}


@mcp.tool
def load_skill(skill_name: str) -> dict:
    """Use this tool when you need the instructions for a specific skill."""
    return {
        "skill_name": skill_name,
        "content": load_project_skill(skill_name),
    }


if __name__ == "__main__":
    transport = os.getenv("FASTMCP_TRANSPORT", "stdio")
    host = os.getenv("FASTMCP_HOST", "0.0.0.0")
    port = int(os.getenv("FASTMCP_PORT", "9000"))

    if transport == "http":
        mcp.run(transport="http", host=host, port=port)
    else:
        mcp.run()
