"""全量行业字典构建器 · 理杏仁 API → industry_peers.py.

数据源:
  - POST /api/{cn|hk}/company?pageIndex=N       → 全量股票代码+名称 (不分股票码)
  - POST /api/{cn|hk}/company/industries          → 每只股票的申万行业 (单只调用)

API 限制: 1000 次/分钟 → 本工具限流 900 次/分钟 (留 10% 安全边际)

运行:
  python build_industry_peers.py                  # 全量构建 (首次 ~9min)
  python build_industry_peers.py --incremental    # 增量更新 (只查新代码，秒级)
  python build_industry_peers.py --market cn      # 仅 A 股
  python build_industry_peers.py --dry-run        # 只对比差异不写文件
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib.lixinger_client import (
    _post,
    _token,
    LIXINGER_BASE,
    _cache_path,
    fetch_industries,
)

PAGE_SIZE_HINT = 500        # 实测 API 每页 500 条
MAX_WORKERS = 10            # 并发线程
RATE_LIMIT_PER_MIN = 900    # 留 10% 安全边际，API 上限 1000/min


# ═══════════════════════════════════════════════════════════════
# 速率限制器 · 线程安全 · 滑动窗口
# ═══════════════════════════════════════════════════════════════

class RateLimiter:
    """线程安全的令牌桶式速率限制器。"""
    def __init__(self, max_per_minute: int):
        self._min_interval = 60.0 / max_per_minute
        self._last = 0.0
        self._lock = threading.Lock()

    def acquire(self):
        with self._lock:
            now = time.time()
            wait = self._last + self._min_interval - now
            if wait > 0:
                time.sleep(wait)
            self._last = time.time()


# ═══════════════════════════════════════════════════════════════
# Step 1 · 全量股票列表
# ═══════════════════════════════════════════════════════════════

def list_all_stocks(market: str) -> list[tuple[str, str]]:
    """分页获取所有正常上市的股票 (代码, 名称)。

    不传 stockCodes → API 返回全量，按 pageIndex 翻页。
    """
    endpoint = f"{LIXINGER_BASE}/{market}/company"
    all_stocks: list[tuple[str, str]] = []
    page = 0

    print(f"[{market.upper()}] 分页获取全量股票列表 ...", flush=True)
    while True:
        body = {"token": _token(), "pageIndex": page}
        resp = _post(endpoint, body)
        if not resp or not resp.get("data"):
            break

        rows = resp["data"]
        for r in rows:
            status = r.get("listingStatus", "")
            if status in ("normally_listed", "special_treatment", "delisting_risk_warning"):
                code = r.get("stockCode", "").strip()
                name = r.get("name", "").strip()
                if code and name:
                    all_stocks.append((code, name))

        total = resp.get("total", 0)
        print(f"  page {page}: {len(rows)} rows, accumulated {len(all_stocks)}/{total}",
              flush=True)

        if len(rows) == 0 or len(all_stocks) >= total:
            break
        page += 1

    print(f"[{market.upper()}] 共获取 {len(all_stocks)} 只正常上市股票", flush=True)
    return all_stocks


# ═══════════════════════════════════════════════════════════════
# Step 2 · 并行查询行业 (带速率控制)
# ═══════════════════════════════════════════════════════════════

def build_industry_map(stocks: list[tuple[str, str]], market: str,
                       skip_cache_hit: bool = False) -> dict[str, list[tuple[str, str]]]:
    """并行查行业 → 按行业分组。

    fetch_industries() 自带 7 天缓存，二次跑几乎全部命中。

    Args:
        stocks: [(code, name), ...]
        market: "cn" | "hk"
        skip_cache_hit: True = 先读缓存文件，跳过已有行业数据的股票

    Returns:
        {"白酒": [("600519", "贵州茅台"), ...], ...}
    """
    # —— 预扫描：分离已缓存和待查询 ——
    cached_results: dict[str, str | None] = {}  # code → industry_name (None = API 返回空)
    uncached: list[tuple[str, str]] = []

    for code, name in stocks:
        cache_key = f"industries__{market}__{code}"
        cache_file = _cache_path(cache_key)
        hit = False
        if cache_file.exists():
            try:
                cached = json.loads(cache_file.read_text(encoding="utf-8"))
                age = time.time() - cached.get("_cached_at", 0)
                if age < 7 * 24 * 60 * 60:
                    rows = cached.get("data", [])
                    if rows and isinstance(rows[0], dict):
                        cached_results[code] = (rows[0] or {}).get("name")
                    else:
                        cached_results[code] = None  # API 曾返回空
                    hit = True
            except (json.JSONDecodeError, KeyError):
                pass
        if not hit:
            uncached.append((code, name))

    total = len(stocks)
    done_count = len(cached_results)
    api_calls = 0
    lock = threading.Lock()
    limiter = RateLimiter(RATE_LIMIT_PER_MIN)
    t_start = time.time()

    print(f"  {'增量模式: ' if skip_cache_hit else ''}"
          f"缓存命中 {len(cached_results)} · 待查询 {len(uncached)}",
          flush=True)

    if not uncached:
        print("  所有股票已缓存，无需 API 调用", flush=True)
    else:
        def _fetch_one(code: str) -> tuple[str, str | None]:
            """线程 worker: 速率限制 → API 调用 → 返回 (code, industry_name)."""
            limiter.acquire()
            ind = fetch_industries(code, market)
            return (code, ind)

        codes_only = [c for c, _ in uncached]
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(_fetch_one, c): c for c in codes_only}
            for future in as_completed(futures):
                code, ind_name = future.result()
                with lock:
                    api_calls += 1
                    done_count += 1
                    cached_results[code] = ind_name
                    if done_count % 200 == 0 or done_count == total:
                        _progress(done_count, total, api_calls, t_start)

    # 组装
    industry_map: dict[str, list[tuple[str, str]]] = {}
    for code, name in stocks:
        ind_name = cached_results.get(code)
        if ind_name:
            industry_map.setdefault(ind_name, []).append((code, name))

    print()
    return industry_map


def _progress(done: int, total: int, api_calls: int, t_start: float):
    elapsed = time.time() - t_start
    rate = done / elapsed if elapsed > 0 else 0
    eta = (total - done) / rate if rate > 0 else 0
    print(f"\r  {done}/{total} ({done*100//total}%) · API {api_calls} 次 · "
          f"{elapsed:.0f}s · ETA {eta:.0f}s", end="", flush=True)


# ═══════════════════════════════════════════════════════════════
# Step 3 · 输出
# ═══════════════════════════════════════════════════════════════

def render_py(industry_map: dict[str, list[tuple[str, str]]]) -> str:
    """将行业字典渲染为 Python 模块文本，可直接覆盖 lib/industry_peers.py。"""
    sorted_items = sorted(industry_map.items(), key=lambda kv: len(kv[1]), reverse=True)
    total_stocks = sum(len(v) for v in industry_map.values())

    lines = [
        '"""共享行业同行股票代码字典 — 理杏仁全量构建。',
        '',
        f'自动生成于: {time.strftime("%Y-%m-%d %H:%M:%S")}',
        f'覆盖: {len(industry_map)} 个行业 · {total_stocks} 只股票',
        '',
        '来源: 理杏仁 /api/{cn|hk}/company + /api/{cn|hk}/company/industries',
        '分类体系: 申万 (sw) — 每只股票取 industries 接口第一条记录',
        '',
        '更新方式: python build_industry_peers.py --incremental',
        '',
        'Used by:',
        '- fetch_peers.py: 当 akshare EastMoney 板块接口失败时作为 fallback',
        '- fetch_similar_stocks.py: 同业相似股推荐的主数据源',
        '',
        'Format: dict[str, list[tuple[str, str]]]  # 行业 → [(代码, 名称), ...]',
        '"""',
        '',
        'INDUSTRY_PEERS: dict[str, list[tuple[str, str]]] = {',
    ]

    for industry, stocks in sorted_items:
        stock_lines = [f'        ("{c}", "{n}"),' for c, n in stocks]
        block = f'    "{industry}": [\n' + "\n".join(stock_lines) + "\n    ],"
        lines.append(block)

    lines.append("}")
    lines.append("")
    lines.append("")
    lines.append("def get_peer_codes(industry: str) -> list[str]:")
    lines.append('    """为指定行业返回纯股票代码列表（用于 fetch_peers fallback）。"""')
    lines.append("    peers = INDUSTRY_PEERS.get(industry)")
    lines.append("    if not peers:")
    lines.append("        return []")
    lines.append("    return [code for code, _ in peers]")
    lines.append("")
    lines.append("")
    lines.append("def get_peer_codes_with_names(industry: str) -> list[tuple[str, str]]:")
    lines.append('    """为指定行业返回 (代码, 名称) 元组列表（用于 fetch_similar_stocks）。"""')
    lines.append("    return INDUSTRY_PEERS.get(industry, [])")
    lines.append("")

    return "\n".join(lines)


def check_diff_stats(new_map: dict, old_path: Path) -> dict:
    """对比新旧字典。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location("old_peers", old_path)
    old_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old_mod)
    old_map = old_mod.INDUSTRY_PEERS

    old_industries = set(old_map.keys())
    new_industries = set(new_map.keys())

    return {
        "old_industries": len(old_industries),
        "new_industries": len(new_industries),
        "added": sorted(new_industries - old_industries),
        "removed": sorted(old_industries - new_industries),
        "old_stocks": sum(len(v) for v in old_map.values()),
        "new_stocks": sum(len(v) for v in new_map.values()),
    }


# ═══════════════════════════════════════════════════════════════
# main
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="全量行业字典构建器 · 理杏仁 API")
    parser.add_argument("--market", choices=["cn", "hk", "all"], default="all")
    parser.add_argument("--output", type=str, default=None,
                        help="输出路径 (默认覆盖 lib/industry_peers.py)")
    parser.add_argument("--incremental", action="store_true",
                        help="增量模式: 先从缓存文件读取，只对缓存未命中股票调 API")
    parser.add_argument("--dry-run", action="store_true",
                        help="对比模式: 只显示新旧差异，不写文件")
    args = parser.parse_args()

    token = os.environ.get("LIXINGER_TOKEN", "").strip()
    if not token:
        print("LIXINGER_TOKEN 未设置", file=sys.stderr)
        sys.exit(1)

    print(f"速率限制: {RATE_LIMIT_PER_MIN}/min · 线程: {MAX_WORKERS}", flush=True)

    markets = ["cn", "hk"] if args.market == "all" else [args.market]
    combined: dict[str, list[tuple[str, str]]] = {}

    for mkt in markets:
        stocks = list_all_stocks(mkt)
        if not stocks:
            print(f"[{mkt.upper()}] 未获取到股票列表，跳过", flush=True)
            continue

        print(f"\n[{mkt.upper()}] 查询行业分类 ({len(stocks)} 只) ...", flush=True)
        ind_map = build_industry_map(stocks, mkt, skip_cache_hit=args.incremental)

        # 港股行业名加后缀避免与 A 股同名行业混淆
        if mkt == "hk":
            ind_map = {f"{k}·HK": v for k, v in ind_map.items()}

        for ind, stock_list in ind_map.items():
            combined.setdefault(ind, []).extend(stock_list)

        n = sum(len(v) for v in ind_map.values())
        print(f"[{mkt.upper()}] {len(ind_map)} 个行业 · {n} 只股票分类完成", flush=True)

    if not combined:
        print("未构建任何行业数据", file=sys.stderr)
        sys.exit(1)

    output_path = Path(args.output) if args.output else (HERE / "lib" / "industry_peers.py")

    if args.dry_run:
        if output_path.exists():
            diff = check_diff_stats(combined, output_path)
            print(f"\n差异对比 (旧 -> 新):")
            print(f"  行业: {diff['old_industries']} -> {diff['new_industries']}")
            print(f"  股票: {diff['old_stocks']} -> {diff['new_stocks']}")
            if diff["added"]:
                print(f"  新增行业: {diff['added']}")
            if diff["removed"]:
                print(f"  移除行业: {diff['removed']}")
        else:
            print(f"\n新文件: {len(combined)} 个行业 · "
                  f"{sum(len(v) for v in combined.values())} 只股票")
        return

    content = render_py(combined)
    output_path.write_text(content, encoding="utf-8")
    print(f"\n已写入 {output_path} "
          f"({len(combined)} 个行业 · {sum(len(v) for v in combined.values())} 只股票)",
          flush=True)


if __name__ == "__main__":
    main()
