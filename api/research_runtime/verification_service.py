from typing import Dict, List, Optional

from .claim_verifier import verify_claim_with_evidence
from .evidence_service import build_evidence_store, retrieve_evidence_candidates
from .fetch_service import fetch_url
from .models import ClaimSupportResult, EvidenceChunk, ExtractedPage
from .rerank_service import rerank_evidence_chunks


async def retrieve_evidence_chunks(
    claim: str,
    source_urls: List[str],
    prefetched_pages: Optional[List[ExtractedPage]] = None,
) -> List[EvidenceChunk]:
    pages_by_url: Dict[str, ExtractedPage] = {str(page.url): page for page in prefetched_pages or []}
    fetched_pages: List[ExtractedPage] = []

    for url in source_urls:
        page = pages_by_url.get(url)
        if page is None:
            page = await fetch_url(url)
        if page.fetch_status != "ok":
            continue
        fetched_pages.append(page)

    if not fetched_pages:
        return []

    store = build_evidence_store(fetched_pages)
    retrieved = retrieve_evidence_candidates(claim=claim, chunks=store.values(), limit=8)
    reranked = await rerank_evidence_chunks(claim=claim, chunks=retrieved.candidates, limit=5)
    ranked_lookup = {chunk_id: index for index, chunk_id in enumerate(reranked.ranked_chunk_ids)}

    selected_chunks: List[EvidenceChunk] = []
    for chunk_id in reranked.ranked_chunk_ids:
        chunk = store.get(chunk_id)
        if chunk is None:
            continue
        chunk.rerank_score = float(max(len(reranked.ranked_chunk_ids) - ranked_lookup[chunk_id], 1))
        selected_chunks.append(chunk)

    if selected_chunks:
        return selected_chunks[:4]

    return retrieved.candidates[:4]


async def verify_claim_support(
    claim: str,
    source_urls: List[str],
    prefetched_pages: Optional[List[ExtractedPage]] = None,
) -> ClaimSupportResult:
    evidence_chunks = await retrieve_evidence_chunks(
        claim=claim,
        source_urls=source_urls,
        prefetched_pages=prefetched_pages,
    )
    return await verify_claim_with_evidence(claim=claim, chunks=evidence_chunks)
