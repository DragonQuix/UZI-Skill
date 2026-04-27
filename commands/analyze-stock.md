---
description: 完整深度分析一只股票（22 维数据 + 51 位大佬量化评委 + 17 种机构分析方法 + 杀猪盘检测 + Bloomberg 风格 HTML 报告）
argument-hint: "[股票名称或代码，例如 华工科技 / 002273 / AAPL / 00700.HK]"
---

# 深度分析任务

用户输入: $ARGUMENTS

## 执行流程（两段式 · 你必须在中间介入）

### 第一段 · 数据采集 + 骨架分（脚本完成）

```bash
cd <plugin_root>
pip install -r requirements.txt 2>/dev/null
cd skills/deep-analysis/scripts
python -c "from run_real_test import stage1; stage1('$ARGUMENTS')"
```

这会跑完 Task 1 → 1.5 → 2 → 3（规则引擎骨架分），输出到 `.cache/{ticker}/` 下。

### 第二段 · 你来分析（核心！不能跳过！）

Stage 1 跑完后，**你必须做以下事情**：

**0. v2.13.5 · Playwright 兜底前置（必走）**

```python
import json, os
from pathlib import Path
net = json.loads(Path(".cache/_global/network_profile.json").read_text(encoding="utf-8"))
issues = json.loads(Path(f".cache/{ticker}/_review_issues.json").read_text(encoding="utf-8"))
low_quality_dims = [
    i["dim"] for i in issues.get("issues", [])
    if i.get("category") == "data" and i.get("severity") in ("critical", "warning")
]
if low_quality_dims:
    os.environ["UZI_PLAYWRIGHT_FORCE"] = "1"
    from lib.playwright_fallback import autofill_via_playwright
    autofill_via_playwright(raw, ticker)  # 主动强制再跑一次 · 补数据
```

**1. 读取评委骨架分**

读 `.cache/{ticker}/panel.json`，看 51 人各自打了多少分。特别关注：
- Top 5 看多和 Top 5 看空分别是谁？他们的 headline 有没有说服力？
- 有多少人 skip 了？（非 A 股时游资会 skip）
- 有没有明显不合理的分数？

**2. 逐组分析（spawn 4 个并行 sub-agent）**

对每组投资者，spawn 一个 Agent：

**Agent 1 · 价值 + 成长派（10 人）**
```
你要扮演巴菲特/格雷厄姆/费雪/芒格/邓普顿/卡拉曼/林奇/欧奈尔/蒂尔/木头姐，
逐一对 {stock_name} ({ticker}) 给出判断。

公司数据：{从 raw_data.json 摘取关键数据}
规则引擎参考分：{从 panel.json 摘取这 10 人的 score/headline}
真实持仓：{巴菲特持有苹果/BYD, 段永平持有苹果/茅台/腾讯 等}

对每人输出: investor_id, signal, score(0-100), headline(引用数字), reasoning(2-3句)
你可以覆盖规则引擎的分数——你是在模拟这个人的判断，不是跑公式。
```

**Agent 2 · 宏观 + 技术派（9 人）**
**Agent 3 · 中国价投 + 量化（9 人）**
**Agent 4 · 游资（23 人）** — 非 A 股直接全部 skip

**3. 合并 agent 结果**

把 4 个 agent 返回的 {signal, score, headline, reasoning} 覆盖到 `.cache/{ticker}/panel.json` 的对应投资者上。

**4. 写 agent_analysis.json（闭环关键！）**

对关键维度（财报/估值/护城河/行业）写 1-2 句定性评语。如果需要，web search 补充信息。

把所有 agent 产出写入 `.cache/{ticker}/agent_analysis.json`：
```python
from lib.cache import write_task_output
write_task_output(ticker, "agent_analysis", {
    "agent_reviewed": True,
    "dim_commentary": { "0_basic": "...", "1_financials": "...", ... },
    "panel_insights": "整体评委观察...",
    "great_divide_override": {
        "punchline": "冲突金句",
        "bull_say_rounds": ["R1", "R2", "R3"],
        "bear_say_rounds": ["R1", "R2", "R3"]
    },
    "narrative_override": {
        "core_conclusion": "综合结论",
        "risks": ["风险1", "风险2", "风险3"],
        "buy_zones": {
            "value":      {"price": 17.50, "rationale": "DCF安全边际>50%，卡拉曼/格雷厄姆入场区"},
            "growth":     {"price": 20.00, "rationale": "PEG<1 + 营收加速拐点，林奇/欧奈尔入场区"},
            "technical":  {"price": 18.50, "rationale": "MA200支撑位 + 缩量止跌确认，利弗莫尔/米内尔维尼入场区"},
            "youzi":      {"price": 0, "rationale": "非A股，游资不参与 — 设为0或skip"}
        }
    }
})
```

### 第三段 · 生成报告 + 自动补漏（v3.3 自愈循环）

```bash
python -c "from run_real_test import stage2; stage2('$ARGUMENTS')"
```

stage2 会自动读取 panel.json + agent_analysis.json，合并生成最终报告。
agent_analysis.json 中的字段优先级高于脚本 stub。

**⚠️ 如果 stage2 因结构性错误失败（RuntimeError）**：
读 `_agent_analysis_errors.json` → 逐条修复 → 重写 agent_analysis.json → 重跑 stage2。
这些是可以在 1 分钟内修复的翻译错误（缺 key / 类型不对 / 字符串太短）。

**📋 stage2 成功后，必须读 `.cache/{ticker}/_pending_improvements.json`**：

```
import json
pending = json.loads(Path(f".cache/{ticker}/_pending_improvements.json").read_text(encoding="utf-8"))
```

如果 `pending` 为空 → 直接跳到第四段汇报。
如果 `pending` 非空 → **自主修复（不询问用户）**：

| pending key | 修复方式 |
|---|---|
| `qualitative_deep_dive` | spawn 3 parallel sub-agents (Macro-Policy / Industry-Events / Cost-Transmission)，搜 web → 填充 evidence/associations/conclusion |
| `qualitative_deep_dive_associations` | 基于已有的 agent 分析上下文，补写跨域因果链 |
| `dim_commentary_coverage` | 读 raw_data.json 该维度数据 → 写 1-2 句定性评语（≥20 字） |

修复后：重写 agent_analysis.json → 重跑 stage2 → 再次检查 pending。
**最多 2 轮自愈循环。** 2 轮后无论是否完全修复都向用户汇报。

### 第四段 · 向用户汇报

1. 综合评分 + 定调
2. 51 评委投票分布
3. DCF 内在价值 vs 当前价
4. Top 3 看多理由 + Top 3 看空理由
5. Great Divide 金句
6. 杀猪盘等级
7. 报告文件路径

## 快速模式（跳过 agent 介入）

如果用户说"快速分析"或"不用那么详细"：
```bash
cd <plugin_root>
python run.py $ARGUMENTS --no-browser
```
这会 stage1 + stage2 一把跑完，不做 agent 分析。

## 禁止

- 不跑脚本就编造数据
- 跳过 agent 分析直接出报告（除非用户明确要快速模式）
- 用"基本面良好"等模板话术
