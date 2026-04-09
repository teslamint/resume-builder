#!/usr/bin/env python3
"""Characterization tests: compare search.py vs search_quick.py filter behavior.

Captures the semantic divergence between the two implementations:
  - search.py quick_filter_title() -> Optional[str]: "pass" | "prefer" | None
  - search_quick.py quick_filter_title() -> bool: True (skip) | False (keep)

Also captures identical functions that should be unified:
  - parse_remember_experience() vs _parse_remember_experience()
  - load_config() vs load_config()
"""

import pytest

from search import quick_filter_title as search_filter
from search import parse_remember_experience
from search_quick import quick_filter_title as quick_filter
from search_quick import _parse_remember_experience


CONFIG = {
    "quick_filters": {
        "title_exclude": [
            "\ub9ac\ub354", "\ud300\uc7a5", "Lead", "CTO",
            "\uc778\ud134",
        ],  # 리더, 팀장, Lead, CTO, 인턴
        "title_include": [
            "\ubc31\uc5d4\ub4dc", "Backend", "Back-end", "Back End",
            "\uac1c\ubc1c\uc790", "Developer",
            "\uc5d4\uc9c0\ub2c8\uc5b4", "Engineer",
            "\uc11c\ubc84", "Server", "Software",
        ],  # 백엔드, 개발자, 엔지니어, 서버
        "title_prefer": [
            "\uc2dc\ub2c8\uc5b4", "Senior",
        ],  # 시니어
    }
}


# ---------------------------------------------------------------------------
# Return type divergence: the core semantic difference
# ---------------------------------------------------------------------------

class TestReturnTypeDivergence:
    """search.py returns str|None, search_quick.py returns bool.

    When consolidating: decide whether to keep 3-way (pass/prefer/neutral)
    or simplify to 2-way (skip/keep).
    """

    def test_exclude_match(self):
        """Both agree: excluded titles should be skipped."""
        title = "Tech Lead (\ubc31\uc5d4\ub4dc)"  # 백엔드
        assert search_filter(title, CONFIG) == "pass"
        assert quick_filter(title, CONFIG) is True

    def test_include_match_with_prefer(self):
        """Divergence: search.py marks as 'prefer', quick returns False (keep)."""
        title = "Senior Backend Engineer"
        assert search_filter(title, CONFIG) == "prefer"
        assert quick_filter(title, CONFIG) is False  # no prefer concept

    def test_include_match_no_prefer(self):
        """Both agree: included without prefer keyword."""
        title = "Backend Developer"
        assert search_filter(title, CONFIG) is None  # neutral
        assert quick_filter(title, CONFIG) is False  # keep

    def test_no_include_match(self):
        """Both agree: title without include keyword should be skipped."""
        title = "\ub9c8\ucf00\ud305 \ub9e4\ub2c8\uc800"  # 마케팅 매니저
        assert search_filter(title, CONFIG) == "pass"
        assert quick_filter(title, CONFIG) is True

    def test_empty_title(self):
        """Both agree on empty input."""
        assert search_filter("", CONFIG) == "pass"
        assert quick_filter("", CONFIG) is True

    def test_exclude_takes_priority_over_include(self):
        """Both agree: exclude overrides include."""
        title = "\ubc31\uc5d4\ub4dc \ud300\uc7a5"  # 백엔드 팀장
        assert search_filter(title, CONFIG) == "pass"
        assert quick_filter(title, CONFIG) is True


class TestFilterAgreement:
    """Inputs where both filters agree on skip/keep (ignoring prefer)."""

    SHOULD_SKIP = [
        "\uc194\ub8e8\uc158 \uae30\ud68d\ud300",     # 솔루션 기획팀
        "\ub514\uc9c0\ud138 \ub9c8\ucf00\ud305",      # 디지털 마케팅
        "CTO",
        "\uc778\ud134 \uac1c\ubc1c\uc790",            # 인턴 개발자 (exclude wins)
        "\ub9ac\ub354\uae09 \uc5d4\uc9c0\ub2c8\uc5b4",  # 리더급 엔지니어 (exclude wins)
    ]

    SHOULD_KEEP = [
        "\ubc31\uc5d4\ub4dc \uac1c\ubc1c\uc790",     # 백엔드 개발자
        "Backend Engineer",
        "Node.js \uac1c\ubc1c\uc790",                  # Node.js 개발자
        "Python Developer",
        "\uc11c\ubc84 \uc5d4\uc9c0\ub2c8\uc5b4",     # 서버 엔지니어
        "Software Engineer",
    ]

    @pytest.mark.parametrize("title", SHOULD_SKIP)
    def test_both_skip(self, title):
        assert search_filter(title, CONFIG) == "pass"
        assert quick_filter(title, CONFIG) is True

    @pytest.mark.parametrize("title", SHOULD_KEEP)
    def test_both_keep(self, title):
        assert search_filter(title, CONFIG) != "pass"
        assert quick_filter(title, CONFIG) is False


# ---------------------------------------------------------------------------
# parse_remember_experience: identical implementations
# ---------------------------------------------------------------------------

class TestParseRememberExperience:
    """Both implementations use identical regex and logic."""

    CASES = [
        (["Company", "3\ub144~9\ub144 \ucc28"], "3\ub144~9\ub144 \ucc28"),  # 3년~9년 차
        (["Company", "5\ub144 \uc774\uc0c1"], "5\ub144 \uc774\uc0c1"),  # 5년 이상
        (["\uacbd\ub825 \ubb34\uad00"], "\uacbd\ub825 \ubb34\uad00"),  # 경력 무관
        (["\ub9ac\ub354\uae09"], "\ub9ac\ub354\uae09"),  # 리더급
        (["No experience info", "Other"], ""),
        ([], ""),
    ]

    @pytest.mark.parametrize("lines,expected", CASES)
    def test_identical_output(self, lines, expected):
        """Both functions must return the same result for all inputs."""
        assert parse_remember_experience(lines) == expected
        assert _parse_remember_experience(lines) == expected

    @pytest.mark.parametrize("lines,expected", CASES)
    def test_functions_agree(self, lines, expected):
        """Cross-check: outputs always match."""
        assert parse_remember_experience(lines) == _parse_remember_experience(lines)


# ---------------------------------------------------------------------------
# load_config divergence
# ---------------------------------------------------------------------------

class TestLoadConfigDivergence:
    """Document known behavioral differences in load_config().

    search.py: returns {} when config missing, prints warning
    search_quick.py: returns {"search_queries": ["백엔드 시니어"]} when missing

    These tests are documentation-only (we don't test file I/O here).
    """

    def test_search_quick_has_default_query(self):
        """search_quick.py provides a default query when config is missing."""
        # This is a documentation test — the actual divergence is:
        # search.py:88 → print(f"⚠️  Config not found: {CONFIG_PATH}"); return {}
        # search_quick.py:48 → return {"search_queries": ["백엔드 시니어"]}
        pass
