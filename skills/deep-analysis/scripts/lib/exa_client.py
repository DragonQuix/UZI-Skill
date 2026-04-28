"""Exa API client — REST wrapper for Exa semantic search.

Replaces DDGS (DuckDuckGo) with Exa's cleaner structured results.
Two-step: search (URLs + titles) → contents (page text as markdown).
API key read from EXA_API_KEY env var (same key as Exa MCP server).
"""

from __future__ import annotations

import os
import random
import time
from typing import Optional

import requests

EXA_BASE = "https://api.exa.ai"
REQUEST_TIMEOUT = 15


def _retry_request(method: str, url: str, max_retries: int = 2, **kwargs) -> requests.Response:
    """带指数退避的 HTTP 请求。重试条件: ConnectionError/Timeout/5xx/429。"""
    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            r = requests.request(method, url, **kwargs)
            if r.status_code in (429, 500, 502, 503, 504):
                if attempt < max_retries:
                    time.sleep((2 ** attempt) + random.uniform(0, 0.5))
                    continue
            r.raise_for_status()
            return r
        except (requests.ConnectionError, requests.Timeout) as e:
            last_exc = e
            if attempt < max_retries:
                time.sleep((2 ** attempt) + random.uniform(0, 0.5))
                continue
            raise
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code < 500 and e.response.status_code != 429:
                raise
            last_exc = e
            if attempt < max_retries:
                time.sleep((2 ** attempt) + random.uniform(0, 0.5))
                continue
            raise
    raise last_exc  # type: ignore[misc]


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
        r = _retry_request("POST", f"{EXA_BASE}/search",
                           json=payload, headers=_headers(), timeout=REQUEST_TIMEOUT)
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
            r2 = _retry_request("POST", f"{EXA_BASE}/contents",
                                json={"urls": urls, "maxCharacters": 2000},
                                headers=_headers(), timeout=REQUEST_TIMEOUT + 5)
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
        r = _retry_request("POST", f"{EXA_BASE}/contents",
                           json={"urls": [url], "maxCharacters": max_chars},
                           headers=_headers(), timeout=REQUEST_TIMEOUT)
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
