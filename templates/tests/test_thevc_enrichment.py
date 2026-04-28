#!/usr/bin/env python3
"""Tests for TheVC bulk enrichment candidate selection."""

import tempfile
import unittest
from pathlib import Path

from enrich_thevc_company_info import scan_candidates


LabradorLike = """# 래브라도랩스

## 기업 정보

| 항목 | 내용 |
|------|------|
| 회사명 | 래브라도랩스 |
| 업종 | IT |
| 설립 | 2018년 |
| 직원수 | 36명 |

## 연봉 정보

| 항목 | 금액 | 출처 |
|------|------|------|
| 평균 연봉 | **5680만원** | Wanted |

## 인원 통계

| 항목 | 수치 |
|------|------|
| 현재 인원 | 36명 |
| 1년간 입사자 | 15명 |
| 1년간 퇴사자 | 11명 |

## 투자 정보

| 항목 | 내용 |
|------|------|
| 현재 라운드 | Series B |
| 누적 투자금 | 100억원 |

## 태그
- 인원 급성장
"""


class TestThevcEnrichmentScan(unittest.TestCase):
    def test_labrador_like_complete_startup_without_thevc_is_candidate(self):
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            file_path = tmp_path / "래브라도랩스.md"
            file_path.write_text(LabradorLike, encoding="utf-8")

            candidates = scan_candidates(tmp_path, min_completeness=70)

        self.assertEqual([c.file_path.name for c in candidates], ["래브라도랩스.md"])
        self.assertEqual(candidates[0].investment_round, "Series B")

    def test_explicit_no_or_listed_company_is_excluded(self):
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            (tmp_path / "상장사.md").write_text(
                LabradorLike.replace("# 래브라도랩스", "# 상장사").replace(
                    "| 현재 라운드 | Series B |", "| 현재 라운드 | IPO |"
                ),
                encoding="utf-8",
            )
            (tmp_path / "비스타트업.md").write_text(
                LabradorLike.replace("# 래브라도랩스", "# 비스타트업").replace(
                    "| 회사명 | 래브라도랩스 |", "| 회사명 | 비스타트업 |\n| 스타트업 여부 | No |"
                ),
                encoding="utf-8",
            )

            candidates = scan_candidates(tmp_path, min_completeness=70)

        self.assertEqual(candidates, [])

    def test_existing_thevc_source_is_excluded(self):
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            (tmp_path / "출처있음.md").write_text(
                LabradorLike + "\n출처: https://thevc.kr/labradorlabs\n",
                encoding="utf-8",
            )

            candidates = scan_candidates(tmp_path, min_completeness=70)

        self.assertEqual(candidates, [])


if __name__ == "__main__":
    unittest.main()
