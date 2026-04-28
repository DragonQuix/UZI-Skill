"""Dimension 4 · 同行对比 — v3.0 · 理杏仁批量查指标 + akshare 发现同行."""
from __future__ import annotations

import json
import os

from lib.industry_peers import get_peer_codes
import sys
import time

import akshare as ak  # type: ignore
from lib import data_sources as ds
from lib.market_router import parse_ticker


def _float(v, default=0.0):
    try:
        s = str(v).replace(",", "").replace("%", "")
        if s in ("", "nan", "-", "--", "None"):
            return default
        return float(s)
    except (ValueError, TypeError):
        return default


def _build_self_only_table(ti, basic: dict) -> tuple[list, list]:
    self_row = {
        "name": basic.get("name") or ti.full,
        "code": ti.full,
        "pe": "{:.1f}".format(_float(basic.get("pe_ttm"))) if _float(basic.get("pe_ttm")) > 0 else "-",
        "pb": "{:.2f}".format(_float(basic.get("pb"))) if _float(basic.get("pb")) > 0 else "-",
        "roe": "-",
        "revenue_growth": "-",
        "is_self": True,
    }
    return [self_row], []


def _lixinger_available() -> bool:
    return bool(os.environ.get("LIXINGER_TOKEN", "").strip())


def _enrich_peers_with_lixinger(peer_codes: list[str], market: str) -> dict | None:
    """逐只查询同行最新年报指标 (startDate/endDate 模式, 各有 24h 缓存).

    理杏仁 date:latest 多股票模式不可靠, 改用 startDate 单股票模式逐个查.
    每个查询 24h 缓存, 首次 ~2s/只, 之后 0s.
    """
    try:
        from lib.lixinger_client import (
            fetch_financials as lx_fs,
            to_float as lx_tof,
        )
    except ImportError:
        return None

    # Only need latest year; short date range
    import datetime
    this_year = datetime.date.today().year
    start_y = this_year - 3  # 确保覆盖最近已出的年报

    out: dict = {}
    for code in set(peer_codes):
        raw = lx_fs(code, market=market, start_year=start_y, end_year=this_year)
        if not raw or not raw.get("metrics"):
            continue
        m = raw["metrics"]

        def _val(*keys):
            for k in keys:
                vals = m.get(k, [])
                if vals:
                    for v in reversed(vals):  # newest first
                        fv = lx_tof(v, None)
                        if fv is not None:
                            return fv
            return None

        entry: dict = {}
        pe = _val("y.bs.pe_ttm.t")
        pb = _val("y.bs.pb.t")
        ps = _val("y.bs.ps_ttm.t")
        roe = _val("y.ps.wroe.t")
        mcap = _val("y.bs.mc.t")
        gp_m = _val("y.ps.gp_m.t")
        debt_r = _val("y.bs.tl_ta_r.t")
        dyr = _val("y.bs.dyr.t")
        rev = _val("y.ps.oi.t")
        np_ = _val("y.ps.npatoshopc.t")

        if pe is not None:
            entry["pe"] = round(pe, 1)
        if pb is not None:
            entry["pb"] = round(pb, 2)
        if ps is not None:
            entry["ps"] = round(ps, 2)
        if roe is not None:
            entry["roe"] = round(roe * 100, 1) if abs(roe) < 1 else round(roe, 1)
        if mcap is not None:
            entry["mcap_yi"] = round(mcap / 1e8, 1)
        if gp_m is not None:
            entry["gross_margin"] = round(gp_m * 100, 1) if abs(gp_m) < 1 else round(gp_m, 1)
        if debt_r is not None:
            entry["debt_ratio"] = round(debt_r * 100, 1) if abs(debt_r) < 1 else round(debt_r, 1)
        if dyr is not None:
            entry["dyr"] = round(dyr * 100, 2)

        if entry:
            out[code] = entry

    return out if out else None


def main(ticker: str) -> dict:
    ti = parse_ticker(ticker)
    basic = ds.fetch_basic(ti)
    industry = basic.get("industry") or ""
    peers_raw: list = []
    peer_table: list = []
    peer_comparison: list = []

    # v2.5 · HK 分支：用 akshare HK valuation/scale comparison 给出 rank-in-HK-universe，
    # 没有具体同行名单（akshare 港股没有按行业列表函数；agent 可走 AASTOCKS Playwright 兜底）
    if ti.market == "H":
        # v2.12.1 · HK 分支独立 try/except 隔离（HK 数据路径与 A 股独立，失败不应污染）
        try:
            ranks = (basic.get("_ranks") or {})
            val = ranks.get("valuation") or {}
            scale = ranks.get("scale") or {}
            growth = ranks.get("growth") or {}
        except Exception:
            ranks, val, scale, growth = {}, {}, {}, {}
        # 用 PE/PB/Mcap 排名构造一行 self
        self_row = {
            "name": basic.get("name") or ti.full,
            "code": ti.full,
            "pe": f"{val.get('pe_ttm', 0):.1f}" if val.get("pe_ttm") else "—",
            "pb": f"{val.get('pb_mrq', 0):.2f}" if val.get("pb_mrq") else "—",
            "roe": "—",
            "revenue_growth": f"{growth.get('revenue_yoy', 0):.1f}%" if growth.get("revenue_yoy") else "—",
            "is_self": True,
        }
        peer_table = [self_row]
        peer_comparison = [
            {"name": "PE-TTM 排名 (HK 全市场)", "self": val.get("pe_ttm_rank"), "peer": "—"},
            {"name": "PB-MRQ 排名 (HK 全市场)", "self": val.get("pb_mrq_rank"), "peer": "—"},
            {"name": "总市值排名 (HK 全市场)", "self": scale.get("market_cap_rank"), "peer": "—"},
            {"name": "营收 YoY 排名", "self": growth.get("revenue_yoy_rank"), "peer": "—"},
        ]
        # rank string for the report
        mcap_rank = scale.get("market_cap_rank")
        rank_str = f"HK 第 {mcap_rank} 位（按总市值）" if mcap_rank else "—"
        return {
            "ticker": ti.full,
            "data": {
                "industry": industry or "未分类（akshare HK 无行业聚合）",
                "self": basic,
                "peer_table": peer_table,
                "peer_comparison": peer_comparison,
                "rank": rank_str,
                "peers_top20_raw": [],
                "_note": "HK peer LIST 需走 AASTOCKS Playwright 或问财；本字段提供 rank-in-universe 作替代",
            },
            "source": "akshare:hk_valuation_comparison_em + scale_comparison_em + growth_comparison_em",
            "fallback": False,
        }

    # v3.0 · A 股 · 理杏仁批量指标优先，akshare 兜底
    fallback_used = False
    fallback_reason = ""
    source_used = "akshare:stock_board_industry_cons_em"

    # Fallback via shared INDUSTRY_PEERS in lib/industry_peers.py (34 industries)

    lx_peers: dict = {}
    if industry and _lixinger_available():
        peer_codes: list[str] = []
        try:
            df = ak.stock_board_industry_cons_em(symbol=industry)
            if df is not None and not df.empty:
                peer_codes = [str(c).zfill(6) for c in df["代码"].tolist()]
        except Exception:
            pass

        if not peer_codes:
            peer_codes = get_peer_codes(industry)
            if peer_codes:
                source_used += " + INDUSTRY_PEERS_fallback"

        if peer_codes:
            lx_peers = _enrich_peers_with_lixinger(peer_codes, "cn") or {}
            if lx_peers:
                source_used += " + lixinger:peers"

    if industry or lx_peers:
        # Try akshare for name list; fall back to lx_peers keys
        name_map: dict[str, str] = {}
        akshare_raw: list[dict] = []

        try:
            df = ak.stock_board_industry_cons_em(symbol=industry)
            if df is not None and not df.empty:
                for _, r2 in df.iterrows():
                    c = str(r2.get("代码", "")).zfill(6)
                    n = str(r2.get("名称", ""))
                    name_map[c] = n
                df2 = df.copy()
                df2["_mcap"] = df2["总市值"].apply(_float) if "总市值" in df2.columns else 0
                df2 = df2.sort_values("_mcap", ascending=False)
                akshare_raw = df2.head(20).to_dict("records")
                peers_raw = akshare_raw
        except Exception:
            pass

        # Merge 理杏仁 data
        self_row = None
        peer_rows = []

        # Collect all codes (from lx_peers + akshare)
        all_codes: list[tuple[str, str, dict]] = []
        seen = set()
        for code, lx in lx_peers.items():
            name = name_map.get(code, lx.get("name", code))
            mcap = lx.get("mcap_yi", 0)
            all_codes.append((code, name, lx))
            seen.add(code)
        for r2 in akshare_raw:
            code = str(r2.get("代码", "")).zfill(6)
            if code not in seen:
                name = str(r2.get("名称", ""))
                all_codes.append((code, name, {}))
                seen.add(code)

        # Sort by mcap and take top 20
        all_codes.sort(key=lambda x: x[2].get("mcap_yi", 0), reverse=True)
        all_codes = all_codes[:20]

        for code, name, lx in all_codes:
            pe_val = lx.get("pe") or _float({})
            pb_val = lx.get("pb") or 0.0
            roe_val = lx.get("roe")
            ps_val = lx.get("ps")
            dyr_val = lx.get("dyr")
            mcap_val = lx.get("mcap_yi", 0)

            entry = {
                "name": name, "code": code,
                "pe": "{:.1f}".format(pe_val) if pe_val > 0 else "-",
                "pb": "{:.2f}".format(pb_val) if pb_val > 0 else "-",
                "roe": "{:.1f}%".format(roe_val) if roe_val else "-",
                "revenue_growth": "-",
            }
            if dyr_val is not None:
                entry["dyr"] = "{:.2f}%".format(dyr_val)
            if ps_val is not None:
                entry["ps"] = "{:.1f}".format(ps_val)
            entry["_mcap"] = mcap_val

            if code == ti.code:
                entry["is_self"] = True
                self_row = entry
            elif len(peer_rows) < 5:
                peer_rows.append(entry)

        peer_table = ([self_row] if self_row else []) + peer_rows

        # Peer averages
        lx_all_pe = [lx.get("pe") for lx in lx_peers.values() if lx.get("pe") and lx.get("pe") > 0]
        lx_all_pb = [lx.get("pb") for lx in lx_peers.values() if lx.get("pb") and lx.get("pb") > 0]
        lx_all_roe = [lx.get("roe") for lx in lx_peers.values() if lx.get("roe") is not None]
        peer_cmp = [
            {"name": "PE-TTM (越低越好)", "self": _float(basic.get("pe_ttm")),
             "peer": round(sum(lx_all_pe) / len(lx_all_pe), 1) if lx_all_pe else "-"},
            {"name": "PB (越低越好)", "self": _float(basic.get("pb")),
             "peer": round(sum(lx_all_pb) / len(lx_all_pb), 2) if lx_all_pb else "-"},
        ]
        if lx_all_roe:
            self_roe = lx_peers.get(ti.code, {}).get("roe")
            peer_cmp.append({"name": "ROE (越高越好)", "self": self_roe,
                             "peer": round(sum(lx_all_roe) / len(lx_all_roe), 1)})
        peer_comparison = peer_cmp

    if not peer_table:
        peer_table, peer_comparison = _build_self_only_table(ti, basic)
        fallback_used = True
        if not fallback_reason:
            fallback_reason = "同行数据源失败 · 仅公司自身"
        source_used += " (self-only)"

    return {
        "ticker": ti.full,
        "data": {
            "industry": industry,
            "self": basic,
            "peer_table": peer_table,
            "peer_comparison": peer_comparison,
            "rank": "—",  # 真实排名需要 聚合查询
            "peers_top20_raw": peers_raw[:20],
            "fallback_reason": fallback_reason,  # v2.12.1
        },
        "source": source_used,
        "fallback": fallback_used,
    }


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1] if len(sys.argv) > 1 else "002273.SZ"), ensure_ascii=False, indent=2, default=str))
