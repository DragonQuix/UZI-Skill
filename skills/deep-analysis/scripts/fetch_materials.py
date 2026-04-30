"""Dimension 8 · 原材料价格 — 使用 futures_main_sina 拿真实期货价格."""
from __future__ import annotations

import json
import sys

import akshare as ak  # type: ignore


# Industry → [(contract_symbol, name, sina_futures_code)] — core raw materials
INDUSTRY_MATERIALS: dict[str, list[tuple]] = {
    "光学光电子": [
        ("玻璃", "FG0"),
        ("铜",   "CU0"),
    ],
    "半导体": [
        ("铜",   "CU0"),
        ("黄金", "AU0"),
        ("白银", "AG0"),
    ],
    "医药生物": [
        ("黄金", "AU0"),
    ],
    "电池": [
        ("碳酸锂", "LC0"),
        ("镍",     "NI0"),
        ("钴",     "—"),
    ],
    "钢铁": [
        ("铁矿石", "I0"),
        ("焦炭",   "J0"),
        ("螺纹钢", "RB0"),
    ],
    "建材": [
        ("水泥",   "—"),
        ("玻璃",   "FG0"),
        ("沥青",   "BU0"),
    ],
    "化工": [
        ("原油",   "SC0"),
        ("聚丙烯", "PP0"),
        ("PVC",    "V0"),
        ("甲醇",   "MA0"),
    ],
    "白酒": [
        ("玉米",   "C0"),
        ("大豆",   "A0"),
    ],
    "养殖业": [
        ("豆粕",   "M0"),
        ("玉米",   "C0"),
        ("生猪",   "LH0"),
    ],
    "农业": [
        ("大豆",   "A0"),
        ("玉米",   "C0"),
        ("棕榈油", "P0"),
    ],
    # v2.8.4 · 补齐有色金属类 —— 云铝股份等 coverage gap
    "工业金属": [
        ("沪铝",   "AL0"),
        ("沪铜",   "CU0"),
        ("沪锌",   "ZN0"),
    ],
    "有色金属": [
        ("沪铝",   "AL0"),
        ("沪铜",   "CU0"),
        ("沪镍",   "NI0"),
    ],
    "贵金属": [
        ("黄金",   "AU0"),
        ("白银",   "AG0"),
    ],
    "能源金属": [
        ("碳酸锂", "LC0"),
        ("镍",     "NI0"),
    ],
    "小金属": [
        ("沪锡",   "SN0"),
        ("沪铅",   "PB0"),
    ],
    "煤炭开采": [
        ("焦煤",   "JM0"),
        ("动力煤", "ZC0"),
    ],
    "焦炭": [
        ("焦炭",   "J0"),
        ("焦煤",   "JM0"),
    ],
    "油气开采": [
        ("原油",   "SC0"),
    ],
}


def _get_material_trend(sina_code: str) -> dict:
    """Pull 12-month futures price history via sina."""
    try:
        df = ak.futures_main_sina(symbol=sina_code)
        if df is None or df.empty:
            return {}
        df = df.sort_values("日期") if "日期" in df.columns else df
        tail = df.tail(250)  # ~1 year trading days
        closes = [float(v) for v in tail["收盘价"] if v and float(v) > 0]
        if not closes:
            return {}
        # Downsample to 12 points (monthly)
        step = max(1, len(closes) // 12)
        downsampled = closes[::step][:12]
        first, last = closes[0], closes[-1]
        trend_pct = ((last - first) / first * 100) if first else 0
        return {
            "latest_price": round(last, 2),
            "price_history_12m": [round(v, 2) for v in downsampled],
            "trend_pct_12m": round(trend_pct, 1),
            "trend_label": f"12月 {'+' if trend_pct >= 0 else ''}{trend_pct:.1f}%",
            "data_points": len(closes),
        }
    except Exception as e:
        return {"error": str(e)[:80]}


def _build_insurance_cost_structure(ticker: str) -> dict:
    """保险公司成本与运营效率分析（替代制造业原材料维度）。

    使用理杏仁 /cn/company/fs/insurance 端点获取赔付/费用/保费数据，
    计算综合赔付率、手续费率、管理费用率等核心成本指标。
    """
    try:
        from lib.market_router import parse_ticker
        from lib.lixinger_client import fetch_insurance_fs, to_float, latest as lx_latest
    except ImportError:
        return _not_applicable_result("保险")

    ti = parse_ticker(ticker)
    fs = fetch_insurance_fs(ti.code, "cn")
    if not fs or not fs.get("metrics"):
        return _not_applicable_result("保险")

    m = fs["metrics"]

    def _v(*keys):
        for k in keys:
            vals = m.get(k, [])
            v = lx_latest(vals)
            if v is not None:
                return v
        return None

    premium = _v("y.ps.ir.t")        # 保险服务收入（IFRS17等价已赚保费）
    claims = _v("y.ps.ce.t")          # 赔付支出
    admin = _v("y.ps.baae.t")         # 业务管理费
    commission = _v("y.ps.faceoio.t") # 手续费佣金支出
    nbv = _v("y.ps.nbv.t")           # 新业务价值
    ev = _v("y.bs.ev.t")              # 内含价值
    coresr = _v("y.bs.coresr.t")      # 核心偿付能力充足率
    roe = _v("y.m.wroe.t")            # 加权ROE
    np_margin = _v("y.m.np_s_r.t")    # 净利润率
    op = _v("y.ps.op.t")              # 营业利润

    # 计算比率
    def _pct(num, den):
        if num is not None and den is not None and den != 0:
            return f"{num / den * 100:.1f}%"
        return "—"

    cost_items = []
    if admin is not None and premium is not None:
        cost_items.append(f"管理费占保费 {admin/premium*100:.1f}%")
    if claims is not None and premium is not None and claims > 0:
        cost_items.append(f"赔付占保费 {claims/premium*100:.1f}%")

    summary_parts = []
    if roe is not None:
        summary_parts.append(f"ROE {roe*100:.1f}%")
    if np_margin is not None:
        summary_parts.append(f"净利率 {np_margin*100:.1f}%")
    if nbv is not None and ev is not None:
        summary_parts.append(f"NBV/EV {nbv/ev*100:.1f}%")

    return {
        "data": {
            "industry_type": "insurance",
            "not_applicable_manufacturing": True,
            "core_material": "保费收入（保险业无传统原材料）",
            "price_trend": " / ".join(summary_parts) if summary_parts else "—",
            "cost_share": " / ".join(cost_items) if cost_items else "—",
            "materials_detail": [
                {"name": "保险服务收入", "value": f"{premium/1e8:.0f}亿" if premium else "—"},
                {"name": "业务及管理费", "value": f"{admin/1e8:.1f}亿" if admin else "—"},
                {"name": "赔付支出", "value": f"{claims/1e8:.0f}亿" if claims and claims > 0 else "—"},
                {"name": "NBV", "value": f"{nbv/1e8:.1f}亿" if nbv else "—"},
                {"name": "核心偿付能力", "value": f"{coresr*100:.0f}%" if coresr and coresr < 10 else (f"{coresr:.0f}%" if coresr else "—")},
            ],
            "price_history_12m": [],
            "import_dep": "—",
            "industry_resolved": "保险",
            "_note": "保险公司无制造业原材料概念，本维度重定义为成本与运营效率分析",
        },
        "source": "lixinger:insurance_fs",
        "fallback": False,
    }


def _not_applicable_result(industry: str) -> dict:
    return {
        "data": {
            "industry_type": "financial",
            "not_applicable_manufacturing": True,
            "core_material": f"{industry}行业无传统原材料",
            "price_trend": "—",
            "cost_share": "—",
            "materials_detail": [],
            "price_history_12m": [],
            "import_dep": "—",
            "industry_resolved": industry,
            "_note": f"{industry}行业不适用制造业原材料分析框架",
        },
        "source": f"INDUSTRY_MATERIALS mapping (financial:{industry})",
        "fallback": False,
    }


def main(ticker_or_industry: str) -> dict:
    industry = ticker_or_industry  # fetch_materials can receive industry
    # If we got a ticker, look it up
    if industry.replace(".", "").replace("SZ", "").replace("SH", "").isdigit():
        try:
            from lib import data_sources as ds
            from lib.market_router import parse_ticker
            ti = parse_ticker(industry)
            basic = ds.fetch_basic(ti)
            industry = basic.get("industry") or "综合"
        except Exception:
            pass

    # v3.11 · 仅保险公司走理杏仁成本结构分析（赔付/费用/保费）
    # 银行/证券/其他金融无传统原材料框架，跳过
    from lib.lixinger_client import classify_financial_industry
    if classify_financial_industry(industry) == "insurance":
        return _build_insurance_cost_structure(ticker_or_industry)

    materials = INDUSTRY_MATERIALS.get(industry, [])
    # Try fuzzy match
    if not materials:
        for k, v in INDUSTRY_MATERIALS.items():
            if k[:2] in industry or industry[:2] in k:
                materials = v
                break

    material_data = []
    combined_history: list[float] = []
    for name, code in materials[:3]:
        if code == "—":
            material_data.append({"name": name, "note": "无直接期货品种", "trend": "—"})
            continue
        trend = _get_material_trend(code)
        if trend and "error" not in trend:
            material_data.append({"name": name, "code": code, **trend})
            if not combined_history:
                combined_history = trend.get("price_history_12m", [])
        else:
            material_data.append({"name": name, "code": code, "note": "数据获取失败"})

    core_names = " / ".join(m["name"] for m in material_data[:3]) if material_data else "—"

    # Best overall trend summary
    valid_trends = [m.get("trend_pct_12m", 0) for m in material_data if "trend_pct_12m" in m]
    avg_trend = sum(valid_trends) / len(valid_trends) if valid_trends else 0

    return {
        "data": {
            "core_material": core_names,
            "price_trend": f"12月均 {'+' if avg_trend >= 0 else ''}{avg_trend:.1f}%" if valid_trends else "—",
            "price_history_12m": combined_history,
            "materials_detail": material_data,
            "cost_share": "原材料约占 25-40%" if industry in ("钢铁", "化工", "建材") else "—",
            "import_dep": "—",
            "industry_resolved": industry,
        },
        "source": "akshare:futures_main_sina + INDUSTRY_MATERIALS mapping",
        "fallback": not bool(material_data),
    }


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "光学光电子"
    print(json.dumps(main(arg), ensure_ascii=False, indent=2, default=str))
