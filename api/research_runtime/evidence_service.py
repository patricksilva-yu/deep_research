import hashlib
import os
import re
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
            raw_id = f"{page.url}:{page.retrieval_method}:{start}:{end}".encode("utf-8")
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


def _tokenize(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) > 2}


def _is_review_like(text: str) -> bool:
    lowered = text.lower()
    first_person_hits = sum(lowered.count(token) for token in (" i ", " my ", " we ", " our "))
    service_hits = sum(lowered.count(token) for token in (" boarding", " luggage", " cabin crew", " seat", "wifi", "pilot", "flight was"))
    return first_person_hits >= 3 and service_hits >= 2


def _is_navigation_like(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) >= 8:
        short_lines = sum(1 for line in lines if len(line.split()) <= 4)
        if short_lines / len(lines) >= 0.6:
            return True
    return False


def _candidate_score(claim: str, chunk: EvidenceChunk) -> float:
    claim_tokens = _tokenize(claim)
    chunk_tokens = _tokenize(chunk.text)
    overlap = len(claim_tokens & chunk_tokens)
    numeric_bonus = len(re.findall(r"(?:cad|\$|usd|€|£|\d{2,})", chunk.text.lower()))
    score = float(overlap) + min(numeric_bonus * 0.25, 3.0)
    if _is_review_like(f" {chunk.text.lower()} "):
        score -= 4.0
    if _is_navigation_like(chunk.text):
        score -= 3.0
    return score


def _preselect_candidates(claim: str, chunks: List[EvidenceChunk], limit: int) -> List[EvidenceChunk]:
    ranked = sorted(chunks, key=lambda chunk: (_candidate_score(claim, chunk), chunk.lexical_score), reverse=True)
    selected = [chunk for chunk in ranked if _candidate_score(claim, chunk) > 0][:limit]
    return selected or ranked[:limit]


async def retrieve_evidence_candidates(
    claim: str,
    chunks: Iterable[EvidenceChunk],
    limit: int = 8,
) -> EvidenceRetrievalResult:
    candidate_pool = list(chunks)
    if not candidate_pool:
        return EvidenceRetrievalResult(claim=claim, candidates=[])

    selector_candidates = _preselect_candidates(claim, candidate_pool, MAX_SELECTOR_CANDIDATES)
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
