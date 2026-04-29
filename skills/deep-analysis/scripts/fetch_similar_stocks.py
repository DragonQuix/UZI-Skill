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


from lib.industry_peers import INDUSTRY_PEERS, get_peer_codes_with_names


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

    # v3.6 · 行业别名映射 — 非理杏仁来源的行业名 → 理杏仁字典 key
    # 理杏仁名已是主路径（精确命中），此表仅兜底雪球/东财等非标准名。
    _INDUSTRY_ALIASES = {
        # 港口交通 → 交通基本设施
        "港口航运": "交通基本设施", "港口服务": "交通基本设施", "港口运输": "交通基本设施",
        "港口": "交通基本设施",
        # 航空/铁路/公路 → 陆运 / 航空运输
        "航空运输": "航空运输", "公路铁路运输": "陆运", "铁路运输": "陆运",
        "交通运输": "陆运",
        # 航运 → 水上运输
        "海运": "水上运输", "水上运输": "水上运输", "远洋运输": "水上运输",
        "航运": "水上运输",
        # 物流
        "快递物流": "物流", "仓储物流": "物流",
        # 电力 → 电力公用事业
        "火电": "电力公用事业", "水电": "电力公用事业", "核电": "电力公用事业",
        "新能源发电": "电力公用事业", "电力": "电力公用事业",
        # 农业
        "种植业": "农牧渔产品", "养殖业": "农牧渔产品", "饲料": "农牧渔产品",
        "畜禽养殖": "农牧渔产品", "农业": "农牧渔产品",
        # 传媒
        "游戏": "传媒", "影视": "传媒", "广告": "传媒",
        # 医疗
        "医疗服务": "医疗保健设备与用品", "医疗设备": "医疗保健设备与用品",
        "医疗器械": "医疗保健设备与用品", "医药生物": "医疗保健设备与用品",
        # 家电
        "白色家电": "家用电器", "小家电": "家用电器", "厨卫电器": "家用电器",
        "家电": "家用电器",
        # 半导体电子
        "集成电路": "半导体", "芯片": "半导体", "芯片设计": "半导体",
        "电子化学品": "半导体", "元件": "半导体", "光学光电子": "光电子器件",
        "消费电子": "电子元器件", "其他电子": "电子元器件",
        # 电池新能源
        "锂电池": "电气部件与设备", "动力电池": "电气部件与设备",
        "储能": "电气部件与设备", "电池": "电气部件与设备",
        # 电力设备
        "光伏设备": "电气部件与设备", "风电设备": "电气部件与设备",
        "光伏": "电气部件与设备", "风电": "电气部件与设备",
        "电网设备": "重型电气设备",
        "通用设备": "通用机械", "专用设备": "专用设备",
        "电力设备": "电气部件与设备",
        # 饮料食品
        "白酒": "饮料", "啤酒": "饮料", "饮料": "饮料",
        "乳制品": "食品", "食品饮料": "食品",
        # 有色金属
        "黄金": "有色金属", "铜": "有色金属", "铝": "有色金属", "锂": "有色金属",
        "工业金属": "有色金属", "贵金属": "有色金属", "小金属": "有色金属",
        "能源金属": "有色金属", "稀有金属": "有色金属", "金属新材料": "有色金属",
        # 钢铁
        "普钢": "黑色金属", "特钢": "黑色金属", "冶钢原料": "黑色金属",
        "钢铁": "黑色金属",
        # 煤炭
        "煤炭开采": "煤炭", "焦炭": "煤炭",
        # 石油石化
        "油气开采": "石油天然气", "炼化及贸易": "石油天然气",
        "油服工程": "能源设备与服务", "石油石化": "石油天然气",
        # 化工
        "化学原料": "化学原料", "化学制品": "化学制品", "化学纤维": "合成纤维",
        "塑料": "化学制品", "橡胶": "化学制品", "农药": "农用化工",
        "农化制品": "农用化工", "化工": "化工",
        # 军工
        "航空发动机": "航天航空", "航天": "航天航空", "船舶制造": "航天航空",
        "军工": "航天航空",
        # 汽车
        "乘用车": "汽车", "商用车": "汽车", "汽车零部件": "汽车零配件与设备",
        # 医药
        "化学制药": "制药", "中药": "中药", "生物制品": "生物科技",
        # 建筑
        "建筑装饰": "建筑与工程",
        # 房地产
        "房地产": "住宅地产开发和管理",
        # 光模块
        "光模块": "通信设备",
    }

    # v3.10 · 通过 get_peer_codes_with_names() 做集中解析（精确→别名→包含）
    # 替代旧版分散在 fetch_similar_stocks 的 _INDUSTRY_ALIASES + 手写模糊匹配
    peers = get_peer_codes_with_names(industry)
    # 2. 本地别名兜底（表中未覆盖的特殊映射）
    if not peers:
        alias = _INDUSTRY_ALIASES.get(industry)
        if alias:
            peers = get_peer_codes_with_names(alias)

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
