import hashlib
import os
from typing import Dict, Iterable, List

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIResponsesModelSettings

from .models import EvidenceChunk, EvidenceRetrievalResult, ExtractedPage

load_dotenv()

EVIDENCE_SELECTOR_MODEL = os.getenv("RESEARCH_EVIDENCE_SELECTOR_MODEL", "openai-responses:gpt-5-mini")
MAX_SELECTOR_CANDIDATES = int(os.getenv("RESEARCH_EVIDENCE_SELECTOR_CANDIDATES", "12"))


class _EvidenceSelectorOutput(BaseModel):
    selected_chunk_ids: List[str] = Field(default_factory=list, description="Chunk ids most relevant to the claim")
    reasoning: str = Field(description="Short explanation of why these chunks were selected")


evidence_selector_agent = Agent(
    EVIDENCE_SELECTOR_MODEL,
    instructions=(
        "You select the most relevant evidence chunks for a claim. Prefer direct support, precise scope match, "
        "and chunks that contain concrete facts or explanations. Return only chunk ids and a short reason."
    ),
    output_type=_EvidenceSelectorOutput,
    model_settings=OpenAIResponsesModelSettings(
        openai_reasoning_effort="minimal",
        openai_reasoning_summary="auto",
    ),
    retries=2,
)


def chunk_page(
    page: ExtractedPage,
    chunk_size: int = 1200,
    overlap: int = 150,
) -> List[EvidenceChunk]:
    if not page.extracted_text:
        return []

    chunks: List[EvidenceChunk] = []
    step = max(chunk_size - overlap, 1)
    start = 0
    text = page.extracted_text

    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk_text = text[start:end].strip()
        if chunk_text:
            raw_id = f"{page.url}:{start}:{end}".encode("utf-8")
            chunk_id = hashlib.sha1(raw_id).hexdigest()[:16]
            chunks.append(
                EvidenceChunk(
                    chunk_id=chunk_id,
                    url=page.url,
                    title=page.title,
                    text=chunk_text,
                    char_start=start,
                    char_end=end,
                    retrieval_method=page.retrieval_method,
                )
            )
        start += step

    return chunks


def build_evidence_store(pages: Iterable[ExtractedPage]) -> Dict[str, EvidenceChunk]:
    store: Dict[str, EvidenceChunk] = {}
    for page in pages:
        if page.fetch_status != "ok":
            continue
        for chunk in chunk_page(page):
            store[chunk.chunk_id] = chunk
    return store


def _breadth_first_fallback(chunks: List[EvidenceChunk], limit: int) -> List[EvidenceChunk]:
    grouped: Dict[str, List[EvidenceChunk]] = {}
    for chunk in chunks:
        grouped.setdefault(str(chunk.url), []).append(chunk)

    selected: List[EvidenceChunk] = []
    exhausted = False
    index = 0
    groups = list(grouped.values())
    while len(selected) < limit and not exhausted:
        exhausted = True
        for group in groups:
            if index < len(group):
                selected.append(group[index])
                exhausted = False
                if len(selected) >= limit:
                    break
        index += 1
    return selected


async def retrieve_evidence_candidates(
    claim: str,
    chunks: Iterable[EvidenceChunk],
    limit: int = 8,
) -> EvidenceRetrievalResult:
    candidate_pool = list(chunks)
    if not candidate_pool:
        return EvidenceRetrievalResult(claim=claim, candidates=[])

    selector_candidates = candidate_pool[:MAX_SELECTOR_CANDIDATES]
    prompt = {
        "claim": claim,
        "candidate_chunks": [
            {
                "chunk_id": chunk.chunk_id,
                "url": str(chunk.url),
                "title": chunk.title,
                "text_preview": chunk.preview(420),
            }
            for chunk in selector_candidates
        ],
    }

    try:
        result = await evidence_selector_agent.run(prompt)
        selected_lookup = {chunk.chunk_id: chunk for chunk in selector_candidates}
        selected = [
            selected_lookup[chunk_id]
            for chunk_id in result.output.selected_chunk_ids
            if chunk_id in selected_lookup
        ]
        if selected:
            for score, chunk in enumerate(selected, start=1):
                chunk.lexical_score = float(max(len(selected) - score + 1, 1))
            return EvidenceRetrievalResult(claim=claim, candidates=selected[:limit])
    except Exception:
        pass

    fallback = _breadth_first_fallback(candidate_pool, limit)
    for score, chunk in enumerate(fallback, start=1):
        chunk.lexical_score = float(max(len(fallback) - score + 1, 1))
    return EvidenceRetrievalResult(
        claim=claim,
        candidates=fallback,
    )
