#!/usr/bin/env python3
"""Characterization tests: verdict parsing, classification, and status normalization.

Captures current behavior of the pipeline's verdict/classification system
in utils.py before refactoring into separate modules.
"""

import pytest

from constants import PROTECTED_STATUSES, STATUS_ALIASES, VERDICT_FOLDER_MAP, VERDICT_PRIORITY
from jd_content import normalize_status
from verdict import classify_by_verdict, normalize_verdict


# ---------------------------------------------------------------------------
# normalize_verdict: many variants -> canonical 3-state
# ---------------------------------------------------------------------------

class TestNormalizeVerdict:
    """utils.normalize_verdict() -> "지원 추천" | "지원 보류" | "지원 비추천" | None."""

    # --- 지원 비추천 (reject) variants ---
    @pytest.mark.parametrize("inp", [
        "\uc9c0\uc6d0 \ube44\ucd94\ucc9c",       # 지원 비추천
        "**\ube44\ucd94\ucc9c**",                   # **비추천**
        "PASS",
        "pass",
        "\ud328\uc2a4",                             # 패스
        "\uc9c0\uc6d0 \uc548 \ud568",              # 지원 안 함
        "\uc9c0\uc6d0\uc548\ud568",                # 지원안함
        "\ucef7",                                   # 컷
    ])
    def test_reject_variants(self, inp):
        assert normalize_verdict(inp) == "\uc9c0\uc6d0 \ube44\ucd94\ucc9c"  # 지원 비추천

    # --- 지원 보류 (hold) variants ---
    @pytest.mark.parametrize("inp", [
        "\uc9c0\uc6d0 \ubcf4\ub958",               # 지원 보류
        "\uc870\uac74\ubd80",                       # 조건부
        "\ubcf4\ub958",                             # 보류
        "hold",
        "HOLD",
        "\uac80\ud1a0",                             # 검토
        "\ud0b5",                                   # 킵
        "keep",
        "\uc6b0\uc120",                             # 우선
    ])
    def test_hold_variants(self, inp):
        assert normalize_verdict(inp) == "\uc9c0\uc6d0 \ubcf4\ub958"  # 지원 보류

    # --- 지원 추천 (recommend) variants ---
    @pytest.mark.parametrize("inp", [
        "\uc9c0\uc6d0 \ucd94\ucc9c",               # 지원 추천
        "\uac15\ub825 \ucd94\ucc9c",               # 강력 추천
        "\uc989\uc2dc \uc9c0\uc6d0",               # 즉시 지원
        "\ucd94\ucc9c",                             # 추천
        "\uc9c0\uc6d0",                             # 지원
    ])
    def test_recommend_variants(self, inp):
        assert normalize_verdict(inp) == "\uc9c0\uc6d0 \ucd94\ucc9c"  # 지원 추천

    # --- None (unrecognized) ---
    @pytest.mark.parametrize("inp", [
        "",
        None,
        "| \ud3ec\uc9c0\uc158 | \ud310\uc815 | \uc0ac\uc720 |",  # table header
        "\ud310\uc815",                                            # 판정 (label only)
        "\uc54c \uc218 \uc5c6\uc74c",                             # 알 수 없음
    ])
    def test_none_variants(self, inp):
        assert normalize_verdict(inp) is None

    def test_markdown_formatting_stripped(self):
        """Markdown bold/italic/backtick should be stripped before matching."""
        assert normalize_verdict("**\uc9c0\uc6d0 \ucd94\ucc9c**") == "\uc9c0\uc6d0 \ucd94\ucc9c"
        assert normalize_verdict("`\ube44\ucd94\ucc9c`") == "\uc9c0\uc6d0 \ube44\ucd94\ucc9c"

    def test_priority_order(self):
        """비추천 < 보류 < 추천 in priority (worst-case = lowest number)."""
        assert VERDICT_PRIORITY["\uc9c0\uc6d0 \ube44\ucd94\ucc9c"] < VERDICT_PRIORITY["\uc9c0\uc6d0 \ubcf4\ub958"]
        assert VERDICT_PRIORITY["\uc9c0\uc6d0 \ubcf4\ub958"] < VERDICT_PRIORITY["\uc9c0\uc6d0 \ucd94\ucc9c"]


# ---------------------------------------------------------------------------
# classify_by_verdict: verdict -> folder path
# ---------------------------------------------------------------------------

class TestClassifyByVerdict:
    """utils.classify_by_verdict() maps verdict to folder path."""

    def test_recommend_to_high(self):
        assert classify_by_verdict("\uc9c0\uc6d0 \ucd94\ucc9c") == "conditional/high"

    def test_hold_to_hold(self):
        assert classify_by_verdict("\uc9c0\uc6d0 \ubcf4\ub958") == "conditional/hold"

    def test_reject_to_pass(self):
        assert classify_by_verdict("\uc9c0\uc6d0 \ube44\ucd94\ucc9c") == "pass"

    def test_raw_variant_is_normalized_first(self):
        """classify_by_verdict normalizes before mapping."""
        assert classify_by_verdict("PASS") == "pass"
        assert classify_by_verdict("\ucd94\ucc9c") == "conditional/high"
        assert classify_by_verdict("\ubcf4\ub958") == "conditional/hold"

    def test_unrecognized_returns_none(self):
        assert classify_by_verdict("unknown") is None
        assert classify_by_verdict("") is None

    def test_folder_map_completeness(self):
        """Every canonical verdict must have a folder mapping."""
        for verdict in VERDICT_PRIORITY:
            assert verdict in VERDICT_FOLDER_MAP


# ---------------------------------------------------------------------------
# normalize_status + STATUS_ALIASES
# ---------------------------------------------------------------------------

class TestNormalizeStatus:
    """utils.normalize_status() -> canonical status string."""

    @pytest.mark.parametrize("inp,expected", [
        ("pending", "pending"),
        ("\ubcf4\ub958", "pending"),           # 보류
        ("\uc870\uac74\ubd80", "pending"),     # 조건부
        ("\uc870\uac74\ubd80(\uc0c1)", "pending"),  # 조건부(상)
        ("\uc6b0\uc120", "pending"),            # 우선
        ("pass", "rejected"),
        ("\ud328\uc2a4", "rejected"),           # 패스
        ("rejected", "rejected"),
        ("\uc9c0\uc6d0", "applied"),           # 지원
        ("applied", "applied"),
        ("\uba74\uc811", "interview"),          # 면접
        ("interview", "interview"),
        ("\uc624\ud37c", "offer"),              # 오퍼
        ("offer", "offer"),
    ])
    def test_known_aliases(self, inp, expected):
        assert normalize_status(inp) == expected

    def test_protected_statuses(self):
        """Protected statuses should not be auto-reclassified."""
        assert PROTECTED_STATUSES == {"rejected", "applied", "interview", "offer"}
        for status in PROTECTED_STATUSES:
            assert status in STATUS_ALIASES.values()

    def test_all_aliases_map_to_valid_status(self):
        """Every alias must map to one of the canonical statuses."""
        valid = {"pending", "rejected", "applied", "interview", "offer"}
        for alias, canonical in STATUS_ALIASES.items():
            assert canonical in valid, f"Alias {alias!r} maps to invalid status {canonical!r}"
