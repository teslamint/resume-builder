"""Unit tests for ce_merge — merge priority logic and markdown generation."""
from ce_types import PlatformData


def _make(platform, **kwargs):
    """Helper: create PlatformData with defaults."""
    return PlatformData(platform=platform, source_url=f"https://{platform}.test", company_name="TestCo", **kwargs)


class TestMergePlatformData:
    """Tests for merge_platform_data priority rules."""

    def test_wanted_salary_over_saramin(self):
        """Wanted salary has priority (국민연금 기반)."""
        from ce_merge import merge_platform_data

        result = merge_platform_data([_make("wanted", avg_salary=5000), _make("saramin", avg_salary=4000)])
        assert result["avg_salary"] == 5000

    def test_thevc_investment_over_wanted(self):
        """TheVC investment data has priority."""
        from ce_merge import merge_platform_data

        result = merge_platform_data([_make("wanted", investment_round="Series A"), _make("thevc", investment_round="Series B")])
        assert result["investment_round"] == "Series B"

    def test_saramin_industry_over_wanted(self):
        """Saramin industry uses standard classification."""
        from ce_merge import merge_platform_data

        result = merge_platform_data([_make("wanted", industry="IT"), _make("saramin", industry="소프트웨어 개발")])
        assert result["industry"] == "소프트웨어 개발"

    def test_saramin_benefits_over_wanted(self):
        """Saramin benefits are richest."""
        from ce_merge import merge_platform_data

        result = merge_platform_data([_make("wanted", benefits=["식대"]), _make("saramin", benefits=["식대", "통근버스", "자기개발비"])])
        assert result["benefits"] == ["식대", "통근버스", "자기개발비"]

    def test_jd_investment_lowest_priority(self):
        """JD file extraction is fallback for investment."""
        from ce_merge import merge_platform_data

        result = merge_platform_data([_make("jd", investment_round="Seed"), _make("wanted", investment_round="Series A")])
        assert result["investment_round"] == "Series A"

    def test_jd_fallback_when_no_other_source(self):
        """JD fills investment when no other platform has it."""
        from ce_merge import merge_platform_data

        result = merge_platform_data([_make("wanted"), _make("jd", investment_round="Series B", investment_total="100억원")])
        assert result["investment_round"] == "Series B"
        assert result["investment_total"] == "100억원"

    def test_single_platform(self):
        """Single source fills all available fields."""
        from ce_merge import merge_platform_data

        result = merge_platform_data([_make("wanted", avg_salary=5000, founded_year=2018, employee_count=150)])
        assert result["avg_salary"] == 5000
        assert result["founded_year"] == 2018
        assert result["employee_count"] == 150

    def test_empty_input(self):
        """Empty list returns all-None/empty merged dict."""
        from ce_merge import merge_platform_data

        result = merge_platform_data([])
        assert result["company_name"] == ""
        assert result["avg_salary"] is None
        assert result["investors"] == []

    def test_saramin_raw_extra_fields(self):
        """Saramin-only fields (ceo, location) via raw_extra."""
        from ce_merge import merge_platform_data

        result = merge_platform_data([_make("saramin", raw_extra={"ceo": "홍길동", "location": "서울"})])
        assert result["raw_extra"]["ceo"] == "홍길동"
        assert result["raw_extra"]["location"] == "서울"

    def test_source_urls_accumulated(self):
        """All platform source URLs are collected."""
        from ce_merge import merge_platform_data

        result = merge_platform_data([_make("wanted"), _make("saramin"), _make("thevc")])
        assert len(result["source_urls"]) == 3


class TestFmt:
    def test_none_returns_info_missing(self):
        from ce_merge import fmt

        assert fmt(None) == "정보 없음"

    def test_value_with_suffix(self):
        from ce_merge import fmt

        assert fmt(150, "명") == "150명"

    def test_value_without_suffix(self):
        from ce_merge import fmt

        assert fmt("IT") == "IT"


class TestBuildEnrichedMarkdown:
    def test_contains_company_info_section(self):
        from ce_merge import build_enriched_markdown, merge_platform_data

        merged = merge_platform_data([_make("wanted", industry="IT", founded_year=2020)])
        md = build_enriched_markdown(merged, "테스트회사", ["https://example.com"])
        assert "## 기업 정보" in md
        assert "| 업종 | IT |" in md
        assert "| 스타트업 여부 | No |" in md

    def test_salary_bold_format(self):
        """Salary must be in **N만원** bold format for validator compatibility."""
        from ce_merge import build_enriched_markdown, merge_platform_data

        merged = merge_platform_data([_make("wanted", avg_salary=5200)])
        md = build_enriched_markdown(merged, "A", [])
        assert "**5,200만원**" in md

    def test_no_investment_section_when_empty(self):
        """투자 정보 section is omitted when no investment data."""
        from ce_merge import build_enriched_markdown, merge_platform_data

        merged = merge_platform_data([_make("wanted")])
        md = build_enriched_markdown(merged, "A", [])
        assert "## 투자 정보" not in md

    def test_investment_section_present(self):
        from ce_merge import build_enriched_markdown, merge_platform_data

        merged = merge_platform_data([_make("thevc", investment_round="Series A", investment_total="50억원")])
        md = build_enriched_markdown(merged, "A", [])
        assert "## 투자 정보" in md
        assert "| 스타트업 여부 | Yes |" in md
        assert "Series A" in md
