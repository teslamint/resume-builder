"""Focused characterization tests for auto_company.ensure_company_info."""

from types import SimpleNamespace
from unittest.mock import patch


def _write_jd(tmp_path, company: str, extra: str = ""):
    jd_path = tmp_path / "jd.md"
    jd_path.write_text(
        "# Backend\n\n"
        f"{extra}\n\n"
        "## 기본 정보\n\n"
        "| 항목 | 내용 |\n"
        "|------|------|\n"
        f"| 회사명 | {company} |\n"
        "| 출처 | [Wanted](https://www.wanted.co.kr/wd/123456) |\n",
        encoding="utf-8",
    )
    return jd_path


def _existing_company_file(company_dir, filename="startupco.md"):
    company_file = company_dir / filename
    company_file.write_text(
        "# StartupCo\n\n"
        "## 기업 정보\n\n"
        "| 항목 | 내용 |\n|------|------|\n"
        "| 회사명 | StartupCo |\n| 설립 | 2021년 |\n| 직원수 | 30명 |\n\n"
        "## 연봉 정보\n\n"
        "| 항목 | 금액 | 출처 |\n|------|------|------|\n"
        "| 평균 연봉 | **5000만원** | test |\n\n"
        "---\n",
        encoding="utf-8",
    )
    return company_file


class TestEnsureCompanyInfoCharacterization:
    def test_headhunting_company_writes_exclusion_stub(self, tmp_path):
        from auto_company import ensure_company_info

        company_dir = tmp_path / "company_info"
        jd_path = _write_jd(tmp_path, "굿서치펌")

        with patch("auto_company.COMPANY_INFO_DIR", company_dir):
            result = ensure_company_info(
                jd_path=jd_path,
                jd_url="https://www.wanted.co.kr/wd/123456",
                company_name="굿서치펌",
            )

        assert result.company == "굿서치펌"
        assert result.used_existing is True
        assert result.completeness == 0.0
        assert result.thevc_attempted is False
        assert result.thevc_status == "skipped"
        assert result.investment_data_source == "headhunting_excluded"
        assert result.file_path.exists()
        assert "정보 수집 제외 대상" in result.file_path.read_text(encoding="utf-8")

    def test_existing_startup_enriches_with_thevc_when_missing_investment(self, tmp_path):
        from auto_company import ensure_company_info

        company_dir = tmp_path / "company_info"
        company_dir.mkdir()
        existing = _existing_company_file(company_dir)
        jd_path = _write_jd(tmp_path, "StartupCo", extra="시리즈 A 스타트업")
        company_data = SimpleNamespace(
            is_startup=True,
            investment_round=None,
            investment_total=None,
        )
        validation = SimpleNamespace(completeness_score=90.0)
        investment = {
            "round": "Series A",
            "total": "100억원",
            "source": "https://thevc.kr/startupco",
        }

        with patch("auto_company.COMPANY_INFO_DIR", company_dir), \
             patch("auto_company.parse_company_file", return_value=company_data), \
             patch("auto_company.validate_company", return_value=validation), \
             patch("auto_company._extract_thevc_investment", return_value=("success", investment)) as mock_thevc, \
             patch("auto_company._completeness_score", return_value=95.0):
            result = ensure_company_info(
                jd_path=jd_path,
                jd_url="https://www.wanted.co.kr/wd/123456",
                company_name="StartupCo",
                min_completeness=70.0,
            )

        mock_thevc.assert_called_once_with("StartupCo")
        assert result.file_path == existing
        assert result.used_existing is True
        assert result.completeness == 95.0
        assert result.thevc_attempted is True
        assert result.thevc_status == "success"
        assert result.investment_data_source == "thevc"
        content = existing.read_text(encoding="utf-8")
        assert "## 투자 정보" in content
        assert "| 현재 라운드 | Series A |" in content

    def test_existing_startup_skip_mode_reuses_file_without_thevc(self, tmp_path):
        from auto_company import ensure_company_info

        company_dir = tmp_path / "company_info"
        company_dir.mkdir()
        existing = _existing_company_file(company_dir)
        jd_path = _write_jd(tmp_path, "StartupCo", extra="시리즈 A 스타트업")
        company_data = SimpleNamespace(
            is_startup=True,
            investment_round=None,
            investment_total=None,
        )
        validation = SimpleNamespace(completeness_score=90.0)

        with patch("auto_company.COMPANY_INFO_DIR", company_dir), \
             patch("auto_company.parse_company_file", return_value=company_data), \
             patch("auto_company.validate_company", return_value=validation), \
             patch("auto_company.verify_company_match", return_value=(True, 1.0, [])), \
             patch("auto_company._extract_thevc_investment") as mock_thevc:
            result = ensure_company_info(
                jd_path=jd_path,
                jd_url="https://www.wanted.co.kr/wd/123456",
                company_name="StartupCo",
                thevc_mode="skip",
                min_completeness=70.0,
            )

        mock_thevc.assert_not_called()
        assert result.file_path == existing
        assert result.used_existing is True
        assert result.completeness == 90.0
        assert result.thevc_attempted is False
        assert result.thevc_status == "skipped"
        assert result.investment_data_source == "existing"

    def test_new_company_uses_extracted_company_info_when_available(self, tmp_path):
        from auto_company import ensure_company_info

        company_dir = tmp_path / "company_info"
        company_dir.mkdir()
        extracted_file = company_dir / "extractedco.md"
        extraction = SimpleNamespace(
            platforms_used=["wanted"],
            platforms_failed=[],
            file_path=extracted_file,
        )
        validation = SimpleNamespace(completeness_score=88.0)
        jd_path = _write_jd(tmp_path, "ExtractedCo")

        def extract_company_info(**kwargs):
            extracted_file.write_text("# ExtractedCo\n", encoding="utf-8")
            return extraction

        with patch("auto_company.COMPANY_INFO_DIR", company_dir), \
             patch("auto_company.extract_company_info", side_effect=extract_company_info) as mock_extract, \
             patch("auto_company.parse_company_file", return_value=SimpleNamespace(is_startup=False)), \
             patch("auto_company.validate_company", return_value=validation), \
             patch("auto_company.verify_company_match", return_value=(True, 1.0, [])):
            result = ensure_company_info(
                jd_path=jd_path,
                jd_url="https://www.wanted.co.kr/wd/123456",
                company_name="ExtractedCo",
            )

        mock_extract.assert_called_once_with(
            company_name="ExtractedCo",
            platforms=["wanted", "saramin"],
        )
        assert result.file_path == extracted_file
        assert result.used_existing is False
        assert result.completeness == 88.0
        assert result.thevc_attempted is False
        assert result.investment_data_source == "extraction"

    def test_new_company_falls_back_to_stub_when_extraction_fails(self, tmp_path):
        from auto_company import ensure_company_info

        company_dir = tmp_path / "company_info"
        jd_path = _write_jd(tmp_path, "StubCo")

        with patch("auto_company.COMPANY_INFO_DIR", company_dir), \
             patch("auto_company.extract_company_info", side_effect=RuntimeError("no browser")), \
             patch("auto_company.parse_company_file", return_value=SimpleNamespace(is_startup=False)), \
             patch("auto_company.validate_company", return_value=SimpleNamespace(completeness_score=0.0)), \
             patch("auto_company.verify_company_match", return_value=(True, 1.0, [])):
            result = ensure_company_info(
                jd_path=jd_path,
                jd_url="https://www.wanted.co.kr/wd/123456",
                company_name="StubCo",
            )

        assert result.file_path == company_dir / "stubco.md"
        assert result.file_path.exists()
        assert result.used_existing is False
        assert result.completeness == 0.0
        assert result.thevc_attempted is False
        assert result.investment_data_source == "none"
        content = result.file_path.read_text(encoding="utf-8")
        assert "| 회사명 | StubCo |" in content
        assert "| 업종 | 정보 없음 |" in content
