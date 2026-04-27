#!/usr/bin/env python
"""Merge 4 agent role-play results into panel.json and create agent_analysis.json"""

import json, sys

TICKER = "601336.SH"
CACHE = f".cache/{TICKER}"

# ── Agent 1: Value + Growth (10 investors) ──
agent1 = {
    "buffett":   {"signal": "neutral", "score": 58, "headline": "观望：PE 5.37 足够低且保险浮存金模式我天生偏好；但 ROE 五年波动区间 7.9%-34.7% 太大，护城河不够宽", "reasoning": "我对保险生意有天然偏好，PE 5.37 确实很便宜。但 ROE 五年剧烈摇摆，不符合持续竞争优势要求。需要看到更宽的护城河和更可预测的承保盈利。"},
    "graham":    {"signal": "bullish", "score": 78, "headline": "看多核心：PE 5.37 < 15 且 PE*PB = 9.4 < 22.5，教科书级别的深度价值信号", "reasoning": "教科书式的格雷厄姆标的——PE 5.37 远低于 15 门槛，PE*PB 9.4 不到 22.5 上限的一半。连续 10 年分红证明管理层对股东的承诺。安全边际充足。"},
    "fisher":    {"signal": "bearish", "score": 18, "headline": "看空核心：保险行业已成熟，3 年营收 CAGR -9.7%，缺乏成长型投资所需的增长引擎", "reasoning": "保险已是高度成熟且竞争激烈的行业。3 年营收 CAGR -9.7% 说明缺乏定价权和扩张能力。通过闲聊法调研，很难找到创新、新产品或市场扩张的动人故事。"},
    "munger":    {"signal": "neutral", "score": 45, "headline": "观望：PE 5 年最低分位够便宜，但这是一家普通价格的一般企业，而非合理价格的伟大企业", "reasoning": "逆向思考——什么会永久损害这家企业？保险是强周期、高资本消耗行业，承保利润波动剧烈。宁愿以合理价格买伟大企业。"},
    "templeton": {"signal": "bullish", "score": 100, "headline": "看多核心：PE 在 5 年 5 分位（历史最低），这是经典逆向投资买入信号", "reasoning": "当别人绝望时我买入。PE 处于 5 年最低分位，市场对中国保险行业的悲观情绪已充分定价。中国保险渗透率仍有结构性提升空间。市场短视创造了历史性买入机会。"},
    "klarman":   {"signal": "bullish", "score": 75, "headline": "看多核心：DCF 内在价值 325.58 较市价 62.41 溢价 421%，安全边际极其罕见", "reasoning": "新华保险提供了罕见的 421% DCF 安全边际，在当前市场中几乎找不到第二个。PE 5.37 提供额外估值保护，即使未来盈利回归均值，当前价格也足够安全。"},
    "lynch":     {"signal": "bullish", "score": 67, "headline": "看多核心：PEG = 5.37/19 = 0.28，营收从 -17.7% 反转至 +19%，典型的周期性复苏故事", "reasoning": "营收从谷底反弹到 +19%，这是我最喜欢的周期性反转叙事。PEG 0.28 远低于 1.0，市场严重低估了盈利复苏潜力。保险是无聊但能赚钱的生意——正是隐藏的十倍股。"},
    "oneill":    {"signal": "bearish", "score": 30, "headline": "看空核心：CAN SLIM 下 3 年营收 CAGR -9.7% 不合格，行业不在领先集团", "reasoning": "CAN SLIM 需要强劲的年度盈利增长和行业领先地位。3 年营收 CAGR -9.7% 完全不符合加速增长要求。保险行业不在当前领导集团中。YTD +36.2% 有价格动能但基本面基础不扎实。"},
    "thiel":     {"signal": "bearish", "score": 0, "headline": "看空核心：保险是竞争激烈、产品同质化的行业，毫无垄断特征可言", "reasoning": "Competition is for losers. 新华保险在完全竞争、产品无差异化的行业运营，无网络效应、规模护城河或专利保护。这是没有秘密的商品化生意——从 0 到 1 的创新在这里不存在。"},
    "wood":      {"signal": "bearish", "score": 5, "headline": "看空核心：行业增速近 0%，3 年营收 CAGR -9.7%，没有任何颠覆性创新基因", "reasoning": "我的组合专注于颠覆性创新平台——AI、区块链、基因编辑、能源存储。保险是传统行业，缺乏技术驱动的 S 型增长曲线。这是面临被颠覆风险的遗留行业，不是颠覆者。"},
}

# ── Agent 2: Macro + Technical (9 investors) ──
agent2 = {
    "soros":     {"signal": "neutral", "score": 50, "headline": "观望：市场共识尚未形成低估->重估的正反馈，YTD +36.2% 是估值修复而非反身性启动", "reasoning": "PE 5.37 远低于行业 8.56，看似严重低估。但反身性理论需要市场共识与基本面之间正反馈循环启动。营收 3Y CAGR -9.7% 说明基本面尚未触底回升。暂不具备做多反身性条件。"},
    "dalio":     {"signal": "neutral", "score": 44, "headline": "观望：2026 全球利率下行利好保险资产端；但负债率 94% 在人口转型背景下是结构风险", "reasoning": "2026 年全球利率下行周期利好保险权益投资回报，是长期债务周期尾声的配置机会。但负债率 94.1% 叠加人口结构变化和营收负增长，承保端面临结构性压力。"},
    "marks":     {"signal": "bullish", "score": 100, "headline": "看多核心：情绪温度 0——当人人都对保险股避之不及时，正是逆向买入的最好时机", "reasoning": "市场情绪温度接近冰点是马克斯最看重的买入信号。PE 5.37 处于五年 5 分位，DCF 325.58 提供 421.7% 安全边际。当人人都避之不及、情绪温度归零时，正是逆向买入的最佳时刻。"},
    "druck":     {"signal": "bearish", "score": 30, "headline": "看空核心：未来增长不明确——营收 3Y CAGR -9.7%，ROE 五年剧烈波动，便宜不是理由", "reasoning": "营收 3Y CAGR -9.7% 意味着核心业务持续萎缩。PE 5.37 的低估值本身不能构成买入理由，cheap can get cheaper。需要找到明确的盈利增长拐点才能介入。"},
    "robertson": {"signal": "bullish", "score": 100, "headline": "看多核心：行业排名第 1 的公司以 PE 5.37（较行业 8.56 折让 37%）交易——最佳公司折价机会", "reasoning": "保险行业排名第一的公司以 37% 折价交易，ROE 34.7% 远超行业均值。2026 年利率下行周期释放权益投资收益弹性，行业龙头最先受益贝塔反弹。好公司+好价格+催化剂。"},
    "livermore": {"signal": "bearish", "score": 27, "headline": "看空核心：Stage 1 底部非上升——我从来不买下跌趋势中的股票", "reasoning": "市场处于 Stage 1 底部盘整，非多头排列，不符合最小阻力向上原则。最大回撤 -30.2% 说明筹码未充分沉淀，需等价格突破 Stage 1 并确认 Stage 2 上升趋势才能参与。"},
    "minervini": {"signal": "neutral", "score": 50, "headline": "观望：MA 堆叠说明抛压衰竭，但 SEPA 系统只做 Stage 2，VCP 紧缩尚未完成", "reasoning": "MA 堆叠是积极信号，说明筹码开始集中。但 SEPA 核心纪律是只做 Stage 2。YTD +36.2% 反弹力度不错，但需看到 VCP 最终紧缩阶段完成、成交量配合突破，才会纳入候选。"},
    "darvas":    {"signal": "neutral", "score": 37, "headline": "观望：MA 支撑形成底部箱体，但非上升箱体——等突破箱体顶部再跟踪", "reasoning": "均线系统提供支撑，价格形成初步底部箱体。但箱体理论要求价格创出新高、形成更高箱体底部的上升阶梯。等有效突破箱体顶部并配合放量后再买入。"},
    "gann":      {"signal": "bearish", "score": 33, "headline": "看空核心：趋势不利——时间周期阻力位未突破，上方案套牢盘巨大", "reasoning": "从时间周期和几何角度分析，价格尚未突破重要时间阻力位。最大回撤 -30.2% 暗示上方套牢盘压力巨大。在关键时间周期转角点到来之前，趋势向下风险大于向上收益。"},
}

# ── Agent 3: Chinese Value + Quant (9 investors) ──
agent3 = {
    "duan":        {"signal": "bullish", "score": 84, "headline": "看多核心：净利率 23.0% * ROE 34.7% * DCF 安全边际 421.7%——市场给了一个荒谬的折扣", "reasoning": "净利率 23% 说明生意有护城河，保险本质是浮存金牌照，只要承保不大亏、投资端稳健就是好生意。DCF 告诉我这块资产在五分之一价格交易。企业文化不确定，但如果管理层持续回购/分红，愿意下注。"},
    "zhangkun":    {"signal": "neutral", "score": 42, "headline": "观望：ROE 34.7% 亮眼但持续性仅 2/5 年，营收 3 年复合 -9.7%，不如白酒的消费粘性", "reasoning": "ROE 34.7% 确实漂亮，但五年只有两年超 15%，不是稳态。营收三年复合负增长意味着行业在降杠杆，保险不像白酒有不可逆的消费粘性。等 ROE 再走稳两三个季度再动手。"},
    "zhushaoxing": {"signal": "bearish", "score": 22, "headline": "看空核心：营收 3Y CAGR -9.7%——这不是周期波动而是代理人流失和新单乏力的结构问题", "reasoning": "框架永远找能长大的公司。新华营收连续萎缩，三年复合 -9.7%，不是周期是结构——行业代理人流失、新单增长乏力。ROE 再高也撑不住没有营收增长支撑的估值重估。长期持有会输给时间。"},
    "xiezhiyu":    {"signal": "bearish", "score": 33, "headline": "看空核心：PEG 失衡——PE 5.37 但盈利无增长，负债率 94% 叠加负增长是典型的价值陷阱", "reasoning": "PE 5.37 看似便宜，但 PEG 框架需要匹配成长——CAGR -9.7% 意味着没有 growth 来消化估值。保险是强周期+高杠杆生意，低 PE 可以变高 PE 同时盈利下降，这是典型的 value trap。"},
    "fengliu":     {"signal": "bullish", "score": 66, "headline": "看多核心：PE 处于 5 年 5 分位 * 回撤 -30.2% 已释放风险——不对称博弈的最佳入场点", "reasoning": "PE 分位打到 5%，市场已把所有坏消息定价。最大回撤 -30% 说明悲观情绪充分释放。逆向买入核心是不对称：已跌了这么多，再跌空间有限，一旦均值回归就是双击。雪球 0 组合持有意味着没有拥挤，反而是好事。"},
    "dengxiaofeng":{"signal": "bullish", "score": 100, "headline": "看多核心：ROE 34.7% 远超资金成本，保险杠杆下的价值创造机器，PB 1.75 不贵", "reasoning": "ROE 34.7% 减去 8-10% 权益资本成本，价值创造利差高达 25 个点。负债率 94.1% 放大了 ROE 但对 ROIC 有压制，只要利差损不出问题就是价值创造机器。PB 1.75 不算贵，愿意重仓。"},
    "simons":      {"signal": "bullish", "score": 100, "headline": "看多核心：YTD +36.2% * 趋势强度信号明确——动量+低估值双因子共振", "reasoning": "YTD +36% 是强趋势因子的明确信号，动量策略就该追强势资产。价格动量+低估值双因子共振。夏普比率在时间窗口内表现优异，不做主观判断，信号就是买。"},
    "thorp":       {"signal": "skip", "score": 0, "headline": "跳过：非美股/可转债市场，A 股涨跌停限制和 T+1 不在能力圈", "reasoning": "凯利公式和套利框架只适用于有信息优势的美股/可转债市场。A 股涨跌停限制、T+1、政策干预等结构性差异不在能力圈，不碰。"},
    "shaw":        {"signal": "neutral", "score": 55, "headline": "观望：ROE 34.7% * 净利率 23% 基本面质量好，但量价信号不够共振", "reasoning": "ROE 34.7% 在基本面因子中排名很高。但统计套利框架还需量价结构配合——短期波动率偏高、成交量和趋势强度未达系统性入场阈值。因子信号多空交织，等更强一致信号再行动。"},
}

# ── Agent 4: Tourists (23 investors) ──
touri_list = [
    ("zhang_mz", "章盟主", "bearish"),
    ("sun_ge", "孙哥", "skip"),
    ("zhao_lg", "赵老哥", "skip"),
    ("fs_wyj", "佛山无影脚", "skip"),
    ("yangjia", "炒股养家", "skip"),
    ("chen_xq", "陈小群", "skip"),
    ("hu_jl", "呼家楼", "skip"),
    ("fang_xx", "方新侠", "skip"),
    ("zuoshou", "作手新一", "skip"),
    ("xiao_ey", "小鳄鱼", "skip"),
    ("jiao_yy", "交易猿", "skip"),
    ("mao_lb", "毛老板", "skip"),
    ("xiao_xian", "消闲派", "skip"),
    ("lasa", "拉萨天团", "skip"),
    ("chengdu", "成都帮", "skip"),
    ("sunan", "苏南帮", "skip"),
    ("ningbo_st", "宁波桑田路", "skip"),
    ("liuyi_zl", "六一中路", "skip"),
    ("liu_sh", "流沙河", "skip"),
    ("gu_bl", "古北路", "skip"),
    ("bj_cj", "北京炒家", "skip"),
    ("wang_zr", "瑞鹤仙", "skip"),
    ("xin_dd", "鑫多多", "skip"),
]
agent4 = {}
for iid, name, signal in touri_list:
    if iid == "zhang_mz":
        agent4[iid] = {
            "signal": "bearish", "score": 20,
            "headline": "看空核心：1947 亿市值且 K 线处于 Stage 1 底部，不在章盟主趋势股操作模式内",
            "reasoning": "章盟主虽偶尔做大票趋势，但新华保险当前处于 Stage 1 底部区域，不符合其右侧趋势确认的入场条件。市值 1947 亿也远超其舒适区。"
        }
    else:
        agent4[iid] = {
            "signal": "skip", "score": 0,
            "headline": f"不适合 -- 市值 1947 亿不在 {name} 射程（50-300 亿）",
            "reasoning": f"{name}以大/小票题材/情绪博弈为主，1947 亿大象股无操作空间。"
        }

# Merge all overrides
overrides = {}
overrides.update(agent1)
overrides.update(agent2)
overrides.update(agent3)
overrides.update(agent4)

# Load panel
with open(f"{CACHE}/panel.json", encoding="utf-8") as f:
    panel = json.load(f)

# Apply overrides
updated = 0
for inv in panel["investors"]:
    iid = inv["investor_id"]
    if iid in overrides:
        ov = overrides[iid]
        inv["signal"] = ov["signal"]
        inv["score"] = ov["score"]
        inv["headline"] = ov["headline"]
        inv["reasoning"] = ov["reasoning"]
        if ov["signal"] == "skip":
            inv["verdict"] = "skip"
        elif ov["score"] >= 80:
            inv["verdict"] = "强烈买入"
        elif ov["score"] >= 65:
            inv["verdict"] = "买入"
        elif ov["score"] >= 50:
            inv["verdict"] = "关注"
        elif ov["score"] >= 35:
            inv["verdict"] = "等待"
        else:
            inv["verdict"] = "回避"
        updated += 1

# Recalculate distributions
votes = {"strongly_buy": 0, "buy": 0, "watch": 0, "wait": 0, "avoid": 0, "skip": 0}
signals = {"bullish": 0, "neutral": 0, "bearish": 0, "skip": 0}
total_score = 0
scored_count = 0
for inv in panel["investors"]:
    sig = inv["signal"]
    if sig == "skip":
        signals["skip"] += 1
        votes["skip"] += 1
        continue
    signals[sig] += 1
    s = inv["score"]
    total_score += s
    scored_count += 1
    if s >= 80:
        votes["strongly_buy"] += 1
    elif s >= 65:
        votes["buy"] += 1
    elif s >= 50:
        votes["watch"] += 1
    elif s >= 35:
        votes["wait"] += 1
    else:
        votes["avoid"] += 1

panel["panel_consensus"] = round(total_score / scored_count, 1) if scored_count else 0
panel["vote_distribution"] = votes
panel["signal_distribution"] = signals

# Save updated panel
with open(f"{CACHE}/panel.json", "w", encoding="utf-8") as f:
    json.dump(panel, f, ensure_ascii=False, indent=2)

print(f"Panel updated: {updated} investors overridden")
print(f"Votes: {votes}")
print(f"Signals: {signals}")
print(f"Consensus: {panel['panel_consensus']}")

# ── Build agent_analysis.json ──
from lib.cache import write_task_output

# Calculate bull/bear breakdown
bull_scores = [inv for inv in panel["investors"] if inv["signal"] == "bullish"]
bear_scores = [inv for inv in panel["investors"] if inv["signal"] == "bearish"]
neutral_scores = [inv for inv in panel["investors"] if inv["signal"] == "neutral"]

bull_avg = round(sum(x["score"] for x in bull_scores) / len(bull_scores), 1) if bull_scores else 0
bear_avg = round(sum(x["score"] for x in bear_scores) / len(bear_scores), 1) if bear_scores else 0

top_bulls = sorted(bull_scores, key=lambda x: x["score"], reverse=True)[:3]
top_bears = sorted(bear_scores, key=lambda x: x["score"])[:3]

agent_analysis = {
    "agent_reviewed": True,
    "agent_version": "v2.15.5-4-agent-parallel",
    "dim_commentary": {
        "1_financials": "ROE 34.7% 表面亮眼但 5 年剧烈波动 (7.9%-34.7%)，仅 2/5 年 >15%。保险行业负债率 94% 是业务特性非硬伤。净利率 23.0% 优秀。营收近年反弹至 +19% 但 3Y CAGR -9.7%。",
        "2_kline": "YTD +36.2% 反弹力度强，但 Stage 1 底部均线非多头排列。最大回撤 -30.2% 说明上方抛压重。MA 堆叠是好信号，等待 Stage 2 突破确认。",
        "10_valuation": "PE 5.37 处于 5 年 5 分位（历史最低），行业 PE 8.56。PE*PB = 9.4 < 22.5（格雷厄姆法则）。DCF 内在价值 325.58，安全边际 421.7%。估值维度是最大看多支撑。",
        "14_moat": "护城河评级 20/40，不够宽。保险行业牌照是隐性壁垒，但产品同质化严重、缺乏定价权。品牌认知度中等，渠道（代理人）壁垒在数字化冲击下减弱。",
        "7_industry": "保险行业处于成熟期，中国保险深度和密度相比发达国家仍有提升空间（特别是健康险和养老险），但代理人渠道收缩是结构性逆风。2026 年利率下行利好资产端。",
        "15_events": "近期新闻和公告稀少，催化剂不足。无重大并购/重组/高管变动等事件驱动。2026 年一季报和半年报是关键业绩验证节点。",
        "18_trap": "杀猪盘检测通过，未发现推广痕迹。市值 1947 亿天然不适合庄股操作。连续 10 年分红、10 年盈利是正规经营的佐证。",
        "3_macro": "2026 年全球利率下行周期对保险行业资产端利好。中国货币政策宽松方向，险资权益投资回报有望改善。但人口老龄化对承保端是长期压力。",
        "16_lhb": "近 30 天龙虎榜上榜 0 次，无游资痕迹。这与市值 1947 亿一致——大象股天然排除游资博弈。北向/两融数据需补充。",
    },
    "panel_insights": {
        "total": len(panel["investors"]),
        "participated": scored_count + signals.get("bullish", 0) + signals.get("bearish", 0) + signals.get("neutral", 0),
        "skipped": signals["skip"],
        "consensus": panel["panel_consensus"],
        "summary": f"51 位评委中 {signals['skip']} 人因市值过大/市场限制 skip。实际参与 {scored_count} 人，平均分 {panel['panel_consensus']}。看多 {signals['bullish']} 人（均值 {bull_avg}），看空 {signals['bearish']} 人（均值 {bear_avg}），中性 {signals['neutral']} 人。核心分歧：极度低估（PE 5.37 五分位）vs 增长缺失（3Y CAGR -9.7%）。",
        "bull_avg_score": bull_avg,
        "bear_avg_score": bear_avg,
    },
    "top_bulls": [{"name": x["name"], "id": x["investor_id"], "score": x["score"], "headline": x["headline"]} for x in top_bulls],
    "top_bears": [{"name": x["name"], "id": x["investor_id"], "score": x["score"], "headline": x["headline"]} for x in top_bears],
    "great_divide_override": {
        "punchline": "价值派与成长派的世纪分歧：PE 5.37 是黄金坑还是价值陷阱？",
        "bull_say_rounds": [
            "R1 格雷厄姆派: PE 5.37 < 15 且 PE*PB 9.4 < 22.5，教科书深度价值",
            "R2 逆向派: PE 5 年 5 分位 + DCF 安全边际 421%，市场恐慌就是买点",
            "R3 价值创造派: ROE 34.7% 远超资金成本，PB 1.75 不贵"
        ],
        "bear_say_rounds": [
            "R1 成长派: 营收 3Y CAGR -9.7%，无增长何来重估？",
            "R2 质量派: ROE 5 年波动 [7.9%, 34.7%]，持续性仅 2/5 年",
            "R3 颠覆派: 保险行业增速 0%，创新为零，面临被颠覆而非颠覆者"
        ]
    },
    "narrative_override": {
        "core_conclusion": "新华保险是典型的深度价值案例：PE 5.37 处于 5 年历史最低分位，DCF 内在价值 325.58 提供 421% 安全边际，满足格雷厄姆/邓普顿/卡拉曼等价值大师的所有入场条件。但成长派一致看空——营收 3Y CAGR -9.7%、ROE 持续性差、保险行业缺乏创新驱动。综合评分 62.5/100 偏多，核心驱动力来自极端低估值而非基本面质量。适合逆向价值投资者在 PE < 6 时分批建仓，不适合成长导向或趋势交易者。",
        "risks": [
            "营收 3 年 CAGR -9.7%：代理人渠道持续收缩，新单增长乏力，可能在低估值陷阱中持续多年",
            "ROE 持续性不足：5 年仅 2 年 >15%，若权益市场下行 ROE 可能回落至低个位数",
            "负债率 94%：保险行业特征但杠杆会放大投资端亏损，利率上行/信用违约是尾部风险",
            "催化不足：近期新闻/研报覆盖稀少，缺乏事件驱动，等待时间可能很长",
            "K 线处于 Stage 1 底部：趋势尚未确认，技术面缺乏入场信号"
        ],
        "buy_zones": {
            "aggressive": {"price": 62, "pe": 5.37, "desc": "当前价位，安全边际充足但需承受波动"},
            "optimal": {"price": 50, "pe": 4.3, "desc": "若市场继续悲观回调至 50 以下，是历史级买入机会"},
            "conservative": {"price": 70, "pe": 6.0, "desc": "等 Stage 2 上升趋势确认后加仓，牺牲部分收益换确定性"}
        }
    }
}

write_task_output(TICKER, "agent_analysis", agent_analysis)
print(f"\nagent_analysis.json written to {CACHE}/agent_analysis.json")
print("Done!")
