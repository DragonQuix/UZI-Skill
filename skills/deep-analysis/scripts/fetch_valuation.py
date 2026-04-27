"""Dimension 10 · 估值 — v3.0 · 理杏仁 PE/PB/PS 分位 + DCF.

数据源优先级:
  PE/PB/PS 历史分位: 理杏仁 API (LIXINGER_TOKEN) → 百度估值 akshare fallback
  行业 PE: cninfo (akshare stock_industry_pe_ratio_cninfo)
  DCF: 内部计算 (基于 fetch_financials 输出, 现已走理杏仁)
"""
from __future__ import annotations

import json
import sys
import os
from typing import Any

from lib.market_router import parse_ticker


# ── DCF 模型 (保留原实现) ────────────────────────────────────────
def simple_dcf(
    fcf_latest: float,
    growth_5y: float = 0.10,
    growth_terminal: float = 0.03,
    wacc: float = 0.10,
    years: int = 10,
) -> dict:
    if fcf_latest <= 0:
        return {"intrinsic_value": None, "_note": "negative FCF, DCF not applicable"}
    fcfs = []
    fcf = fcf_latest
    for y in range(1, years + 1):
        g = growth_5y if y <= 5 else (growth_5y + growth_terminal) / 2
        fcf *= 1 + g
        fcfs.append(fcf)
    pv_fcfs = sum(f / (1 + wacc) ** (i + 1) for i, f in enumerate(fcfs))
    terminal_value = fcfs[-1] * (1 + growth_terminal) / (wacc - growth_terminal)
    pv_terminal = terminal_value / (1 + wacc) ** years
    return {
        "intrinsic_value_total": pv_fcfs + pv_terminal,
        "pv_fcfs": pv_fcfs,
        "pv_terminal": pv_terminal,
        "assumptions": {
            "fcf_latest": fcf_latest, "growth_5y": growth_5y,
            "growth_terminal": growth_terminal, "wacc": wacc,
        },
    }


def dcf_sensitivity_matrix(
    fcf_latest: float,
    waccs: list[float],
    growths: list[float],
    current_price: float,
    shares_out: float = 1e9,
    years: int = 10,
) -> dict:
    values = []
    for w in waccs:
        row = []
        for g in growths:
            result = simple_dcf(fcf_latest=fcf_latest, growth_5y=g / 100, wacc=w / 100, years=years)
            iv = result.get("intrinsic_value_total") or 0
            per_share = iv / shares_out if shares_out else 0
            row.append(round(per_share, 2))
        values.append(row)
    return {
        "waccs": waccs,
        "growths": growths,
        "values": values,
        "current_price": current_price,
    }


# ── 理杏仁估值历史 ─────────────────────────────────────────────────
def _lixinger_available() -> bool:
    return bool(os.environ.get("LIXINGER_TOKEN", "").strip())


def _fetch_valuation_via_lixinger(ti, current_pe=None, current_pb=None) -> dict | None:
    try:
        from lib.lixinger_client import (
            fetch_valuation_history as lx_valhist,
            to_float as lx_tof,
        )
    except ImportError:
        return None

    market = "hk" if ti.market == "H" else "cn"
    raw = lx_valhist(ti.code, market=market, years_back=5)
    if not raw or not raw.get("metrics"):
        return None

    m = raw["metrics"]

    def _series(key, reverse=True):
        vals = m.get(key, [])
        if not vals:
            return []
        result = []
        for v in (reversed(vals) if reverse else vals):
            result.append(lx_tof(v, None))
        return [v for v in result if v is not None]

    pe_hist = _series("q.bs.pe_ttm.t")
    pb_hist = _series("q.bs.pb.t")
    ps_hist = _series("q.bs.ps_ttm.t")
    pcf_hist = _series("q.bs.pcf_ttm.t")
    dyr_hist = _series("q.bs.dyr.t")
    mcap_hist = _series("q.bs.mc.t")
    shn_hist = _series("q.bs.shn.t")

    out: dict = {}

    cur_pe = current_pe or (pe_hist[-1] if pe_hist else 0)
    if cur_pe and pe_hist:
        sorted_pe = sorted(pe_hist)
        pe_pct = sum(1 for x in sorted_pe if x < cur_pe) / len(sorted_pe) * 100
        out["pe_quantile"] = "5 年 {:.0f} 分位".format(pe_pct)
    else:
        out["pe_quantile"] = "-"

    cur_pb = current_pb or (pb_hist[-1] if pb_hist else 0)
    if cur_pb and pb_hist:
        sorted_pb = sorted(pb_hist)
        pb_pct = sum(1 for x in sorted_pb if x < cur_pb) / len(sorted_pb) * 100
        out["pb_quantile"] = "{:.0f}%".format(pb_pct)
    else:
        out["pb_quantile"] = "-"

    if ps_hist:
        cur_ps = ps_hist[-1]
        sorted_ps = sorted(ps_hist)
        ps_pct = sum(1 for x in sorted_ps if x < cur_ps) / len(sorted_ps) * 100
        out["ps_quantile"] = "{:.0f}%".format(ps_pct)

    if pe_hist:
        out["pe_history"] = pe_hist[-60:] if len(pe_hist) > 60 else pe_hist
    if pb_hist:
        out["pb_history"] = pb_hist[-60:] if len(pb_hist) > 60 else pb_hist
    if ps_hist:
        out["ps_history"] = ps_hist[-60:] if len(ps_hist) > 60 else ps_hist
    if pcf_hist:
        out["pcf_ttm"] = "{:.2f}".format(pcf_hist[-1]) if pcf_hist[-1] else "-"
        out["pcf_history"] = pcf_hist
    if dyr_hist:
        out["dyr"] = "{:.2f}%".format(dyr_hist[-1] * 100) if dyr_hist[-1] else "-"
    if mcap_hist:
        out["market_cap_bn"] = round(mcap_hist[-1] / 1e8, 1) if mcap_hist[-1] else None
    if shn_hist:
        out["shareholders"] = int(shn_hist[-1]) if shn_hist[-1] else None

    out["_valuation_source"] = "lixinger"
    return out


# ── 百度估值 akshare 兜底 ──────────────────────────────────────────
def _fetch_valuation_legacy(ti, basic: dict) -> dict:
    import akshare as ak
    out: dict = {}
    pe_history: list = []
    pe_quantile_val = None
    pb_quantile_val = None

    try:
        df_pe = ak.stock_zh_valuation_baidu(symbol=ti.code, indicator="市盈率(TTM)", period="近五年")
        if df_pe is not None and not df_pe.empty and "value" in df_pe.columns:
            pes_full = [round(float(v), 2) for v in df_pe["value"] if v and float(v) > 0]
            pe_history = pes_full[:]
            if len(pe_history) > 60:
                step = len(pe_history) // 60
                pe_history = pe_history[::step]
            cur_pe = basic.get("pe_ttm") or (pes_full[-1] if pes_full else 0)
            if cur_pe and pes_full:
                sorted_pe = sorted(pes_full)
                pe_quantile_val = sum(1 for x in sorted_pe if x < cur_pe) / len(sorted_pe) * 100
    except Exception:
        pass

    try:
        df_pb = ak.stock_zh_valuation_baidu(symbol=ti.code, indicator="市净率", period="近五年")
        if df_pb is not None and not df_pb.empty and "value" in df_pb.columns:
            pbs = [float(v) for v in df_pb["value"] if v and float(v) > 0]
            cur_pb = basic.get("pb")
            if cur_pb and pbs:
                sorted_pb = sorted(pbs)
                pb_quantile_val = sum(1 for x in sorted_pb if x < cur_pb) / len(sorted_pb) * 100
    except Exception:
        pass

    if pe_history:
        out["pe_history"] = pe_history
    if pe_quantile_val is not None:
        out["pe_quantile"] = "5 年 {:.0f} 分位".format(pe_quantile_val)
    else:
        out["pe_quantile"] = "-"
    if pb_quantile_val is not None:
        out["pb_quantile"] = "{:.0f}%".format(pb_quantile_val)
    else:
        out["pb_quantile"] = "-"

    out["_valuation_source"] = "baidu"
    return out


# ── 行业 PE (cninfo, 保留) ──────────────────────────────────────────
def _fetch_industry_pe(ti, basic: dict) -> float | None:
    import akshare as ak
    try:
        from datetime import datetime as _dt, timedelta as _td
        today = _dt.now()
        for d in [today - _td(days=i) for i in range(1, 8)]:
            try:
                df = ak.stock_industry_pe_ratio_cninfo(
                    symbol="证监会行业分类", date=d.strftime("%Y%m%d")
                )
                if df is not None and not df.empty:
                    ind_name = basic.get("industry") or ""
                    from lib.industry_mapping import resolve_csrc_industry as _resolve
                    row = _resolve(ind_name, df) if ind_name else None
                    if row is not None:
                        pe_col = next((c for c in df.columns if "市盈率" in c and "加权" in c), None)
                        if pe_col:
                            return round(float(row[pe_col]), 2)
            except Exception:
                continue
    except Exception:
        pass
    return None


def _fetch_industry_pe_hk(ti) -> float | None:
    try:
        import akshare as ak
        df_hk = ak.hk_valuation_comparison_em(symbol=ti.code.zfill(5))
        if df_hk is not None and not df_hk.empty and "PE(TTM)" in df_hk.columns:
            pes = []
            for v in df_hk["PE(TTM)"]:
                try:
                    p = float(v)
                    if 0 < p < 500:
                        pes.append(p)
                except (ValueError, TypeError):
                    pass
            if pes:
                return round(sum(pes) / len(pes), 2)
    except Exception:
        pass
    return None


# ── 主入口 ─────────────────────────────────────────────────────────
def main(ticker: str) -> dict:
    ti = parse_ticker(ticker)
    from lib import data_sources as ds
    basic = ds.fetch_basic(ti)

    cur_pe = basic.get("pe_ttm")
    cur_pb = basic.get("pb")
    val_data: dict = {}
    val_source = ""

    if _lixinger_available():
        val_data = _fetch_valuation_via_lixinger(ti, current_pe=cur_pe, current_pb=cur_pb) or {}
        if val_data.get("_valuation_source") == "lixinger":
            val_source = "lixinger:valuation_history"
        else:
            val_data = _fetch_valuation_legacy(ti, basic)
            val_source = "baidu:fallback"
    else:
        val_data = _fetch_valuation_legacy(ti, basic)
        val_source = "baidu:legacy"

    pe_history = val_data.get("pe_history", [])

    industry_pe_avg = None
    if ti.market == "A":
        industry_pe_avg = _fetch_industry_pe(ti, basic)
    elif ti.market == "H":
        industry_pe_avg = _fetch_industry_pe_hk(ti)

    dcf_result: dict = {}
    dcf_sensitivity: dict = {}
    try:
        from fetch_financials import main as _fin_main
        fin_result = _fin_main(ti.full)
        fin_data = fin_result.get("data", {}) if isinstance(fin_result, dict) else {}
        net_profit_hist = fin_data.get("net_profit_history", [])
        net_profit_latest_yi = net_profit_hist[-1] if net_profit_hist else 0

        if net_profit_latest_yi > 0:
            net_profit_yuan = net_profit_latest_yi * 1e8
            dcf_result = simple_dcf(fcf_latest=net_profit_yuan * 0.8)
            current_price = basic.get("price") or 0
            total_shares = basic.get("total_shares") or 0
            if not total_shares:
                mcap_raw = basic.get("market_cap_raw") or 0
                if current_price and mcap_raw:
                    total_shares = mcap_raw / current_price
            total_shares = total_shares or 1e9
            dcf_sensitivity = dcf_sensitivity_matrix(
                fcf_latest=net_profit_yuan * 0.8,
                waccs=[8, 9, 10, 11, 12],
                growths=[6, 8, 10, 12],
                current_price=current_price,
                shares_out=total_shares,
            )
    except Exception as e:
        dcf_result = {"error": str(e)[:80]}

    iv_total = dcf_result.get("intrinsic_value_total") if isinstance(dcf_result, dict) else None
    dcf_display = "¥{:.1f}亿".format(iv_total / 1e8) if iv_total else "-"

    assembled: dict = {
        "pe": str(cur_pe) if cur_pe is not None else "-",
        "pb": str(cur_pb) if cur_pb is not None else "-",
        "pe_quantile": val_data.get("pe_quantile", "-"),
        "pb_quantile": val_data.get("pb_quantile", "-"),
        "industry_pe": str(industry_pe_avg) if industry_pe_avg else "-",
        "dcf": dcf_display,
        "pe_history": pe_history,
        "dcf_simple": dcf_result,
        "dcf_sensitivity": dcf_sensitivity,
    }

    for key in ("ps_quantile", "ps_history", "pb_history", "pcf_history",
                "pcf_ttm", "dyr", "market_cap_bn", "shareholders"):
        if key in val_data:
            assembled[key] = val_data[key]

    return {
        "ticker": ti.full,
        "data": assembled,
        "source": val_source + (" + cninfo" if industry_pe_avg else "") + " + simple_dcf",
        "fallback": not bool(val_data),
    }


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1] if len(sys.argv) > 1 else "002273.SZ"), ensure_ascii=False, indent=2, default=str))
