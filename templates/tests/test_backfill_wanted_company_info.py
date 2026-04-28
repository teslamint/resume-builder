import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "jd"))


class TestBackfillWantedCompanyInfo(unittest.TestCase):
    def test_extracts_wanted_jd_id(self):
        from backfill_wanted_company_info import _wanted_jd_id

        self.assertEqual(_wanted_jd_id("https://www.wanted.co.kr/wd/330723"), "330723")
        self.assertIsNone(_wanted_jd_id("https://career.rememberapp.co.kr/job/posting/1"))

    def test_backfills_exact_target_file(self):
        from backfill_wanted_company_info import backfill_target
        from enrich_company_fields import TargetInfo
        from ce_types import PlatformData

        with tempfile.TemporaryDirectory() as tmp:
            company_dir = Path(tmp) / "company_info"
            company_dir.mkdir()
            target_file = company_dir / "네오랩컨버전스-neolab.md"
            target_file.write_text("# 네오랩컨버전스(NeoLab)\n", encoding="utf-8")

            target = TargetInfo(
                file_name=target_file.name,
                company_name="네오랩컨버전스",
                empty_count=10,
                completeness=0,
                wanted_url=None,
                jd_source_url="https://www.wanted.co.kr/wd/330723",
            )
            data = PlatformData(
                platform="wanted",
                source_url="https://www.wanted.co.kr/company/2018",
                company_name="네오랩컨버전스(NeoLab)",
                industry="IT",
                founded_year=2009,
                employee_count=100,
                avg_salary=5000,
            )

            with patch("backfill_wanted_company_info.COMPANY_INFO_DIR", company_dir), \
                 patch("backfill_wanted_company_info.fetch_wanted_posting", return_value={"company": {"company_name": "네오랩컨버전스(NeoLab)", "company_id": 2018}}), \
                 patch("backfill_wanted_company_info._platform_data_from_wanted", return_value=data):
                result = backfill_target(target)

            text = target_file.read_text(encoding="utf-8")
            self.assertEqual(result.status, "backfilled")
            self.assertIn("| 설립 | 2009년 |", text)
            self.assertIn("| 직원수 | 100명 |", text)
            self.assertIn("https://www.wanted.co.kr/company/2018", text)


if __name__ == "__main__":
    unittest.main()
