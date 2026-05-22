"""Tests for ce_wanted.extract_wanted_http — HTTP-only company info extraction."""
import json
from unittest.mock import patch

from ce_wanted import extract_wanted_http, _strip_html, parse_next_data_company


SAMPLE_NEXT_DATA = {
    "props": {
        "pageProps": {
            "dehydrateState": {
                "queries": [
                    {
                        "queryKey": ["companyInfo"],
                        "state": {
                            "data": {
                                "name": "비바리퍼블리카",
                                "industryName": "핀테크",
                                "foundedYear": 2013,
                                "description": "토스를 만드는 회사",
                                "companyTags": [{"title": "연봉상위1%"}],
                            }
                        },
                    },
                    {
                        "queryKey": ["companySummary"],
                        "state": {
                            "data": {
                                "detail": {"npsEmployeeCount": 2500},
                                "salary": {"salary": 85000000, "rate": 0.04},
                                "employee": {"total": 2500, "hired": 300, "left": 100},
                                "sales": {"total": 500_000_000_000},
                            }
                        },
                    },
                ]
            }
        }
    }
}


def _make_html(next_data: dict) -> str:
    nd_json = json.dumps(next_data, ensure_ascii=False)
    return f'<html><body><script id="__NEXT_DATA__" type="application/json">{nd_json}</script></body></html>'


class TestStripHtml:
    def test_removes_tags(self):
        assert "hello world" in _strip_html("<p>hello</p> <b>world</b>")

    def test_collapses_whitespace(self):
        result = _strip_html("<div>a</div>  <div>b</div>")
        assert "  " not in result


class TestExtractWantedHttp:
    @patch("wanted_client.fetch_company_html")
    @patch("wanted_client.search_company")
    def test_full_extraction(self, mock_search, mock_fetch):
        mock_search.return_value = ("113", "비바리퍼블리카(토스)")
        mock_fetch.return_value = _make_html(SAMPLE_NEXT_DATA)

        result = extract_wanted_http("토스")

        assert result is not None
        assert result.platform == "wanted"
        assert result.company_name == "비바리퍼블리카"
        assert result.industry == "핀테크"
        assert result.founded_year == 2013
        assert result.employee_count == 2500
        assert result.avg_salary == 8500
        assert result.salary_percentile == "4"
        assert result.employee_joined_1y == 300
        assert result.employee_left_1y == 100
        assert result.revenue[0]["amount_억"] == 5000.0
        assert "연봉상위1%" in result.tags
        assert result.raw_extra["company_id"] == "113"

    @patch("wanted_client.search_company")
    def test_search_not_found(self, mock_search):
        mock_search.return_value = None
        assert extract_wanted_http("없는회사") is None

    @patch("wanted_client.search_company")
    def test_search_api_error(self, mock_search):
        from wanted_client import WantedAPIError
        mock_search.side_effect = WantedAPIError("fail")
        assert extract_wanted_http("토스") is None

    @patch("wanted_client.fetch_company_html")
    @patch("wanted_client.search_company")
    def test_no_next_data_uses_text_fallback(self, mock_search, mock_fetch):
        mock_search.return_value = ("113", "토스")
        mock_fetch.return_value = "<html><body>평균 연봉 8,500만원 상위 4%</body></html>"

        result = extract_wanted_http("토스")

        assert result is not None
        assert result.avg_salary == 8500
        assert result.salary_percentile == "4"

    @patch("wanted_client.fetch_company_html")
    @patch("wanted_client.search_company")
    def test_fetch_error(self, mock_search, mock_fetch):
        from wanted_client import WantedAPIError
        mock_search.return_value = ("113", "토스")
        mock_fetch.side_effect = WantedAPIError("HTTP 500")

        assert extract_wanted_http("토스") is None
