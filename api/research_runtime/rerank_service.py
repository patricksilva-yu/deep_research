import os
from typing import List

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIResponsesModelSettings

from .models import EvidenceChunk, RerankedEvidenceResult

load_dotenv()

RERANKER_MODEL = os.getenv("RESEARCH_RERANKER_MODEL", "openai-responses:gpt-5-mini")


class _RerankOutput(BaseModel):
    ranked_chunk_ids: List[str] = Field(default_factory=list)
    reasoning: str = Field(description="Short explanation of the ranking")


reranker_agent = Agent(
    RERANKER_MODEL,
    instructions=(
        "You rerank evidence chunks for a claim. Prefer direct support, precise scope match, "
        "and chunks with concrete facts over vague mentions. Return only ranked chunk ids and a short reason."
    ),
    output_type=_RerankOutput,
    model_settings=OpenAIResponsesModelSettings(
        openai_reasoning_effort="minimal",
        openai_reasoning_summary="auto",
    ),
    retries=2,
)


async def rerank_evidence_chunks(claim: str, chunks: List[EvidenceChunk], limit: int = 5) -> RerankedEvidenceResult:
    if not chunks:
        return RerankedEvidenceResult(claim=claim, ranked_chunk_ids=[], reasoning="No candidate chunks available.")

    prompt = {
        "claim": claim,
        "candidates": [
            {
                "chunk_id": chunk.chunk_id,
                "url": str(chunk.url),
                "title": chunk.title,
                "lexical_score": chunk.lexical_score,
                "text_preview": chunk.preview(),
            }
            for chunk in chunks[:limit]
        ],
    }

    try:
        result = await reranker_agent.run(prompt)
        ranked_chunk_ids = [chunk_id for chunk_id in result.output.ranked_chunk_ids if chunk_id in {chunk.chunk_id for chunk in chunks}]
        if ranked_chunk_ids:
            return RerankedEvidenceResult(
                claim=claim,
                ranked_chunk_ids=ranked_chunk_ids,
                reasoning=result.output.reasoning,
            )
    except Exception:
        pass

    fallback_ids = [chunk.chunk_id for chunk in sorted(chunks, key=lambda item: item.lexical_score, reverse=True)[:limit]]
    return RerankedEvidenceResult(
        claim=claim,
        ranked_chunk_ids=fallback_ids,
        reasoning="Fell back to lexical candidate ranking.",
    )
