"""Experience range parsing and filtering for JD search pipelines.

Parses Korean experience requirement strings (e.g. "경력 5-10년", "3년~9년 차")
and filters JDs whose experience range doesn't match the user's career level.
"""
from __future__ import annotations

import re

_UNREALISTIC_MAX = 50


def _strip_formatting(s: str) -> str:
    return re.sub(r'\*+', '', s).strip()


def parse_experience_range(exp_str: str | None) -> tuple[int | None, int | None]:
    """Parse experience string into (min_years, max_years).

    Returns (None, None) for unparseable or "경력 무관" strings.
    Unrealistic upper bounds (>= 50) are treated as open-ended (None).
    """
    if not exp_str:
        return None, None

    exp_str = _strip_formatting(exp_str)

    if re.search(r'경력\s*무관|무관', exp_str):
        return None, None

    if re.fullmatch(r'\s*경력\s*', exp_str):
        return None, None

    # "경력 7년 이상 14년 이하" / "5년 이상 ~ 15년 미만"
    compound = re.search(r'(\d+)\s*년\s*이상\s*~?\s*(\d+)\s*년\s*(?:이하|미만)', exp_str)
    if compound:
        min_y, max_y = int(compound.group(1)), int(compound.group(2))
        if '미만' in exp_str:
            max_y -= 1
        if max_y >= _UNREALISTIC_MAX:
            return min_y, None
        return min_y, max_y

    # "3년~9년 차", "5-10년", "경력 5~10년"
    range_match = re.search(r'(\d+)\s*년?\s*[-~]\s*(\d+)\s*년(?:\s*차)?', exp_str)
    if range_match:
        min_y, max_y = int(range_match.group(1)), int(range_match.group(2))
        if max_y >= _UNREALISTIC_MAX:
            return min_y, None
        return min_y, max_y

    # "경력 3년↑" / "3년 이상" / "5년+"
    min_match = re.search(r'(\d+)\s*년\s*(?:차\s*)?(?:↑|이상|\+)', exp_str)
    if min_match:
        return int(min_match.group(1)), None

    # "5년 이하" / "10년 미만" / "10년차 이하"
    max_match = re.fullmatch(r'\s*(?:경력\s*)?(\d+)\s*년(?:\s*차)?\s*(?:이하|미만)\s*', exp_str)
    if max_match:
        max_y = int(max_match.group(1))
        if '미만' in exp_str:
            max_y -= 1
        return None, max_y

    # "경력 3년" (exact)
    exact_match = re.fullmatch(r'\s*(?:경력\s*)?(\d+)\s*년(?:\s*차)?\s*', exp_str)
    if exact_match:
        years = int(exact_match.group(1))
        return years, years

    return None, None


def filter_experience(exp_str: str | None, config: dict) -> bool:
    """Returns True if the JD should be skipped based on experience range.

    Config keys (under 'filters'):
      min_experience_upper: JD's upper bound must be >= this (default 14)
      max_experience: JD's lower bound must not exceed this (None = disabled)
    """
    filters = config.get("filters", {})
    min_upper = filters.get("min_experience_upper", 14)
    max_exp_cfg = filters.get("max_experience")

    min_years, max_years = parse_experience_range(exp_str)

    # Rule 1: JD upper < min_upper → skip ("경력 5-12년" for 14yr user)
    if max_years is not None and max_years < min_upper:
        return True

    # Rule 2: JD lower > max_experience → skip ("경력 20년↑" for 14yr user)
    if max_exp_cfg is not None and min_years is not None and min_years > max_exp_cfg:
        return True

    return False
