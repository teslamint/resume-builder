"""Pre-screening helpers — shared between auto.py and pre_screen.py.

Extracted from auto.py to break the circular import that would arise from
auto.py → pre_screen.py → auto.py. Both modules now import from here.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    from .constants import JOB_POSTINGS_DIR
    from .naming import slugify_company
except ImportError:
    from constants import JOB_POSTINGS_DIR
    from naming import slugify_company


_CLOSED_MARKERS = (
    "채용 마감",
    "채용이 마감",
    "마감되었습니다",
    "이 공고는 마감",
    "지원 기간이 종료",
    "상시채용 종료",
    "Position closed",
    "이 포지션은 마감",
)

_PRIOR_HISTORY_FOLDERS = ("applied", "rejected", "submitted")
_PRIOR_HISTORY_DAYS = 180  # 6개월


def _is_closed_jd(jd_path: Path) -> bool:
    try:
        text = jd_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return any(marker in text for marker in _CLOSED_MARKERS)


def _extract_company_slug(jd_path: Path) -> Optional[str]:
    """JD에서 회사 슬러그 추출. naming.slugify_company 활용."""
    try:
        text = jd_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for pat in (
        r"\|\s*회사명?\s*\|\s*([^|\n]+?)\s*\|",
        r"\*\*회사\*\*\s*:\s*([^\n]+)",
        r"^회사명?\s*:\s*([^\n]+)",
    ):
        m = re.search(pat, text, re.MULTILINE)
        if m:
            raw = m.group(1).split("/")[0].split("(")[0].strip()
            return slugify_company(raw, max_len=30, fallback="")
    parts = jd_path.stem.split("-", 2)
    if len(parts) > 1:
        return slugify_company(parts[1], max_len=30, fallback="")
    return None


def _check_prior_application(jd_path: Path) -> Optional[tuple]:
    """직전 6개월 내 동일 회사 지원/탈락 이력 검사.

    Returns: (matched_file, mtime) 또는 None
    """
    company_slug = _extract_company_slug(jd_path)
    if not company_slug or len(company_slug) < 2:
        return None
    cutoff = datetime.now().timestamp() - _PRIOR_HISTORY_DAYS * 86400
    for folder_name in _PRIOR_HISTORY_FOLDERS:
        folder = JOB_POSTINGS_DIR / folder_name
        if not folder.exists():
            continue
        for prior in folder.glob("*.md"):
            if prior.stat().st_mtime < cutoff:
                continue
            prior_slug = _extract_company_slug(prior)
            if not prior_slug:
                continue
            if company_slug == prior_slug:
                return prior, datetime.fromtimestamp(prior.stat().st_mtime)
            if len(company_slug) >= 4 and len(prior_slug) >= 4:
                if company_slug in prior_slug or prior_slug in company_slug:
                    return prior, datetime.fromtimestamp(prior.stat().st_mtime)
    return None
