from typing import Optional

from .browser_service import browse_page_with_playwright
from .fetch_service import fetch_url
from .models import ExtractedPage


async def browse_page(url: str, goal: Optional[str] = None) -> ExtractedPage:
    try:
        return await browse_page_with_playwright(url=url, goal=goal)
    except Exception:
        page = await fetch_url(url)
        page.retrieval_method = f"fetch-fallback:{goal or 'general'}"
        return page
