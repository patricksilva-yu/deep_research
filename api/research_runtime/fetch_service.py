import html
import re
from typing import Optional

import httpx

from .models import ExtractedPage

try:
    import trafilatura
except ImportError:  # pragma: no cover - optional dependency until installed
    trafilatura = None


def _strip_html(raw_html: str) -> str:
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", raw_html)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _build_excerpt(text: str, max_chars: int = 500, max_sentences: int = 3) -> Optional[str]:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return None

    sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    excerpt_parts = []
    total_chars = 0
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        projected = total_chars + len(sentence) + (1 if excerpt_parts else 0)
        if projected > max_chars and excerpt_parts:
            break
        excerpt_parts.append(sentence)
        total_chars = projected
        if len(excerpt_parts) >= max_sentences:
            break

    if excerpt_parts:
        return " ".join(excerpt_parts)[:max_chars]
    return cleaned[:max_chars]


def _classify_http_status(status_code: int) -> str:
    if status_code == 403:
        return "blocked_forbidden"
    if status_code == 429:
        return "blocked_rate_limited"
    if status_code >= 500:
        return f"http_{status_code}"
    return f"http_{status_code}"


def _classify_extracted_content(text: str) -> Optional[str]:
    normalized = text.lower()
    if "verify that you're not a robot" in normalized or "verify that you are not a robot" in normalized:
        return "blocked_antibot"
    if "enable javascript" in normalized and ("reload the page" in normalized or "run this app" in normalized):
        return "blocked_javascript"
    if "access denied" in normalized:
        return "blocked_access_denied"
    return None


async def fetch_url(url: str, timeout_seconds: float = 20.0) -> ExtractedPage:
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout_seconds) as client:
            response = await client.get(url)
    except httpx.HTTPError as exc:
        return ExtractedPage(
            url=url,
            title=None,
            extracted_text=f"Fetch failed for {url}: {exc}",
            excerpt=None,
            retrieval_method="httpx-error",
            fetch_status="network_error",
        )

    body = response.text
    fetch_status = "ok" if response.status_code < 400 else f"http_{response.status_code}"
    if response.status_code >= 400:
        return ExtractedPage(
            url=url,
            title=None,
            extracted_text=f"Fetch failed for {url}: HTTP {response.status_code}",
            excerpt=None,
            retrieval_method="httpx-error",
            fetch_status=_classify_http_status(response.status_code),
        )

    if trafilatura:
        extracted_text = trafilatura.extract(body, include_comments=False, include_links=False) or ""
    else:
        extracted_text = ""

    if not extracted_text:
        extracted_text = _strip_html(body)

    title_match = re.search(r"(?is)<title>(.*?)</title>", body)
    title: Optional[str] = html.unescape(title_match.group(1)).strip() if title_match else None
    content_status = _classify_extracted_content(extracted_text)
    excerpt = _build_excerpt(extracted_text)
    retrieval_method = "trafilatura" if trafilatura else "httpx-html-strip"
    return ExtractedPage(
        url=url,
        title=title,
        extracted_text=extracted_text,
        excerpt=excerpt,
        retrieval_method=retrieval_method,
        fetch_status=content_status or fetch_status,
    )
