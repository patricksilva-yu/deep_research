import html
import re
from typing import Optional

from .models import ExtractedPage

try:
    from playwright.async_api import async_playwright
except ImportError:  # pragma: no cover - optional dependency until installed
    async_playwright = None


def _strip_html(raw_html: str) -> str:
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", raw_html)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _extract_title(raw_html: str) -> Optional[str]:
    title_match = re.search(r"(?is)<title>(.*?)</title>", raw_html)
    if not title_match:
        return None
    return html.unescape(title_match.group(1)).strip()


async def browse_page_with_playwright(
    url: str,
    goal: Optional[str] = None,
    timeout_ms: int = 20_000,
) -> ExtractedPage:
    if async_playwright is None:
        raise RuntimeError("Playwright is not installed.")

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            await page.wait_for_timeout(750)
            content = await page.content()
        finally:
            await browser.close()

    text = _strip_html(content)
    return ExtractedPage(
        url=url,
        title=_extract_title(content),
        extracted_text=text,
        excerpt=text[:400] if text else None,
        retrieval_method=f"playwright:{goal or 'general'}",
    )
