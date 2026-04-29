"""Tiered JSON cache for fetcher scripts.

TTL is differentiated by data volatility:
- Real-time quote (price/change_pct):        60s
- Intraday K-line / capital flow / sentiment: 5 min
- Daily aggregates (LHB, north-bound):       2 hours
- News:                                       1 hour
- Quarterly financials / valuation history:  24 hours
- Static metadata (industry, name):          7 days

Set env STOCK_NO_CACHE=1 to bypass cache entirely (force refresh).
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Callable

# Tiered TTL constants (seconds)
TTL_REALTIME    = 60          # 1 minute — price snapshot
TTL_INTRADAY    = 5 * 60      # 5 min — kline, fund flow, sentiment hot rank
TTL_HOURLY      = 60 * 60     # 1 hour — news
TTL_DAILY       = 2 * 60 * 60 # 2 hours — LHB, northbound, margin (after market close)
TTL_QUARTERLY   = 24 * 60 * 60       # 24 hours — financials, research reports
TTL_STATIC      = 7 * 24 * 60 * 60   # 7 days — industry classification

# Default TTL when caller doesn't specify
CACHE_TTL_SECONDS = TTL_INTRADAY

CACHE_ROOT = Path(".cache")
NO_CACHE = os.environ.get("STOCK_NO_CACHE") == "1"


def _cache_path(ticker: str, key: str) -> Path:
    h = hashlib.md5(key.encode("utf-8")).hexdigest()[:12]
    safe_key = "".join(c if c.isalnum() or c in "._-" else "_" for c in key)[:60]
    return CACHE_ROOT / ticker / "api_cache" / f"{safe_key}__{h}.json"


def cached(ticker: str, key: str, fetch_fn: Callable[[], Any], ttl: int = CACHE_TTL_SECONDS) -> Any:
    """Return cached value if fresh, else call fetch_fn and store.
    Set STOCK_NO_CACHE=1 in the environment to force refresh.
    """
    path = _cache_path(ticker, key)
    now = time.time()

    if not NO_CACHE and path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if now - payload.get("_cached_at", 0) < ttl:
                return payload["data"]
        except (json.JSONDecodeError, KeyError):
            pass

    data = fetch_fn()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"_cached_at": now, "data": data, "_ttl": ttl}, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    return data


def market_status() -> dict:
    """Return current A-share market status: open/closed + next event.
    Used to label data freshness in the report header.
    """
    from datetime import datetime, time as dt_time
    now = datetime.now()
    weekday = now.weekday()  # 0=Mon, 6=Sun
    t = now.time()

    if weekday >= 5:
        return {"is_open": False, "label": "已收盘 (周末)", "now": now.isoformat(timespec="seconds")}

    morning_open = dt_time(9, 30)
    morning_close = dt_time(11, 30)
    afternoon_open = dt_time(13, 0)
    afternoon_close = dt_time(15, 0)

    if morning_open <= t < morning_close or afternoon_open <= t < afternoon_close:
        return {"is_open": True, "label": "交易中", "now": now.isoformat(timespec="seconds")}
    if morning_close <= t < afternoon_open:
        return {"is_open": False, "label": "午间休市", "now": now.isoformat(timespec="seconds")}
    if t < morning_open:
        return {"is_open": False, "label": "未开盘", "now": now.isoformat(timespec="seconds")}
    return {"is_open": False, "label": "已收盘", "now": now.isoformat(timespec="seconds")}


def write_task_output(ticker: str, task_name: str, data: dict) -> Path:
    """Write a task's final JSON to .cache/{ticker}/{task_name}.json

    v3.3+: When task_name is 'agent_analysis', validates schema before writing.
    Structural errors (buy_zones missing keys, wrong types) raise RuntimeError
    so the Agent can fix them immediately before stage2.

    v3.4+: Stamps _validated_by and _written_at into the saved JSON so stage2 can
    detect files that bypassed this API (e.g. agent using Path.write_text directly).
    """
    import datetime as _dt

    # ── v3.3 · agent_analysis 写入前校验 ──
    if task_name == "agent_analysis":
        try:
            from lib.agent_analysis_validator import validate as _validate
            issues = _validate(data)
            errs = [i for i in issues if i.severity == "error"]
            if errs:
                msg = ["agent_analysis.json 写入被阻断 — 以下字段必须修复:"]
                for e in errs:
                    msg.append(f"  🔴 {e.field}: {e.message}")
                    msg.append(f"     → {e.suggestion}")
                msg.append(f"\n  共 {len(errs)} 条结构性错误，修复后重试 write_task_output")
                raise RuntimeError("\n".join(msg))
            # v3.4 · 通过校验的打水印，供 stage2 识别合法来源
            data["_validated_by"] = "write_task_output"
            data["_written_at"] = _dt.datetime.now().isoformat(timespec="seconds")
        except ImportError:
            pass  # validator not available, write anyway

    path = CACHE_ROOT / ticker / f"{task_name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path


# ═══════════════════════════════════════════════════════════════
# v3.4 · agent_analysis 模板 — Agent 填值即可，不用记字段名
# ═══════════════════════════════════════════════════════════════

def agent_analysis_template(ticker: str, stock_name: str = "", extra: dict | None = None) -> dict:
    """Return a pre-populated agent_analysis.json template with all required
    fields and inline comments.  The Agent only needs to fill in the values —
    the structure, field names, and thresholds are enforced by the template.

    Usage from analyze-stock.md step 4:
        from lib.cache import agent_analysis_template, write_task_output
        aa = agent_analysis_template(ticker, stock_name)
        # fill in aa["dim_commentary"]["1_financials"] = "..."
        # fill in aa["panel_insights"] = "..."
        write_task_output(ticker, "agent_analysis", aa)
    """
    dims = [
        "0_basic", "1_financials", "2_kline", "3_macro", "4_peers", "5_chain",
        "6_research", "7_industry", "8_materials", "9_futures", "10_valuation",
        "11_governance", "12_capital_flow", "13_policy", "14_moat", "15_events",
        "16_lhb", "17_sentiment", "18_trap", "19_contests",
    ]
    template: dict = {
        "agent_reviewed": True,
        "_comment": "本文件由 agent_analysis_template() 生成骨架。Agent 填入具体值后通过 write_task_output() 写入。",
        "dim_commentary": {d: f"【待填充】基于 raw_data.json 写 1-2 句定性评语（≥20 字），引用具体数字" for d in dims},
        "panel_insights": "【待填充 ≥30 字】51 评委投票分布 + 多空分歧分析 + 各组特征",
        "great_divide_override": {
            "punchline": "【待填充 ≥10 字】基本面派 vs 技术派的核心冲突金句",
            "bull_say_rounds": [
                "【待填充】R1: 投资者名 — 看多论据（引用数字）",
                "【待填充】R2: ...",
                "【待填充】R3: ...",
            ],
            "bear_say_rounds": [
                "【待填充】R1: 投资者名 — 看空论据（引用数字）",
                "【待填充】R2: ...",
                "【待填充】R3: ...",
            ],
        },
        "narrative_override": {
            "core_conclusion": "【待填充 ≥20 字】综合结论 + 评分 + 关键证据",
            "risks": [
                "【待填充】下行风险 1",
                "【待填充】下行风险 2",
                "【待填充】上行风险 1（或更多下行风险，至少 3 条）",
            ],
            "buy_zones": {
                "value":      {"price": "【待填充】如 125-145 元", "rationale": "【待填充 ≥5 字】价值派入场理由"},
                "growth":     {"price": "【待填充】", "rationale": "【待填充 ≥5 字】成长派入场理由"},
                "technical":  {"price": "【待填充】", "rationale": "【待填充 ≥5 字】技术派入场理由"},
                "youzi":      {"price": "【待填充】", "rationale": "【待填充 ≥5 字】游资入场理由或 skip 说明"},
            },
        },
        "qualitative_deep_dive": {
            d: {
                "evidence": [
                    {
                        "source": "【待填充】来源名 (如 新浪财经/雪球/招商证券研报)",
                        "url": "【待填充】",
                        "finding": "【待填充】1-2 句发现",
                        "retrieved_at": "【待填充】ISO 日期",
                    },
                    {
                        "source": "【待填充】至少 2 条 evidence",
                        "url": "【待填充】",
                        "finding": "【待填充】",
                        "retrieved_at": "【待填充】",
                    },
                ],
                "associations": [
                    {
                        "link_to": "【待填充】关联维度 (如 1_financials)",
                        "chain_id": "【待填充】如 chain_macro_to_financials",
                        "causal_chain": "【待填充】宏观 → 行业 → 公司的因果链描述",
                        "estimated_impact": "【待填充】高/中/低",
                    },
                ],
                "conclusion": "【待填充】1-2 句该维度结论",
            }
            for d in ("3_macro", "7_industry", "8_materials", "9_futures", "13_policy", "15_events")
        },
        "data_gap_acknowledged": {},
    }
    if extra:
        template.update(extra)
    return template


def normalize_qualitative_deep_dive(
    raw_agent_output: dict,
    dim_name: str,
    link_to_dim: str = "1_financials",
) -> dict:
    """Convert free-form agent deep-dive output to the schema expected by stage2.

    Agent outputs for qualitative_deep_dive often contain extra keys
    (cross_causal_chains, sensitivity, industry_analysis, etc.) that don't
    match the strict {evidence[], associations[], conclusion} schema enforced
    by Gate 2.  This function normalizes to the canonical form.

    Returns: {"evidence": [...], "associations": [...], "conclusion": "..."}
    """
    # Evidence: keep up to 5 entries, map to canonical keys
    evidence = []
    for e in raw_agent_output.get("evidence", [])[:5]:
        if isinstance(e, dict):
            evidence.append({
                "source": str(e.get("source", "")),
                "url": str(e.get("url", "")),
                "finding": str(e.get("finding", "")),
                "retrieved_at": str(e.get("retrieved_at", "2026-04-29")),
            })

    # Associations: keep up to 3 entries, add required schema keys
    associations = []
    for i, a in enumerate(raw_agent_output.get("associations", [])[:3]):
        if isinstance(a, dict):
            associations.append({
                "link_to": link_to_dim,
                "chain_id": f"chain_{dim_name}_{i}",
                "causal_chain": str(a.get("causal_chain", "")),
                "estimated_impact": str(a.get("estimated_impact", "中")),
            })

    # Conclusion: unwrap if nested dict, truncate to 500 chars
    conclusion = raw_agent_output.get("conclusion", "")
    if isinstance(conclusion, dict):
        conclusion = str(conclusion)
    conclusion = str(conclusion)[:500]

    return {
        "evidence": evidence,
        "associations": associations,
        "conclusion": conclusion,
    }


# ═══════════════════════════════════════════════════════════════
# v3.6 · Agent 输出工具 — 健壮 JSON 加载 + panel 合并 + 深研归一化
# ═══════════════════════════════════════════════════════════════

def safe_load_agent_json(path: Path) -> dict:
    """Robustly load agent-generated JSON, auto-fixing Chinese double-quote
    nesting (e.g. '国十条' inside a JSON string value).

    Agent LLMs routinely emit Chinese-context ASCII double quotes within JSON
    string values, which breaks standard JSON parsing.  This function first
    tries standard parsing, and only applies targeted fixes on failure -
    valid JSON passes through untouched.

    Fix strategy (only applied when json.loads fails):
      1. Replace curly quotes (some agents use them)
      2. Replace Chinese-context ASCII quotes on the same line
      3. Re-raise the original error if all fixes fail
    """
    import re as _re

    text = path.read_text(encoding="utf-8")

    # Fast path: most agent outputs are valid JSON
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Fix path: only applied when standard parsing fails
    fixed = text
    fixed = fixed.replace(""", "「").replace(""", "」")  # " " → 「」

    # Chinese-char + " + short Chinese text + " + Chinese-char (same line only)
    fixed = _re.sub(
        r'([一-鿿，、。；：）)+])'
        r'"'
        r'([^\"\n]{1,40})'
        r'"'
        r'([一-鿿\d，、。；：（(])',
        r'\1「\2」\3',
        fixed,
    )

    # Edge case: symbol + "ChineseText" + symbol (e.g. + "报行合一" +)
    fixed = _re.sub(
        r'([\s+])"([一-鿿][^\"\n]{0,30}[一-鿿])"([\s)）→，、。；：+])',
        r'\1「\2」\3',
        fixed,
    )

    return json.loads(fixed)


# ═══════════════════════════════════════════════════════════════
# v3.5 · 缓存清理 — 一键清除某只股票的所有缓存
# ═══════════════════════════════════════════════════════════════

def _resolve_ticker_dirs(ticker: str) -> list[Path]:
    """Resolve all cache directories matching a ticker.

    Handles: '00700.HK', '00700', '700'
    Returns list of matching .cache/{ticker}/ directories.
    """
    ticker_upper = ticker.upper().strip()
    if not CACHE_ROOT.exists():
        return []

    dirs = []
    for d in CACHE_ROOT.iterdir():
        if not d.is_dir():
            continue
        dname = d.name.upper()
        if ticker_upper == dname:
            dirs.append(d)
        # Also match bare code (e.g. '00700') when ticker='00700.HK'
        elif ticker_upper.endswith(('.HK', '.SZ', '.SH')) and dname == ticker_upper.rsplit('.', 1)[0]:
            dirs.append(d)
    return dirs


def _match_lixinger_files(ticker: str) -> list[Path]:
    """Find Lixinger cache files related to a ticker."""
    lx_dir = CACHE_ROOT / "lixinger"
    if not lx_dir.exists():
        return []

    from lib.market_router import parse_ticker as _parse
    try:
        ti = _parse(ticker)
    except Exception:
        return []

    # Collect all code variants that could appear in cache keys
    codes = {ti.code}  # bare code e.g. '700'
    codes.add(ti.code.zfill(5))  # zero-padded e.g. '00700'
    if ti.full:
        codes.add(ti.full.upper())  # full e.g. '00700.HK'

    # Also try the raw ticker itself
    codes.add(ticker.upper().replace('.HK', '').replace('.SZ', '').replace('.SH', ''))

    files = []
    for f in lx_dir.iterdir():
        if not f.is_file():
            continue
        fname = f.name.upper()
        for c in codes:
            if f"__{c}__" in fname or f"__{c}_" in fname or fname.endswith(f"__{c}"):
                files.append(f)
                break
    return files


def clear_ticker_cache(
    ticker: str,
    *,
    keep_reports: bool = True,
    keep_agent: bool = False,
    dry_run: bool = False,
) -> dict:
    """Clear all cached data for a single stock.

    Args:
        ticker: Stock ticker like '00700.HK' or '00700'
        keep_reports: Preserve generated HTML reports
        keep_agent: Preserve agent_analysis.json (expensive manual work)
        dry_run: Only report what would be deleted, don't delete

    Returns:
        dict with counts of deleted/kept items and freed bytes
    """
    result = {
        "ticker": ticker,
        "deleted_dirs": [],
        "deleted_files": [],
        "kept_files": [],
        "freed_bytes": 0,
    }

    # 1. Per-ticker cache directories
    for d in _resolve_ticker_dirs(ticker):
        size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
        if not dry_run:
            import shutil
            shutil.rmtree(d)
        result["deleted_dirs"].append({"path": str(d), "size": size})
        result["freed_bytes"] += size

    # 2. Lixinger cache files
    for f in _match_lixinger_files(ticker):
        size = f.stat().st_size
        if not dry_run:
            f.unlink()
        result["deleted_files"].append({"path": str(f), "size": size, "source": "lixinger"})
        result["freed_bytes"] += size

    # 3. Reports directory (unless keep_reports)
    if not keep_reports:
        reports_dir = Path("reports")
        if reports_dir.exists():
            ticker_upper = ticker.upper().strip()
            for d in reports_dir.iterdir():
                if d.is_dir() and d.name.upper().startswith(ticker_upper):
                    size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
                    if not dry_run:
                        import shutil
                        shutil.rmtree(d)
                    result["deleted_dirs"].append({"path": str(d), "size": size, "source": "reports"})
                    result["freed_bytes"] += size

    # 4. Agent analysis (if keep_agent, exclude from deletion)
    if keep_agent:
        for d in _resolve_ticker_dirs(ticker):
            aa = d / "agent_analysis.json"
            if aa.exists():
                result["kept_files"].append(str(aa))

    result["freed_mb"] = round(result["freed_bytes"] / (1024 * 1024), 2)
    return result


def clear_all_cache(*, keep_reports: bool = True, dry_run: bool = False) -> dict:
    """Nuclear option: clear ALL cached data for ALL stocks."""
    result = {"tickers": [], "total_freed_mb": 0.0, "total_freed_bytes": 0}
    if not CACHE_ROOT.exists():
        return result

    for d in sorted(CACHE_ROOT.iterdir()):
        if d.is_dir() and d.name != "lixinger":
            # Only ticker dirs (exclude lixinger and _global)
            r = clear_ticker_cache(
                d.name,
                keep_reports=keep_reports,
                keep_agent=False,
                dry_run=dry_run,
            )
            if r["freed_bytes"] > 0:
                result["tickers"].append(d.name)
                result["total_freed_bytes"] += r["freed_bytes"]

    # Lixinger cache
    lx_dir = CACHE_ROOT / "lixinger"
    if lx_dir.exists():
        lx_size = sum(f.stat().st_size for f in lx_dir.rglob("*") if f.is_file())
        if not dry_run:
            import shutil
            shutil.rmtree(lx_dir)
        result["total_freed_bytes"] += lx_size

    result["total_freed_mb"] = round(result["total_freed_bytes"] / (1024 * 1024), 2)
    return result


def list_cached_tickers() -> list[dict]:
    """List all cached tickers with their sizes and artifact status."""
    if not CACHE_ROOT.exists():
        return []

    tickers = []
    for d in sorted(CACHE_ROOT.iterdir()):
        if not d.is_dir() or d.name in ("lixinger", "_global"):
            continue
        size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
        artifacts = [f.name for f in d.iterdir() if f.is_file()]
        tickers.append({
            "ticker": d.name,
            "size_mb": round(size / (1024 * 1024), 2),
            "artifacts": sorted(artifacts),
        })

    # Lixinger cache
    lx_dir = CACHE_ROOT / "lixinger"
    if lx_dir.exists():
        lx_size = sum(f.stat().st_size for f in lx_dir.rglob("*") if f.is_file())
        lx_files = [f.name for f in lx_dir.iterdir() if f.is_file()]
        tickers.append({
            "ticker": "(lixinger shared cache)",
            "size_mb": round(lx_size / (1024 * 1024), 2),
            "artifacts": sorted(lx_files)[:10] + (["..."] if len(lx_files) > 10 else []),
        })

    return tickers


def read_task_output(ticker: str, task_name: str) -> dict | None:
    path = CACHE_ROOT / ticker / f"{task_name}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def require_task_output(ticker: str, task_name: str) -> dict:
    """Hard gate: raise if previous task hasn't run."""
    data = read_task_output(ticker, task_name)
    if data is None:
        raise RuntimeError(
            f"Gate failed: {task_name}.json missing for {ticker}. "
            f"Run the previous task first."
        )
    return data
