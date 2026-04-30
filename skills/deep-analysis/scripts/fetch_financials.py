"""Dimension 1 · 财报 — v3.0 · 理杏仁主源 + akshare 兜底.

数据源优先级:
  A股/HK: 理杏仁 API (LIXINGER_TOKEN) → akshare fallback
  美股:   yfinance

Output shape (backward compatible with v2.x report viz):
{
  "roe": "30.5%", "net_margin": "47.8%", "revenue_growth": "-1.2%", "fcf": "500.0亿",
  "roe_history":        [25.3, 28.1, 31.2, 29.5, 30.2, 31.5],   # 5Y+
  "revenue_history":    [888.5, 979.9, 1095.2, 1275.5, 1476.9, 1550.2],   # 亿
  "net_profit_history": [412.1, 466.9, 524.6, 627.2, 747.3, 798.5],      # 亿
  "financial_years":    ["2019","2020","2021","2022","2023","2024"],
  "dividend_years":     ["2020", ...],
  "dividend_amounts":   [...],   # 元/10 股
  "dividend_yields":    [...],   # %
  "financial_health": {
      "current_ratio": 3.8,
      "debt_ratio":    19.2,
      "fcf_margin":   118.0,
      "roic":          29.5,
  }
}
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from collections import defaultdict

from lib.market_router import parse_ticker


def _to_float(v) -> float:
    try:
        if v in (None, "", "--", "-"):
            return 0.0
        return float(str(v).replace(",", "").replace("%", ""))
    except (ValueError, TypeError):
        return 0.0


def _to_yi(v) -> float:
    n = _to_float(v)
    return round(n / 1e8, 2)


# ─────────────────────────────────────────────────────────────
# 理杏仁路径
# ─────────────────────────────────────────────────────────────
def _lixinger_available() -> bool:
    return bool(os.environ.get("LIXINGER_TOKEN", "").strip())


def _fetch_via_lixinger(ti, industry: str = "") -> dict | None:
    try:
        from lib.lixinger_client import (
            classify_financial_industry,
            fetch_bank_fs, fetch_security_fs, fetch_insurance_fs,
            fetch_other_financial_fs,
            fetch_financials as lx_fetch,
            to_float as lx_tof,
        )
    except ImportError:
        return None

    market = "hk" if ti.market == "H" else "cn"
    code = ti.code.zfill(5) if market == "hk" else ti.code

    # v3.11 · 按金融子类型路由到正确的 fs 端点
    ftype = classify_financial_industry(industry) if industry else None
    if ftype == "bank":
        raw = fetch_bank_fs(code, market=market, start_year=2016, end_year=2026)
    elif ftype == "security":
        raw = fetch_security_fs(code, market=market, start_year=2016, end_year=2026)
    elif ftype == "insurance":
        raw = fetch_insurance_fs(code, market=market, start_year=2016, end_year=2026)
    elif ftype == "other_financial":
        raw = fetch_other_financial_fs(code, market=market, start_year=2016, end_year=2026)
    else:
        raw = lx_fetch(code, market=market, start_year=2016, end_year=2026)
    if not raw or not raw.get("metrics"):
        return None

    m = raw["metrics"]
    dates = raw["dates"]

    # API returns newest-first; reverse to oldest-first for consistent indexing
    def _series(*keys, div=1.0, ndigits=2, is_pct=False):
        """Extract and reverse a metric series. is_pct multiplies by 100 (API returns decimals)."""
        for k in keys:
            vals = m.get(k, [])
            if vals and any(v is not None for v in vals):
                result = []
                for v in reversed(vals):
                    if v is not None:
                        raw_val = lx_tof(v)
                        if is_pct:
                            raw_val *= 100
                        result.append(round(raw_val / div, ndigits))
                    else:
                        result.append(0.0)
                return result
        return []

    rev = _series("y.ps.oi.t", "y.ps.toi.t", div=1e8)
    np_ = _series("y.ps.npatoshopc.t", "y.ps.np.t", div=1e8)
    # API returns ROE as decimal: 0.3253 → 32.53%
    # v3.11 · bank/security 端点 ROE 在 y.m.wroe.t, non_financial 在 y.ps.wroe.t
    # v3.12→v3.13 · 港股银行/保险/其他金融用 y.m.roe.t (非加权 ROE)
    # A 股金融业 bank/security 端点用 y.m.wroe.t, non_financial 用 y.ps.wroe.t
    roe_raw = _series("y.ps.wroe.t", "y.ps.wdroe.t", "y.m.wroe.t", "y.m.roe.t", is_pct=True)
    gpm = _series("y.ps.gp_m.t", is_pct=True)
    # 净利率 = 净利润/营收 (推算, y.m.np_s_r 不可用)
    npm_raw: list[float] = []
    if np_ and rev:
        npm_raw = [round(np_[i] / rev[i] * 100, 1) if rev[i] else 0.0 for i in range(min(len(np_), len(rev)))]

    # Reverse dates → oldest first
    years = [d[:4] for d in reversed(dates)] if dates else []
    latest_rev = rev[-1] if rev else 0
    latest_np = np_[-1] if np_ else 0

    def _pct(vals, idx=-1):
        if vals:
            return "{:.1f}%".format(vals[idx])
        return "-"

    # HK fallback: ROE = NP / (TA - TL) if weighted ROE not available in API
    if not roe_raw and np_:
        ta_vals = _series("y.bs.ta.t", div=1e8)
        tl_vals = _series("y.bs.tl.t", div=1e8)
        if ta_vals and tl_vals:
            roe_raw = []
            for i in range(min(len(np_), len(ta_vals), len(tl_vals))):
                equity = ta_vals[i] - tl_vals[i]
                if equity > 0:
                    roe_raw.append(round(np_[i] / equity * 100, 1))
                else:
                    roe_raw.append(0.0)

    roe_str = _pct(roe_raw) if roe_raw else "-"
    npm_str = _pct(npm_raw) if npm_raw else "-"
    gpm_str = _pct(gpm) if gpm else "-"

    rev_growth = "-"
    if len(rev) >= 2 and rev[-2]:
        g = (rev[-1] - rev[-2]) / rev[-2] * 100
        rev_growth = "{:+.1f}%".format(g)

    # FCF = OCF + 投资活动现金流 (理杏仁 y.m.fcf 不可用，推算)
    ocf_vals = _series("y.cfs.ncffoa.t", div=1e8)
    icf_vals = _series("y.cfs.ncffia.t", div=1e8)
    fcf_raw: list[float] = []
    if ocf_vals and icf_vals:
        fcf_raw = [ocf_vals[i] + icf_vals[i] for i in range(min(len(ocf_vals), len(icf_vals)))]
    fcf_str = "-"
    fcf_latest = 0.0
    if fcf_raw:
        fcf_latest = fcf_raw[-1]
        fcf_str = "{:.1f}亿".format(fcf_latest)

    # Financial health
    health: dict = {}
    # 资产负债率: API returns decimal (0.1642 → 16.42%)
    debt_vals = _series("y.bs.tl_ta_r.t", is_pct=True)
    if debt_vals:
        health["debt_ratio"] = round(debt_vals[-1], 1)
    cr_vals = _series("y.bs.tca_tcl_r.t", "y.bs.q_r.t", ndigits=2)
    if cr_vals:
        health["current_ratio"] = round(cr_vals[-1], 2)
    # ROIC = NOPAT / (总资产 - 流动负债) 近似
    ta_vals = _series("y.bs.ta.t", div=1e8)
    tcl_vals = _series("y.bs.tca_tcl_r.t")  # need absolute CL
    # 用负债率倒推: CL = TL 近似，ROIC ~= NP / (TA - TL*0.6)
    tl_vals = _series("y.bs.tl.t", div=1e8)
    if latest_np and ta_vals and tl_vals:
        ic = ta_vals[-1] - tl_vals[-1] * 0.6
        if ic > 0:
            health["roic"] = round(latest_np / ic * 100, 1)
    # FCF margin
    if fcf_latest and latest_rev:
        health["fcf_margin"] = round(fcf_latest / latest_rev * 100, 1)

    # EBIT / EBITDA
    ebit_vals = _series("y.ps.ebit.t", div=1e8)
    ebitda_vals = _series("y.ps.ebitda.t", div=1e8)
    extra = {}
    if ebit_vals:
        extra["ebit"] = "{:.1f}亿".format(ebit_vals[-1])
    if ebitda_vals:
        extra["ebitda"] = "{:.1f}亿".format(ebitda_vals[-1])

    # 分红
    da_vals = _series("y.ps.da.t", div=1e8)
    tsc_vals = _series("y.bs.tsc.t", div=1e8)
    div_years: list[str] = []
    div_amounts: list[float] = []
    div_yields: list[float] = []
    if da_vals and len(da_vals) == len(years):
        for i in range(len(da_vals)):
            if da_vals[i] and years[i]:
                div_years.append(years[i])
                tsc = tsc_vals[i] if i < len(tsc_vals) and tsc_vals[i] else 12.56
                dps = round(da_vals[i] / tsc * 10, 2)
                div_amounts.append(dps)
                div_yields.append(round(dps / 20, 2))

    out: dict = {}
    if rev:
        out["revenue_history"] = rev
    if np_:
        out["net_profit_history"] = np_
    if years:
        out["financial_years"] = years
    if roe_raw:
        out["roe_history"] = roe_raw
    if roe_str != "-":
        out["roe"] = roe_str
    if npm_str != "-":
        out["net_margin"] = npm_str
    if gpm_str != "-":
        out["gross_margin"] = gpm_str
    if rev_growth != "-":
        out["revenue_growth"] = rev_growth
    if fcf_str != "-":
        out["fcf"] = fcf_str
    if health:
        out["financial_health"] = health
    if div_years:
        out["dividend_years"] = div_years
        out["dividend_amounts"] = div_amounts
        out["dividend_yields"] = div_yields
    out.update(extra)
    return out


# ─────────────────────────────────────────────────────────────
# A 股 akshare 兜底路径（保留原有逻辑）
# ─────────────────────────────────────────────────────────────
def _fetch_a_share_legacy(ti) -> dict:
    import akshare as ak
    out: dict = {}
    code = ti.code

    try:
        df_abs = ak.stock_financial_abstract(symbol=code)
        if df_abs is not None and not df_abs.empty:
            period_cols = [c for c in df_abs.columns if c not in ("选项", "指标")]
            period_cols_annual = [c for c in period_cols if str(c).endswith("1231")][:6]
            period_cols_annual = sorted(period_cols_annual)

            def _row(keyword: str) -> list:
                row = df_abs[df_abs["指标"].astype(str).str.contains(keyword, na=False, regex=False)]
                if row.empty:
                    return []
                return [_to_yi(row[c].iloc[0]) for c in period_cols_annual]

            out["revenue_history"] = _row("营业总收入")
            out["net_profit_history"] = _row("归属于母公司所有者的净利润") or _row("净利润")
            out["financial_years"] = [str(c)[:4] for c in period_cols_annual]
    except Exception as e:
        out["_abstract_error"] = str(e)

    try:
        df_ind = ak.stock_financial_analysis_indicator(symbol=code, start_year="2018")
        if df_ind is not None and not df_ind.empty:
            date_col = "日期" if "日期" in df_ind.columns else df_ind.columns[0]
            df_ind = df_ind.sort_values(date_col)
            df_annual = df_ind[df_ind[date_col].astype(str).str.endswith("12-31")]
            if len(df_annual) < 3:
                df_annual = df_ind

            for col_key, target in [
                ("加权净资产收益率(%)", "roe_history"),
                ("净资产收益率加权(%)", "roe_history"),
                ("ROE", "roe_history"),
            ]:
                if col_key in df_ind.columns:
                    out[target] = [_to_float(v) for v in df_annual[col_key].tail(6).tolist()]
                    break

            last = df_ind.iloc[-1]
            health = {}
            for src_key, dst_key, unit_div in [
                ("流动比率", "current_ratio", 1),
                ("资产负债率(%)", "debt_ratio", 1),
                ("总资产净利率(%)", "roic", 1),
                ("销售净利率(%)", "net_margin_pct", 1),
            ]:
                if src_key in df_ind.columns:
                    v = _to_float(last.get(src_key))
                    if v:
                        health[dst_key] = v / unit_div
            if health:
                out["financial_health"] = health

            if "加权净资产收益率(%)" in df_ind.columns:
                out["roe"] = "{:.1f}%".format(_to_float(last["加权净资产收益率(%)"]))
            if "销售净利率(%)" in df_ind.columns:
                out["net_margin"] = "{:.1f}%".format(_to_float(last["销售净利率(%)"]))
    except Exception as e:
        out["_indicator_error"] = str(e)

    try:
        rh = out.get("revenue_history") or []
        if len(rh) >= 2 and rh[-2]:
            growth = (rh[-1] - rh[-2]) / rh[-2] * 100
            out["revenue_growth"] = "{:+.1f}%".format(growth)
    except Exception:
        pass

    try:
        import akshare as ak2
        prefix = "SH" + code if code.startswith("60") else "SZ" + code
        df_cf = ak2.stock_cash_flow_sheet_by_report_em(symbol=prefix)
        if df_cf is not None and not df_cf.empty:
            if "经营活动产生的现金流量净额" in df_cf.columns:
                ocf = _to_float(df_cf["经营活动产生的现金流量净额"].iloc[0])
                out["fcf"] = "{:.1f}亿".format(ocf / 1e8)
                np_latest = (out.get("net_profit_history") or [0])[-1]
                if np_latest:
                    out.setdefault("financial_health", {})["fcf_margin"] = round(ocf / 1e8 / np_latest * 100, 1)
    except Exception:
        pass

    try:
        import akshare as ak3
        df_div = ak3.stock_history_dividend_detail(symbol=code, indicator="分红")
        if df_div is not None and not df_div.empty:
            by_year: dict[str, float] = defaultdict(float)
            for _, row in df_div.head(30).iterrows():
                date_str = str(row.get("公告日期", row.get("除权除息日", "")))
                year = date_str[:4] if date_str and len(date_str) >= 4 else ""
                amount = _to_float(row.get("派息", row.get("现金分红-派息(税前)(元/10股)", 0)))
                if year and amount:
                    by_year[year] += amount
            if by_year:
                years_sorted = sorted(by_year.keys())[-5:]
                out["dividend_years"] = years_sorted
                out["dividend_amounts"] = [round(by_year[y], 2) for y in years_sorted]
                out["dividend_yields"] = [round(by_year[y] / 20, 2) for y in years_sorted]
    except Exception as e:
        out["_dividend_error"] = str(e)

    return out


# ─────────────────────────────────────────────────────────────
# HK akshare 兜底路径
# ─────────────────────────────────────────────────────────────
def _fetch_hk_legacy(ti) -> dict:
    import akshare as ak
    code5 = ti.code.zfill(5)
    out: dict = {}
    try:
        df = ak.stock_financial_hk_analysis_indicator_em(symbol=code5, indicator="年度")
        if df is None or df.empty:
            return {}
        df = df.sort_values("REPORT_DATE").tail(6).reset_index(drop=True)
        years = [str(d)[:4] for d in df["REPORT_DATE"].tolist()]
        out["financial_years"] = years

        def _col(name, div=1.0, ndigits=2):
            if name not in df.columns:
                return []
            vals = []
            for v in df[name].tolist():
                try:
                    vals.append(round(float(v) / div, ndigits))
                except (TypeError, ValueError):
                    vals.append(None)
            return vals

        out["revenue_history"] = _col("OPERATE_INCOME", div=1e8, ndigits=2)
        out["net_profit_history"] = _col("HOLDER_PROFIT", div=1e8, ndigits=2)
        out["roe_history"] = _col("ROE_AVG", ndigits=2)

        last = df.iloc[-1].to_dict()

        def _lpct(key, default="-"):
            v = last.get(key)
            try:
                return "{:.1f}%".format(float(v))
            except (TypeError, ValueError):
                return default

        out["roe"] = _lpct("ROE_AVG")
        out["roic"] = _lpct("ROIC_YEARLY")
        out["net_margin"] = _lpct("NET_PROFIT_RATIO")
        out["gross_margin"] = _lpct("GROSS_PROFIT_RATIO")

        try:
            out["revenue_growth"] = "{:.1f}%".format(float(last.get("OPERATE_INCOME_YOY", 0)))
        except (TypeError, ValueError):
            out["revenue_growth"] = "-"
        try:
            out["profit_growth"] = "{:.1f}%".format(float(last.get("HOLDER_PROFIT_YOY", 0)))
        except (TypeError, ValueError):
            out["profit_growth"] = "-"

        try:
            out["financial_health"] = {
                "debt_ratio": round(float(last.get("DEBT_ASSET_RATIO") or 0), 1),
                "current_ratio": round(float(last.get("CURRENT_RATIO") or 0), 2),
                "roic": round(float(last.get("ROIC_YEARLY") or 0), 2),
                "fcf_margin": None,
            }
        except Exception:
            pass
        try:
            out["eps"] = round(float(last.get("BASIC_EPS") or 0), 3)
        except Exception:
            pass
        try:
            out["bps"] = round(float(last.get("BPS") or 0), 2)
        except Exception:
            pass
        out["currency"] = str(last.get("CURRENCY") or "HKD")
    except Exception as e:
        out["_hk_indicator_error"] = "{}: {}".format(type(e).__name__, e)

    return out


# ─────────────────────────────────────────────────────────────
# US yfinance
# ─────────────────────────────────────────────────────────────
def _fetch_us(ti) -> dict:
    try:
        import yfinance as yf
    except ImportError:
        return {}
    try:
        t = yf.Ticker(ti.code)
        fin = t.financials
        info = t.info or {}
        out: dict = {}
        if fin is not None and not fin.empty:
            rev_row = next((r for r in ["Total Revenue", "TotalRevenue"] if r in fin.index), None)
            np_row = next((r for r in ["Net Income", "NetIncome"] if r in fin.index), None)
            if rev_row:
                out["revenue_history"] = [round(float(v) / 1e8, 2) for v in fin.loc[rev_row].tolist()[::-1]]
            if np_row:
                out["net_profit_history"] = [round(float(v) / 1e8, 2) for v in fin.loc[np_row].tolist()[::-1]]
            out["financial_years"] = [str(c)[:4] for c in fin.columns[::-1]]
        out["roe"] = "{:.1f}%".format(info.get("returnOnEquity", 0) * 100) if info.get("returnOnEquity") else "-"
        out["net_margin"] = "{:.1f}%".format(info.get("profitMargins", 0) * 100) if info.get("profitMargins") else "-"
        return out
    except Exception:
        return {}


# ─────────────────────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────────────────────
def main(ticker: str) -> dict:
    ti = parse_ticker(ticker)
    source = ""
    fallback = False
    error = None
    data: dict = {}

    # v3.11 · 获取行业分类以路由正确的理杏仁端点
    industry = ""
    try:
        from lib.data_sources import fetch_basic as _ds_basic
        basic = _ds_basic(ti) or {}
        industry = basic.get("industry", "")
    except Exception:
        pass

    # v3.11 · 端点后缀（用于 source label）
    ftype = ""
    try:
        from lib.lixinger_client import classify_financial_industry
        ftype = classify_financial_industry(industry) or ""
    except Exception:
        pass

    try:
        if ti.market == "A":
            if _lixinger_available():
                data = _fetch_via_lixinger(ti, industry)
                if data:
                    source = f"lixinger:{ftype}" if ftype else "lixinger:non_financial"
                else:
                    fallback = True
                    data = _fetch_a_share_legacy(ti)
                    source = "akshare:fallback"
            else:
                data = _fetch_a_share_legacy(ti)
                source = "akshare:legacy"

        elif ti.market == "H":
            if _lixinger_available():
                data = _fetch_via_lixinger(ti, industry)
                if data:
                    source = f"lixinger:hk_{ftype}" if ftype else "lixinger:hk_non_financial"
                else:
                    fallback = True
                    data = _fetch_hk_legacy(ti)
                    source = "akshare:hk_fallback"
            else:
                data = _fetch_hk_legacy(ti)
                source = "akshare:hk_legacy"

        elif ti.market == "U":
            data = _fetch_us(ti)
            source = "yfinance"
        else:
            data = {}
            error = "unsupported market: {}".format(ti.market)

    except Exception as e:
        data = {}
        error = "{}: {}".format(type(e).__name__, e)
        traceback.print_exc(file=sys.stderr)

    return {
        "ticker": ti.full,
        "data": data,
        "source": source,
        "fallback": fallback or (not bool(data)),
        "error": error,
    }


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "002273.SZ"
    print(json.dumps(main(arg), ensure_ascii=False, indent=2, default=str))
