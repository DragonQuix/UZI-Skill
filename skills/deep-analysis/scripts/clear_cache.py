#!/usr/bin/env python3
"""Clear cached data for one or all stocks.

Usage:
    python clear_cache.py 00700.HK              # Clear all cache for 00700.HK
    python clear_cache.py 00700.HK --keep-agent  # Keep agent_analysis.json
    python clear_cache.py 00700.HK --dry-run     # Preview without deleting
    python clear_cache.py --all                  # Nuclear: clear everything
    python clear_cache.py --all --dry-run        # Preview nuclear
    python clear_cache.py --list                 # Show all cached tickers

Cache layers affected per ticker:
    1. .cache/{ticker}/         — raw_data, dimensions, panel, agent_analysis, api_cache
    2. .cache/lixinger/*        — Lixinger API cached responses for this stock
    3. reports/{ticker}_*/      — generated HTML reports (kept by default)

After clearing, re-run:
    python -c "from run_real_test import stage1; stage1('{ticker}')"
    # then agent writes agent_analysis.json
    python -c "from run_real_test import stage2; stage2('{ticker}')"
"""
import argparse
import io
import json
import os
import sys
from pathlib import Path

# Force UTF-8 on Windows GBK terminals
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from lib.cache import clear_ticker_cache, clear_all_cache, list_cached_tickers


def _print_result(r: dict) -> None:
    """Pretty-print a clear operation result."""
    if r.get("tickers"):
        # bulk result
        print(f"  已清除 {len(r['tickers'])} 只股票缓存")
        print(f"  释放空间: {r['total_freed_mb']} MB")
        return

    print(f"\n  Ticker: {r['ticker']}")
    dirs = r.get("deleted_dirs", [])
    files = r.get("deleted_files", [])
    kept = r.get("kept_files", [])

    for d in dirs:
        src = d.get("source", "cache")
        print(f"  X 目录 [{src}]: {d['path']} ({d['size'] / 1024:.0f} KB)")
    for f in files:
        src = f.get("source", "cache")
        print(f"  X 文件 [{src}]: {f['path']} ({f['size'] / 1024:.0f} KB)")
    for k in kept:
        print(f"  V 保留: {k}")

    total = len(dirs) + len(files)
    if total == 0:
        print(f"  [!] 未找到 {r['ticker']} 的缓存（可能已被清除或从未运行）")
    else:
        print(f"  --")
        print(f"  共删除 {len(dirs)} 个目录 + {len(files)} 个文件")
        print(f"  释放: {r['freed_mb']} MB")
        if kept:
            print(f"  保留: {len(kept)} 个文件")


def _print_list(tickers: list[dict]) -> None:
    """Pretty-print cached ticker list."""
    if not tickers:
        print("  没有缓存数据")
        return

    total_mb = sum(t["size_mb"] for t in tickers)
    print(f"\n  {'Ticker':<30} {'大小':>8}  {'文件':<20}")
    print(f"  {'─' * 30} {'─' * 8}  {'─' * 20}")
    for t in tickers:
        arts = ", ".join(t["artifacts"][:3])
        if len(t["artifacts"]) > 3:
            arts += f" +{len(t['artifacts']) - 3} more"
        print(f"  {t['ticker']:<30} {t['size_mb']:>5.1f} MB  {arts}")
    print(f"  {'─' * 30} {'─' * 8}")
    print(f"  共 {len(tickers)} 项 · 总计 {total_mb:.1f} MB")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="清除股票缓存数据",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "ticker",
        nargs="?",
        help="股票代码，如 00700.HK / 600519.SH",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="清除所有股票的全部缓存（核选项）",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="列出所有已缓存的股票",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅预览，不实际删除",
    )
    parser.add_argument(
        "--keep-reports",
        action="store_true",
        default=True,
        help="保留已生成的 HTML 报告（默认）",
    )
    parser.add_argument(
        "--rm-reports",
        action="store_true",
        help="同时删除 HTML 报告",
    )
    parser.add_argument(
        "--keep-agent",
        action="store_true",
        help="保留 agent_analysis.json（昂贵的人工分析产物）",
    )
    parser.add_argument(
        "--yes", "-y",
        action="store_true",
        help="跳过确认提示",
    )

    args = parser.parse_args()

    # --list mode
    if args.list:
        tickers = list_cached_tickers()
        _print_list(tickers)
        return

    # --all mode
    if args.all:
        if args.dry_run:
            print("[预览] 预览模式 — 以下内容将被清除:\n")
            r = clear_all_cache(keep_reports=not args.rm_reports, dry_run=True)
            tickers_list = list_cached_tickers()
            _print_list(tickers_list)
            print(f"\n  预计释放: {r['total_freed_mb']} MB")
            return

        if not args.yes:
            tickers_list = list_cached_tickers()
            _print_list(tickers_list)
            print(f"\n  [!] 将清除以上所有缓存数据！")
            resp = input("  确认? [y/N] ").strip().lower()
            if resp not in ("y", "yes"):
                print("  已取消")
                return

        r = clear_all_cache(keep_reports=not args.rm_reports, dry_run=False)
        print(f"\n  已清除所有缓存 · 释放 {r['total_freed_mb']} MB")
        return

    # Single ticker mode
    if not args.ticker:
        parser.print_help()
        print("\n  示例: python clear_cache.py 00700.HK")
        print("        python clear_cache.py --list")
        print("        python clear_cache.py --all --dry-run")
        sys.exit(1)

    ticker = args.ticker.upper().strip()

    if args.dry_run:
        print(f"[预览] 预览模式 — {ticker} 的以下缓存将被清除:\n")
        r = clear_ticker_cache(
            ticker,
            keep_reports=not args.rm_reports,
            keep_agent=args.keep_agent,
            dry_run=True,
        )
        _print_result(r)
        return

    # Confirmation
    r = clear_ticker_cache(
        ticker,
        keep_reports=not args.rm_reports,
        keep_agent=args.keep_agent,
        dry_run=True,
    )
    total_items = len(r.get("deleted_dirs", [])) + len(r.get("deleted_files", []))
    if total_items == 0:
        print(f"  [!] 未找到 {ticker} 的缓存")
        return

    if not args.yes:
        print(f"\n  将清除 {ticker} 的 {total_items} 项缓存（{r['freed_mb']} MB）")
        kept = r.get("kept_files", [])
        if kept:
            print(f"  保留: {len(kept)} 个文件")
        resp = input("  确认? [y/N] ").strip().lower()
        if resp not in ("y", "yes"):
            print("  已取消")
            return

    r = clear_ticker_cache(
        ticker,
        keep_reports=not args.rm_reports,
        keep_agent=args.keep_agent,
        dry_run=False,
    )
    _print_result(r)

    print(f"\n  重跑命令:")
    print(f"    python -c \"from run_real_test import stage1; stage1('{ticker}')\"")
    print(f"    # agent 写 agent_analysis.json")
    print(f"    python -c \"from run_real_test import stage2; stage2('{ticker}')\"")


if __name__ == "__main__":
    main()
