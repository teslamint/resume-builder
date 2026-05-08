"""Pre-screening hook — short-circuit before LLM screening.

Order: closed → prior_application → title_exclude → domain.
Source-of-truth alignment (drift prevention):
  1. Python taxonomy (domain_filter.DOMAIN_TAXONOMY)
  2. LLM prompt (private/job_postings/jd-screening-rules.md §0)
  3. search_config.yaml quick_filters.title_exclude (this hook reuses it)

Substring matching: quick_filter_title은 부분 문자열 매칭이라 "Lead"가
"Leader"에도 매칭됨 — 검색 단계와 일관성 유지를 위한 의도된 동작.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    from .pre_screen_helpers import _CLOSED_MARKERS, _check_prior_application
    from .domain_filter import classify_domain
    from .jd_content import extract_metadata_from_jd
    from .search import quick_filter_title
except ImportError:
    from pre_screen_helpers import _CLOSED_MARKERS, _check_prior_application
    from domain_filter import classify_domain
    from jd_content import extract_metadata_from_jd
    from search import quick_filter_title


@dataclass
class PreScreenResult:
    hit: bool
    reason_code: str           # "" | "closed" | "prior_application" | "title_exclude" | "domain_<cat>"
    reason_detail: str         # human readable
    target_folder: str         # "" | "closed" | "rejected" | "pass" | "conditional/hold"
    is_review: bool = False    # counter_indicator → manual review


def _read_text(jd_path: Path) -> str:
    try:
        return jd_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _check_closed(jd_text: str) -> bool:
    return any(marker in jd_text for marker in _CLOSED_MARKERS)


def _check_title_exclude(jd_text: str, config: dict) -> Optional[str]:
    """Return matched title if title_exclude hits, else None."""
    metadata = extract_metadata_from_jd(jd_text)
    title = metadata.get("position") or ""
    if not title:
        return None
    if quick_filter_title(title, config) == "pass":
        return title
    return None


def pre_screen_jd(jd_path: Path, config: dict) -> PreScreenResult:
    jd_text = _read_text(jd_path)
    if not jd_text:
        return PreScreenResult(False, "", "JD 본문 읽기 실패", "")

    # 1) closed marker
    if _check_closed(jd_text):
        return PreScreenResult(
            hit=True, reason_code="closed",
            reason_detail="채용 마감 감지", target_folder="closed",
        )

    # 2) prior 6mo application
    prior = _check_prior_application(jd_path)
    if prior is not None:
        prior_path, prior_dt = prior
        return PreScreenResult(
            hit=True, reason_code="prior_application",
            reason_detail=f"직전 지원 이력: {prior_path.name} ({prior_dt:%Y-%m-%d})",
            target_folder="rejected",
        )

    # 3) title_exclude
    matched_title = _check_title_exclude(jd_text, config)
    if matched_title is not None:
        return PreScreenResult(
            hit=True, reason_code="title_exclude",
            reason_detail=f"title_exclude: {matched_title}",
            target_folder="pass",
        )

    # 4) domain taxonomy (3-tier from domain_filter)
    cls = classify_domain(jd_path)
    if cls.action == "delete":
        return PreScreenResult(
            hit=True, reason_code=f"domain_{cls.category or 'unknown'}",
            reason_detail=cls.reason, target_folder="pass",
        )
    if cls.action == "needs_manual":
        return PreScreenResult(
            hit=True, reason_code=f"domain_{cls.category or 'unknown'}",
            reason_detail=cls.reason, target_folder="conditional/hold",
            is_review=True,
        )

    # action == "skip" → no hit (backend-aligned or protected status)
    return PreScreenResult(False, "", "", "")
