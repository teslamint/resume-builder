#!/usr/bin/env python3
"""Tests for company_validator.py — pure functions and file parsing."""

import unittest
from pathlib import Path

from company_validator import (
    CompanyData,
    RiskFlag,
    ValidationResult,
    generate_report,
    parse_company_file,
    parse_money_billions,
    parse_number,
    parse_percentage,
    validate_company,
    validation_result_to_dict,
)


class TestParseNumber(unittest.TestCase):
    def test_plain_number(self):
        self.assertEqual(parse_number("50명"), 50)

    def test_approximate_with_commas(self):
        self.assertEqual(parse_number("약 1,220명"), 1220)

    def test_undisclosed(self):
        self.assertIsNone(parse_number("비공개"))

    def test_no_info(self):
        self.assertIsNone(parse_number("정보없음"))

    def test_empty_string(self):
        self.assertIsNone(parse_number(""))

    def test_none_input(self):
        self.assertIsNone(parse_number(None))

    def test_complex_format(self):
        self.assertEqual(parse_number("2,774명 (국민연금)"), 2774)

    def test_salary_format(self):
        self.assertEqual(parse_number("5,619만원"), 5619)


class TestParsePercentage(unittest.TestCase):
    def test_simple_percentage(self):
        self.assertAlmostEqual(parse_percentage("15.3%"), 15.3)

    def test_undisclosed(self):
        self.assertIsNone(parse_percentage("비공개"))

    def test_na(self):
        self.assertIsNone(parse_percentage("N/A"))

    def test_empty(self):
        self.assertIsNone(parse_percentage(""))

    def test_top_percentage(self):
        self.assertAlmostEqual(parse_percentage("상위 7%"), 7.0)

    def test_negative(self):
        self.assertAlmostEqual(parse_percentage("-3%"), -3.0)


class TestParseMoneyBillions(unittest.TestCase):
    def test_simple(self):
        self.assertAlmostEqual(parse_money_billions("100억"), 100.0)

    def test_with_won(self):
        self.assertAlmostEqual(parse_money_billions("약 50억원"), 50.0)

    def test_undisclosed(self):
        self.assertIsNone(parse_money_billions("미공개"))

    def test_empty(self):
        self.assertIsNone(parse_money_billions(""))

    def test_with_commas(self):
        self.assertAlmostEqual(parse_money_billions("1,234억원"), 1234.0)


class TestValidateCompany(unittest.TestCase):
    def _make_data(self, **kwargs):
        defaults = dict(
            name="TestCo",
            employee_current=100,
            avg_salary=5000,
            founded_year=2015,
        )
        defaults.update(kwargs)
        return CompanyData(**defaults)

    def test_turnover_critical_no_net_positive(self):
        data = self._make_data(employee_left_1y=60, employee_joined_1y=30)
        result = validate_company(data, Path("test.md"))
        codes = [f.code for f in result.risk_flags]
        self.assertIn("TURNOVER_CRITICAL", codes)

    def test_turnover_critical_net_positive_downgrades_to_high(self):
        data = self._make_data(employee_left_1y=55, employee_joined_1y=70)
        result = validate_company(data, Path("test.md"))
        codes = [f.code for f in result.risk_flags]
        self.assertIn("TURNOVER_HIGH", codes)
        self.assertNotIn("TURNOVER_CRITICAL", codes)

    def test_turnover_high_no_net_positive(self):
        data = self._make_data(employee_left_1y=35, employee_joined_1y=20)
        result = validate_company(data, Path("test.md"))
        codes = [f.code for f in result.risk_flags]
        self.assertIn("TURNOVER_HIGH", codes)

    def test_turnover_high_net_positive_downgrades_to_medium(self):
        data = self._make_data(employee_left_1y=35, employee_joined_1y=50)
        result = validate_company(data, Path("test.md"))
        codes = [f.code for f in result.risk_flags]
        self.assertIn("TURNOVER_MEDIUM", codes)
        self.assertNotIn("TURNOVER_HIGH", codes)

    def test_turnover_medium_no_net_positive(self):
        data = self._make_data(employee_left_1y=25, employee_joined_1y=20)
        result = validate_company(data, Path("test.md"))
        codes = [f.code for f in result.risk_flags]
        self.assertIn("TURNOVER_MEDIUM", codes)

    def test_turnover_medium_net_positive_no_flag(self):
        data = self._make_data(employee_left_1y=25, employee_joined_1y=40)
        result = validate_company(data, Path("test.md"))
        turnover_codes = [f.code for f in result.risk_flags if "TURNOVER" in f.code]
        self.assertEqual(turnover_codes, [])

    def test_completeness_all_required_present(self):
        data = self._make_data()
        result = validate_company(data, Path("test.md"))
        self.assertEqual(result.completeness_score, 100.0)

    def test_completeness_startup_partial(self):
        data = self._make_data(is_startup=True, investment_round="Series A")
        result = validate_company(data, Path("test.md"))
        # 3 base + 1 startup = 4 of 7
        self.assertAlmostEqual(result.completeness_score, 4 / 7 * 100, places=1)

    def test_no_risk_flags_for_healthy_company(self):
        data = self._make_data(employee_left_1y=10, employee_joined_1y=15)
        result = validate_company(data, Path("test.md"))
        high_severity = [f for f in result.risk_flags if f.severity in ("critical", "high")]
        self.assertEqual(high_severity, [])


class TestGenerateReport(unittest.TestCase):
    def test_report_has_summary(self):
        data = CompanyData(name="ReportCo")
        result = ValidationResult(file_path=Path("test.md"), company_name="ReportCo", data=data)
        report = generate_report([result])
        self.assertIn("기업정보 검증 리포트", report)
        self.assertIn("총 1개 기업", report)

    def test_report_risky_section(self):
        data = CompanyData(name="RiskyCo")
        result = ValidationResult(
            file_path=Path("test.md"),
            company_name="RiskyCo",
            data=data,
            risk_flags=[RiskFlag(code="TURNOVER_CRITICAL", severity="critical", message="test")],
        )
        report = generate_report([result])
        self.assertIn("주의 필요 기업", report)


class TestValidationResultToDict(unittest.TestCase):
    def test_file_path_serialized(self):
        data = CompanyData(name="DictCo")
        result = ValidationResult(file_path=Path("/tmp/test.md"), company_name="DictCo", data=data)
        d = validation_result_to_dict(result)
        self.assertEqual(d["file_path"], "/tmp/test.md")
        self.assertIsInstance(d["file_path"], str)


class TestParseCompanyFile(unittest.TestCase):
    def test_parse_basic_file(self, tmp_path=None):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "company.md"
            p.write_text(
                "# 테스트회사 (TestCo)\n\n"
                "## 기업 정보\n\n"
                "| 항목 | 내용 |\n|------|------|\n"
                "| 설립 | 2018년 |\n"
                "| 직원수 | 150명 |\n"
                "| 업종 | IT |\n\n"
                "## 연봉 정보\n\n"
                "| 항목 | 금액 |\n|------|------|\n"
                "| 평균 연봉 | **5,200만원** |\n"
                "| 상위 | 상위 15% |\n",
                encoding="utf-8",
            )
            data = parse_company_file(p)
            self.assertEqual(data.name, "테스트회사")
            self.assertEqual(data.name_en, "TestCo")
            self.assertEqual(data.founded_year, 2018)
            self.assertEqual(data.employee_current, 150)
            self.assertEqual(data.avg_salary, 5200)
            self.assertEqual(data.industry, "IT")

    def test_parse_investment_section(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "startup.md"
            p.write_text(
                "# 스타트업\n\n"
                "## 투자 정보\n\n"
                "| 항목 | 내용 |\n|------|------|\n"
                "| 현재 라운드 | Series B |\n"
                "| 누적 투자금 | 약 130억원 |\n",
                encoding="utf-8",
            )
            data = parse_company_file(p)
            self.assertTrue(data.is_startup)
            self.assertEqual(data.investment_round, "Series B")
            self.assertAlmostEqual(data.investment_total, 130.0)


if __name__ == "__main__":
    unittest.main()
