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

**4. 补全定性深研（🔴 v3.6 硬门禁 · 不可跳过）**

`qualitative_deep_dive` 覆盖 6 个爬虫无法推理的维度的因果分析。**必须在调用 write_task_output() 之前完成。**

Spawn **3 个并行 sub-agent**，每个覆盖 2 个维度：

| Sub-agent | 维度 | 核心问题 |
|-----------|------|----------|
| **Macro-Policy** | 3_macro + 13_policy | 利率/汇率/地缘如何传导到这只股？政策对业务的量化影响？ |
| **Industry-Events** | 7_industry + 15_events | 赛道在生命周期的哪个阶段？近期事件的货币化影响？ |
| **Cost-Transmission** | 8_materials + 9_futures | 原材料涨价能否顺价？毛利率弹性？期货 contango/backwardation 含义？ |

每个 sub-agent 的输出格式：
```json
{
  "evidence": [{"source": "来源名", "url": "https://...", "finding": "发现", "retrieved_at": "2026-04-28"}],
  "associations": [{"causal_chain": "X → Y → Z 影响股价", "estimated_impact": "±X%"}],
  "conclusion": "2-3 句量化结论"
}
```

参考详细操作手册：`skills/deep-analysis/references/task2.5-qualitative-deep-dive.md`

**5. 写 agent_analysis.json（闭环关键！）**

对关键维度（财报/估值/护城河/行业）写 1-2 句定性评语。将步骤 4 的 qualitative_deep_dive 结果填入。

**⚠️ 必须使用模板 + API，禁止直接用 Path.write_text()：**

```python
from lib.cache import agent_analysis_template, write_task_output

# Step 1: 获取带注释的预填充模板（所有必填字段已就位）
aa = agent_analysis_template(ticker, stock_name="山西汾酒")

# Step 2: 填入 dim_commentary + panel_insights + great_divide + narrative
aa["dim_commentary"]["1_financials"] = "ROE 33.5% 连续五年 > 15%，净利率 31.6%..."
aa["panel_insights"] = "51 位评委中 12 人看多..."

# Step 3: 填入 qualitative_deep_dive（步骤 4 的 3 个 sub-agent 输出）
aa["qualitative_deep_dive"] = {
    "3_macro": { 宏观 sub-agent 输出 },
    "7_industry": { 行业 sub-agent 输出 },
    ...
}

# Step 4: 写入（自动校验 schema，error 级阻断）
write_task_output(ticker, "agent_analysis", aa)
```

**模板已包含所有必填字段**：`buy_zones` 四派系 (value/growth/technical/youzi)、`qualitative_deep_dive` 6 维结构、`data_gap_acknowledged`。
你只需替换 `【待填充】` 占位符，不用记字段名。

### 第三段 · 生成报告（脚本完成）

> ⚠️ v3.6 起：如果 qualitative_deep_dive 在 medium/deep 模式下缺失，stage2 会 **raise RuntimeError 阻断**（Gate 2 硬门禁）。
> 正常情况第一遍 stage2 就应该通过。以下自愈流程仅用于处理 dim_commentary 覆盖率不足或 causal associations 不够等非阻断问题。

**第一步 · 运行 stage2**

```bash
python -c "from run_real_test import stage2; stage2('$ARGUMENTS')"
```

stage2 会自动读取 panel.json + agent_analysis.json，合并生成最终报告。

**⚠️ 如果 stage2 因 Gate 1/Gate 2 失败（RuntimeError）**：
- **Gate 1**（`_validated_by != "write_task_output"`）：用 `write_task_output()` 重写 agent_analysis.json → 重跑 stage2
- **Gate 2**（`qualitative_deep_dive` 缺失）：回第二段步骤 4，spawn 3 个 sub-agent → 填入 agent_analysis.json → `write_task_output()` → 重跑 stage2

**第二步 · 检查 pending（安全网）**

```python
import json
from pathlib import Path
pending_path = Path(f".cache/{ticker}/_pending_improvements.json")
if pending_path.exists():
    pending = json.loads(pending_path.read_text(encoding="utf-8"))
else:
    pending = {}
```

- 如果 `pending` 为空 → **直接跳到第四段汇报**
- 如果 `pending` 非空 → 执行第三步自主修复

**第三步 · 自主修复（不询问用户，最多 2 轮）**

| pending key | 修复方式 |
|---|---|
| `qualitative_deep_dive_associations` | 基于已有的 agent 分析上下文，补写跨域因果链（≥ 3 条） |
| `dim_commentary_coverage` | 读 raw_data.json 该维度数据 → 写 1-2 句定性评语（≥20 字） |

> `qualitative_deep_dive` 缺失不再出现在此表中——它在 stage2 中是硬阻断（Gate 2），必须修复后才能跑到这里。

修复后必须执行：
```python
# ⚠️ 必须用 write_task_output，禁止直接 Path.write_text
from lib.cache import write_task_output
write_task_output(ticker, "agent_analysis", aa)  # aa 是你修复后的 dict
```
然后重跑 stage2 → 再次检查 pending。
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
