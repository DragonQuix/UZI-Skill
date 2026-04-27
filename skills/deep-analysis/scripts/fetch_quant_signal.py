"""Dimension _quant_signal · v3.0.0 理杏仁基金持仓 + 名称匹配量化识别.

替代旧版 quant_signal.detect_quant_signal() 在 generate_synthesis 热路径中
触发 741 次 akshare API 的架构缺陷。

数据源优先级：
1. 理杏仁 fetch_fund_shareholders (1 次 API → 基金列表 + netValueRatio)
2. 名称关键词匹配 (0 次 API · 公募量化/私募量化名单)
3. 两者结果合并去重

用法：
    from fetch_quant_signal import main
    result = main("601336.SH")
    # → {"data": {"count": 3, "quant_funds": [...], "is_quant_factor_style": True, ...}}
"""
from __future__ import annotations

import os as _os
import json as _json
from pathlib import Path as _Path


def main(ticker: str) -> dict:
    """理杏仁基金持仓 + 名称匹配 → 量化基金信号.

    Args:
        ticker: "601336.SH"

    Returns:
        {"data": {quant_signal_dict}, "source": "lixinger+name_matching"}
    """
    result = _detect(ticker)

    return {
        "data": result,
        "source": result.get("method", "name_matching"),
        "fallback": not result.get("_lixinger_used", False),
    }


def _detect(ticker: str) -> dict:
    code5 = ticker.split(".")[0].strip()

    fund_holders: list[dict] = []
    lx_used = False

    # ── 数据源 1: 理杏仁 ──
    if _os.environ.get("LIXINGER_TOKEN", "").strip():
        try:
            import sys as _sys
            _here = _Path(__file__).resolve().parent
            if str(_here) not in _sys.path:
                _sys.path.insert(0, str(_here))

            from lib.lixinger_client import fetch_fund_shareholders as _lx_fund
            lx_raw = _lx_fund(code5, start_date="2025-01-01", end_date="2026-12-31", limit=200)
            if lx_raw:
                lx_used = True
                for row in lx_raw:
                    fund_holders.append({
                        "fund_code": str(row.get("fundCode", "")).strip(),
                        "fund_name": str(row.get("name", "")).strip(),
                        "net_value_ratio": row.get("netValueRatio"),
                        "market_cap": row.get("marketCap"),
                        "holdings": row.get("holdings"),
                        "date": row.get("date"),
                    })
        except Exception:
            pass

    # ── 数据源 2: 从 raw_data cache 读 fund_managers（兜底）──
    if not fund_holders:
        try:
            cache_path = _Path(".cache") / ticker / "raw_data.json"
            if cache_path.exists():
                raw = _json.loads(cache_path.read_text(encoding="utf-8"))
                wave3_funds = raw.get("fund_managers", [])
                for m in wave3_funds:
                    fund_holders.append({
                        "fund_code": str(m.get("fund_code") or m.get("基金代码") or "").strip(),
                        "fund_name": str(m.get("fund_name") or m.get("基金名称") or m.get("name") or "").strip(),
                    })
        except Exception:
            pass

    # ── 名称匹配 ──
    from lib.quant_signal import detect_quant_signal_fast as _fast

    if fund_holders:
        sig = _fast(ticker, fund_holders)
        sig["_lixinger_used"] = lx_used
        sig["_total_funds_from_lixinger"] = len(fund_holders) if lx_used else 0
        return sig

    return {
        "count": 0, "quant_funds": [],
        "active_funds_total": 0, "quant_funds_total": 0,
        "is_quant_factor_style": False,
        "method": "name_matching",
        "_lixinger_used": False,
    }


if __name__ == "__main__":
    import sys
    ticker_arg = sys.argv[1] if len(sys.argv) > 1 else "601336.SH"
    result = main(ticker_arg)
    print(_json.dumps(result, ensure_ascii=False, indent=2, default=str))
