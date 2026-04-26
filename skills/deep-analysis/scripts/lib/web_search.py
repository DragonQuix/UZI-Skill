"""Unified web search wrapper with caching + fallback chain.

Primary: Exa API — clean structured results, no DDGS noise/garbage
Fallback: ddgs (DuckDuckGo) — free, no key needed, works via proxy

All searches go through lib/cache.py so repeated queries are cheap (12h TTL).
"""
from __future__ import annotations

import os
import time
from typing import Callable, Optional

from .cache import cached, TTL_HOURLY

# Exa (primary)
try:
    from .exa_client import search as _exa_api_search
    _EXA_OK = True
except Exception:
    _EXA_OK = False

# DDGS (fallback)
try:
    from ddgs import DDGS  # type: ignore
    _DDGS_OK = True
except ImportError:
    _DDGS_OK = False


_SEARCH_TTL = 12 * 60 * 60  # 12h — news can update but we don't need bleeding edge


# ═══════════════════════════════════════════════════════════════
# v2.10.1 · 全局 ddgs 预算（防止首次跑爆炸 + Codex token 消耗过大）
# ═══════════════════════════════════════════════════════════════
# UZI_LITE=1 时 search() 进入严格预算模式：全生命周期最多 N 次真实搜索
# （命中 cache 的不计）。超出后直接返空，agent 会看到空结果知道走备选。
import threading as _threading
_BUDGET_LOCK = _threading.Lock()
_BUDGET_STATE = {"used": 0, "skipped": 0}


def _budget_allows() -> bool:
    import os
    cap_raw = os.environ.get("UZI_DDG_BUDGET")
    if not cap_raw:
        return True  # 未设预算 = 无限
    try:
        cap = int(cap_raw)
    except ValueError:
        return True
    with _BUDGET_LOCK:
        return _BUDGET_STATE["used"] < cap


def _budget_mark_used(n: int = 1) -> None:
    with _BUDGET_LOCK:
        _BUDGET_STATE["used"] += n


def _budget_mark_skipped(n: int = 1) -> None:
    with _BUDGET_LOCK:
        _BUDGET_STATE["skipped"] += n


def get_budget_state() -> dict:
    """让 fetcher 和 self_review 能查用量."""
    with _BUDGET_LOCK:
        return dict(_BUDGET_STATE)


# ═══════════════════════════════════════════════════════════════
# v2.7.3 · Trusted authority domains per dimension
# ═══════════════════════════════════════════════════════════════
# 把 Codex 建议的权威媒体 + 官方宏观源映射到定性维度。fetcher 可以调
# search_trusted(dim_key=..., query=...) 自动 prepend `(site:d1 OR site:d2 ...)`，
# 让 ddgs 限定在权威域里，显著提升结果质量（减少小红书/爬虫站噪声）。
#
# 验证（v2.7.3 发布前）：每个域 ddgs site: 查询都能返真实新闻标题。
TRUSTED_DOMAINS_BY_DIM: dict[str, tuple[str, ...]] = {
    # 宏观 / 政策
    "3_macro":  ("stats.gov.cn", "pbc.gov.cn", "safe.gov.cn", "gov.cn",
                 "chinamoney.com.cn", "chinabond.com.cn",
                 "cs.com.cn", "cnstock.com", "stcn.com", "nbd.com.cn"),
    "13_policy": ("gov.cn", "csrc.gov.cn", "miit.gov.cn", "ndrc.gov.cn",
                  "samr.gov.cn", "pbc.gov.cn", "safe.gov.cn",
                  "cs.com.cn", "cnstock.com", "stcn.com"),
    # 事件 / 公告 / 新闻
    "15_events": ("cs.com.cn", "cnstock.com", "stcn.com", "nbd.com.cn",
                  "sse.com.cn", "szse.cn", "hkexnews.hk",
                  "yicai.com", "cls.cn", "wallstreetcn.com"),
    # 舆情 / 散户
    "17_sentiment": ("xueqiu.com", "guba.eastmoney.com", "tgb.cn",
                     "jisilu.cn", "zhihu.com",
                     "nbd.com.cn", "stcn.com"),
    # 杀猪盘 / 风险信号
    "18_trap": ("zhihu.com", "weibo.com", "xiaohongshu.com", "douyin.com",
                "tgb.cn", "guba.eastmoney.com",
                "cs.com.cn", "nbd.com.cn"),
    # 行业 / 产业链
    "7_industry": ("stats.gov.cn", "miit.gov.cn", "ndrc.gov.cn",
                   "cs.com.cn", "cnstock.com", "stcn.com", "nbd.com.cn"),
    # 护城河 / 竞争格局
    "14_moat": ("nbd.com.cn", "yicai.com", "cs.com.cn", "stcn.com",
                "wallstreetcn.com", "cls.cn"),
    # 原材料 / 期货
    "8_materials": ("shfe.com.cn", "dce.com.cn", "czce.com.cn",
                    "ine.cn", "100ppi.com", "fx678.com"),
    "9_futures":   ("shfe.com.cn", "dce.com.cn", "czce.com.cn",
                    "ine.cn", "fx678.com"),
}


def trusted_domains_for(dim_key: str) -> tuple[str, ...]:
    """Return authority-ranked domains for a dim. Empty tuple if dim unknown."""
    return TRUSTED_DOMAINS_BY_DIM.get(dim_key, ())


def _exa_search(query: str, max_results: int = 10, include_domains: Optional[list[str]] = None) -> list[dict]:
    """Exa search with field normalization to DDGS-compatible format."""
    if not _EXA_OK:
        return [{"error": "exa: module not available"}]
    try:
        results = _exa_api_search(
            query, num_results=max_results, include_domains=include_domains,
        )
    except Exception as e:
        return [{"error": f"exa: {type(e).__name__}: {str(e)[:120]}"}]
    # Already normalized by exa_client: {title, body, url, source: "exa"}
    return results


def _exa_search_trusted(query: str, dim_key: str, max_results: int = 8,
                       extra_domains: tuple[str, ...] = ()) -> list[dict]:
    """Exa search with domain whitelist from TRUSTED_DOMAINS_BY_DIM.

    Unlike DDGS which uses `site:` syntax, Exa has native `includeDomains` parameter
    — cleaner and more reliable.
    """
    domains = list(trusted_domains_for(dim_key))
    if extra_domains:
        domains += list(extra_domains)
    # Cap at 6 domains to avoid overly restrictive queries
    domains = domains[:6]
    if not domains:
        return _exa_search(query, max_results=max_results)
    return _exa_search(query, max_results=max_results, include_domains=domains)


def _ddg_search(query: str, max_results: int = 10, region: str = "cn-zh") -> list[dict]:
    """v2.10.2 · 加硬超时保护（代理/GFW 挂时卡 60s+ 的核心原因）."""
    if not _DDGS_OK:
        return []
    # 用独立线程 + 硬超时把 DDGS 内部无 timeout 的 requests 兜住
    # UZI_DDG_TIMEOUT 可调（默认 10 秒）
    import os, concurrent.futures as _cf
    timeout_sec = int(os.environ.get("UZI_DDG_TIMEOUT", "10"))

    def _inner():
        with DDGS() as d:
            return list(d.text(
                query, region=region, safesearch="off", max_results=max_results,
            ))
    try:
        with _cf.ThreadPoolExecutor(max_workers=1) as pool:
            try:
                results = pool.submit(_inner).result(timeout=timeout_sec)
            except _cf.TimeoutError:
                return [{"error": f"ddgs: timeout > {timeout_sec}s（代理/网络不通？）"}]
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

    Tries Exa API first (clean structured results), falls back to DDGS.
    Includes a quality filter to remove dictionary/Wikipedia garbage results.

    v2.10.1 · 命中 cache 的不占预算；未命中 cache 时检查 UZI_DDG_BUDGET 预算。
    v2.16 · Exa 为主搜索后端，DDGS 仅 fallback。
    """
    key = f"{cache_key_prefix}__{query[:100]}__n{max_results}"

    def _fetcher():
        # Try Exa first
        if _EXA_OK:
            results = _exa_search(query, max_results=max_results)
            if results and not any("error" in r for r in results):
                return results
        # Fall back to DDGS
        if not _DDGS_OK:
            return [{"error": "search: no backend available (Exa unavailable, DDGS not installed)"}]
        if not _budget_allows():
            _budget_mark_skipped()
            return [{"_budget_exceeded": True,
                     "body": "全局 ddgs 预算已用尽（UZI_DDG_BUDGET），agent 请用 cached / hardcoded 数据"}]
        _budget_mark_used()
        return _ddg_search(query, max_results=max_results)

    raw = cached("_global", key, _fetcher, ttl=_SEARCH_TTL)
    return [r for r in raw if not _is_garbage_result(r) and not r.get("_budget_exceeded")]


def search_trusted(
    query: str,
    dim_key: str,
    max_results: int = 8,
    extra_sites: tuple[str, ...] = (),
    max_sites: int = 6,
) -> list[dict]:
    """v2.7.3 · site: 限定在 dim 对应的权威域里搜索。

    v2.16 · Exa 模式下用 native includeDomains 替代 DDGS site: 语法，
    更可靠、更干净。DDGS fallback 仍使用 site: 拼接。

    示例：
        search_trusted("贵州茅台 2026 Q1 业绩", dim_key="15_events")
        → 只从 cs.com.cn / cnstock.com / stcn.com / nbd.com.cn / ... 返结果

    参数：
      query: 用户查询
      dim_key: 维度 key（"3_macro" / "15_events" / ...）决定权威域白名单
      max_results: 总条数上限
      extra_sites: 追加域（比如特定行业要加自建站点）
      max_sites: 最多几个域（Exa 用 includeDomains，DDGS 用 site: OR 拼）

    返回：与 search() 一致的 list[dict]。若 dim 无映射，回退到普通 search。
    """
    domains = trusted_domains_for(dim_key)
    if extra_sites:
        domains = tuple(list(domains) + list(extra_sites))
    if not domains:
        return search(query, max_results=max_results)
    domains = domains[:max_sites]

    # Exa path: native domain filtering, separate cache key
    if _EXA_OK:
        key = f"wst_exa_{dim_key}__{query[:80]}__n{max_results}"
        def _fetcher():
            return _exa_search_trusted(query, dim_key, max_results=max_results,
                                       extra_domains=extra_sites)
        raw = cached("_global", key, _fetcher, ttl=_SEARCH_TTL)
        if raw and not any("error" in r for r in raw):
            return [r for r in raw if not _is_garbage_result(r)]

    # DDGS fallback: site: clause
    site_clause = " OR ".join(f"site:{d}" for d in domains)
    combined = f"({site_clause}) {query}"
    return search(combined, max_results=max_results, cache_key_prefix=f"wst_{dim_key}")


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
