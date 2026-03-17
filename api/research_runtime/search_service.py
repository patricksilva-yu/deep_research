import os
from typing import List
from urllib.parse import urlparse

from tavily import TavilyClient

from .models import SearchResult


def search_web(query: str, max_results: int = 5) -> List[SearchResult]:
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY environment variable not set.")

    client = TavilyClient(api_key=api_key)
    response = client.search(query=query, max_results=max_results)
    results = response.get("results", [])

    search_results: List[SearchResult] = []
    for result in results:
        search_results.append(
            SearchResult(
                title=result.get("title") or urlparse(result.get("url", "")).netloc,
                url=result["url"],
                content=result.get("content"),
                score=result.get("score"),
            )
        )
    return search_results
