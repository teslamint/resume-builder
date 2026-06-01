#!/usr/bin/env python3
"""Golden-path regression tests for auto_screening.py."""

import subprocess
from pathlib import Path

import auto_screening


FIXED_RULES = """\
# JD Screening Rules

- Prefer backend roles with clear operational ownership.
- Reject unsupported inferred experience.
"""

FIXED_JD = """\
# Golden Backend Role

| 항목 | 내용 |
|------|------|
| 회사명 | GoldenCo |
| 포지션 | Senior Backend Engineer |
| 경력 | 8년 이상 |

출처: [Remember](https://example.com/jobs/123456)
"""

GOLDEN_LLM_OUTPUT = """\
## 기본 정보

| 항목 | 내용 |
|------|------|
| 회사명 | GoldenCo |
| 포지션 | Senior Backend Engineer |

## 스크리닝 결과

백엔드 운영 경험과 JD 요구사항이 일치한다.

## 이력/경험 매칭

| 요건 | 매칭 | 근거 |
|------|------|------|
| Backend | O | 고정 후보자 컨텍스트 |

## 최종 판정

### 최종 판정: 지원 추천

## 핵심 근거

- 운영 안정성 경험과 역할 요구가 맞는다.
- 기술 범위가 백엔드 중심이다.
"""


def test_run_screening_writes_golden_output_and_result(monkeypatch, tmp_path):
    jd_path = tmp_path / "123456-golden-backend.md"
    jd_path.write_text(FIXED_JD, encoding="utf-8")
    screening_dir = tmp_path / "screening"
    summary_calls = []

    monkeypatch.setenv("CLAUDE_SCREENING_CMD", "fake-llm --print")
    monkeypatch.delenv("CODEX_SCREENING_CMD", raising=False)
    monkeypatch.setattr(auto_screening, "SCREENING_DIR", screening_dir)
    monkeypatch.setattr(auto_screening, "load_screening_rules", lambda: FIXED_RULES)
    monkeypatch.setattr(auto_screening, "_load_candidate_context", lambda: "fixed candidate context")
    monkeypatch.setattr(auto_screening, "update_summary", lambda **kwargs: summary_calls.append(kwargs))

    def fake_run(cmd, input, text, capture_output, timeout, env):
        assert cmd == ["fake-llm", "--print"]
        assert text is True
        assert capture_output is True
        assert timeout == 30
        assert FIXED_RULES in input
        assert FIXED_JD in input
        return subprocess.CompletedProcess(cmd, 0, stdout=GOLDEN_LLM_OUTPUT, stderr="")

    monkeypatch.setattr(auto_screening.subprocess, "run", fake_run)

    result = auto_screening.run_screening(
        jd_path=jd_path,
        company_file=None,
        llm_timeout=30,
        dry_run=False,
    )

    expected_path = screening_dir / "123456-golden-backend.md"
    assert result.verdict == "지원 추천"
    assert result.screening_path == expected_path
    assert result.provider == "claude"
    assert result.used_fallback is False
    assert expected_path.read_text(encoding="utf-8") == GOLDEN_LLM_OUTPUT.rstrip() + "\n"
    assert summary_calls == [
        {
            "job_id": "123456",
            "company": "GoldenCo",
            "position": "Senior Backend Engineer",
            "verdict": "지원 추천",
            "folder": "pending",
        }
    ]
