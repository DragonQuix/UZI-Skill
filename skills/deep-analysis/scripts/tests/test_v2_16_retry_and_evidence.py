"""v2.16 · 核心路径测试 — _retry_request + _check_evidence_quality.

覆盖 fe76a6a 两项关键新增逻辑:
1. exa_client._retry_request 重试/不重试决策
2. agent_analysis_validator._check_evidence_quality 合成数据检测
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))


# ═══════════════════════════════════════════════════════════════
# _retry_request 测试
# ═══════════════════════════════════════════════════════════════

class TestRetryRequest:
    """验证 _retry_request 的重试决策矩阵。"""

    def _get_fn(self):
        from lib.exa_client import _retry_request
        return _retry_request

    def test_success_first_attempt(self):
        """正常 200 一次成功，不重试。"""
        fn = self._get_fn()
        with patch("lib.exa_client.requests.request") as mock_req:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_req.return_value = mock_resp

            result = fn("POST", "https://test/api")
            assert result is mock_resp
            assert mock_req.call_count == 1

    def test_retry_on_500_then_success(self):
        """第 1 次 500 → 重试 → 第 2 次 200 成功。"""
        fn = self._get_fn()
        with patch("lib.exa_client.requests.request") as mock_req:
            with patch("lib.exa_client.time.sleep") as mock_sleep:
                resp_500 = MagicMock()
                resp_500.status_code = 500
                resp_ok = MagicMock()
                resp_ok.status_code = 200
                mock_req.side_effect = [resp_500, resp_ok]

                result = fn("POST", "https://test/api")
                assert result is resp_ok
                assert mock_req.call_count == 2
                assert mock_sleep.call_count == 1  # sleep 1 次

    def test_retry_on_429_then_success(self):
        """第 1 次 429 rate limit → 重试 → 第 2 次 200。"""
        fn = self._get_fn()
        with patch("lib.exa_client.requests.request") as mock_req:
            with patch("lib.exa_client.time.sleep") as mock_sleep:
                resp_429 = MagicMock()
                resp_429.status_code = 429
                resp_ok = MagicMock()
                resp_ok.status_code = 200
                mock_req.side_effect = [resp_429, resp_ok]

                result = fn("POST", "https://test/api")
                assert result is resp_ok
                assert mock_req.call_count == 2

    def test_no_retry_on_400(self):
        """400 客户端错误不应重试，直接 raise。"""
        fn = self._get_fn()
        with patch("lib.exa_client.requests.request") as mock_req:
            import requests as rq
            resp_400 = MagicMock()
            resp_400.status_code = 400
            # raise_for_status 会抛 HTTPError
            http_err = rq.HTTPError("400 Client Error")
            http_err.response = resp_400
            resp_400.raise_for_status.side_effect = http_err
            mock_req.return_value = resp_400

            with pytest.raises(rq.HTTPError):
                fn("POST", "https://test/api")
            assert mock_req.call_count == 1  # 无重试

    def test_no_retry_on_401(self):
        """401 认证错误不重试。"""
        fn = self._get_fn()
        with patch("lib.exa_client.requests.request") as mock_req:
            import requests as rq
            resp_401 = MagicMock()
            resp_401.status_code = 401
            http_err = rq.HTTPError("401 Unauthorized")
            http_err.response = resp_401
            resp_401.raise_for_status.side_effect = http_err
            mock_req.return_value = resp_401

            with pytest.raises(rq.HTTPError):
                fn("POST", "https://test/api")
            assert mock_req.call_count == 1

    def test_retry_on_connection_error(self):
        """ConnectionError 重试，最终成功。"""
        fn = self._get_fn()
        with patch("lib.exa_client.requests.request") as mock_req:
            with patch("lib.exa_client.time.sleep"):
                import requests as rq
                resp_ok = MagicMock()
                resp_ok.status_code = 200
                mock_req.side_effect = [
                    rq.ConnectionError("Connection refused"),
                    resp_ok,
                ]
                result = fn("POST", "https://test/api")
                assert result is resp_ok
                assert mock_req.call_count == 2

    def test_connection_error_exhausted(self):
        """ConnectionError 耗尽 3 次重试后 raise。"""
        fn = self._get_fn()
        with patch("lib.exa_client.requests.request") as mock_req:
            with patch("lib.exa_client.time.sleep"):
                import requests as rq
                mock_req.side_effect = rq.ConnectionError("Connection refused")
                with pytest.raises(rq.ConnectionError):
                    fn("POST", "https://test/api")
                # max_retries=2 → 0,1,2 = 3 次尝试
                assert mock_req.call_count == 3

    def test_500_all_attempts_exhausted(self):
        """所有 3 次 5xx，最后一次 raise_for_status 抛 HTTPError。"""
        fn = self._get_fn()
        with patch("lib.exa_client.requests.request") as mock_req:
            with patch("lib.exa_client.time.sleep"):
                import requests as rq
                resp_500 = MagicMock()
                resp_500.status_code = 500
                http_err = rq.HTTPError("500 Server Error")
                http_err.response = resp_500
                resp_500.raise_for_status.side_effect = http_err
                mock_req.return_value = resp_500

                with pytest.raises(rq.HTTPError):
                    fn("POST", "https://test/api")
                assert mock_req.call_count == 3

    def test_exponential_backoff_sleep_times(self):
        """验证指数退避时间: 2^0 + jitter, 2^1 + jitter。"""
        fn = self._get_fn()
        with patch("lib.exa_client.requests.request") as mock_req:
            with patch("lib.exa_client.time.sleep") as mock_sleep:
                resp_500 = MagicMock()
                resp_500.status_code = 500
                resp_ok = MagicMock()
                resp_ok.status_code = 200
                mock_req.side_effect = [resp_500, resp_500, resp_ok]

                fn("POST", "https://test/api")
                assert mock_sleep.call_count == 2
                # 第 1 次 sleep: 2^0=1 秒 + jitter (0-0.5)
                sleep_0 = mock_sleep.call_args_list[0][0][0]
                assert 1.0 <= sleep_0 <= 1.5
                # 第 2 次 sleep: 2^1=2 秒 + jitter (0-0.5)
                sleep_1 = mock_sleep.call_args_list[1][0][0]
                assert 2.0 <= sleep_1 <= 2.5


# ═══════════════════════════════════════════════════════════════
# _check_evidence_quality 测试
# ═══════════════════════════════════════════════════════════════

class TestEvidenceQuality:
    """验证合成数据检测的五维判定。"""

    def _call(self, dim_k: str, ev: list) -> list:
        from lib.agent_analysis_validator import _check_evidence_quality
        issues: list = []
        _check_evidence_quality(issues, dim_k, ev)
        return issues

    def test_clean_evidence_no_issues(self):
        """正常的 evidence 应该 0 条 issue。"""
        issues = self._call("3_macro", [
            {
                "source": "中国人民银行",
                "url": "https://www.pbc.gov.cn/zhengcehuobisi/125207/125217/125925/2026Q1.html",
                "finding": "2026 Q1 MLF 利率维持 2.5%，流动性中性偏松，利好权益资产估值修复",
            },
            {
                "source": "国家统计局",
                "url": "https://www.stats.gov.cn/sj/zxfb/202604/t20260415_1956789.html",
                "finding": "3 月 CPI 同比 0.3%，PPI 降幅收窄至 -1.2%，通缩压力缓解",
            },
        ])
        assert len(issues) == 0

    def test_empty_url_detection(self):
        """空 URL 应被检测为 error。"""
        issues = self._call("7_industry", [
            {"source": "某券商研报", "url": "", "finding": "行业景气度回升"},
            {"source": "行业协会", "url": "https://example.com/report", "finding": "产能利用率 85%"},
        ])
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) >= 1
        assert any("缺少 url" in e.message for e in errors)

    def test_generic_domain_url_detection(self):
        """裸域名 URL 应被检测为 error（合成数据）。"""
        issues = self._call("13_policy", [
            {"source": "财政部", "url": "https://finance.sina.com.cn", "finding": "财政赤字率上调至 4%"},
        ])
        errors = [i for i in issues if i.severity == "error"]
        assert any("通用域名" in e.message for e in errors)

    def test_generic_domain_with_trailing_slash(self):
        """https://eastmoney.com/ 也应按 catch-all 被 flag。"""
        issues = self._call("8_materials", [
            {"source": "百川盈孚", "url": "https://www.eastmoney.com/", "finding": "锂价企稳反弹"},
        ])
        errors = [i for i in issues if i.severity == "error"]
        assert any("通用域名" in e.message for e in errors)

    def test_specific_article_url_not_flagged(self):
        """含路径的具体文章 URL 不应被 flag。"""
        issues = self._call("15_events", [
            {"source": "雪球", "url": "https://xueqiu.com/1234567890/320001234", "finding": "大宗交易折价 3%"},
        ])
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) == 0

    def test_missing_source_warning(self):
        """缺 source 字段应产生 warning。"""
        issues = self._call("9_futures", [
            {"url": "https://example.com/copper", "finding": "铜期货 contango 结构"},
        ])
        warns = [i for i in issues if i.severity == "warning"]
        assert any("缺少 source" in w.message for w in warns)

    def test_short_finding_warning(self):
        """finding 少于 10 字应产生 warning。"""
        issues = self._call("3_macro", [
            {"source": "新闻", "url": "https://example.com/news", "finding": "GDP 增"},
        ])
        warns = [i for i in issues if i.severity == "warning"]
        assert any("过短" in w.message for w in warns)

    def test_duplicate_url_detection(self):
        """相同 URL 应被检测为重复。"""
        same_url = "https://example.com/report"
        issues = self._call("7_industry", [
            {"source": "A", "url": same_url, "finding": "行业景气度回升明显"},
            {"source": "B", "url": same_url, "finding": "行业需求增长"},
        ])
        warns = [i for i in issues if i.severity == "warning"]
        assert any("与其他条目相同" in w.message for w in warns)

    def test_duplicate_url_trailing_slash_normalized(self):
        """https://a.com/page 和 https://a.com/page/ 应被视为相同 URL。"""
        issues = self._call("3_macro", [
            {"source": "A", "url": "https://example.com/article", "finding": "数据表明通胀回落"},
            {"source": "B", "url": "https://example.com/article/", "finding": "通胀继续回落"},
        ])
        warns = [i for i in issues if i.severity == "warning"]
        assert any("与其他条目相同" in w.message for w in warns), (
            f"预期检测到重复 URL（trailing slash 标准化），实际 issues: {json.dumps([{'sev': i.severity, 'msg': i.message} for i in issues], ensure_ascii=False)}"
        )

    def test_empty_list_all_non_dict(self):
        """evidence 列表非 dict 项应产生 error。"""
        issues = self._call("3_macro", ["not a dict", 123])
        errors = [i for i in issues if i.severity == "error"]
        assert any("为空或所有项均为非 dict" in e.message for e in errors)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
