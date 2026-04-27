"""量化基金 / 量化重仓信号检测 · v3.0.0

v3.0 重构：名称关键词匹配（主）+ 理杏仁 enrich（辅）替代 akshare 741 次串行 API。
旧判定逻辑（top-1 < 2%）在 generate_synthesis 中触发 741 次 HTTP 调用导致 Stage 2 卡死，
且存在假阳性（指数 ETF top-1 也 < 2%）。

判定流程（v3.0）：
1. 遍历 raw["fund_managers"]（wave3 已抓取，无额外 API）
2. 公募：名称匹配量化关键词（量化/Quant/指数增强/多因子/AI/算法/大数据）
3. 私募：匹配 KNOWN_PRIVATE_QUANTS 名单
4. count >= QUANT_FACTOR_MIN_COUNT (3) → quant_factor style 触发

使用：
    from lib.quant_signal import detect_quant_signal_fast
    sig = detect_quant_signal_fast("601336.SH", raw.get("fund_managers", []))
    if sig["is_quant_factor_style"]:
        # quant_factor type

旧版 detect_quant_signal() 保留向后兼容，但标记为 deprecated。
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor  # noqa: F401 保留给旧版

from .cache import cached, TTL_QUARTERLY  # noqa: F401 保留给旧版

try:
    import akshare as ak  # type: ignore
except ImportError:
    ak = None


QUANT_TOP1_THRESHOLD = 2.0       # [旧版] 第一大持仓占净值 < 2% → 疑似量化
QUANT_FACTOR_MIN_COUNT = 3       # 至少 3 家量化基金持有 → 触发 style
HOLDINGS_QUARTER = "2025"        # [旧版] akshare 接受年份


# ─── 私募量化备查名单 ──
KNOWN_PRIVATE_QUANTS: tuple[str, ...] = (
    "幻方", "九坤", "灵均", "鸣石", "因诺", "明汯", "玄信", "衍复", "宽德", "念空",
    "锐天", "九章", "信弘", "汐泰", "黑翼", "白鹭", "诚奇", "盛冠达", "千象",
)

# ─── 公募量化基金名称关键词 ──
PUBLIC_QUANT_KEYWORDS: tuple[str, ...] = (
    "量化", "Quant", "指数增强", "多因子", "smart beta",
    "Smart Beta", "AI优选", "算法", "机器学习", "大数据",
    "基本面量化", "绝对收益",
)


def _is_quant_by_name(fund_name: str) -> bool:
    """名称关键词匹配判定公募量化基金。

    覆盖 A 股公募量化基金常见命名模式：
    - "国金量化多因子A" → 含"量化"
    - "景顺长城沪深300指数增强" → 含"指数增强"
    - "招商量化精选股票A" → 含"量化"
    """
    if not fund_name:
        return False
    for kw in PUBLIC_QUANT_KEYWORDS:
        if kw.lower() in fund_name.lower():
            return True
    return False


def _is_private_quant(fund_name: str) -> bool:
    """私募量化判定：匹配已知私募量化名单。"""
    if not fund_name:
        return False
    for q in KNOWN_PRIVATE_QUANTS:
        if q in fund_name:
            return True
    return False


def detect_quant_signal_fast(
    stock_code: str,
    fund_managers: list[dict] | None = None,
) -> dict:
    """v3.0 · 纯计算量化信号 — 0 次 API 调用。

    依赖 wave3 已抓取的 fund_managers 列表（含 fund_code + fund_name）。
    名称匹配 + 已知私募名单，无网络 I/O。

    Args:
        stock_code: "601336.SH" or "601336"
        fund_managers: list[{fund_code, fund_name, name?, ...}]

    Returns:
        {
            "count": 3,
            "quant_funds": [{"name": "国金量化多因子A", "fund_code": "006195", ...}],
            "active_funds_total": 741,
            "quant_funds_total": 12,
            "is_quant_factor_style": True,   # count >= 3
            "method": "name_matching",        # 标记判定方法
        }
    """
    code5 = (stock_code or "").split(".")[0].strip()

    if not fund_managers:
        return {
            "count": 0, "quant_funds": [],
            "active_funds_total": 0, "quant_funds_total": 0,
            "is_quant_factor_style": False,
            "method": "name_matching",
        }

    quant_funds: list[dict] = []
    quant_total = 0

    for m in fund_managers:
        name = str(m.get("fund_name") or m.get("基金名称") or m.get("name") or "")
        code = str(m.get("fund_code") or m.get("基金代码") or "").strip()

        if not name:
            continue

        is_quant = _is_quant_by_name(name) or _is_private_quant(name)
        if not is_quant:
            continue

        quant_total += 1
        quant_funds.append({
            "name": name,
            "fund_code": code,
            "manager": str(m.get("name") or m.get("基金经理") or ""),
        })

    return {
        "count": len(quant_funds),
        "quant_funds": quant_funds[:10],
        "active_funds_total": len(fund_managers),
        "quant_funds_total": quant_total,
        "is_quant_factor_style": len(quant_funds) >= QUANT_FACTOR_MIN_COUNT,
        "method": "name_matching",
    }


# ═══════════════════════════════════════════════════════════════
# 以下为旧版函数（向后兼容 · 不推荐使用 · 保留用于独立脚本调用）
# ═══════════════════════════════════════════════════════════════

def _fetch_top_holdings(fund_code: str, top_n: int = 10) -> list[dict]:
    """[旧版] 带 24h cache 的前 N 大持仓抓取。失败/空 → []。NEVER raises."""
    if not fund_code or ak is None:
        return []

    def _do() -> list[dict]:
        try:
            df = ak.fund_portfolio_hold_em(symbol=str(fund_code), date=HOLDINGS_QUARTER)
            if df is None or df.empty:
                return []
            return df.head(top_n).to_dict("records")
        except Exception:
            return []

    return cached(f"_quant/{fund_code}", "top10_holdings", _do, ttl=TTL_QUARTERLY)


def _is_quant_like(top_holdings: list[dict]) -> tuple[bool, float]:
    """[旧版] 结构性判定：top-1 占净值 < QUANT_TOP1_THRESHOLD → True"""
    if not top_holdings:
        return False, 0.0
    try:
        top1_pct = float(top_holdings[0].get("占净值比例", 0))
    except (ValueError, TypeError):
        return False, 0.0
    return top1_pct < QUANT_TOP1_THRESHOLD, top1_pct


def _fetch_all_holding_funds(ticker_code: str, max_funds: int = 80) -> list[dict]:
    """[旧版] 调 fetch_fund_holders.fetch_holding_funds 拿全部持有本股的基金。"""
    if ak is None:
        return []
    try:
        import sys
        from pathlib import Path
        scripts_dir = Path(__file__).resolve().parent.parent
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        from fetch_fund_holders import fetch_holding_funds
        all_funds = fetch_holding_funds(ticker_code)
        out = []
        for h in all_funds[:max_funds]:
            code = str(h.get("基金代码") or h.get("fund_code") or "").strip()
            name = str(h.get("基金名称") or h.get("fund_name") or "").strip()
            if code:
                out.append({"fund_code": code, "fund_name": name})
        return out
    except Exception:
        return []


def detect_quant_signal(stock_code: str, fund_managers: list[dict] | None = None,
                        max_funds: int = 80) -> dict:
    """[旧版 · 不推荐] 结构性判定 — 逐基金调 akshare API 检查 Top 10 持仓。

    ⚠️ 此函数会触发 N 次 akshare API 调用（N = len(fund_managers)）。
    在 generate_synthesis 热路径中使用会导致 Stage 2 卡死。
    新代码请使用 detect_quant_signal_fast()。
    """
    code5 = (stock_code or "").split(".")[0].strip()

    if not fund_managers or len(fund_managers) < 20:
        bigger = _fetch_all_holding_funds(code5, max_funds=max_funds)
        if bigger:
            fund_managers = bigger

    if not fund_managers:
        return {
            "count": 0, "quant_funds": [],
            "active_funds_total": 0, "quant_funds_total": 0,
            "is_quant_factor_style": False,
        }

    def _check_one(m: dict) -> dict | None:
        fund_code = m.get("fund_code")
        if not fund_code:
            return None
        top10 = _fetch_top_holdings(str(fund_code), top_n=10)
        is_q, top1_pct = _is_quant_like(top10)
        if not is_q:
            return None
        for rank, h in enumerate(top10, start=1):
            holding_code = str(h.get("股票代码", "")).strip()
            if holding_code == code5:
                try:
                    weight_pct = float(h.get("占净值比例", 0))
                except (ValueError, TypeError):
                    weight_pct = 0.0
                return {
                    "name": str(m.get("fund_name", "") or ""),
                    "fund_code": str(fund_code),
                    "rank": rank,
                    "weight_pct": weight_pct,
                    "top1_pct": top1_pct,
                    "manager": str(m.get("name", "") or ""),
                }
        return {"_quant_no_hold": True}

    quant_holders: list[dict] = []
    quant_total = 0

    import os as _os
    _w = max(1, int(_os.environ.get("UZI_QUANT_WORKERS", "1")))
    with ThreadPoolExecutor(max_workers=_w) as pool:
        for r in pool.map(_check_one, fund_managers):
            if r is None:
                continue
            quant_total += 1
            if r.get("_quant_no_hold"):
                continue
            quant_holders.append(r)

    quant_holders.sort(key=lambda x: -x.get("weight_pct", 0))

    return {
        "count": len(quant_holders),
        "quant_funds": quant_holders[:10],
        "active_funds_total": len(fund_managers),
        "quant_funds_total": quant_total,
        "is_quant_factor_style": len(quant_holders) >= QUANT_FACTOR_MIN_COUNT,
        "method": "structural_top1_threshold",
    }


if __name__ == "__main__":
    import json
    import sys

    code = sys.argv[1] if len(sys.argv) > 1 else "600120.SH"

    from pathlib import Path
    cache = Path(".cache") / code / "raw_data.json"
    if not cache.exists():
        print(f"No cached raw_data for {code}; run stage1 first.")
        sys.exit(1)

    raw = json.loads(cache.read_text(encoding="utf-8"))
    fund_managers = raw.get("fund_managers", [])
    print(f"Testing {code} · {len(fund_managers)} fund_managers from cache")

    print("\n── v3.0 fast (name matching) ──")
    sig_fast = detect_quant_signal_fast(code, fund_managers)
    print(json.dumps(sig_fast, ensure_ascii=False, indent=2, default=str))
