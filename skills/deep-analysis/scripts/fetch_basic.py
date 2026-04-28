"""Dimension 0 · 基础信息 (name, code, industry, price, mcap, PE, PB).

Returns either:
    - Success:       {"ticker", "market", "data", "source", "fallback": False}
    - Name error:    {"ticker", "error": "name_not_resolved", "user_input",
                     "suggestions": [...], "source": "name_resolver", "fallback": True}

The second shape lets stage1() early-return and hand off to the agent / user
for disambiguation, instead of silently running 22 fetchers with a garbage
ticker and producing a half-empty report (see the 北部港湾 incident).
"""
import json
import sys

from lib import data_sources as ds
from lib.market_router import is_chinese_name, parse_ticker, classify_security_type


_NON_STOCK_GUIDANCE = {
    "etf": {
        "label": "ETF",
        "why": "插件的 51 评委跑 ROE / 护城河 / 管理层 / 分红 等个股财务指标，ETF 没这些字段",
        "what_to_do": "分析该 ETF 的**前 3-5 大持仓股**（ak.fund_portfolio_hold_em 可查），对每只成分股单独跑 /analyze-stock",
    },
    "lof": {
        "label": "LOF 基金",
        "why": "基金没有企业基本面字段，不适合 51 评委流程",
        "what_to_do": "基金评估应看：基金经理 / 规模 / 持仓集中度 / 业绩基准差 / 回撤；这些该用 /fund-analyze 类工具（本插件未覆盖）",
    },
    "convertible_bond": {
        "label": "可转债",
        "why": "可转债评估看的是转股价 / 溢价率 / 到期收益率 / 赎回条款，不是 ROE",
        "what_to_do": "集思录的可转债工具 / 东财可转债专题；或直接分析**正股**",
    },
}


def main(user_input: str) -> dict:
    if is_chinese_name(user_input):
        r = ds.resolve_chinese_name_rich(user_input)
        if r["resolved"] is None:
            # Ambiguous or unresolvable — surface candidates for UI confirmation.
            return {
                "ticker": user_input,
                "market": None,
                "data": {},
                "error": "name_not_resolved",
                "user_input": user_input,
                "suggestions": r["candidates"][:5],
                "source": f"name_resolver:{r['source']}",
                "fallback": True,
            }
        ti = r["resolved"]
    else:
        ti = parse_ticker(user_input)

    # v2.9.2 · 早期拦截 ETF/LOF/可转债（插件是个股分析引擎，跑非个股标的会输出垃圾）
    sec_type = classify_security_type(ti.code) if ti.market == "A" else "stock"
    if sec_type in _NON_STOCK_GUIDANCE:
        g = _NON_STOCK_GUIDANCE[sec_type]
        return {
            "ticker": ti.full,
            "market": ti.market,
            "data": {},
            "error": "non_stock_security",
            "security_type": sec_type,
            "guidance": g,
            "message": (
                f"{ti.full} 是 {g['label']}，不是个股。\n"
                f"原因: {g['why']}\n"
                f"建议: {g['what_to_do']}"
            ),
            "source": "market_router:classify_security_type",
            "fallback": True,
        }

    data = ds.fetch_basic(ti)

    # v3.0: 理杏仁基础信息补充 (上市日期/ST状态/融资融券/陆股通)
    if ti.market in ("A", "H"):
        import os
        if os.environ.get("LIXINGER_TOKEN", "").strip():
            try:
                from lib.lixinger_client import fetch_company_info as lx_company
                from lib.lixinger_client import fetch_industries as lx_industry
                market = "hk" if ti.market == "H" else "cn"
                code = ti.code.zfill(5) if market == "hk" else ti.code
                co = lx_company(code, market=market)
                if co:
                    rows = co.get("_raw") or co.get("data") or []
                    if rows:
                        r = rows[0]
                        for key, label in [
                            ("ipoDate", "ipo_date"),
                            ("listingStatus", "listing_status"),
                            ("exchange", "exchange"),
                            ("mutualMarketFlag", "stock_connect"),
                            ("marginTradingAndSecuritiesLendingFlag", "margin_trading"),
                        ]:
                            val = r.get(key)
                            if val is not None:
                                data["_lx_" + label] = val
                        # v3.6 · 理杏仁 name 直接覆盖主字段（修复港股 name 缺失）
                        lx_name = r.get("name")
                        if lx_name and not data.get("name"):
                            data["name"] = lx_name
                        data["_lx_enriched"] = True
                        # v3.0 · 理杏仁行业分类（申万/中信）
                        try:
                            lx_ind = lx_industry(code, market=market)
                            if lx_ind:
                                data["industry"] = lx_ind
                        except Exception:
                            pass  # 行业非致命，失败让雪球/东财 fallback 兜底
            except Exception:
                pass  # non-critical, silently skip

    return {
        "ticker": ti.full,
        "market": ti.market,
        "data": data,
        "source": f"akshare:{ti.market}" + (" + lixinger:company" if data.get("_lx_enriched") else ""),
        "fallback": False,
    }


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "002273"
    print(json.dumps(main(arg), ensure_ascii=False, indent=2, default=str))
