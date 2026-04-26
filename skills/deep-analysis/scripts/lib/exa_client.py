"""Exa API client — REST wrapper for Exa semantic search.

Replaces DDGS (DuckDuckGo) with Exa's cleaner structured results.
Two-step: search (URLs + titles) → contents (page text as markdown).
API key read from EXA_API_KEY env var (same key as Exa MCP server).
"""

from __future__ import annotations

import os
from typing import Optional

import requests

EXA_BASE = "https://api.exa.ai"
REQUEST_TIMEOUT = 15


def _api_key() -> str:
    return os.environ.get("EXA_API_KEY", "").strip()


def _headers() -> dict:
    return {
        "x-api-key": _api_key(),
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def search(
    query: str,
    num_results: int = 8,
    *,
    include_domains: Optional[list[str]] = None,
    exclude_domains: Optional[list[str]] = None,
) -> list[dict]:
    """Exa two-step search: search for URLs, then batch fetch page content.

    Returns [{title, body, url, source: "exa", published}] with DDGS-compatible
    field names for drop-in replacement.
    """
    # Step 1: Search for URLs
    payload: dict = {
        "query": query,
        "numResults": num_results,
        "type": "auto",
    }
    if include_domains:
        payload["includeDomains"] = include_domains
    if exclude_domains:
        payload["excludeDomains"] = exclude_domains

    try:
        r = requests.post(
            f"{EXA_BASE}/search",
            json=payload,
            headers=_headers(),
            timeout=REQUEST_TIMEOUT,
        )
        r.raise_for_status()
        meta = r.json()
    except Exception as e:
        return [{"error": f"exa search: {type(e).__name__}: {str(e)[:120]}"}]

    items = meta.get("results", [])
    if not items:
        return []

    # Step 2: Batch fetch page content
    urls = [it["url"] for it in items if it.get("url")]
    text_map: dict[str, str] = {}
    if urls:
        try:
            r2 = requests.post(
                f"{EXA_BASE}/contents",
                json={"urls": urls, "maxCharacters": 2000},
                headers=_headers(),
                timeout=REQUEST_TIMEOUT + 5,
            )
            r2.raise_for_status()
            contents_data = r2.json()
            for page in contents_data.get("results", []):
                t = (page.get("text") or "")
                if t:
                    text_map[page.get("url", "")] = t[:2000]
        except Exception:
            pass  # text fetch is best-effort

    # Merge
    results = []
    for item in items:
        url = item.get("url", "")
        body = text_map.get(url, "")
        results.append({
            "title": item.get("title", ""),
            "body": body,
            "url": url,
            "source": "exa",
            "published": item.get("publishedDate", ""),
        })

    return results


def fetch_page(url: str, max_chars: int = 3000) -> dict | None:
    """Fetch single page content as clean markdown via Exa contents API."""
    try:
        r = requests.post(
            f"{EXA_BASE}/contents",
            json={"urls": [url], "maxCharacters": max_chars},
            headers=_headers(),
            timeout=REQUEST_TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
        pages = data.get("results", [])
        if pages and pages[0].get("text"):
            return {
                "url": pages[0].get("url", url),
                "text": pages[0]["text"][:max_chars],
            }
        return None
    except Exception:
        return None
