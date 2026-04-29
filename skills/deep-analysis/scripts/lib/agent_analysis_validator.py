"""Schema validator for agent_analysis.json · v2.6.

Catches malformed structures from non-Claude LLMs (Codex / 国产模型 etc) so
stage2 can warn the agent and fall back gracefully instead of silently
producing garbage in the report.

Usage from `run_real_test.stage2`:
    from lib.agent_analysis_validator import validate
    issues = validate(agent_analysis)
    if issues:
        # write _agent_analysis_errors.json + console warning
        # error-level issues → fall back to script stub
        # warning-level → still merge but log

Issue types:
- error   : structural / type errors that would cause downstream crash or
            missing critical data (e.g. dim_commentary 是 list 不是 dict)
- warning : content quality issues (e.g. commentary 太短、score 范围不对)

The validator is INTENTIONALLY lenient on Claude's variations. It only flags
patterns that genuinely break stage2 / assemble_report rendering.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

VALID_SIGNALS = {"bullish", "bearish", "neutral", "skip"}

# 合成/通用 URL 模式 — agent 返回域名首页而非具体文章时，判定为合成数据。
# 第一条 catch-all (^https?://[^/]+/?$) 已覆盖所有裸域名首页。
# 后续特定域名作为 defense-in-depth 文档：即使 catch-all 被意外移除，
# 这些已知合成数据源仍能被拦截。新增域名在此追加即可。
_GENERIC_URL_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r'^https?://[^/]+/?$'),                          # catch-all · 纯域名无路径
    re.compile(r'^https?://finance\.sina\.com\.cn/?$'),
    re.compile(r'^https?://finance\.eastmoney\.com/?$'),
    re.compile(r'^https?://(www\.)?xueqiu\.com/?$'),
    re.compile(r'^https?://(www\.)?eastmoney\.com/?$'),
    re.compile(r'^https?://research\.eastmoney\.com/?$'),
    re.compile(r'^https?://(www\.)?cninfo\.com\.cn/?$'),
    re.compile(r'^https?://(www\.)?stats\.gov\.cn/?$'),
    re.compile(r'^https?://(www\.)?sxcoal\.com/?$'),
    re.compile(r'^https?://(www\.)?coalmine\.org\.cn/?$'),
    re.compile(r'^https?://paper\.cnstock\.com/?$'),
)

REQUIRED_DIM_KEYS = (
    "0_basic", "1_financials", "2_kline", "3_macro", "4_peers", "5_chain",
    "6_research", "7_industry", "8_materials", "9_futures", "10_valuation",
    "11_governance", "12_capital_flow", "13_policy", "14_moat", "15_events",
    "16_lhb", "17_sentiment", "18_trap", "19_contests",
)
REQUIRED_BUY_ZONE_KEYS = ("value", "growth", "technical", "youzi")


@dataclass
class ValidationIssue:
    severity: str        # "error" | "warning"
    field: str           # dotted path
    message: str         # human-readable Chinese
    suggestion: str      # 一行修复建议


def _add(issues: list, sev: str, field: str, msg: str, sugg: str) -> None:
    issues.append(ValidationIssue(severity=sev, field=field, message=msg, suggestion=sugg))


def _is_dict(v) -> bool:
    return isinstance(v, dict)


def _is_list(v) -> bool:
    return isinstance(v, list)


def _is_str(v, min_len: int = 1) -> bool:
    return isinstance(v, str) and len(v.strip()) >= min_len


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def validate(agent_analysis: dict) -> list:
    """Return list[ValidationIssue]. Empty list = clean."""
    issues: list = []

    if not _is_dict(agent_analysis):
        _add(issues, "error", "(root)",
             f"agent_analysis 必须是 dict，实际是 {type(agent_analysis).__name__}",
             "整体重写，参考 SKILL.md 的 agent_analysis.json 示例")
        return issues

    # ── agent_reviewed 标记 ──
    if not agent_analysis.get("agent_reviewed"):
        _add(issues, "warning", "agent_reviewed",
             "缺少 agent_reviewed: true 标记",
             '加 "agent_reviewed": true 在顶层')

    # ── dim_commentary ──
    dc = agent_analysis.get("dim_commentary")
    placeholder_count = 0
    if dc is not None:
        if not _is_dict(dc):
            _add(issues, "error", "dim_commentary",
                 f"dim_commentary 必须是 dict（key 是维度名），实际是 {type(dc).__name__}",
                 '改为 {"0_basic": "...", "1_financials": "...", ...}')
        else:
            for k, v in dc.items():
                if not isinstance(v, str):
                    _add(issues, "error", f"dim_commentary.{k}",
                         f"评语必须是字符串，实际是 {type(v).__name__}",
                         "把评语改成一段连贯文字")
                elif len(v.strip()) < 20:
                    _add(issues, "warning", f"dim_commentary.{k}",
                         f"评语太短（{len(v.strip())} 字），低于 20 字门槛",
                         "至少写 1-2 句话，引用具体数字")
                elif "【待填充】" in v or "【TODO】" in v:
                    placeholder_count += 1
                    _add(issues, "warning", f"dim_commentary.{k}",
                         "评语包含占位符 '【待填充】' 或 '【TODO】'，未实际填写",
                         "替换为基于 raw_data.json 的具体定性评语")

    # ── panel_insights ──
    pi = agent_analysis.get("panel_insights")
    if pi is not None:
        if not _is_str(pi, 30):
            _add(issues, "warning", "panel_insights",
                 f"panel_insights 应是 30+ 字字符串，实际 {type(pi).__name__} / 长度 {len(str(pi))}",
                 "用一段话概括 51 评委的投票结构和主要分歧")
        elif "【待填充】" in pi or "【TODO】" in pi:
            _add(issues, "warning", "panel_insights",
                 "panel_insights 包含占位符，未实际填写",
                 "替换为 51 评委投票分布 + 多空分歧分析")

    # ── great_divide_override ──
    gdo = agent_analysis.get("great_divide_override")
    if gdo is not None:
        if not _is_dict(gdo):
            _add(issues, "error", "great_divide_override",
                 "必须是 dict（含 punchline / bull_say_rounds / bear_say_rounds）",
                 "参考 SKILL.md 的格式")
        else:
            pl = gdo.get("punchline")
            if pl is not None:
                if not _is_str(pl, 10):
                    _add(issues, "warning", "great_divide_override.punchline",
                         "punchline 应是 10+ 字冲突金句",
                         "写一句能传播的话，含具体数字")
                elif "【待填充】" in pl or "【TODO】" in pl:
                    _add(issues, "warning", "great_divide_override.punchline",
                         "punchline 包含占位符，未实际填写",
                         "替换为基本面派 vs 技术派的核心冲突金句")
            for side in ("bull_say_rounds", "bear_say_rounds"):
                rounds = gdo.get(side)
                if rounds is not None:
                    if not _is_list(rounds):
                        _add(issues, "error", f"great_divide_override.{side}",
                             f"必须是 list，实际是 {type(rounds).__name__}",
                             '改为 ["第 1 轮", "第 2 轮", "第 3 轮"]')
                    elif len(rounds) < 3:
                        _add(issues, "warning", f"great_divide_override.{side}",
                             f"应有 3 轮（至少），实际 {len(rounds)}",
                             "凑齐 3 句辩论")

    # ── narrative_override ──
    no = agent_analysis.get("narrative_override")
    if no is not None:
        if not _is_dict(no):
            _add(issues, "error", "narrative_override",
                 "必须是 dict",
                 "参考 SKILL.md 的格式")
        else:
            cc = no.get("core_conclusion")
            if cc is not None:
                if not _is_str(cc, 20):
                    _add(issues, "warning", "narrative_override.core_conclusion",
                         "core_conclusion 应是 20+ 字定论",
                         "1-2 句结论 + 评分 + 关键证据")
                elif "【待填充】" in cc or "【TODO】" in cc:
                    _add(issues, "warning", "narrative_override.core_conclusion",
                         "core_conclusion 包含占位符，未实际填写",
                         "替换为基于 agent 分析的综合定论")
            risks = no.get("risks")
            if risks is not None:
                if not _is_list(risks):
                    _add(issues, "error", "narrative_override.risks",
                         f"必须是 list，实际是 {type(risks).__name__}",
                         "改为 [\"风险 1\", \"风险 2\", ...]")
                elif len(risks) < 3:
                    _add(issues, "warning", "narrative_override.risks",
                         f"建议至少 3 条风险，实际 {len(risks)}",
                         "补齐 Top 3 风险")
            bz = no.get("buy_zones")
            if bz is not None:
                if not _is_dict(bz):
                    _add(issues, "error", "narrative_override.buy_zones",
                         f"必须是 dict，含 value/growth/technical/youzi 4 key",
                         "参考 SKILL.md 示例")
                else:
                    for k in REQUIRED_BUY_ZONE_KEYS:
                        zone = bz.get(k)
                        if zone is None:
                            _add(issues, "error", f"narrative_override.buy_zones.{k}",
                                 f"缺少 {k} 派系买入区间", f'加 "{k}": {{"price": X, "rationale": "..."}}')
                        elif not _is_dict(zone):
                            _add(issues, "error", f"narrative_override.buy_zones.{k}",
                                 f"必须是 dict 含 price + rationale，实际 {type(zone).__name__}",
                                 '改为 {"price": 10.5, "rationale": "..."}')
                        else:
                            if zone.get("price") is None:
                                _add(issues, "warning", f"narrative_override.buy_zones.{k}.price",
                                     "缺 price 字段", '加 "price": <数值>')
                            if not _is_str(zone.get("rationale", ""), 5):
                                _add(issues, "warning", f"narrative_override.buy_zones.{k}.rationale",
                                     "缺 rationale 解释", '加 "rationale": "..."')

    # ── data_gap_acknowledged (v2.3 引入) ──
    dga = agent_analysis.get("data_gap_acknowledged")
    if dga is not None and not _is_dict(dga):
        _add(issues, "error", "data_gap_acknowledged",
             f"必须是 dict（key 是 dim 或 dim.field），实际 {type(dga).__name__}",
             '改为 {"4_peers": "已尝试 X 但失败", ...}')

    # ── qualitative_deep_dive (v2.4 引入) ──
    qdd = agent_analysis.get("qualitative_deep_dive")
    if qdd is not None:
        if not _is_dict(qdd):
            _add(issues, "error", "qualitative_deep_dive",
                 f"必须是 dict（key 是 6 个 dim），实际 {type(qdd).__name__}",
                 "参考 references/task2.5-qualitative-deep-dive.md 第 5 节")
        else:
            for dim_k, dim_v in qdd.items():
                if not _is_dict(dim_v):
                    _add(issues, "error", f"qualitative_deep_dive.{dim_k}",
                         f"维度内容必须是 dict（含 evidence/associations/conclusion），实际 {type(dim_v).__name__}",
                         "参考 task2.5 的输出 schema")
                else:
                    ev = dim_v.get("evidence")
                    if ev is not None and not _is_list(ev):
                        _add(issues, "error", f"qualitative_deep_dive.{dim_k}.evidence",
                             "evidence 必须是 list",
                             '改为 [{"source": "...", "url": "...", "finding": "..."}, ...]')
                    elif _is_list(ev):
                        # v3.x · 合成数据检测（Gate 2 硬阻断标准）
                        _check_evidence_quality(issues, dim_k, ev)

    return issues


def _check_evidence_quality(issues: list, dim_k: str, ev: list) -> None:
    """逐条校验 evidence 的 url/source/finding 质量，检测合成数据。"""
    dict_items = [e for e in ev if isinstance(e, dict)]
    if not dict_items:
        _add(issues, "error", f"qualitative_deep_dive.{dim_k}.evidence",
             "evidence 列表为空或所有项均为非 dict",
             "每条 evidence 必须是 dict 含 source/url/finding")
        return

    empty_url = 0
    generic_url = 0
    missing_source = 0
    short_finding = 0
    seen_urls: set[str] = set()
    dup_url = 0

    for idx, e in enumerate(dict_items):
        url = str(e.get("url", "")).strip()

        if not url:
            empty_url += 1
        else:
            if any(p.search(url) for p in _GENERIC_URL_PATTERNS):
                generic_url += 1
            # 标准化后比较（去 trailing slash / query fragment 尾部差异）
            url_norm = url.rstrip("/").rstrip("/?")
            if url_norm in seen_urls:
                dup_url += 1
            else:
                seen_urls.add(url_norm)

        if not e.get("source"):
            missing_source += 1

        finding = str(e.get("finding", ""))
        if len(finding.strip()) < 10:
            short_finding += 1

    n = len(dict_items)
    if empty_url > 0:
        _add(issues, "error",
             f"qualitative_deep_dive.{dim_k}.evidence",
             f"{empty_url}/{n} 条 evidence 缺少 url 字段",
             "每条 evidence 必须有 url，参考 task2.5 规范第 382 行")
    if generic_url > 0:
        _add(issues, "error",
             f"qualitative_deep_dive.{dim_k}.evidence",
             f"{generic_url}/{n} 条 url 是通用域名（非具体文章 URL），可能是合成数据",
             "url 必须指向具体文章页面（含路径），而非首页/域名。请用 WebSearch 获取真实 URL 后重写。")
    if missing_source > 0:
        _add(issues, "warning",
             f"qualitative_deep_dive.{dim_k}.evidence",
             f"{missing_source}/{n} 条缺少 source 字段",
             '加 "source": "来源名称"')
    if short_finding > 0:
        _add(issues, "warning",
             f"qualitative_deep_dive.{dim_k}.evidence",
             f"{short_finding}/{n} 条 finding 过短（< 10 字）",
             "每条 finding 至少 10 字，说明具体证据内容")
    if dup_url > 0:
        _add(issues, "warning",
             f"qualitative_deep_dive.{dim_k}.evidence",
             f"{dup_url}/{n} 条 url 与其他条目相同",
             "每条 evidence 应有独立的来源 URL")


def format_issues(issues: list) -> str:
    """Pretty-print issues for console output (ASCII-safe for Windows GBK terminals)."""
    if not issues:
        return "[OK] agent_analysis.json schema validation passed"
    lines = []
    errs = [i for i in issues if i.severity == "error"]
    warns = [i for i in issues if i.severity == "warning"]
    if errs:
        lines.append(f"[ERROR] {len(errs)} schema error(s) — structural, stage2 will fallback:")
        for i in errs[:10]:
            lines.append(f"   - {i.field}: {i.message}")
            lines.append(f"     -> {i.suggestion}")
        if len(errs) > 10:
            lines.append(f"   ... {len(errs) - 10} more")
    if warns:
        lines.append(f"[WARN] {len(warns)} schema warning(s) — quality, stage2 OK but report quality may degrade:")
        for i in warns[:10]:
            lines.append(f"   - {i.field}: {i.message}")
        if len(warns) > 10:
            lines.append(f"   ... {len(warns) - 10} more")
    return "\n".join(lines)


if __name__ == "__main__":
    import json, sys
    # Smoke tests
    print("=== Test 1: dim_commentary as list (error) ===")
    iss = validate({"dim_commentary": ["wrong"]})
    print(format_issues(iss))
    print()
    print("=== Test 2: missing buy_zones.value ===")
    iss = validate({"narrative_override": {"buy_zones": {"growth": {"price": 10}}}})
    print(format_issues(iss))
    print()
    print("=== Test 3: clean Claude-style payload ===")
    iss = validate({
        "agent_reviewed": True,
        "dim_commentary": {"0_basic": "公司是港口龙头，市值 270 亿，PE 25 倍偏高。"},
        "panel_insights": "51 评委里 12 人看多 19 中性 19 看空，分歧主要在估值和催化剂之间。",
        "great_divide_override": {"punchline": "PE 25 买 ROE 6% 是为运河支付溢价",
                                  "bull_say_rounds": ["a", "b", "c"],
                                  "bear_say_rounds": ["a", "b", "c"]},
        "narrative_override": {
            "core_conclusion": "综合 48 分谨慎评级，等待回调再介入。",
            "risks": ["风险 1", "风险 2", "风险 3"],
            "buy_zones": {k: {"price": 10.0, "rationale": "test"} for k in REQUIRED_BUY_ZONE_KEYS},
        },
    })
    print(format_issues(iss))
