"""NEW Fetcher · 相似股推荐 — 硬编码同行 + 真实行情对比.

策略:
1. 按 industry 在 INDUSTRY_PEERS 里查到同行列表
2. 对每只同行股，调用 fetch_basic 拿 name/price/pe/market_cap (复用各种 fallback)
3. 如果 industry 不在硬编码表里，返回空（可后续加 stock_info_a_code_name 关键词搜索）

无需 push2 blocked 的 stock_board_industry_cons_em。
"""
from __future__ import annotations

import json
import sys

from lib import data_sources as ds
from lib.market_router import parse_ticker


from lib.industry_peers import INDUSTRY_PEERS


def _fetch_peer_basics(peers: list[tuple[str, str]], self_code: str, top_n: int) -> list[dict]:
    results = []
    for code, known_name in peers:
        if code == self_code:
            continue
        if len(results) >= top_n:
            break
        try:
            ti = parse_ticker(code)
            basic = ds.fetch_basic(ti)
            if not basic or not basic.get("price"):
                continue
            name = basic.get("name") or known_name
            results.append({
                "name": name,
                "code": ti.full,
                "price": basic.get("price"),
                "pe_ttm": basic.get("pe_ttm"),
                "pb": basic.get("pb"),
                "market_cap": basic.get("market_cap"),
                "change_pct": basic.get("change_pct"),
                "url": f"https://xueqiu.com/S/SZ{code}" if ti.full.endswith("SZ") else f"https://xueqiu.com/S/SH{code}",
            })
        except Exception:
            continue
    return results


def main(ticker: str, top_n: int = 4) -> dict:
    ti = parse_ticker(ticker)
    if ti.market != "A":
        return {"ticker": ti.full, "data": {"similar_stocks": []}, "source": "n/a", "fallback": True}

    basic = ds.fetch_basic(ti)
    industry = basic.get("industry") or ""

    # Find peers from hardcoded industry map (direct + fuzzy)
    # Guard: industry must be a non-empty string for matching
    if not industry or not isinstance(industry, str) or len(industry.strip()) < 2:
        return {
            "ticker": ti.full,
            "data": {"similar_stocks": [], "industry": industry or "未知", "_note": "行业未识别，无法匹配同行"},
            "source": "INDUSTRY_PEERS (no industry)",
            "fallback": True,
        }

    # v2.2 · 行业别名映射（XueQiu/EastMoney 返回的名称可能不同于 INDUSTRY_PEERS 的 key）
    _INDUSTRY_ALIASES = {
        "港口航运": "港口", "港口服务": "港口", "港口运输": "港口",
        "航空运输": "交通运输", "公路铁路运输": "交通运输", "铁路运输": "交通运输",
        "海运": "航运", "水上运输": "航运", "远洋运输": "航运",
        "快递物流": "物流", "仓储物流": "物流",
        "火电": "电力", "水电": "电力", "核电": "电力", "新能源发电": "电力",
        "种植业": "农业", "养殖业": "农业", "饲料": "农业", "畜禽养殖": "农业",
        "游戏": "传媒", "影视": "传媒", "广告": "传媒",
        "医疗服务": "医疗器械", "医疗设备": "医疗器械",
        "白色家电": "家电", "小家电": "家电", "厨卫电器": "家电",
        "集成电路": "半导体", "芯片": "半导体", "芯片设计": "半导体",
        "锂电池": "电池", "动力电池": "电池", "储能": "电池",
        "光伏设备": "电力设备", "风电设备": "电力设备",
        "白酒": "白酒", "啤酒": "食品饮料", "饮料": "食品饮料", "乳制品": "食品饮料",
        "黄金": "有色金属", "铜": "有色金属", "铝": "有色金属", "锂": "有色金属",
        "航空发动机": "军工", "航天": "军工", "船舶制造": "军工",
        # v2.8.4 · 申万三级行业 → INDUSTRY_PEERS key 别名映射
        # 之前"工业金属"等申万三级行业找不到 peers，similar_stocks 静默为空
        "工业金属": "有色金属", "贵金属": "有色金属", "小金属": "有色金属",
        "能源金属": "有色金属", "稀有金属": "有色金属", "金属新材料": "有色金属",
        "普钢": "钢铁", "特钢": "钢铁", "冶钢原料": "钢铁",
        "煤炭开采": "煤炭", "焦炭": "煤炭",
        "油气开采": "石油石化", "炼化及贸易": "石油石化", "油服工程": "石油石化",
        "化学原料": "化工", "化学制品": "化工", "化学纤维": "化工", "塑料": "化工",
        "橡胶": "化工", "农药": "化工", "农化制品": "化工",
        "通用设备": "电力设备", "专用设备": "电力设备",
        "光伏": "电力设备", "风电": "电力设备", "电网设备": "电力设备",
        "电子化学品": "半导体", "元件": "半导体", "光学光电子": "半导体",
        "消费电子": "半导体", "其他电子": "半导体",
        "乘用车": "汽车", "商用车": "汽车", "汽车零部件": "汽车",
        "化学制药": "医药生物", "中药": "医药生物", "生物制品": "医药生物",
    }

    # 1. 精确匹配
    peers = INDUSTRY_PEERS.get(industry, [])
    # 2. 别名映射
    if not peers:
        alias = _INDUSTRY_ALIASES.get(industry)
        if alias:
            peers = INDUSTRY_PEERS.get(alias, [])
    # 3. 子串模糊匹配
    if not peers:
        for key, val in INDUSTRY_PEERS.items():
            if len(industry) >= 2 and (key in industry or industry in key or industry[:2] in key):
                peers = val
                break

    if not peers:
        return {
            "ticker": ti.full,
            "data": {"similar_stocks": [], "industry": industry, "_note": f"行业 '{industry}' 未在同行映射表里"},
            "source": "INDUSTRY_PEERS (missing)",
            "fallback": True,
        }

    peer_basics = _fetch_peer_basics(peers, ti.code, top_n)

    # Build similar_stocks output with similarity score + reason
    similar = []
    self_pe = basic.get("pe_ttm") or 0
    for p in peer_basics:
        # Similarity = PE proximity (normalized)
        pe_sim = 0
        if self_pe and p.get("pe_ttm"):
            pe_ratio = min(self_pe, p["pe_ttm"]) / max(self_pe, p["pe_ttm"])
            pe_sim = pe_ratio * 100
        similarity_score = int(max(75, min(98, pe_sim if pe_sim > 0 else 85)))

        similar.append({
            "name": p["name"],
            "code": p["code"],
            "price": p.get("price"),
            "pe_ttm": p.get("pe_ttm"),
            "market_cap": p.get("market_cap"),
            "change_pct": p.get("change_pct"),
            "similarity": f"{similarity_score}%",
            "reason": f"同属{industry} · PE {p.get('pe_ttm', '—')} · 市值 {p.get('market_cap', '—')}",
            "url": p.get("url"),
        })

    return {
        "ticker": ti.full,
        "data": {
            "similar_stocks": similar,
            "industry": industry,
            "peers_attempted": len(peers),
        },
        "source": "INDUSTRY_PEERS + fetch_basic (XueQiu / baidu / sina)",
        "fallback": False,
    }


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1] if len(sys.argv) > 1 else "002273.SZ"), ensure_ascii=False, indent=2, default=str))
