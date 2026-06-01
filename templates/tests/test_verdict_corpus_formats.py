#!/usr/bin/env python3
"""Verdict parser robustness tests against real corpus format variants.

Derived from format distribution observed in 1091 screening files.
Tests normalize_verdict and parse_verdict_from_screening against
every format variant that actually appears in production outputs.
"""

import pytest

from verdict import normalize_verdict, parse_verdict_from_screening


class TestNormalizeVerdictCorpusFormats:
    """normalize_verdict handles all real format variants found in corpus."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("지원 비추천", "지원 비추천"),
            ("🔴 지원 비추천", "지원 비추천"),
            ("지원 비추천 🔴", "지원 비추천"),
            ("**지원 비추천** ❌", "지원 비추천"),
            ("**: 🔴 지원 비추천", "지원 비추천"),
            ("🔴 **지원 비추천**", "지원 비추천"),
            ("**지원 비추천 (❌)**", "지원 비추천"),
            ("**지원 비추천** (🔴)", "지원 비추천"),
            ("지원 보류", "지원 보류"),
            ("🟡 지원 보류", "지원 보류"),
            ("**: 🟡 지원 보류", "지원 보류"),
            ("🟡 지원 보류 (2026-04-25 정정)", "지원 보류"),
            ("**: 🟡 지원 보류 (2026-04-25 정정)", "지원 보류"),
            ("🟡 조건부 추천", "지원 보류"),
            ("조건부 지원 추천", "지원 보류"),
            ("지원 추천", "지원 추천"),
            ("🟢 지원 추천", "지원 추천"),
            ("**: 🟢 지원 추천", "지원 추천"),
            ("🟢 지원 추천 (2026-04-26 코테 정책 완화로 자동 승급)", "지원 추천"),
            ("강력 추천", "지원 추천"),
            ("즉시 지원", "지원 추천"),
        ],
        ids=[
            "plain-reject",
            "emoji-prefix-reject",
            "emoji-suffix-reject",
            "bold-x-reject",
            "bold-prefix-reject",
            "bold-emoji-reject",
            "bold-paren-x-reject",
            "bold-paren-emoji-reject",
            "plain-hold",
            "emoji-hold",
            "bold-prefix-hold",
            "hold-with-date",
            "bold-hold-with-date",
            "conditional-recommend",
            "conditional-apply",
            "plain-recommend",
            "emoji-recommend",
            "bold-prefix-recommend",
            "recommend-with-annotation",
            "strong-recommend",
            "immediate-apply",
        ],
    )
    def test_format_variant(self, raw, expected):
        assert normalize_verdict(raw) == expected

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("| 지원 보류 |", "지원 보류"),
            ("| 지원 비추천 |", "지원 비추천"),
            ("검토 대상이 아닙니다", "지원 비추천"),
            ("추가 검토 없이 제외", "지원 비추천"),
            ("검토 대상이 아닌 JD", "지원 비추천"),
            ("지원 안 함", "지원 비추천"),
            ("자동 컷", "지원 비추천"),
            ("PASS", "지원 비추천"),
            ("HOLD", "지원 보류"),
            ("킵", "지원 보류"),
        ],
        ids=[
            "table-cell-hold",
            "table-cell-reject",
            "negated-review-full",
            "negated-review-exclude",
            "negated-review-not-target",
            "no-apply",
            "auto-cut",
            "english-pass-reject",
            "english-hold",
            "korean-keep",
        ],
    )
    def test_alternative_keywords(self, raw, expected):
        assert normalize_verdict(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        [
            "",
            "| 포지션 | 판정 | 사유 |",
            "포지션 판정 사유",
            "판정",
        ],
        ids=["empty", "table-header-full", "table-header-plain", "label-only"],
    )
    def test_non_verdict_returns_none(self, raw):
        assert normalize_verdict(raw) is None


class TestParseVerdictFromScreeningCorpusPatterns:
    """parse_verdict_from_screening handles real heading/section patterns."""

    def test_heading_with_emoji_prefix(self):
        content = "## 최종 판정\n\n### 최종 판정: 🔴 지원 비추천\n\n## 핵심 근거\n\n- reason"
        assert parse_verdict_from_screening(content) == "지원 비추천"

    def test_heading_with_bold_and_emoji(self):
        content = "## 최종 판정\n\n### 최종 판정: **지원 비추천** ❌\n\n## 핵심 근거\n\n- reason"
        assert parse_verdict_from_screening(content) == "지원 비추천"

    def test_heading_with_annotation(self):
        content = "## 최종 판정\n\n### 최종 판정: 🟢 지원 추천 (2026-04-26 코테 정책 완화로 자동 승급)\n\n## 핵심 근거\n\n- 합격"
        assert parse_verdict_from_screening(content) == "지원 추천"

    def test_table_format_verdict(self):
        content = """\
## 최종 판정

| 포지션 | 판정 | 사유 |
|--------|------|------|
| Backend Engineer | 지원 보류 | 정보 불충분 |

## 핵심 근거

- 보�� 사유
"""
        assert parse_verdict_from_screening(content) == "지원 보류"

    def test_blockquote_verdict(self):
        content = """\
## 최종 판정

> 판정: 지원 비추천

## 핵심 근거

- 부적합
"""
        assert parse_verdict_from_screening(content) == "지원 비추천"

    def test_multiple_verdict_blocks_uses_last(self):
        content = """\
## 최종 판정

### 최종 판정: 지원 보류

---

## 최종 판정

### 최종 판정: 🟢 지원 추천

## 핵심 근거

- 재심 결과 추천
"""
        result = parse_verdict_from_screening(content)
        assert result in ("지원 추천", "지원 보류")

    def test_bold_prefix_colon_format(self):
        content = "## 최종 판정\n\n### 최종 판정**: 🟡 지원 보류\n\n## 핵심 근거\n\n- 검토 ���요"
        assert parse_verdict_from_screening(content) == "지원 보류"

    def test_conditional_recommend_as_hold(self):
        content = "## 최종 판정\n\n### 최종 판정: 🟡 조건부 추천\n\n## 핵심 근거\n\n- 조건 확인 필요"
        assert parse_verdict_from_screening(content) == "지원 보류"
