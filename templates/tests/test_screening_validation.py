#!/usr/bin/env python3
"""Tests for screening structure validation.

Run:
    uv run python -m pytest templates/tests/test_screening_validation.py -v
"""

import unittest


VALID_FULL = """\
## 기본 정보

| 항목 | 내용 |
|------|------|
| 회사명 | 테스트사 |
| 포지션 | 백엔드 개발자 |

## 스크리닝 결과

### 1. 회사 유형 및 안정성 (⭕)
기업 정보 완성도 80%. 재무 안정성 양호.

### 2. 성장 가능성 (⭕)
성장 잠재력 있음.

## 이력/경험 매칭

| 요건 | 매칭 | 근거 |
|------|------|------|
| Java 5년 이상 | ⭕ | [source: private/profile/skills-job.md] |
| Spring Boot | ⭕ | [source: private/companies/A/profile.md] |

## 최종 판정

### 최종 판정: 지원 추천

## 핵심 근거

- 기술 스택 일치도 높음
- 도메인 경험 존재
- 연봉 수준 적합
"""

VALID_WITH_INSIGHT_PREAMBLE = """\
`★ Insight ─────────────────────────────────────`
주목할 3가지 핵심 포인트:
1. **도메인 불일치** - 데이터 엔지니어링 중심
2. **기술 스택 전환** - TypeScript/NestJS 필수
3. **성장 vs 운영** - 혼재
`─────────────────────────────────────────────────`

JD 스크리닝을 시작하겠습니다.

---

## 기본 정보

| 항목 | 내용 |
|------|------|
| 회사명 | 테이텀 |
| 포지션 | 백엔드 개발자 |

## 스크리닝 결과

### 1. 회사 유형 및 안정성 (❌)
스타트업, 정보 불충분

## 이력/경험 매칭

| 요건 | 매칭 |
|------|------|
| TypeScript | △ |

## 최종 판정

### 최종 판정: 지원 비추천

## 핵심 근거

- 기술 스택 불일치
- 조직 안정성 미확인
- 도메인 차이
"""

TRUNCATED_INSIGHT_ONLY = """\
`★ Insight ─────────────────────────────────────`
- **퇴사율 81%**는 매우 이례적인 수치
- **경력 상한 5년**인 JD에 14년차가 지원하면 연봉 협상 어려움
- **스톡옵션으로 현금보상 대체** 구조적으로 수용 불가
`─────────────────────────────────────────────────`

## 최종 판정

### 최종 판정: 지원 보류
"""

TRUNCATED_SUMMARY_ONLY = """\
**요약**: 이 포지션은 반도체 DPU의 하드웨어 설계 검증 엔지니어로, 백엔드와는 완전히 다른 도메인입니다.

## 최종 판정

### 최종 판정: 지원 보류
"""

TRUNCATED_CONVERSATIONAL = """\
## 기본 정보

| 항목 | 내용 |
|------|------|
| 회사명 | 테스트사 |

## 스크리닝 결과

저장할 위치를 알려주세요.

Plan 파일을 작성하겠습니다.

진행 방식을 확인하겠습니다.

## 이력/경험 매칭

매칭 분석을 진행하겠습니다.

## 최종 판정

### 최종 판정: 지원 보류

권한을 요청합니다.

## 핵심 근거

- 분석 대기 중
"""

TRUNCATED_FALLBACK = """\
# JD 스크리닝 (자동 fallback)

## 기본 정보

- 파일: 12345-test.md

## 최종 판정

### 최종 판정: 지원 보류

## 핵심 근거

- LLM 스크리닝 실행 실패로 자동 보류 처리
- 사유: command not found
"""


class TestValidateScreeningStructure(unittest.TestCase):
    def setUp(self):
        from auto_screening import _validate_screening_structure
        self.validate = _validate_screening_structure

    def test_valid_full_output(self):
        valid, reason = self.validate(VALID_FULL)
        self.assertTrue(valid, f"Should be valid but got: {reason}")

    def test_valid_with_insight_preamble(self):
        valid, reason = self.validate(VALID_WITH_INSIGHT_PREAMBLE)
        self.assertTrue(valid, f"Should be valid but got: {reason}")

    def test_truncated_insight_only(self):
        valid, reason = self.validate(TRUNCATED_INSIGHT_ONLY)
        self.assertFalse(valid)
        self.assertIn("필수 섹션 누락", reason)

    def test_truncated_summary_only(self):
        valid, reason = self.validate(TRUNCATED_SUMMARY_ONLY)
        self.assertFalse(valid)
        self.assertIn("필수 섹션 누락", reason)

    def test_truncated_conversational_patterns(self):
        valid, reason = self.validate(TRUNCATED_CONVERSATIONAL)
        self.assertFalse(valid)
        self.assertIn("대화형 패턴", reason)

    def test_truncated_fallback_template(self):
        valid, reason = self.validate(TRUNCATED_FALLBACK)
        self.assertFalse(valid)
        self.assertIn("필수 섹션 누락", reason)

    def test_missing_section_screening_result(self):
        md = VALID_FULL.replace("## 스크리닝 결과", "## 스크리닝 요약")
        valid, reason = self.validate(md)
        self.assertFalse(valid)
        self.assertIn("## 스크리닝 결과", reason)

    def test_missing_section_experience_match(self):
        md = VALID_FULL.replace("## 이력/경험 매칭", "## 경험 비교")
        valid, reason = self.validate(md)
        self.assertFalse(valid)
        self.assertIn("## 이력/경험 매칭", reason)

    def test_missing_multiple_sections(self):
        md = "## 기본 정보\n\n테스트\n" * 5
        valid, reason = self.validate(md)
        self.assertFalse(valid)

    def test_headers_only_no_content(self):
        md = (
            "## 기본 정보\n\n"
            "## 스크리닝 결과\n\n"
            "## 이력/경험 매칭\n\n"
            "## 최종 판정\n\n"
            "### 최종 판정: 지원 보류\n\n"
            "## 핵심 근거\n"
        )
        valid, reason = self.validate(md)
        self.assertFalse(valid)
        self.assertIn("섹션 내용 부족", reason)

    def test_each_conversational_pattern(self):
        from auto_screening import _CONVERSATIONAL_PATTERNS
        base = VALID_FULL
        for pat in _CONVERSATIONAL_PATTERNS:
            md = base.replace("- 연봉 수준 적합", f"- 연봉 수준 적합\n- {pat}")
            valid, reason = self.validate(md)
            self.assertFalse(valid, f"Pattern '{pat}' should be detected")
            self.assertIn("대화형 패턴", reason)


if __name__ == "__main__":
    unittest.main()
