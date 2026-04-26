"""理杏仁 (Lixinger) 开放平台 API 统一客户端 · v1.0

Token: 从环境变量 LIXINGER_TOKEN 读取，不写入代码。
Base URL: https://open.lixinger.com/api
Cache: 复用 lib/cache.py 的 TTL 体系（财报数据 TTL_QUARTERLY = 24h）
Retry: 3 次，指数退避 1s/2s/4s
Error: 所有方法 return None / {} on failure，永不 raise

API 文档参考：
  - 基础信息: /api/cn/company
  - 非金融财报: /api/cn/company/fs/non_financial
  - 港股财报: /api/hk/company/fs/non_financial
"""

from __future__ import annotations

import json
import os
import time
import hashlib
from pathlib import Path
from typing import Any

import requests

CACHE_ROOT = Path(".cache")
LIXINGER_BASE = "https://open.lixinger.com/api"
REQUEST_TIMEOUT = 30  # seconds per request


# ── token ──────────────────────────────────────────────────────────
def _token() -> str:
    t = os.environ.get("LIXINGER_TOKEN", "").strip()
    if not t:
        raise RuntimeError("LIXINGER_TOKEN 未在环境变量中设置")
    return t


# ── cache (self-contained, mirrors lib/cache.py pattern) ───────────
def _cache_path(key: str) -> Path:
    h = hashlib.md5(key.encode("utf-8")).hexdigest()[:12]
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in key)[:60]
    return CACHE_ROOT / "lixinger" / f"{safe}__{h}.json"


def _cached(key: str, fetch_fn, ttl: int = 24 * 60 * 60) -> Any:
    """缓存包装：24h TTL 默认（财报数据），STOCK_NO_CACHE=1 强制刷新。"""
    if os.environ.get("STOCK_NO_CACHE") == "1":
        return fetch_fn()

    path = _cache_path(key)
    now = time.time()
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if now - payload.get("_cached_at", 0) < ttl:
                return payload["data"]
        except (json.JSONDecodeError, KeyError):
            pass

    data = fetch_fn()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"_cached_at": now, "data": data}, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    return data


# ── retry ──────────────────────────────────────────────────────────
def _post(url: str, body: dict, attempts: int = 3) -> dict:
    """POST JSON with retry. Returns decoded JSON dict on success, {} on failure."""
    last_err = None
    for i in range(attempts):
        try:
            r = requests.post(url, json=body, timeout=REQUEST_TIMEOUT,
                              headers={
                                  "Content-Type": "application/json",
                                  "Accept-Encoding": "gzip, deflate, br",
                              })
            if r.status_code == 200:
                resp = r.json()
                if resp.get("code") == 1:
                    return resp
                else:
                    last_err = "code={} msg={}".format(resp.get("code"), resp.get("message", ""))
                    if i < attempts - 1:
                        time.sleep(1 * (i + 1))
                    continue
            else:
                last_err = "HTTP {}: {}".format(r.status_code, r.text[:200])
        except requests.exceptions.RequestException as e:
            last_err = "{}: {}".format(type(e).__name__, e)

        if i < attempts - 1:
            time.sleep(1 * (i + 1))

    print("[lixinger] POST {} failed after {} attempts: {}".format(url, attempts, last_err), flush=True)
    return {}


# ── 指标模板 ───────────────────────────────────────────────────────
# 年报粒度 (y) · 当期值 (t) · 核心财务 + 估值 + 健康度
_FINANCIALS_ANNUAL_METRICS = [
    # ── 资产负债表 ──
    "y.bs.ta.t",             # 总资产
    "y.bs.tca.t",            # 流动资产
    "y.bs.fa.t",             # 固定资产
    "y.bs.i.t",              # 存货
    "y.bs.ar.t",             # 应收账款
    "y.bs.gw.t",             # 商誉
    "y.bs.lwi.t",            # 有息负债
    "y.bs.tl.t",             # 总负债
    "y.bs.tl_ta_r.t",        # 资产负债率
    "y.bs.tca_tcl_r.t",      # 流动比率
    "y.bs.q_r.t",            # 速动比率
    "y.bs.toe.t",            # 股东权益
    "y.bs.tetoshopc.t",      # 归母股东权益
    "y.bs.tetoshopc_ps.t",   # 每股净资产
    # ── 市场估值 ──
    "y.bs.pe_ttm.t",         # PE-TTM
    "y.bs.pb.t",             # PB
    "y.bs.ps_ttm.t",         # PS-TTM
    "y.bs.pcf_ttm.t",        # PCF-TTM
    "y.bs.dyr.t",            # 股息率
    "y.bs.mc.t",             # 市值
    "y.bs.tsc.t",            # 总股本
    "y.bs.csc.t",            # 流通股本
    "y.bs.shn.t",            # 股东人数(季度)
    "y.bs.shbt1sh_tsc_r.t",  # 第一大股东持仓比例
    "y.bs.shbt10sh_tsc_r.t", # 前十大股东持仓比例
    # ── 利润表 ──
    "y.ps.toi.t",            # 营业总收入
    "y.ps.oi.t",             # 营业收入
    "y.ps.oc.t",             # 营业成本
    "y.ps.gp_m.t",           # 毛利率
    "y.ps.se.t",             # 销售费用
    "y.ps.ae.t",             # 管理费用
    "y.ps.rade.t",           # 研发费用
    "y.ps.fe.t",             # 财务费用
    "y.ps.se_r.t",           # 销售费用率
    "y.ps.ae_r.t",           # 管理费用率
    "y.ps.rade_r.t",         # 研发费用率
    "y.ps.fe_r.t",           # 财务费用率
    "y.ps.cp.t",             # 核心利润
    "y.ps.op.t",             # 营业利润
    "y.ps.np.t",             # 净利润
    "y.ps.npatoshopc.t",     # 归母净利润
    "y.ps.npadnrpatoshaopc.t", # 扣非归母净利润
    "y.ps.wroe.t",           # 加权ROE
    "y.ps.wdroe.t",          # 扣非加权ROE
    "y.ps.beps.t",           # 基本EPS
    "y.ps.ebit.t",           # EBIT
    "y.ps.ebitda.t",         # EBITDA
    "y.ps.da.t",             # 分红金额
    "y.ps.d_np_r.t",         # 分红率
    "y.ps.d_oi.t",           # 境内收入
    "y.ps.d_oi_r.t",         # 境内收入占比
    "y.ps.o_oi.t",           # 海外收入
    "y.ps.o_oi_r.t",         # 海外收入占比
    "y.ps.tfci_r.t",         # 前五客户收入占比
    # ── 现金流量表 ──
    "y.cfs.ncffoa.t",        # 经营活动现金流净额
    "y.cfs.ncffia.t",        # 投资活动现金流净额
    "y.cfs.ncfffa.t",        # 筹资活动现金流净额
    "y.cfs.crfscapls.t",     # 销售商品收到现金
    # ── 财务指标 ──
    "y.m.wroe.t",            # ROE (指标)
    "y.m.wdroe.t",           # 扣非ROE (指标)
    "y.m.roa.t",             # ROA
    "y.m.roic.t",            # ROIC
    "y.m.roc.t",             # ROC
    "y.m.gp_m.t",            # 毛利率 (指标)
    "y.m.np_s_r.t",          # 净利润率
    "y.m.fcf.t",             # 自由现金流量
    "y.m.i_tor.t",           # 存货周转率
    "y.m.ar_tor.t",          # 应收账款周转率
    "y.m.i_ds.t",            # 存货周转天数
    "y.m.ar_ds.t",           # 应收账款周转天数
    "y.m.lwi_ta_r.t",        # 有息负债率
    "y.m.c_r.t",             # 流动比率 (指标)
    "y.m.ta_to.t",           # 总资产周转率
]

# 港股专用指标 (HK API 字段远少于 A 股: 无 y.m.*, 无 y.ps.wroe/ebit/ebitda/op, 无 y.bs 部分比率字段)
_FINANCIALS_ANNUAL_METRICS_HK = [
    # ── 利润表 (HK 可用) ──
    "y.ps.oi.t",             # 营业收入
    "y.ps.np.t",             # 净利润
    "y.ps.npatoshopc.t",     # 归母净利润
    "y.ps.gp_m.t",           # 毛利率
    "y.ps.da.t",             # 分红金额
    "y.ps.d_np_r.t",         # 分红率
    # ── 资产负债表 (HK 可用) ──
    "y.bs.pe_ttm.t",         # PE-TTM
    "y.bs.pb.t",             # PB
    "y.bs.ps_ttm.t",         # PS-TTM
    "y.bs.mc.t",             # 市值
    "y.bs.ta.t",             # 总资产
    "y.bs.tl.t",             # 总负债
    "y.bs.tl_ta_r.t",        # 资产负债率
    "y.bs.tsc.t",            # 总股本
    # ── 现金流量表 (HK 可用) ──
    "y.cfs.ncffoa.t",        # 经营活动现金流净额
    "y.cfs.ncffia.t",        # 投资活动现金流净额
    "y.cfs.ncfffa.t",        # 筹资活动现金流净额
]

# 估值历史专用（更少字段，更长时序）
# 季度粒度用于估值分位 — 5 年 × 4Q = ~20 个数据点，比年报 5 个点更精确
_VALUATION_HISTORY_METRICS = [
    "q.bs.pe_ttm.t", "q.bs.pb.t", "q.bs.ps_ttm.t", "q.bs.pcf_ttm.t",
    "q.bs.dyr.t", "q.bs.mc.t", "q.bs.tsc.t", "q.bs.shn.t",
    "q.bs.shbt10sh_tsc_r.t", "q.bs.shbpoof_csc_r.t",
]


# ── 公共 API ───────────────────────────────────────────────────────
def fetch_financials(stock_code: str, market: str = "cn",
                     start_year: int = 2016, end_year: int = 2026) -> dict | None:
    """获取股票完整财务数据（10 年跨度 · 年报粒度）。

    Args:
        stock_code: 股票代码，如 "600519" / "00700"
        market: "cn" (A股) | "hk" (港股)
    """
    token = _token()
    endpoint = "{}/{}/company/fs/non_financial".format(LIXINGER_BASE, market)
    start_date = "{}-12-31".format(start_year)
    end_date = "{}-12-31".format(end_year)

    metrics = _FINANCIALS_ANNUAL_METRICS_HK if market == "hk" else _FINANCIALS_ANNUAL_METRICS

    body = {
        "token": token,
        "stockCodes": [stock_code],
        "startDate": start_date,
        "endDate": end_date,
        "metricsList": metrics,
    }

    cache_key = "fs__{}__{}__{}_{}".format(market, stock_code, start_year, end_year)
    return _cached(cache_key, lambda: _do_fetch(endpoint, body))


def fetch_latest_financials(stock_code: str, market: str = "cn") -> dict | None:
    """获取最近 1.1 年的最新财报数据 (date=latest 模式)。"""
    token = _token()
    endpoint = "{}/{}/company/fs/non_financial".format(LIXINGER_BASE, market)
    # date=latest with single stock allows up to 128 metrics
    body = {
        "token": token,
        "stockCodes": [stock_code],
        "date": "latest",
        "metricsList": _FINANCIALS_ANNUAL_METRICS,
    }

    cache_key = "fs_latest__{}__{}".format(market, stock_code)
    return _cached(cache_key, lambda: _do_fetch(endpoint, body), ttl=4 * 60 * 60)


def fetch_valuation_history(stock_code: str, market: str = "cn",
                            years_back: int = 5) -> dict | None:
    """获取估值指标历史序列，用于 PE/PB 分位计算。

    Returns same shape as fetch_financials but with fewer metrics.
    dates 是财报日期，分位计算需在代码中自行排序和 percentile。
    """
    token = _token()
    endpoint = "{}/{}/company/fs/non_financial".format(LIXINGER_BASE, market)

    import datetime
    end_date = datetime.date.today().isoformat()
    start_date = (datetime.date.today() - datetime.timedelta(days=years_back * 365)).isoformat()

    body = {
        "token": token,
        "stockCodes": [stock_code],
        "startDate": start_date,
        "endDate": end_date,
        "metricsList": _VALUATION_HISTORY_METRICS,
    }

    cache_key = "valhist__{}__{}__{}y".format(market, stock_code, years_back)
    return _cached(cache_key, lambda: _do_fetch(endpoint, body), ttl=12 * 60 * 60)


# 同行批量查询专用指标 (单只股票时 48 指标限制, 多只时更少)
_PEER_METRICS = [
    "y.ps.oi.t",             # 营业收入
    "y.ps.npatoshopc.t",     # 归母净利润
    "y.ps.gp_m.t",           # 毛利率
    "y.ps.wroe.t",           # 加权ROE
    "y.bs.pe_ttm.t",         # PE-TTM
    "y.bs.pb.t",             # PB
    "y.bs.ps_ttm.t",         # PS-TTM
    "y.bs.mc.t",             # 市值
    "y.bs.tl_ta_r.t",        # 资产负债率
    "y.bs.dyr.t",            # 股息率
]
_PEER_METRICS_HK = [
    "y.ps.oi.t", "y.ps.npatoshopc.t", "y.ps.gp_m.t",
    "y.bs.pe_ttm.t", "y.bs.pb.t", "y.bs.ps_ttm.t", "y.bs.mc.t",
    "y.bs.tl_ta_r.t", "y.bs.dyr.t",
]


def fetch_bulk_peers(stock_codes: list[str], market: str = "cn") -> dict | None:
    """批量获取同行股票最新指标。

    Args:
        stock_codes: 股票代码列表 (≤100)
        market: "cn" | "hk"

    Returns:
        {"000858": {"y.bs.pe_ttm.t": 25.3, "y.ps.wroe.t": 30.5, ...}, ...}
    """
    if len(stock_codes) > 100:
        stock_codes = stock_codes[:100]

    token = _token()
    endpoint = "{}/{}/company/fs/non_financial".format(LIXINGER_BASE, market)
    metrics = _PEER_METRICS_HK if market == "hk" else _PEER_METRICS

    body = {
        "token": token,
        "stockCodes": stock_codes,
        "date": "latest",
        "metricsList": metrics,
    }

    cache_key = "peers__{}__{}__{}".format(market, "_".join(sorted(stock_codes[:5])), len(stock_codes))
    raw = _cached(cache_key, lambda: _do_fetch(endpoint, body), ttl=12 * 60 * 60)
    if not raw or not raw.get("_raw"):
        return None

    # Group latest values by stock code
    out: dict[str, dict] = {}
    for row in raw["_raw"]:
        sc = row.get("stockCode", "")
        if not sc:
            continue
        # Flatten metrics for this single row
        flat: dict[str, float | None] = {}
        _flatten_one(row, flat)
        out[sc] = flat
    return out


def _flatten_one(obj: dict, out: dict[str, float | None], prefix: list | None = None):
    """Flatten a single response row into a flat dict (non-list version)."""
    if prefix is None:
        prefix = []
    if not isinstance(obj, dict):
        return
    for k, v in obj.items():
        if k in ("date", "stockCode", "reportDate", "standardDate",
                 "reportType", "currency", "auditOpinionType"):
            continue
        if isinstance(v, dict):
            # Check if it's a leaf with expressionCalculateType
            sub_keys = set(v.keys())
            known_types = {"t", "ttm", "c", "t_r", "t_y2y", "t_c2c",
                           "c_r", "c_y2y", "c_c2c", "c_2y",
                           "ttm_y2y", "ttm_c2c"}
            if sub_keys & known_types:
                for eksp, raw_val in v.items():
                    full_key = ".".join(prefix + [k, eksp])
                    try:
                        out[full_key] = float(raw_val) if raw_val is not None else None
                    except (ValueError, TypeError):
                        out[full_key] = None
            else:
                _flatten_one(v, out, prefix + [k])
        else:
            full_key = ".".join(prefix + [k])
            try:
                out[full_key] = float(v) if v is not None else None
            except (ValueError, TypeError):
                out[full_key] = None


def fetch_company_info(stock_code: str, market: str = "cn") -> dict | None:
    """获取公司基础信息（名称/交易所/上市日期/融资融券/陆股通标志）。"""
    token = _token()
    endpoint = "{}/{}/company".format(LIXINGER_BASE, market)

    body = {
        "token": token,
        "stockCodes": [stock_code],
        "pageIndex": 0,
    }

    cache_key = "company__{}__{}".format(market, stock_code)
    return _cached(cache_key, lambda: _do_fetch(endpoint, body), ttl=7 * 24 * 60 * 60)


def fetch_industries(stock_code: str, market: str = "cn") -> str | None:
    """获取股票所属行业名称（申万/中信分类）。

    POST /api/cn/company/industries · 返回如 "石油石化" / "食品饮料"
    缓存 7 天（行业分类极少变动）。
    """
    endpoint = f"{LIXINGER_BASE}/{market}/company/industries"
    body = {"token": _token(), "stockCode": stock_code}
    cache_key = f"industries__{market}__{stock_code}"
    rows = _cached(cache_key, lambda: _do_simple_fetch(endpoint, body),
                   ttl=7 * 24 * 60 * 60)
    if rows:
        return (rows[0] or {}).get("name")
    return None


# ── internal ───────────────────────────────────────────────────────
def _do_fetch(endpoint: str, body: dict) -> dict | None:
    """Execute POST, parse nested response rows into flat indexed structure.

    理杏仁 API 返回嵌套结构:
      {"y": {"ps": {"oi": {"t": 168838102515}, ...}, "bs": {...}, "m": {...}}}
    本函数将其展平为:
      {"y.ps.oi.t": [1688.38, ...], ...}
    """
    resp = _post(endpoint, body)
    if not resp:
        return None

    rows = resp.get("data", [])
    if not rows:
        return None

    dates = []
    metrics: dict[str, list] = {}
    raw_rows = []

    for row in rows:
        d = row.get("date", "")[:10]
        dates.append(d)
        raw_rows.append(row)

        # Track which keys already have values at current row count
        filled_before = {k: len(v) for k, v in metrics.items()}

        # Recursively flatten nested dict
        _flatten_into(row, metrics, prefix=[])

        # Fill None for any metric key NOT present in this row
        n = len(dates)
        for k in metrics:
            if len(metrics[k]) < n:
                metrics[k].append(None)

    return {
        "stockCode": rows[0].get("stockCode", body["stockCodes"][0]) if rows else body["stockCodes"][0],
        "dates": dates,
        "metrics": metrics,
        "_raw": raw_rows,
    }


def _flatten_into(obj: dict, out: dict[str, list], prefix: list):
    """Recursively flatten a nested dict into flat keys like 'y.ps.oi.t'.

    Leaf structure: {"t": 19.1564} or {"ttm": 30.5}
    Produces keys: 'y.bs.pe_ttm.t', 'y.m.wroe.ttm', etc.
    """
    if not isinstance(obj, dict):
        return
    for k, v in obj.items():
        if isinstance(v, dict) and not _is_leaf_metric(k, v):
            _flatten_into(v, out, prefix + [k])
        elif isinstance(v, dict) and _is_leaf_metric(k, v):
            # Leaf with expressionCalculateType: {"t": 19.1564}
            for eksp, raw_val in v.items():
                full_key = ".".join(prefix + [k, eksp])  # e.g. y.bs.pe_ttm.t
                if full_key not in out:
                    out[full_key] = []
                try:
                    out[full_key].append(float(raw_val) if raw_val is not None else None)
                except (ValueError, TypeError):
                    out[full_key].append(None)
        else:
            # Bare scalar value
            full_key = ".".join(prefix + [k])
            if full_key not in out:
                out[full_key] = []
            try:
                out[full_key].append(float(v) if v is not None else None)
            except (ValueError, TypeError):
                out[full_key].append(None)


def _is_leaf_metric(key: str, val) -> bool:
    """判断是否为指标叶子节点: expressionCalculateType 级别 (t, ttm, c_y2y 等)。"""
    if not isinstance(val, (int, float)):
        # 如果值是 dict 且 key 是 expressionCalculateType，则它是叶子
        if isinstance(val, dict):
            sub_keys = set(val.keys())
            known_types = {"t", "ttm", "c", "t_r", "t_y2y", "t_c2c",
                           "c_r", "c_y2y", "c_c2c", "c_2y",
                           "ttm_y2y", "ttm_c2c"}
            if sub_keys & known_types:
                return True
        return False
    return True


def _extract_metric_value(key: str, val) -> float | None:
    """从叶子节点提取数值。

    val 可能是:
      - 直接的数值: 168838102515
      - dict: {"t": 168838102515}
      - dict with ttm: {"ttm": 0.3253}
    """
    if isinstance(val, (int, float)):
        try:
            return float(val)
        except (ValueError, TypeError):
            return None
    if isinstance(val, dict):
        # Prefer: t > ttm > c > first value
        for preferred in ("t", "ttm", "c"):
            if preferred in val:
                try:
                    return float(val[preferred])
                except (ValueError, TypeError):
                    pass
        # Fallback: take first numeric value
        for v in val.values():
            try:
                return float(v)
            except (ValueError, TypeError):
                continue
    return None


# ── 工具函数 ──────────────────────────────────────────────────────
def to_float(v, default: float = 0.0) -> float:
    """安全转 float：None/空串/异常 → default."""
    try:
        if v is None:
            return default
        if isinstance(v, str):
            v = v.strip().replace(",", "")
            if v in ("", "--", "-", "N/A", "null"):
                return default
        return float(v)
    except (ValueError, TypeError):
        return default


def latest(series: list, default=None):
    """取列表最后一个非 None 值。"""
    for v in reversed(series):
        if v is not None:
            return v
    return default


def to_yi(v) -> float:
    """原始数值（通常是元）转亿。"""
    return round(to_float(v) / 1e8, 2)


def fetch_block_deals(stock_code: str, start_date: str = "2025-01-01",
                      end_date: str = "2026-12-31", limit: int = 50) -> list[dict]:
    """获取单只股票大宗交易数据 (v2.16 · 替代 akshare 全A批量拉取).

    Args:
        stock_code: 股票代码，如 "601336"
        start_date: YYYY-MM-DD
        end_date: YYYY-MM-DD
        limit: 返回条数上限

    Returns:
        [{"date": "2025-08-29", "tradingPrice": 64.69, "tradingAmount": 4819400,
          "tradingVolume": 74500, "buyBranch": "...", "sellBranch": "...",
          "discountRate": 0.052, "stockCode": "601336"}, ...]
    """
    token = _token()
    endpoint = f"{LIXINGER_BASE}/cn/company/block-deal"
    body = {
        "token": token,
        "stockCode": stock_code,
        "startDate": start_date,
        "endDate": end_date,
        "limit": limit,
    }

    cache_key = f"block_deal__{stock_code}__{start_date}_{end_date}"
    return _cached(cache_key, lambda: _do_block_deal_fetch(endpoint, body),
                   ttl=24 * 60 * 60) or []


def fetch_restricted_release(stock_codes: list[str]) -> list[dict]:
    """获取限售解禁热度数据 (v2.16 · 替代 akshare 全 A 解禁日历).

    Args:
        stock_codes: 股票代码列表 (1-100)

    Returns:
        [{"stockCode": "601336", "last_data_date": "...", "srl_last": ...,
          "srl_cap_r_last": ..., "elr_s_y1": ..., "elr_s_cap_r_y1": ...,
          "elr_mc_y1": ...}, ...]
    """
    token = _token()
    endpoint = f"{LIXINGER_BASE}/cn/company/hot/elr"
    body = {"token": token, "stockCodes": stock_codes}
    cache_key = f"hot_elr__{'_'.join(stock_codes[:5])}"
    return _cached(cache_key, lambda: _do_simple_fetch(endpoint, body),
                   ttl=24 * 60 * 60) or []


def fetch_margin_trading(stock_codes: list[str]) -> list[dict]:
    """获取融资融券热度数据 (v2.16 · 替代 akshare 全市场融资明细).

    Args:
        stock_codes: 股票代码列表 (1-100)

    Returns:
        [{"stockCode": "601336", "last_data_date": "...", "spc": ...,
          "mtaslb_fb": ..., "mtaslb_sb": ..., "mtaslb": ...,
          "mtaslb_mc_r": ..., "mtaslb_fbc": ..., "mtaslb_smc": ...,
          "npa_o_f_d1/5/20/60/120/240": ..., ...}, ...]
    """
    token = _token()
    endpoint = f"{LIXINGER_BASE}/cn/company/hot/mtasl"
    body = {"token": token, "stockCodes": stock_codes}
    cache_key = f"hot_mtasl__{'_'.join(stock_codes[:5])}"
    return _cached(cache_key, lambda: _do_simple_fetch(endpoint, body),
                   ttl=24 * 60 * 60) or []


def _do_simple_fetch(endpoint: str, body: dict) -> list[dict]:
    """Execute simple POST (no flattening needed) and return data rows."""
    resp = _post(endpoint, body)
    if not resp:
        return []
    return resp.get("data", [])


def fetch_lhb_records(stock_code: str, start_date: str = "2025-01-01",
                      end_date: str = "2026-12-31", limit: int = 50) -> list[dict]:
    """获取单只股票龙虎榜记录 (v2.16 · 替代 akshare 全市场龙虎榜统计).

    Returns:
        [{"date": "...", "reasonForDisclosure": "...",
          "buyList": [{"branchName": "...", "buyAmount": ..., "sellAmount": ...}],
          "sellList": [...], "institutionBuyAmount": ..., "institutionSellAmount": ...,
          "institutionNetPurchaseAmount": ..., "totalPurchaseAmount": ...,
          "totalSellAmount": ..., "totalNetPurchaseAmount": ...}, ...]
    """
    token = _token()
    endpoint = f"{LIXINGER_BASE}/cn/company/trading-abnormal"
    body = {
        "token": token, "stockCode": stock_code,
        "startDate": start_date, "endDate": end_date, "limit": limit,
    }
    cache_key = f"lhb__{stock_code}__{start_date}_{end_date}"
    return _cached(cache_key, lambda: _do_simple_fetch(endpoint, body),
                   ttl=24 * 60 * 60) or []


def fetch_fund_shareholders(stock_code: str, start_date: str = "2024-01-01",
                            end_date: str = "2026-12-31", limit: int = 50) -> list[dict]:
    """获取公募基金持股明细 (v2.16 · 替代 akshare 全市场基金持仓批量).

    Returns:
        [{"date": "2026-03-31", "fundCode": "...", "name": "招商中证白酒指数A",
          "holdings": 40257055, "marketCap": ..., "marketCapRank": ...,
          "netValueRatio": 0.1432, "outstandingSharesA": ...,
          "proportionOfCapitalization": ...}, ...]
    """
    token = _token()
    endpoint = f"{LIXINGER_BASE}/cn/company/fund-shareholders"
    body = {
        "token": token, "stockCode": stock_code,
        "startDate": start_date, "endDate": end_date, "limit": limit,
    }
    cache_key = f"fund_sh__{stock_code}__{start_date}_{end_date}"
    return _cached(cache_key, lambda: _do_simple_fetch(endpoint, body),
                   ttl=24 * 60 * 60) or []


def fetch_shareholders_num(stock_code: str, start_date: str = "2023-01-01",
                           end_date: str = "2026-12-31", limit: int = 20) -> list[dict]:
    """获取股东人数历史 (v2.16 · 替代 akshare 全市场股东户数批量 — 842 tqdm 终结者).

    Returns:
        [{"date": "2023-12-31", "total": 85775,
          "shareholdersNumberChangeRate": 0.0995, "spc": -0.1548}, ...]
    """
    token = _token()
    endpoint = f"{LIXINGER_BASE}/cn/company/shareholders-num"
    body = {
        "token": token, "stockCode": stock_code,
        "startDate": start_date, "endDate": end_date, "limit": limit,
    }
    cache_key = f"sh_num__{stock_code}__{start_date}_{end_date}"
    return _cached(cache_key, lambda: _do_simple_fetch(endpoint, body),
                   ttl=24 * 60 * 60) or []


def _do_block_deal_fetch(endpoint: str, body: dict) -> list[dict]:
    """Execute block-deal POST and normalize dates to YYYY-MM-DD."""
    resp = _post(endpoint, body)
    if not resp:
        return []
    rows = resp.get("data", [])
    out = []
    for r in rows:
        d = r.get("date", "")
        if isinstance(d, str) and "T" in d:
            d = d[:10]
        out.append({
            "date": d,
            "stockCode": r.get("stockCode", ""),
            "tradingPrice": r.get("tradingPrice"),
            "tradingAmount": r.get("tradingAmount"),
            "tradingVolume": r.get("tradingVolume"),
            "buyBranch": r.get("buyBranch", ""),
            "sellBranch": r.get("sellBranch", ""),
            "discountRate": r.get("discountRate"),
        })
    return out
