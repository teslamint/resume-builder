#!/usr/bin/env python3
"""Synthetic screening-rule regression tests.

These fixtures intentionally avoid private/ files. The LLM call is mocked so
the test covers prompt wiring, structural validation, and verdict parsing with
controlled JD/company inputs.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import auto_screening


SYNTHETIC_RULES = """\
# Synthetic JD Screening Rules

## 0.5 evidence hierarchy
- 자격요건, 우대사항, 주요업무 are primary evidence.
- 포지션 소개 and branding copy are secondary evidence.

## Startup four-condition screen
1. 연봉 수용 가능
2. 리드 전가 없음
3. 업무 범위가 감당 가능한 수준
4. 조직 변동성이 감수 가능한 수준

## Polyglot
- Stack mismatch alone is not a rejection reason.
"""

SYNTHETIC_CANDIDATE_CONTEXT = """\
[source: synthetic/profile.md]
- Senior backend engineer with Java/Kotlin, Python, and TypeScript experience.
- Prefers coding-heavy IC/staff roles with bounded technical leadership.
"""


def _company_markdown(
    *,
    name: str = "Synthetic Startup",
    founded: int = 2019,
    current: int = 80,
    joined: int = 18,
    left: int = 6,
    salary: str = "9,200",
    percentile: str = "상위 12%",
    round_name: str = "Series B",
    investment: str = "180",
) -> str:
    return f"""\
# {name}

## 기업 정보

| 항목 | 내용 |
|------|------|
| 회사명 | {name} |
| 설립연도 | {founded}년 |
| 직원수 | {current}명 |
| 스타트업 여부 | yes |

## 인원 현황

| 항목 | 내용 |
|------|------|
| 현재 인원 | {current}명 |
| 1년간 입사자 | {joined}명 |
| 1년간 퇴사자 | {left}명 |

## 연봉 정보

| 항목 | 금액 | 출처 |
|------|------|------|
| 평균 연봉 | **{salary}만원** | synthetic |
| 연봉 퍼센트 | {percentile} | synthetic |

## 투자 정보

| 항목 | 내용 |
|------|------|
| 현재 라운드 | {round_name} |
| 누적 투자금 | {investment}억원 |
"""


def _screening_output(
    *,
    company: str,
    position: str,
    condition: str,
    condition_judgment: str,
    match_note: str,
    verdict: str,
    reasons: list[str],
) -> str:
    reason_lines = "\n".join(f"- {reason}" for reason in reasons)
    return f"""\
## 기본 정보

| 항목 | 내용 |
|------|------|
| 회사명 | {company} |
| 포지션 | {position} |

## 스크리닝 결과

| 조건 | 판단 | 근거 |
|------|------|------|
| {condition} | {condition_judgment} | synthetic JD/company evidence |

## 이력/경험 매칭

| 요건 | 매칭 | 근거 |
|------|------|------|
| Backend ownership | O | {match_note} |

## 최종 판정

### 최종 판정: {verdict}

## 핵심 근거

{reason_lines}
"""


def _run_synthetic_screening(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    jd_content: str,
    company_content: str,
    llm_output: str,
    prompt_snippets: list[str],
) -> auto_screening.ScreeningResult:
    jd_path = tmp_path / "999001-synthetic-backend.md"
    company_path = tmp_path / "synthetic-company.md"
    jd_path.write_text(jd_content, encoding="utf-8")
    company_path.write_text(company_content, encoding="utf-8")

    monkeypatch.setenv("CLAUDE_SCREENING_CMD", "fake-llm --print")
    monkeypatch.delenv("CODEX_SCREENING_CMD", raising=False)
    monkeypatch.setattr(auto_screening, "SCREENING_DIR", tmp_path / "screening")
    monkeypatch.setattr(auto_screening, "load_screening_rules", lambda: SYNTHETIC_RULES)
    monkeypatch.setattr(
        auto_screening,
        "_load_candidate_context",
        lambda: SYNTHETIC_CANDIDATE_CONTEXT,
    )

    def fake_run(cmd, input, text, capture_output, timeout, env):
        assert cmd == ["fake-llm", "--print"]
        assert text is True
        assert capture_output is True
        assert timeout == 10
        assert SYNTHETIC_RULES in input
        assert SYNTHETIC_CANDIDATE_CONTEXT in input
        for snippet in prompt_snippets:
            assert snippet in input
        return subprocess.CompletedProcess(cmd, 0, stdout=llm_output, stderr="")

    monkeypatch.setattr(auto_screening.subprocess, "run", fake_run)

    return auto_screening.run_screening(
        jd_path=jd_path,
        company_file=company_path,
        llm_timeout=10,
        dry_run=True,
    )


@pytest.mark.parametrize(
    ("case_name", "jd_content", "company_content", "llm_output", "expected_verdict", "snippets"),
    [
        pytest.param(
            "salary_accepted",
            """\
# Stable Startup Backend

| 항목 | 내용 |
|------|------|
| 회사명 | SyntheticPay |
| 포지션 | Senior Backend Engineer |

## 주요업무
- 결제 정산 백엔드 운영과 데이터 정합성 개선

## 자격요건
- Java/Kotlin 기반 API 운영 경험
- 현재 처우 유지 가능한 연봉 밴드 명시
""",
            _company_markdown(name="SyntheticPay", salary="9,800", percentile="상위 8%"),
            _screening_output(
                company="SyntheticPay",
                position="Senior Backend Engineer",
                condition="연봉 수용",
                condition_judgment="O",
                match_note="[source: synthetic/profile.md] backend operations",
                verdict="지원 추천",
                reasons=[
                    "연봉 데이터와 JD 밴드가 현재 기준을 만족한다.",
                    "역할은 백엔드 운영과 정합성 개선 중심이다.",
                ],
            ),
            "지원 추천",
            ["연봉 수용 가능", "평균 연봉 | **9,800만원**", "현재 처우 유지 가능한 연봉 밴드"],
            id="salary",
        ),
        pytest.param(
            "lead_handoff_rejected",
            """\
# Ownerless Platform Lead

| 항목 | 내용 |
|------|------|
| 회사명 | SyntheticLead |
| 포지션 | Backend Engineer |

## 주요업무
- 신규 플랫폼의 기준 수립, 채용 면접, 주니어 평가까지 단독 수행
- 아키텍처 최종 의사결정과 팀 프로세스 정립

## 자격요건
- 팀 리딩과 인사 평가 경험 필수
""",
            _company_markdown(name="SyntheticLead"),
            _screening_output(
                company="SyntheticLead",
                position="Backend Engineer",
                condition="리드 전가",
                condition_judgment="X",
                match_note="candidate prefers bounded IC/staff responsibility",
                verdict="지원 비추천",
                reasons=[
                    "주요업무와 자격요건이 관리 책임을 핵심으로 요구한다.",
                    "코딩 중심 역할로 보기 어렵다.",
                ],
            ),
            "지원 비추천",
            ["리드 전가 없음", "팀 리딩과 인사 평가 경험 필수", "채용 면접"],
            id="lead",
        ),
        pytest.param(
            "scope_too_broad_rejected",
            """\
# Everything Backend

| 항목 | 내용 |
|------|------|
| 회사명 | SyntheticScope |
| 포지션 | Backend Engineer |

## 주요업무
- 백엔드 API, 데이터 파이프라인, 인프라 운영, 크롤러, PM 기획을 모두 담당

## 자격요건
- 제품 기획부터 배포 인프라까지 독립 수행 가능
""",
            _company_markdown(name="SyntheticScope"),
            _screening_output(
                company="SyntheticScope",
                position="Backend Engineer",
                condition="업무 범위",
                condition_judgment="X",
                match_note="backend experience exists, but requested scope is multi-role",
                verdict="지원 비추천",
                reasons=[
                    "한 포지션에 백엔드, 데이터, 인프라, 기획 책임이 함께 묶여 있다.",
                    "역할 경계가 후보자 기준보다 넓다.",
                ],
            ),
            "지원 비추천",
            ["업무 범위가 감당 가능한 수준", "인프라 운영, 크롤러, PM 기획"],
            id="scope",
        ),
        pytest.param(
            "volatility_combined_risk_rejected",
            """\
# Volatile Startup Backend

| 항목 | 내용 |
|------|------|
| 회사명 | SyntheticVolatile |
| 포지션 | Senior Backend Engineer |

## 주요업무
- 축소된 팀에서 신규 시스템 구축과 운영 안정화를 동시에 담당

## 자격요건
- 모호한 문제를 혼자 정의하고 실행할 수 있는 분
""",
            _company_markdown(
                name="SyntheticVolatile",
                current=20,
                joined=3,
                left=14,
                salary="정보 없음",
                percentile="정보 없음",
                round_name="Seed",
                investment="20",
            ),
            _screening_output(
                company="SyntheticVolatile",
                position="Senior Backend Engineer",
                condition="조직 변동성",
                condition_judgment="X",
                match_note="backend fit exists, but company risk combines with role scope",
                verdict="지원 비추천",
                reasons=[
                    "퇴사 규모와 순감소가 역할 범위, 보상 불확실성과 함께 나타난다.",
                    "조직 상황을 감수하기 어렵다.",
                ],
            ),
            "지원 비추천",
            ["조직 변동성이 감수 가능한 수준", "1년간 퇴사자 | 14명", "모호한 문제"],
            id="volatility",
        ),
    ],
)
def test_startup_screening_conditions_flow_through_validation_pipeline(
    monkeypatch,
    tmp_path,
    case_name,
    jd_content,
    company_content,
    llm_output,
    expected_verdict,
    snippets,
):
    result = _run_synthetic_screening(
        monkeypatch,
        tmp_path,
        jd_content=jd_content,
        company_content=company_content,
        llm_output=llm_output,
        prompt_snippets=snippets,
    )

    assert result.verdict == expected_verdict, case_name
    assert result.used_fallback is False
    assert result.provider == "claude"


def test_evidence_hierarchy_prefers_primary_requirements_over_position_intro(
    monkeypatch,
    tmp_path,
):
    jd_content = """\
# Conflicting Intro Backend Role

| 항목 | 내용 |
|------|------|
| 회사명 | SyntheticHierarchy |
| 포지션 | Backend Engineer |

## 포지션 소개
- AI 기술 개발 리더처럼 여러 조직을 조율하는 역할입니다.

## 자격요건
- Backend API 설계와 운영 경험
- RDBMS 기반 트랜잭션 처리 경험
- AWS 기반 서비스 운영 경험
"""
    llm_output = _screening_output(
        company="SyntheticHierarchy",
        position="Backend Engineer",
        condition="증거 계층",
        condition_judgment="primary evidence wins",
        match_note="자격요건의 백엔드 명시 조건을 1차 증거로 우선 적용",
        verdict="지원 보류",
        reasons=[
            "포지션 소개 문구보다 자격요건의 백엔드 요구사항을 우선한다.",
            "상충 근거가 있어 자동 제외 대신 수동 검토 대상으로 둔다.",
        ],
    )

    result = _run_synthetic_screening(
        monkeypatch,
        tmp_path,
        jd_content=jd_content,
        company_content=_company_markdown(name="SyntheticHierarchy"),
        llm_output=llm_output,
        prompt_snippets=[
            "자격요건, 우대사항, 주요업무 are primary evidence",
            "포지션 소개 and branding copy are secondary evidence",
            "AI 기술 개발 리더",
            "Backend API 설계와 운영 경험",
        ],
    )

    assert result.verdict == "지원 보류"
    assert "1차 증거" in result.raw_output
    assert "자격요건" in result.raw_output


@pytest.mark.parametrize(
    ("stack_label", "position", "requirements"),
    [
        pytest.param("python", "Python Backend Engineer", "Python/FastAPI 경험", id="python"),
        pytest.param("go", "Go Backend Engineer", "Go/gRPC 기반 서비스 개발 경험", id="go"),
        pytest.param("ruby", "Ruby on Rails Backend Developer", "Ruby/Rails 서버 개발 경험", id="ruby"),
        pytest.param("rust", "Rust Backend Engineer", "Rust 기반 고성능 서버 개발 경험", id="rust"),
        pytest.param("dotnet", ".NET Backend Engineer", "C#/.NET 기반 API 개발 경험", id="dotnet"),
    ],
)
def test_polyglot_stack_mismatch_alone_is_not_domain_rejection(
    monkeypatch, tmp_path, stack_label, position, requirements,
):
    import domain_filter

    jd_path = tmp_path / f"999998-polyglot-{stack_label}-backend.md"
    jd_path.write_text(
        f"""\
# {position}

| 항목 | 내용 |
|------|------|
| 회사명 | SyntheticPoly |
| 포지션 | {position} |

## 자격요건
- {requirements}
- 백엔드 API 운영 경험
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(domain_filter, "SCREENING_DIR", tmp_path / "screening")

    result = domain_filter.classify_domain(jd_path)

    assert result.action == "skip"
    assert result.reason == "백엔드/도메인 일치"


@pytest.mark.parametrize(
    "keyword",
    ["써치", "서치펌", "헤드헌팅", "리크루팅", "인력파견", "헤드헌터"],
)
def test_headhunting_company_keywords_are_detected(keyword):
    from auto_company import is_headhunting_company

    assert is_headhunting_company(f"테스트{keyword}코리아") is True


def test_non_headhunting_company_name_is_not_detected():
    from auto_company import is_headhunting_company

    assert is_headhunting_company("테스트테크놀로지") is False


def test_closed_jd_detection_covers_all_markers(tmp_path):
    from pre_screen_helpers import _CLOSED_MARKERS, _is_closed_jd

    for index, marker in enumerate(_CLOSED_MARKERS):
        jd_path = tmp_path / f"{index:02d}-closed-marker.md"
        jd_path.write_text(
            f"# Backend Engineer\n\n{marker}\n\n## 자격요건\n- Backend API 운영\n",
            encoding="utf-8",
        )
        assert _is_closed_jd(jd_path) is True, marker
