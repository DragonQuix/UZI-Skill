"""Unified web search wrapper with caching + fallback chain.

Primary: ddgs (DuckDuckGo) — free, no key, works in China via proxy
Fallback: (future) Tavily / Serper if API keys present

All searches go through lib/cache.py so repeated queries are cheap (12h TTL).
"""
from __future__ import annotations

import os
import time
from typing import Callable, Optional

from .cache import cached, TTL_HOURLY

try:
    from ddgs import DDGS  # type: ignore
    _DDGS_OK = True
except ImportError:
    _DDGS_OK = False


_SEARCH_TTL = 12 * 60 * 60  # 12h — news can update but we don't need bleeding edge


def _ddg_search(query: str, max_results: int = 10, region: str = "cn-zh") -> list[dict]:
    if not _DDGS_OK:
        return []
    try:
        with DDGS() as d:
            results = list(d.text(
                query,
                region=region,
                safesearch="off",
                max_results=max_results,
            ))
        # Normalize fields
        return [
            {
                "title": r.get("title", ""),
                "body": r.get("body", "") or r.get("snippet", ""),
                "url": r.get("href", "") or r.get("url", ""),
                "source": "ddgs",
            }
            for r in results
        ]
    except Exception as e:
        return [{"error": f"ddgs: {type(e).__name__}: {str(e)[:120]}"}]


# Garbage patterns — dictionary/wikipedia pages about Chinese characters, not stock data
_GARBAGE_PATTERNS = [
    "拼音", "汉语", "通用规范汉字", "常用字", "甲骨文", "部首",
    "笔画", "Unicode", "字形演变", "偏旁",
    "百科词条概述", "释义", "本义", "引申义",
]


def _is_garbage_result(r: dict) -> bool:
    """Detect dictionary/wikipedia noise — these are not stock analysis."""
    text = (r.get("body", "") + " " + r.get("title", ""))
    return sum(1 for p in _GARBAGE_PATTERNS if p in text) >= 2


def search(query: str, max_results: int = 10, cache_key_prefix: str = "ws") -> list[dict]:
    """Perform a cached web search. Returns list of {title, body, url, source}.

    Includes a quality filter to remove dictionary/Wikipedia garbage results
    that match Chinese character definitions instead of stock analysis.
    """
    key = f"{cache_key_prefix}__{query[:100]}__n{max_results}"
    raw = cached(
        "_global",
        key,
        lambda: _ddg_search(query, max_results=max_results),
        ttl=_SEARCH_TTL,
    )
    # Quality filter: remove dictionary/wikipedia garbage
    return [r for r in raw if not _is_garbage_result(r)]


def search_multi(queries: list[str], per_query: int = 5) -> dict[str, list[dict]]:
    """Run multiple queries, return {query: results}."""
    out = {}
    for q in queries:
        out[q] = search(q, max_results=per_query)
    return out


def extract_snippets(results: list[dict], max_snippets: int = 3, body_chars: int = 200) -> list[str]:
    """Flatten results into displayable snippets for report cards."""
    snippets = []
    for r in results[:max_snippets]:
        if "error" in r:
            continue
        title = r.get("title", "")[:80]
        body = r.get("body", "")[:body_chars]
        url = r.get("url", "")
        if title or body:
            snippets.append(f"{title} · {body} · {url}")
    return snippets


def quick_summary(query: str, max_snippets: int = 3) -> dict:
    """One-shot helper: search + return title/body snippets + urls."""
    results = search(query, max_results=max_snippets * 2)
    valid = [r for r in results if "error" not in r]
    return {
        "query": query,
        "count": len(valid),
        "snippets": [
            {
                "title": r.get("title", "")[:100],
                "body": r.get("body", "")[:280],
                "url": r.get("url", ""),
            }
            for r in valid[:max_snippets]
        ],
        "has_data": len(valid) > 0,
    }


if __name__ == "__main__":
    import json
    import sys
    q = sys.argv[1] if len(sys.argv) > 1 else "贵州茅台 白酒 行业分析"
    print(json.dumps(quick_summary(q), ensure_ascii=False, indent=2))
