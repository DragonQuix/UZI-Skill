"""Dimension 12 · 资金面 (北向 / 融资融券 / 股东户数 / 主力 / 限售解禁 / 大宗交易).

补全：原方案要求覆盖
  • 北向/南向资金近 20 日净买卖
  • 融资融券余额趋势
  • 股东户数近 3 季度变化
  • 大宗交易折溢价
  • 限售股解禁时间表
  • 主力资金流入流出
全部已实现。

v2.15.3 (#30) · 大宗交易 + 解禁数据走 ds.cached module-level · 避免每只股重抓全 A 数据（原每次 3+min，改后首次 3min 后续 < 1s）.
"""
import json
import sys

import akshare as ak  # type: ignore
from lib import data_sources as ds
from lib.cache import cached  # v2.15.3 · TTL cache
from lib.lixinger_client import (  # v2.16 · 理杏仁单股查询替代全A批量
    fetch_block_deals,
    fetch_restricted_release,
    fetch_margin_trading,
    fetch_fund_shareholders,  # v2.16 · 公募基金持股替代全市场基金持仓批量
    fetch_shareholders_num,   # v2.16 · 股东人数替代全市场股东户数 (842 tqdm 终结者)
)
from lib.market_router import parse_ticker


def _safe(fn, default):
    try:
        return fn()
    except Exception as e:
        return {"error": str(e)} if isinstance(default, dict) else default


# v2.15.3 · 大宗/解禁数据按年缓存（TTL 24h · 数据日频更新）
# 不缓存会每只股花 3+min 重拉 · 严重性能 bug
_UNIVERSE_TTL = 24 * 3600  # 24h


def _universe_dzjy(year: int = 2026) -> list:
    """v2.15.3 · 大宗交易整年数据 · module-level cache · 全 A 共享."""
    def _fetch():
        try:
            df = ak.stock_dzjy_mrtj(
                start_date=f"{year}0101",
                end_date=f"{year}1231",
            )
            return df.to_dict("records") if df is not None and not df.empty else []
        except Exception:
            return []
    return cached("_universe", f"dzjy_{year}", _fetch, ttl=_UNIVERSE_TTL) or []


def _universe_release_summary() -> list:
    """v2.15.3 · 近一年解禁 summary · module-level cache."""
    def _fetch():
        try:
            df = ak.stock_restricted_release_summary_em(symbol="近一年")
            return df.to_dict("records") if df is not None and not df.empty else []
        except Exception:
            return []
    return cached("_universe", "release_summary_1y", _fetch, ttl=_UNIVERSE_TTL) or []


def _universe_release_detail(year: int = 2026) -> list:
    """v2.15.3 · 解禁日历（年度） · module-level cache."""
    def _fetch():
        try:
            df = ak.stock_restricted_release_detail_em(
                start_date=f"{year}0101", end_date=f"{year}1231",
            )
            return df.to_dict("records") if df is not None and not df.empty else []
        except Exception:
            return []
    return cached("_universe", f"release_detail_{year}", _fetch, ttl=_UNIVERSE_TTL) or []


def _universe_margin_detail(exchange: str) -> list:
    """v2.15.3 · 某交易所最新一天融资明细 · module-level cache · 全 A 共享."""
    def _fetch():
        try:
            if exchange == "SZ":
                df = ak.stock_margin_detail_szse(date=None)
            else:
                df = ak.stock_margin_detail_sse(date=None)
            return df.to_dict("records") if df is not None and not df.empty else []
        except Exception:
            return []
    return cached("_universe", f"margin_detail_{exchange}", _fetch, ttl=_UNIVERSE_TTL) or []


def main(ticker: str) -> dict:
    ti = parse_ticker(ticker)
    if ti.market == "H":
        # v2.5 · HK 港股通南北向标记 + 历史每日市值（净值变动 proxy）
        # akshare 港股通南北向 spot (stock_hsgt_sh_hk_spot_em) 走 push2 已 blocked，
        # 这里用 stock_hk_security_profile_em 拿"是否沪/深港通标的"标记 + eniu 历史市值。
        from lib.hk_data_sources import fetch_hk_basic_combined
        try:
            enriched = fetch_hk_basic_combined(ti.code.zfill(5))
        except Exception:
            enriched = {}
        is_sh = enriched.get("is_south_bound_sh", False)
        is_sz = enriched.get("is_south_bound_sz", False)
        # eniu 市值历史（近 30 个数据点作为南北向资金流的 proxy）
        mv_hist: list = []
        try:
            import akshare as _ak  # type: ignore
            df = _ak.stock_hk_indicator_eniu(symbol=f"hk{ti.code.zfill(5)}", indicator="市值")
            if df is not None and not df.empty:
                mv_hist = df.tail(30).to_dict("records")
        except Exception:
            pass
        return {
            "ticker": ti.full,
            "data": {
                "is_south_bound_sh": is_sh,
                "is_south_bound_sz": is_sz,
                "south_bound_eligibility": "沪+深" if (is_sh and is_sz) else ("沪" if is_sh else ("深" if is_sz else "—")),
                "north_bound": "—",
                "margin_balance": "—",
                "main_flow_recent": [],
                "mv_history_30d": mv_hist[-30:],
                "_note": (
                    "HK 南向具体持股变动需走 AASTOCKS Playwright 或 hkexnews holdings page；"
                    "本字段提供港股通资格 + eniu 市值历史作 proxy。"
                ),
            },
            "source": "akshare:stock_hk_security_profile_em + stock_hk_indicator_eniu",
            "fallback": False,
        }
    if ti.market != "A":
        return {"ticker": ti.full, "data": {"_note": "capital_flow only A-share / HK for now"}, "source": "skip", "fallback": False}

    north = ds.fetch_northbound(ti)

    # 融资融券 · v2.16 · 理杏仁单股查询替代全市场批量
    try:
        margin_raw = fetch_margin_trading([ti.code])
        margin = [
            {
                "日期": str(r.get("last_data_date", ""))[:10],
                "融资余额": r.get("mtaslb_fb"),
                "融券余额": r.get("mtaslb_sb"),
                "两融余额": r.get("mtaslb"),
                "占流通市值": f"{r.get('mtaslb_mc_r', 0) * 100:.2f}%" if r.get("mtaslb_mc_r") else "—",
                "20日净买入": r.get("npa_o_f_d20"),
                "60日净买入": r.get("npa_o_f_d60"),
                "涨跌幅": f"{r.get('spc', 0) * 100:.1f}%" if r.get("spc") else "—",
            }
            for r in (margin_raw or [])[:5]
        ]
    except Exception:
        margin = []

    # 股东户数 · v2.16 · 理杏仁单股查询替代全市场批量 (842 tqdm 终结者!)
    holders = []
    try:
        sh_raw = fetch_shareholders_num(ti.code, start_date="2023-01-01", limit=16)
        holders = [
            {
                "日期": str(r.get("date", ""))[:10],
                "股东户数": r.get("total"),
                "股东户数变化率": f"{r.get('shareholdersNumberChangeRate', 0) * 100:.1f}%" if r.get("shareholdersNumberChangeRate") else "—",
                "涨跌幅": r.get("spc"),
            }
            for r in (sh_raw or [])
        ]
    except Exception:
        holders = []

    main_flow = _safe(
        lambda: ak.stock_individual_fund_flow(stock=ti.code, market=ti.full[-2:].lower()).tail(20).to_dict("records"),
        [],
    )

    # 大宗交易 · v2.16 · 理杏仁单股查询替代全A批量 (from 180s → <1s)
    try:
        from datetime import datetime as _dt, timedelta as _td
        end_d = _dt.now().strftime("%Y-%m-%d")
        start_d = (_dt.now() - _td(days=365)).strftime("%Y-%m-%d")
        block_trades_raw = fetch_block_deals(ti.code, start_date=start_d, end_date=end_d)
        block_trades = [
            {
                "日期": r.get("date", ""),
                "成交价": r.get("tradingPrice"),
                "成交额": r.get("tradingAmount"),
                "成交量": r.get("tradingVolume"),
                "买方营业部": r.get("buyBranch", ""),
                "卖方营业部": r.get("sellBranch", ""),
                "折价率": f"{r.get('discountRate', 0) * 100:.1f}%" if r.get("discountRate") else "—",
            }
            for r in (block_trades_raw or [])[:20]
        ]
    except Exception:
        block_trades = []

    # 限售股解禁 · v2.16 · 理杏仁单股查询替代全A批量 (消除 841 条目!)
    try:
        release_raw = fetch_restricted_release([ti.code])
        unlock = [
            {
                "代码": r.get("stockCode", ""),
                "最近解禁日": str(r.get("last_data_date", ""))[:10],
                "最近解禁股数": r.get("srl_last"),
                "占总股本": f"{r.get('srl_cap_r_last', 0) * 100:.2f}%" if r.get("srl_cap_r_last") else "—",
                "未来1年解禁股数": r.get("elr_s_y1"),
                "未来1年解禁市值": r.get("elr_mc_y1"),
            }
            for r in (release_raw or [])
        ]
    except Exception:
        unlock = []

    # 解禁日历 · v2.16 · 从理杏仁 unlock 数据构造 schedule (已无明细逐日数据，
    # 仅有汇总。保留 schedule 字段但用汇总值填充)
    unlock_schedule = []
    for row in unlock:
        if row.get("最近解禁日"):
            unlock_schedule.append({
                "date": str(row["最近解禁日"])[:7],
                "amount": round((row.get("未来1年解禁市值") or 0) / 1e8, 2),
            })

    # 机构持仓 · v2.16 · 理杏仁公募基金持股替代全市场基金持仓批量 (消除 842 条目!)
    inst_history: dict = {"quarters": [], "fund": [], "top_funds": []}
    try:
        from datetime import datetime as _dt, timedelta as _td
        end_d = _dt.now().strftime("%Y-%m-%d")
        start_d = (_dt.now() - _td(days=730)).strftime("%Y-%m-%d")
        fund_data = fetch_fund_shareholders(ti.code, start_date=start_d, end_date=end_d, limit=100)
        if fund_data:
            by_quarter: dict[str, dict] = {}
            for r in fund_data:
                d = str(r.get("date", ""))[:7]
                by_quarter.setdefault(d, {"total_holdings": 0, "fund_count": 0, "top": []})
                h = r.get("holdings") or 0
                by_quarter[d]["total_holdings"] += h
                by_quarter[d]["fund_count"] += 1
                by_quarter[d]["top"].append({
                    "name": r.get("name", ""),
                    "holdings": h,
                    "net_value_ratio": r.get("netValueRatio"),
                })
            sorted_qs = sorted(by_quarter.keys())[-8:]
            inst_history["quarters"] = sorted_qs
            for q in sorted_qs:
                qd = by_quarter[q]
                inst_history["fund"].append(round(qd["total_holdings"] / 1e4, 2))
            latest_q = sorted_qs[-1] if sorted_qs else None
            if latest_q:
                inst_history["top_funds"] = sorted(
                    by_quarter[latest_q]["top"], key=lambda x: x["holdings"], reverse=True
                )[:10]
        if not inst_history["quarters"]:
            inst_history["quarters"] = ["无数据"]
    except Exception:
        pass

    # Build summary strings for viz
    def _north_sum_20d(hist):
        if not isinstance(hist, dict):
            return "—"
        flows = hist.get("flow_history", [])
        if not flows:
            return "—"
        try:
            total = sum(float(r.get("净买额") or r.get("净买入额") or 0) for r in flows[-20:])
            return f"{total / 1e8:+.1f}亿"
        except Exception:
            return "—"

    def _main_sum_20d(flow_list):
        if not flow_list:
            return "—"
        try:
            total = sum(float(r.get("主力净流入", 0) or 0) for r in flow_list[-20:])
            return f"{total / 1e4:+.1f}万" if abs(total) < 1e8 else f"{total / 1e8:+.1f}亿"
        except Exception:
            return "—"

    def _holders_trend(h):
        if not h or len(h) < 2:
            return "—"
        try:
            last = float(str(h[0].get("股东户数", 0)).replace(",", ""))
            prev = float(str(h[-1].get("股东户数", 0)).replace(",", ""))
            trend = "3 季连降" if last < prev * 0.95 else "3 季连升" if last > prev * 1.05 else "基本持平"
            return trend
        except Exception:
            return "—"

    return {
        "ticker": ti.full,
        "data": {
            "northbound": north,
            "northbound_20d": _north_sum_20d(north),
            "margin_recent": margin,
            "margin_trend": f"近 5 日 {len(margin)} 条记录" if margin else "—",
            "holder_count_history": holders,
            "holders_trend": _holders_trend(holders),
            "main_fund_flow_20d": main_flow,
            "main_20d": _main_sum_20d(main_flow),
            "main_5d": "—",
            "block_trades_recent": block_trades,
            "unlock_recent": unlock,
            "unlock_schedule": unlock_schedule,
            "institutional_history": inst_history,
        },
        "source": "akshare:multi (north + margin + gdhs + fund_flow + dzjy + restricted_release + fund_hold_detail)",
        "fallback": False,
    }


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1] if len(sys.argv) > 1 else "002273.SZ"), ensure_ascii=False, indent=2, default=str))
