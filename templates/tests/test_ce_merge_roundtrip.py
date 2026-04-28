"""Roundtrip tests: build_enriched_markdown -> parse_company_file.

Verifies markdown format stays compatible with company_validator regex parsing.
Currently 0 existing roundtrip coverage. These 11 fields are coupled by
format (bold salary **만원**, section headers ## 기업 정보, year format YYYY년).
"""
import tempfile
from pathlib import Path

from ce_types import PlatformData
from company_validator import parse_company_file


def _make(platform="wanted", **kwargs):
    return PlatformData(platform=platform, source_url="https://test.com", company_name="테스트회사", **kwargs)


def _roundtrip(data_list, company_name="테스트회사"):
    """Generate markdown -> write temp file -> parse back -> return CompanyData."""
    from ce_merge import build_enriched_markdown, merge_platform_data

    merged = merge_platform_data(data_list)
    markdown = build_enriched_markdown(merged, company_name, ["https://example.com"])
    tmp = tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False, encoding="utf-8")
    tmp.write(markdown)
    tmp.close()
    return parse_company_file(Path(tmp.name))


class TestRoundTrip:
    def test_company_name(self):
        result = _roundtrip([_make()])
        assert result.name == "테스트회사"

    def test_company_name_en(self):
        result = _roundtrip([_make(company_name_en="TestCo")])
        assert result.name_en == "TestCo"

    def test_industry(self):
        result = _roundtrip([_make(industry="소프트웨어 개발")])
        assert result.industry == "소프트웨어 개발"

    def test_founded_year(self):
        result = _roundtrip([_make(founded_year=2018)])
        assert result.founded_year == 2018

    def test_employee_count(self):
        result = _roundtrip([_make(employee_count=150)])
        assert result.employee_current == 150

    def test_employee_joined(self):
        result = _roundtrip([_make(employee_joined_1y=30)])
        assert result.employee_joined_1y == 30

    def test_employee_left(self):
        result = _roundtrip([_make(employee_left_1y=10)])
        assert result.employee_left_1y == 10

    def test_salary_bold_format(self):
        """Validator regex requires **N만원** bold format."""
        result = _roundtrip([_make(avg_salary=5200)])
        assert result.avg_salary == 5200

    def test_salary_percentile(self):
        result = _roundtrip([_make(avg_salary=5200, salary_percentile="15")])
        assert result.salary_percentile == "15"

    def test_investment_round(self):
        result = _roundtrip([_make(platform="thevc", investment_round="Series B")])
        assert result.investment_round == "Series B"
        assert result.is_startup

    def test_investment_total(self):
        result = _roundtrip([_make(platform="thevc", investment_total="298억원")])
        assert result.investment_total is not None

    def test_full_data_roundtrip(self):
        """All 11 coupled fields in one roundtrip."""
        data = _make(
            company_name_en="TestCo",
            industry="IT",
            founded_year=2020,
            employee_count=200,
            employee_joined_1y=50,
            employee_left_1y=20,
            avg_salary=6000,
            salary_percentile="10",
        )
        thevc = _make(platform="thevc", investment_round="Series A", investment_total="100억원")
        result = _roundtrip([data, thevc])
        assert result.name == "테스트회사"
        assert result.founded_year == 2020
        assert result.employee_current == 200
        assert result.avg_salary == 6000
        assert result.investment_round == "Series A"
