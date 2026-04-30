"""Dimension 9 · 期货关联 — 真实期货价格 via futures_main_sina."""
from __future__ import annotations

import json
import sys


# Industry → primary linked futures contract (if any)
INDUSTRY_FUTURES: dict[str, tuple] = {
    "钢铁":   ("螺纹钢 RB", "RB0"),
    "建材":   ("玻璃 FG",   "FG0"),
    "煤炭":   ("焦煤 JM",   "JM0"),
    "有色金属": ("沪铜 CU",  "CU0"),
    "化工":   ("原油 SC",   "SC0"),
    "农业":   ("豆粕 M",    "M0"),
    "养殖业": ("生猪 LH",   "LH0"),
    "电池":   ("碳酸锂 LC", "LC0"),
    # v2.8.4 · 补齐有色金属子类 —— 云铝等 coverage gap
    "工业金属": ("沪铝 AL",  "AL0"),
    "贵金属":   ("黄金 AU",  "AU0"),
    "能源金属": ("碳酸锂 LC", "LC0"),
    "小金属":   ("沪锡 SN",  "SN0"),
    "煤炭开采": ("焦煤 JM",  "JM0"),
    "焦炭":     ("焦炭 J",   "J0"),
    "油气开采": ("原油 SC",  "SC0"),
    "光学光电子": (None, None),  # no direct linkage
    "半导体":  (None, None),
    "医药生物": (None, None),
    "白酒":   (None, None),
    "银行":   (None, None),
    "保险":   (None, None),
}


def _pull_price(code: str) -> dict:
    try:
        import akshare as ak
        df = ak.futures_main_sina(symbol=code)
        if df is None or df.empty:
            return {}
        df = df.sort_values("日期") if "日期" in df.columns else df
        tail = df.tail(60)
        closes = [float(v) for v in tail["收盘价"] if v and float(v) > 0]
        if len(closes) < 2:
            return {}
        first = closes[0]
        last = closes[-1]
        trend_pct = ((last - first) / first * 100) if first else 0
        return {
            "latest": round(last, 2),
            "trend_60d_pct": round(trend_pct, 1),
            "history_60d": [round(v, 2) for v in closes[-60:]],
        }
    except Exception:
        return {}


def _build_insurance_investment_profile(ticker: str) -> dict:
    """保险公司投资端分析（替代商品期货维度）。

    使用理杏仁 /cn/company/fs/insurance 获取投资收益率/EV/NBV/偿付能力，
    使用 /cn/company/fundamental/insurance 获取 PEV。
    """
    try:
        from lib.market_router import parse_ticker
        from lib.lixinger_client import (fetch_insurance_fs, fetch_insurance_fundamental,
                                         to_float, latest as lx_latest)
    except ImportError:
        return _not_applicable_futures_result("保险")

    ti = parse_ticker(ticker)
    fs = fetch_insurance_fs(ti.code, "cn")
    fund = fetch_insurance_fundamental(ti.code, "cn")

    if not fs or not fs.get("metrics"):
        return _not_applicable_futures_result("保险")

    m = fs["metrics"]

    def _v(*keys):
        for k in keys:
            vals = m.get(k, [])
            v = lx_latest(vals)
            if v is not None:
                return v
        return None

    inv_income = _v("y.ps.ivi.t")       # 投资收益
    fv_change = _v("y.ps.ciofv.t")       # 公允价值变动
    total_assets = _v("y.bs.ta.t")        # 资产总计 (近似投资资产, 保险公司总资产≈投资资产)
    ev = _v("y.bs.ev.t")                  # 内含价值
    nbv = _v("y.ps.nbv.t")               # 新业务价值
    coresr = _v("y.bs.coresr.t")          # 核心偿付能力
    compsr = _v("y.bs.compsr.t")          # 综合偿付能力
    roe = _v("y.m.wroe.t")

    pev = fund.get("pev") if fund else None

    # 构建投资收益率（近似）
    yield_parts = []
    if inv_income is not None and total_assets is not None and total_assets > 0:
        yield_parts.append(f"投资收益率约 {inv_income/total_assets*100:.1f}%")
    if fv_change is not None and inv_income is not None:
        total_yield = inv_income + (fv_change if fv_change else 0)
        if total_assets is not None and total_assets > 0:
            yield_parts.append(f"总收益率约 {total_yield/total_assets*100:.1f}%")

    contract_items = []
    if total_assets is not None:
        contract_items.append(f"总资产 {total_assets/1e8:.0f}亿")
    if ev is not None:
        contract_items.append(f"内含价值 {ev/1e8:.0f}亿")
    if pev is not None:
        contract_items.append(f"PEV {pev:.2f}x")
    if nbv is not None:
        contract_items.append(f"NBV {nbv/1e8:.1f}亿")

    return {
        "data": {
            "industry_type": "insurance",
            "not_applicable_manufacturing": True,
            "linked_contract": " / ".join(contract_items) if contract_items else "保险公司投资端数据",
            "contract_trend": " / ".join(yield_parts) if yield_parts else "—",
            "price_history_60d": [],
            "note": "保险公司无商品期货套保需求，本维度重定义为投资端分析（资产配置/收益率/EV/偿付能力）",
            "_insurance_metrics": {
                "investment_income_yi": round(inv_income / 1e8, 1) if inv_income else None,
                "fv_change_yi": round(fv_change / 1e8, 1) if fv_change else None,
                "pev": pev,
                "ev_yi": round(ev / 1e8, 1) if ev else None,
                "nbv_yi": round(nbv / 1e8, 2) if nbv else None,
                "coresr": round(coresr * 100, 1) if coresr and coresr < 10 else (round(coresr, 1) if coresr else None),
                "compsr": round(compsr * 100, 1) if compsr and compsr < 10 else (round(compsr, 1) if compsr else None),
                "roe": round(roe * 100, 1) if roe and abs(roe) < 1 else (round(roe, 1) if roe else None),
            },
        },
        "source": "lixinger:insurance_fs + lixinger:insurance_fundamental",
        "fallback": False,
    }


def _not_applicable_futures_result(industry: str) -> dict:
    return {
        "data": {
            "industry_type": "financial",
            "not_applicable_manufacturing": True,
            "linked_contract": f"{industry}行业与期货市场无强相关品种",
            "contract_trend": "—",
            "note": f"{industry}行业不适用商品期货分析框架",
        },
        "source": "INDUSTRY_FUTURES mapping",
        "fallback": False,
    }


def main(ticker: str = "", industry: str = "") -> dict:
    # v3.11 · 仅保险公司走理杏仁投资端分析（保费/EV/NBV/偿付能力）
    # 银行/证券/其他金融无"期货对冲"概念，返回 N/A
    from lib.lixinger_client import classify_financial_industry
    if ticker and classify_financial_industry(industry) == "insurance":
        return _build_insurance_investment_profile(ticker)

    # 兼容旧调用: main(industry) 仅传行业名
    if not ticker and industry:
        pass
    elif ticker and not industry:
        # 仅传 ticker，解析行业
        industry = ticker
        if industry.replace(".", "").replace("SZ", "").replace("SH", "").isdigit():
            try:
                from lib import data_sources as ds
                from lib.market_router import parse_ticker
                ti = parse_ticker(industry)
                basic = ds.fetch_basic(ti)
                industry = basic.get("industry") or "综合"
            except Exception:
                pass
    # Try exact match first
    linked = INDUSTRY_FUTURES.get(industry)
    if linked is None:
        # Fuzzy match
        for k, v in INDUSTRY_FUTURES.items():
            if k[:2] in industry or industry[:2] in k:
                linked = v
                break
    linked = linked or (None, None)
    name, code = linked

    if not code:
        return {
            "data": {
                "linked_contract": "无直接关联品种",
                "contract_trend": "—",
                "note": f"{industry} 行业与期货市场无强相关品种",
            },
            "source": "INDUSTRY_FUTURES mapping",
            "fallback": False,
        }

    price_data = _pull_price(code)
    trend_label = "—"
    if price_data.get("trend_60d_pct") is not None:
        pct = price_data["trend_60d_pct"]
        trend_label = f"60 日 {'+' if pct >= 0 else ''}{pct:.1f}%"

    return {
        "data": {
            "linked_contract": name,
            "contract_code": code,
            "latest_price": price_data.get("latest"),
            "contract_trend": trend_label,
            "price_history_60d": price_data.get("history_60d", []),
        },
        "source": "akshare:futures_main_sina",
        "fallback": False,
    }


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "光学光电子"
    print(json.dumps(main(arg), ensure_ascii=False, indent=2, default=str))
