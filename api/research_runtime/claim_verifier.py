import os
from typing import Dict, List

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIResponsesModelSettings

from .models import ClaimSupportResult, EvidenceChunk, EvidenceMatch

load_dotenv()

VERIFIER_MODEL = os.getenv("RESEARCH_VERIFIER_MODEL", "openai-responses:gpt-5-mini")


class _VerifierOutput(BaseModel):
    status: str = Field(description="supported, partial, unsupported, or conflicting")
    reasoning: str = Field(description="Short explanation grounded in the evidence")
    cited_chunk_ids: List[str] = Field(default_factory=list, description="Chunk ids that justify the verdict")


verifier_agent = Agent(
    VERIFIER_MODEL,
    instructions=(
        "You verify whether evidence chunks support a claim. "
        "Use only the supplied chunks. Mark 'supported' only when the claim is directly backed. "
        "Mark 'partial' when evidence is incomplete, 'unsupported' when it does not support the claim, "
        "and 'conflicting' when the evidence materially contradicts the claim."
    ),
    output_type=_VerifierOutput,
    model_settings=OpenAIResponsesModelSettings(
        openai_reasoning_effort="low",
        openai_reasoning_summary="auto",
    ),
    retries=2,
)


async def verify_claim_with_evidence(claim: str, chunks: List[EvidenceChunk]) -> ClaimSupportResult:
    if not chunks:
        return ClaimSupportResult(
            claim=claim,
            status="unsupported",
            supporting_urls=[],
            evidence_snippets=[],
            reasoning="No candidate evidence chunks were available for this claim.",
            evidence_matches=[],
        )

    chunk_lookup: Dict[str, EvidenceChunk] = {chunk.chunk_id: chunk for chunk in chunks}
    prompt = {
        "claim": claim,
        "evidence_chunks": [
            {
                "chunk_id": chunk.chunk_id,
                "url": str(chunk.url),
                "title": chunk.title,
                "text": chunk.preview(500),
            }
            for chunk in chunks[:4]
        ],
    }

    try:
        result = await verifier_agent.run(prompt)
        cited_chunks = [
            chunk_lookup[chunk_id]
            for chunk_id in result.output.cited_chunk_ids
            if chunk_id in chunk_lookup
        ]
        if not cited_chunks:
            cited_chunks = chunks[:2]

        evidence_matches = [
            EvidenceMatch(
                chunk_id=chunk.chunk_id,
                url=chunk.url,
                title=chunk.title,
                snippet=chunk.preview(280),
                char_start=chunk.char_start,
                char_end=chunk.char_end,
                retrieval_score=chunk.lexical_score,
                rerank_score=chunk.rerank_score,
            )
            for chunk in cited_chunks
        ]
        return ClaimSupportResult(
            claim=claim,
            status=result.output.status,
            supporting_urls=[chunk.url for chunk in cited_chunks],
            evidence_snippets=[match.snippet for match in evidence_matches],
            reasoning=result.output.reasoning,
            evidence_matches=evidence_matches,
        )
    except Exception:
        fallback_chunks = chunks[:2]
        evidence_matches = [
            EvidenceMatch(
                chunk_id=chunk.chunk_id,
                url=chunk.url,
                title=chunk.title,
                snippet=chunk.preview(280),
                char_start=chunk.char_start,
                char_end=chunk.char_end,
                retrieval_score=chunk.lexical_score,
                rerank_score=chunk.rerank_score,
            )
            for chunk in fallback_chunks
        ]
        return ClaimSupportResult(
            claim=claim,
            status="partial",
            supporting_urls=[chunk.url for chunk in fallback_chunks],
            evidence_snippets=[match.snippet for match in evidence_matches],
            reasoning="Verifier model was unavailable, so the claim was left as partially supported by top-ranked evidence.",
            evidence_matches=evidence_matches,
        )
