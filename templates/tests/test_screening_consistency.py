#!/usr/bin/env python3
"""Golden-fixture rule consistency tests.

Verifies that committed screening fixtures satisfy structural integrity,
verdict parsing correctness, and 4-condition logic consistency including
meta-rule 0.5 (evidence hierarchy hold path).

These fixtures are sanitized versions of real screening output patterns.
They run in CI without private/ data.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from auto_screening import _validate_screening_structure
from verdict import normalize_verdict, parse_verdict_from_screening

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "screening"

GOLDEN_FILES = sorted(FIXTURES_DIR.glob("golden_*.md"))


@pytest.fixture(params=GOLDEN_FILES, ids=[f.stem for f in GOLDEN_FILES])
def golden_fixture(request) -> tuple[Path, str]:
    path = request.param
    return path, path.read_text(encoding="utf-8")


class TestGoldenStructuralIntegrity:
    """Every golden fixture must pass structural validation."""

    def test_structure_is_valid(self, golden_fixture):
        path, content = golden_fixture
        valid, reason = _validate_screening_structure(content)
        assert valid, f"{path.name}: {reason}"


class TestGoldenVerdictParsing:
    """parse_verdict_from_screening extracts correct verdict from each fixture."""

    EXPECTED_VERDICTS = {
        "golden_salary_reject.md": "지원 비추천",
        "golden_lead_handoff_reject.md": "지원 비추천",
        "golden_scope_reject.md": "지원 비추천",
        "golden_all_pass_recommend.md": "지원 추천",
        "golden_evidence_hierarchy_hold.md": "지원 보류",
        "golden_volatility_reject.md": "지원 비추천",
    }

    def test_verdict_extracted_correctly(self, golden_fixture):
        path, content = golden_fixture
        expected = self.EXPECTED_VERDICTS.get(path.name)
        assert expected is not None, (
            f"{path.name}: no expected verdict defined in EXPECTED_VERDICTS — "
            f"every golden fixture must have an explicit expected verdict"
        )

        result = parse_verdict_from_screening(content)
        assert result == expected, f"{path.name}: got {result!r}, expected {expected!r}"


class TestGoldenConditionConsistency:
    """Verify 4-condition logic is consistent with final verdict."""

    _CONDITION_RE = re.compile(
        r"\|\s*[①②③④]\s*\|[^|]+\|\s*(⭕|❌|△)\s*\|",
    )

    def _extract_conditions(self, content: str) -> list[str]:
        """Extract condition judgments (⭕/❌/△) from the 4-condition table."""
        return self._CONDITION_RE.findall(content)

    def test_salary_reject_has_salary_fail(self):
        content = (FIXTURES_DIR / "golden_salary_reject.md").read_text(encoding="utf-8")
        conditions = self._extract_conditions(content)
        assert len(conditions) == 4
        assert conditions[0] == "❌"  # ① salary

    def test_lead_handoff_reject_has_lead_fail(self):
        content = (FIXTURES_DIR / "golden_lead_handoff_reject.md").read_text(encoding="utf-8")
        conditions = self._extract_conditions(content)
        assert len(conditions) == 4
        assert conditions[1] == "❌"  # ② lead handoff

    def test_all_pass_has_four_pass(self):
        content = (FIXTURES_DIR / "golden_all_pass_recommend.md").read_text(encoding="utf-8")
        conditions = self._extract_conditions(content)
        assert len(conditions) == 4
        assert all(c == "⭕" for c in conditions)

    def test_scope_reject_has_scope_fail(self):
        content = (FIXTURES_DIR / "golden_scope_reject.md").read_text(encoding="utf-8")
        conditions = self._extract_conditions(content)
        assert len(conditions) == 4
        assert conditions[2] == "❌"  # ③ scope

    def test_volatility_reject_has_volatility_fail(self):
        content = (FIXTURES_DIR / "golden_volatility_reject.md").read_text(encoding="utf-8")
        conditions = self._extract_conditions(content)
        assert len(conditions) == 4
        assert conditions[3] == "❌"  # ④ volatility

    def test_evidence_hierarchy_uses_triangle(self):
        """Meta-rule 0.5: 1st/2nd evidence conflict → △ (not auto-cut ❌)."""
        content = (FIXTURES_DIR / "golden_evidence_hierarchy_hold.md").read_text(encoding="utf-8")
        conditions = self._extract_conditions(content)
        assert len(conditions) == 4
        assert "△" in conditions  # at least one triangle
        # Triangle cases follow 0.5 hold path, not "3 ⭕ unmet" auto-cut
        verdict = parse_verdict_from_screening(content)
        assert verdict == "지원 보류"


class TestConditionLogicRules:
    """Verify the mapping between condition counts and verdicts."""

    _CONDITION_RE = re.compile(
        r"\|\s*[①②③④]\s*\|[^|]+\|\s*(⭕|❌|△)\s*\|",
    )

    @pytest.mark.parametrize(
        "fixture_name",
        [f.name for f in GOLDEN_FILES],
    )
    def test_condition_verdict_coherence(self, fixture_name):
        """Check that condition results are logically compatible with verdict.

        Rules:
        - 4 ⭕ → 추천 or 보류 (never 비추천)
        - <3 ⭕ (no △) → 비추천
        - Any △ → 보류 path takes priority (0.5절)
        """
        content = (FIXTURES_DIR / fixture_name).read_text(encoding="utf-8")
        conditions = self._CONDITION_RE.findall(content)
        assert len(conditions) == 4, (
            f"{fixture_name}: expected 4-condition table but found {len(conditions)} entries"
        )

        verdict = parse_verdict_from_screening(content)
        pass_count = conditions.count("⭕")
        fail_count = conditions.count("❌")
        triangle_count = conditions.count("△")

        if triangle_count > 0:
            # 0.5절: any evidence conflict → hold path (never auto-cut, never auto-recommend)
            assert verdict == "지원 보류", (
                f"{fixture_name}: △ present but verdict is {verdict!r} "
                f"(0.5절 requires hold path for manual review)"
            )
        elif pass_count >= 3:
            # B 기준: 4조건 중 3개 이상 충족 → 비추천이면 안 됨
            assert verdict != "지원 비추천", (
                f"{fixture_name}: {pass_count}/4 conditions ⭕ (≥3 threshold met) "
                f"but verdict is 비추천"
            )
        else:
            # pass_count < 3, no △ → must be 비추천
            assert verdict == "지원 비추천", (
                f"{fixture_name}: only {pass_count} ⭕ (no △) but verdict is {verdict!r}"
            )
