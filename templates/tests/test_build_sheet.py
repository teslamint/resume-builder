#!/usr/bin/env python3
"""Tests for interview sheet builder (build-sheet.py).

Run with:
    python3 templates/tests/test_build_sheet.py
    python3 templates/tests/test_build_sheet.py -v

Or with pytest (if installed):
    pytest templates/tests/test_build_sheet.py -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "jd_analysis" / "interview"))

from importlib import import_module

# build-sheet.py has a hyphen, need importlib
import importlib.util
_spec = importlib.util.spec_from_file_location(
    "build_sheet",
    Path(__file__).parent.parent.parent / "jd_analysis" / "interview" / "build-sheet.py"
)
build_sheet = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_sheet)


SAMPLE_MD_WITH_ASSIGNMENT = """
## 기본 정보

| 항목 | 내용 |
|------|------|
| 회사명 | TestCo |
| 포지션 | Backend Engineer |
| 면접 단계 | 1st Interview |

## 0. 왜 TestCo인가

> "테스트를 위한 지원 서사입니다."

## 예상 질문 & 답변 가이드

### 기술 질문

| 질문 | 답변 포인트 |
|------|-------------|
| TypeScript 경험? | 3년 경력 |
| 아키텍처 패턴? | Clean Architecture |

### 조직적합성 질문

| 질문 | 답변 포인트 |
|------|-------------|
| 팀 리더 경험? | IC 포지셔닝 |

## 선행과제 방어

### 아키텍처 개요

```
[Input] → Parser → [AST] → Evaluator → [Result]
                              ↑
                        RuleEngine
```

| Module | Role |
|--------|------|
| Parser | DSL 파싱 |
| Evaluator | 조건 평가 |
| RuleEngine | 정책 적용 |

### 핵심 설계 결정

| Decision | Rationale | Trade-off |
|----------|-----------|-----------|
| Object syntax | 확장성 | 장황함 |
| Fail-closed | 보안 우선 | 전면 차단 위험 |

### 예상 Q&A

| 질문 | 답변 포인트 |
|------|-------------|
| 왜 Object syntax? | 확장성 |
| fail-closed 장단점? | 보안 vs 가용성 |
| Production 개선? | 캐싱, 감사 |

### Production 개선

- **캐시 + TTL**: context 캐싱
- **와일드카드 권한**: 정책 중복 감소
- **감사 로깅**: 결과 영속화

## 1. 리스크 검증 질문

### 조직 안정성

| 질문 | 의도 |
|------|------|
| 팀 규모? | 안정성 확인 |

### 업무 범위

| 질문 | 의도 |
|------|------|
| 신규개발 비중? | 업무 범위 |

### 워라밸

| 질문 | 의도 |
|------|------|
| 근무시간? | 워라밸 |

### 연봉

| 질문 | 의도 |
|------|------|
| 연봉 범위? | 처우 |

## 2. 라이브 코딩 테스트 대비

### 예상 유형

| 유형 | 가능성 | 맥락 |
|------|--------|------|
| 알고리즘 | 중 | 기본 |

## 3. 조직적합성 면접 대비

### [My Positioning] Q&A

| 질문 | 답변 프레임 |
|------|-------------|
| 리더십? | IC |

### 주의사항

- ❌ "관리 경험 강조"
- ⭕ "기술 기여 강조"

## 5. 역질문 리스트

- "팀 구성은?"
- "기술 스택은?"

## 8. 최종 판단 기준

### 필수 조건
- [ ] 안정적 팀
- [ ] IC 보장

### 우대 조건
- [ ] 원격 근무
"""

SAMPLE_MD_NO_ASSIGNMENT = """
## 기본 정보

| 항목 | 내용 |
|------|------|
| 회사명 | NoCo |
| 포지션 | Backend |
| 면접 단계 | 1st |

## 0. 왜 NoCo인가

> "서사"

## 예상 질문 & 답변 가이드

### KDL 맞춤 질문

| 질문 | 답변 포인트 |
|------|-------------|
| 경험? | 있음 |

### 압박/포지셔닝 질문

| 질문 | 답변 포인트 |
|------|-------------|
| 약점? | 없음 |

## 1. 리스크 검증 질문

### 조직 안정성

| 질문 | 의도 |
|------|------|
| 규모? | 안정성 |

### 업무 범위

| 질문 | 의도 |
|------|------|
| 범위? | 확인 |

### 워라밸

| 질문 | 의도 |
|------|------|
| 시간? | 확인 |

### 연봉

| 질문 | 의도 |
|------|------|
| 범위? | 확인 |

## 2. 화이트보드 테스트 대비

### 예상 유형

| 유형 | 가능성 | KDL 맥락 |
|------|--------|----------|
| 설계 | 상 | 인프라 |

## 3. 조직적합성 면접 대비

### [My Positioning] Q&A

| 질문 | 답변 프레임 |
|------|-------------|
| 역할? | IC |

### 주의사항

- ❌ "안됨"
- ⭕ "됨"

## 5. 역질문 리스트

- "질문1"

## 8. 최종 판단 기준

### 필수 조건
- [ ] 조건1

### 우대 조건
- [ ] 우대1
"""


class TestExtractExpectedQuestions(unittest.TestCase):
    """extract_expected_questions() 동적 카테고리 검출 테스트."""

    def test_dynamic_categories_with_assignment(self):
        result = build_sheet.extract_expected_questions(SAMPLE_MD_WITH_ASSIGNMENT)
        self.assertIn('기술 질문', result)
        self.assertIn('조직적합성 질문', result)
        self.assertEqual(len(result), 2)

    def test_dynamic_categories_no_assignment(self):
        result = build_sheet.extract_expected_questions(SAMPLE_MD_NO_ASSIGNMENT)
        self.assertIn('KDL 맞춤 질문', result)
        self.assertIn('압박/포지셔닝 질문', result)
        self.assertEqual(len(result), 2)

    def test_empty_content(self):
        result = build_sheet.extract_expected_questions('')
        self.assertEqual(result, {})

    def test_table_content_preserved(self):
        result = build_sheet.extract_expected_questions(SAMPLE_MD_WITH_ASSIGNMENT)
        tech_qs = result['기술 질문']
        self.assertEqual(len(tech_qs), 2)
        self.assertEqual(tech_qs[0]['질문'], 'TypeScript 경험?')


class TestExtractAssignmentDefense(unittest.TestCase):
    """extract_assignment_defense() 추출 테스트."""

    def test_extracts_all_fields(self):
        result = build_sheet.extract_assignment_defense(SAMPLE_MD_WITH_ASSIGNMENT)
        self.assertIn('architecture', result)
        self.assertIn('decisions', result)
        self.assertIn('qa', result)
        self.assertIn('production', result)

    def test_architecture_not_empty(self):
        result = build_sheet.extract_assignment_defense(SAMPLE_MD_WITH_ASSIGNMENT)
        self.assertTrue(len(result['architecture']) > 0)

    def test_decisions_count(self):
        result = build_sheet.extract_assignment_defense(SAMPLE_MD_WITH_ASSIGNMENT)
        self.assertEqual(len(result['decisions']), 2)

    def test_qa_count(self):
        result = build_sheet.extract_assignment_defense(SAMPLE_MD_WITH_ASSIGNMENT)
        self.assertEqual(len(result['qa']), 3)

    def test_production_count(self):
        result = build_sheet.extract_assignment_defense(SAMPLE_MD_WITH_ASSIGNMENT)
        self.assertEqual(len(result['production']), 3)

    def test_production_strips_bold(self):
        result = build_sheet.extract_assignment_defense(SAMPLE_MD_WITH_ASSIGNMENT)
        for item in result['production']:
            self.assertNotIn('**', item)

    def test_empty_when_no_section(self):
        result = build_sheet.extract_assignment_defense(SAMPLE_MD_NO_ASSIGNMENT)
        self.assertEqual(result, {})


class TestConditionalSecAssign(unittest.TestCase):
    """sec-assign 조건부 활성화 테스트."""

    def test_sec_assign_included_when_present(self):
        """선행과제 있으면 sec-assign 포함."""
        html_out = build_sheet.build_html(
            SAMPLE_MD_WITH_ASSIGNMENT,
            Path('style-sheet.css'),
            pages=None
        )
        self.assertIn('id="sec-assign"', html_out)

    def test_sec_assign_excluded_when_absent(self):
        """선행과제 없으면 sec-assign 제외."""
        html_out = build_sheet.build_html(
            SAMPLE_MD_NO_ASSIGNMENT,
            Path('style-sheet.css'),
            pages=None
        )
        self.assertNotIn('id="sec-assign"', html_out)

    def test_tab_nav_excludes_asgn_when_absent(self):
        """선행과제 없으면 ASGN 탭도 제외."""
        html_out = build_sheet.build_html(
            SAMPLE_MD_NO_ASSIGNMENT,
            Path('style-sheet.css'),
            pages=None
        )
        self.assertNotIn('href="#sec-assign"', html_out)

    def test_tab_nav_includes_asgn_when_present(self):
        """선행과제 있으면 ASGN 탭 포함."""
        html_out = build_sheet.build_html(
            SAMPLE_MD_WITH_ASSIGNMENT,
            Path('style-sheet.css'),
            pages=None
        )
        self.assertIn('href="#sec-assign"', html_out)

    def test_stage_preset_with_no_assignment(self):
        """실무 프리셋 + 선행과제 없으면 sec-assign 자동 제거."""
        pages = list(build_sheet.STAGE_PRESETS['실무'])
        html_out = build_sheet.build_html(
            SAMPLE_MD_NO_ASSIGNMENT,
            Path('style-sheet.css'),
            pages=pages
        )
        self.assertNotIn('id="sec-assign"', html_out)


class TestRenderArchitectureHtml(unittest.TestCase):
    """render_architecture_html() 렌더링 테스트."""

    def test_code_block_to_pre(self):
        text = "```\n[A] → [B] → [C]\n```"
        result = build_sheet.render_architecture_html(text)
        self.assertIn('<pre class="arch-diagram">', result)
        self.assertIn('[A]', result)
        self.assertNotIn('```', result)

    def test_table_to_html_table(self):
        text = "| Module | Role |\n|--------|------|\n| Parser | 파싱 |\n| Engine | 평가 |"
        result = build_sheet.render_architecture_html(text)
        self.assertIn('<table class="arch-table">', result)
        self.assertIn('<th>Module</th>', result)
        self.assertIn('<td>Parser</td>', result)
        self.assertIn('<td>Engine</td>', result)
        self.assertNotIn('|', result)

    def test_plain_text_to_arch_item(self):
        text = "Some architecture note"
        result = build_sheet.render_architecture_html(text)
        self.assertIn('<div class="arch-item">', result)
        self.assertIn('Some architecture note', result)

    def test_mixed_content(self):
        text = """```
[A] → [B]
```

| Col1 | Col2 |
|------|------|
| a | b |

Plain text here"""
        result = build_sheet.render_architecture_html(text)
        self.assertIn('<pre class="arch-diagram">', result)
        self.assertIn('<table class="arch-table">', result)
        self.assertIn('<div class="arch-item">', result)

    def test_html_escaping(self):
        text = "Use <script> & \"quotes\""
        result = build_sheet.render_architecture_html(text)
        self.assertIn('&lt;script&gt;', result)
        self.assertIn('&amp;', result)

    def test_code_block_preserves_indentation(self):
        text = "```\n  indented\n    more indented\n```"
        result = build_sheet.render_architecture_html(text)
        self.assertIn('  indented', result)
        self.assertIn('    more indented', result)

    def test_separator_line_skipped_in_table(self):
        text = "| H1 | H2 |\n|-----|-----|\n| v1 | v2 |"
        result = build_sheet.render_architecture_html(text)
        self.assertNotIn('-----', result)


class TestBuildAssignmentPage(unittest.TestCase):
    """build_assignment_page() 출력 테스트."""

    def test_empty_assignment_returns_empty(self):
        self.assertEqual(build_sheet.build_assignment_page({}), '')

    def test_two_page_structure(self):
        assignment = build_sheet.extract_assignment_defense(SAMPLE_MD_WITH_ASSIGNMENT)
        result = build_sheet.build_assignment_page(assignment)
        self.assertIn('id="sec-assign"', result)
        self.assertIn('id="sec-assign-2"', result)

    def test_architecture_rendered_as_pre(self):
        assignment = build_sheet.extract_assignment_defense(SAMPLE_MD_WITH_ASSIGNMENT)
        result = build_sheet.build_assignment_page(assignment)
        self.assertIn('<pre class="arch-diagram">', result)

    def test_architecture_table_rendered(self):
        assignment = build_sheet.extract_assignment_defense(SAMPLE_MD_WITH_ASSIGNMENT)
        result = build_sheet.build_assignment_page(assignment)
        self.assertIn('<table class="arch-table">', result)

    def test_decisions_table_rendered(self):
        assignment = build_sheet.extract_assignment_defense(SAMPLE_MD_WITH_ASSIGNMENT)
        result = build_sheet.build_assignment_page(assignment)
        self.assertIn('class="decision-table"', result)

    def test_qa_table_rendered(self):
        assignment = build_sheet.extract_assignment_defense(SAMPLE_MD_WITH_ASSIGNMENT)
        result = build_sheet.build_assignment_page(assignment)
        self.assertIn('class="qa-table"', result)

    def test_production_list_rendered(self):
        assignment = build_sheet.extract_assignment_defense(SAMPLE_MD_WITH_ASSIGNMENT)
        result = build_sheet.build_assignment_page(assignment)
        self.assertIn('<li>', result)
        self.assertIn('context', result)


class TestTechnicalTestExtraction(unittest.TestCase):
    """기술 테스트 유형 검출 테스트."""

    def test_whiteboard_detection(self):
        test_type, _ = build_sheet.extract_technical_test(SAMPLE_MD_NO_ASSIGNMENT)
        self.assertEqual(test_type, '화이트보드')

    def test_live_coding_detection(self):
        test_type, _ = build_sheet.extract_technical_test(SAMPLE_MD_WITH_ASSIGNMENT)
        self.assertEqual(test_type, '라이브 코딩')


SAMPLE_MD_FREEFORM_QA = """
## 기본 정보

| 항목 | 내용 |
|------|------|
| 회사명 | FreeFormCo |
| 포지션 | Backend Engineer |
| 면접 단계 | 1st Interview |

## 0. 왜 FreeFormCo인가

> "자유형식 테스트용"

## 예상 질문 & 답변 가이드

### 기초 검증 (면접관이 먼저 던질 질문)

**Q1. "Clojure 경험이 없는데 어떻게 기여할 건가?"**

> Polyglot 14년 경력. Kotlin FP 스타일이 Clojure와 유사

<details>
<summary>해설</summary>

- 왜 이 질문이 나오는가: JD에 Clojure 명시
</details>

---

**Q2. "생성형 AI 활용 경험?"**

> 실서비스 중심 경험 있음.
> OpenAI/Anthropic API 연동 운영 경험

<details>
<summary>해설</summary>

- JD 필수 요건
</details>

**Q3. "제품을 어떻게 이해하나?"**

> Figma 보완재. HW Integration이 차별점

### 심화 기술 (JD 기대업무 직결)

**Q4. "실시간 동시편집 시스템을 어떻게 접근하겠는가?"**

> CRDT vs OT 트레이드오프 설명. 인접 경험 있음

**Q5. "멀티테넌시 아키텍처 경험?"**

> B2B Wi-Fi 솔루션에서 테넌트 격리 운영

### 포지셔닝 (IC 역할 검증)

**Q6. "왜 IC를 원하나요?"**

> 기술적 기여에 집중하는 쪽에 강점

## 1. 리스크 검증 질문

### 조직 안정성

| 질문 | 의도 |
|------|------|
| 팀 규모? | 안정성 확인 |

### 업무 범위

| 질문 | 의도 |
|------|------|
| 범위? | 확인 |

### 워라밸

| 질문 | 의도 |
|------|------|
| 시간? | 확인 |

### 연봉

| 질문 | 의도 |
|------|------|
| 범위? | 확인 |

## 2. 화이트보드 테스트 대비

### 예상 유형

| 유형 | 가능성 | 맥락 |
|------|--------|------|
| 설계 | 상 | 인프라 |

## 3. 조직적합성 면접 대비

### [My Positioning] Q&A

| 질문 | 답변 프레임 |
|------|-------------|
| 역할? | IC |

### 주의사항

- ❌ "안됨"
- ⭕ "됨"

## 5. 역질문 리스트

- "질문1"

## 8. 최종 판단 기준

### 필수 조건
- [ ] 조건1

### 우대 조건
- [ ] 우대1
"""

SAMPLE_MD_MIXED_TABLE_AND_FREEFORM = """
## 예상 질문 & 답변 가이드

### 테이블 카테고리

| 질문 | 답변 포인트 |
|------|-------------|
| 테이블 Q? | 테이블 A |

### 자유형식 카테고리

**Q1. "자유형식 질문?"**

> 자유형식 답변
"""


class TestExtractFreeformQuestions(unittest.TestCase):
    """자유형식 Q&A 파싱 테스트."""

    def test_freeform_qa_extraction(self):
        result = build_sheet.extract_expected_questions(SAMPLE_MD_FREEFORM_QA)
        self.assertIn('기초 검증 (면접관이 먼저 던질 질문)', result)
        basic = result['기초 검증 (면접관이 먼저 던질 질문)']
        self.assertEqual(basic[0]['질문'], 'Clojure 경험이 없는데 어떻게 기여할 건가?')
        self.assertIn('Polyglot', basic[0]['답변 포인트'])

    def test_freeform_mixed_with_table(self):
        result = build_sheet.extract_expected_questions(SAMPLE_MD_MIXED_TABLE_AND_FREEFORM)
        self.assertIn('테이블 카테고리', result)
        self.assertIn('자유형식 카테고리', result)
        self.assertEqual(result['테이블 카테고리'][0]['질문'], '테이블 Q?')
        self.assertEqual(result['자유형식 카테고리'][0]['질문'], '자유형식 질문?')

    def test_freeform_multiline_answer(self):
        result = build_sheet.extract_expected_questions(SAMPLE_MD_FREEFORM_QA)
        basic = result['기초 검증 (면접관이 먼저 던질 질문)']
        q2 = next(q for q in basic if '생성형 AI' in q['질문'])
        self.assertIn('실서비스 중심', q2['답변 포인트'])
        self.assertIn('OpenAI/Anthropic', q2['답변 포인트'])

    def test_freeform_details_ignored(self):
        result = build_sheet.extract_expected_questions(SAMPLE_MD_FREEFORM_QA)
        basic = result['기초 검증 (면접관이 먼저 던질 질문)']
        for q in basic:
            self.assertNotIn('해설', q['답변 포인트'])
            self.assertNotIn('JD에', q['답변 포인트'])

    def test_freeform_category_count(self):
        result = build_sheet.extract_expected_questions(SAMPLE_MD_FREEFORM_QA)
        expected = {'기초 검증 (면접관이 먼저 던질 질문)', '심화 기술 (JD 기대업무 직결)', '포지셔닝 (IC 역할 검증)'}
        self.assertEqual(set(result.keys()), expected)


class TestExpectedQuestionsRegression(unittest.TestCase):
    """기존 테이블 형식 Q&A 회귀 테스트."""

    def test_table_format_still_works(self):
        result = build_sheet.extract_expected_questions(SAMPLE_MD_WITH_ASSIGNMENT)
        self.assertIn('기술 질문', result)
        self.assertEqual(len(result['기술 질문']), 2)

    def test_table_format_no_assignment_still_works(self):
        result = build_sheet.extract_expected_questions(SAMPLE_MD_NO_ASSIGNMENT)
        self.assertIn('KDL 맞춤 질문', result)
        self.assertIn('압박/포지셔닝 질문', result)

    def test_table_values_unchanged(self):
        result = build_sheet.extract_expected_questions(SAMPLE_MD_WITH_ASSIGNMENT)
        tech = result['기술 질문']
        self.assertEqual(tech[0]['질문'], 'TypeScript 경험?')
        self.assertEqual(tech[0]['답변 포인트'], '3년 경력')
        self.assertEqual(tech[1]['질문'], '아키텍처 패턴?')
        self.assertEqual(tech[1]['답변 포인트'], 'Clean Architecture')

    def test_empty_section_still_empty(self):
        result = build_sheet.extract_expected_questions('')
        self.assertEqual(result, {})

    def test_build_html_exp_page_rendered(self):
        html_out = build_sheet.build_html(SAMPLE_MD_FREEFORM_QA, Path('style-sheet.css'))
        self.assertIn('id="sec-exp"', html_out)
        self.assertIn('Clojure', html_out)
        self.assertIn('Polyglot', html_out)

    def test_build_html_table_exp_page_unchanged(self):
        html_out = build_sheet.build_html(SAMPLE_MD_WITH_ASSIGNMENT, Path('style-sheet.css'))
        self.assertIn('id="sec-exp"', html_out)
        self.assertIn('TypeScript', html_out)
        self.assertIn('3년 경력', html_out)


if __name__ == '__main__':
    unittest.main()
