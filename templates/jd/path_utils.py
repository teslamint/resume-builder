#!/usr/bin/env python3
"""Job ID extraction, platform detection, and file finding utilities."""

import re
from pathlib import Path
from typing import Optional, Tuple

try:
    from .constants import JOB_POSTINGS_DIR
except ImportError:
    from constants import JOB_POSTINGS_DIR


def extract_job_id(url: str) -> Optional[str]:
    """Extract job ID from various recruitment platform URLs.

    Supports:
    - Wanted: wanted.co.kr/wd/{id}
    - Remember: rememberapp.co.kr/job/{id}, career.rememberapp.co.kr/job/posting/{id}
    - Saramin: saramin.co.kr/zf_user/jobs/relay/view?rec_idx={id}
    - JobKorea: jobkorea.co.kr/Recruit/GI_Read/{id}
    - Jumpit: jumpit.saramin.co.kr/position/{id}
    - GroupBy: groupby.kr/positions/{id} -> "groupby-{id}"
    """
    # GroupBy: return prefixed ID to avoid collision with other platforms
    gb_match = re.search(r"groupby\.kr/positions/(\d+)", url)
    if gb_match:
        return f"groupby-{gb_match.group(1)}"

    patterns = [
        r"wanted\.co\.kr/wd/(\d+)",
        r"rememberapp\.co\.kr/job/(?:posting/)?(\d+)",
        r"career\.rememberapp\.co\.kr/job/posting/(\d+)",
        r"saramin\.co\.kr.*rec_idx=(\d+)",
        r"jobkorea\.co\.kr/Recruit/GI_Read/(\d+)",
        r"jumpit\.saramin\.co\.kr/position/(\d+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)

    return None


def extract_job_id_from_filename(filename: str) -> Optional[str]:
    """Extract job ID from JD filename.

    Patterns:
    - "123456-company-position.md" -> "123456"
    - "remember-273986-company-position.md" -> "273986" (platform prefix)
    - "groupby-8807-company-position.md" -> "groupby-8807" (platform-aware ID)
    - "private-company-position.md" -> "private"
    """
    _PLATFORM_PREFIXES = {"groupby"}

    stem = Path(filename).stem if "." in filename else filename
    parts = stem.split("-")

    if not parts:
        return None

    # First part is numeric -> job_id
    if parts[0].isdigit():
        return parts[0]

    # Platform prefix that requires compound ID (e.g., "groupby-8807")
    if parts[0] in _PLATFORM_PREFIXES and len(parts) > 1 and parts[1].isdigit():
        return f"{parts[0]}-{parts[1]}"

    # Legacy prefix (e.g., "remember"), return raw numeric part
    if len(parts) > 1 and parts[1].isdigit():
        return parts[1]

    # Fallback to first part (e.g., "private")
    return parts[0]


def get_platform_from_url(url: str) -> Optional[str]:
    """Identify platform from URL."""
    if "wanted.co.kr" in url:
        return "wanted"
    elif "rememberapp.co.kr" in url:
        return "remember"
    elif "saramin.co.kr" in url:
        return "saramin"
    elif "jobkorea.co.kr" in url:
        return "jobkorea"
    elif "jumpit.saramin.co.kr" in url:
        return "jumpit"
    elif "groupby.kr" in url:
        return "groupby"
    return None


def find_existing_jd(job_id: str) -> Optional[Path]:
    """Find existing JD file by job_id in any folder."""
    search_dirs = [
        JOB_POSTINGS_DIR,
        JOB_POSTINGS_DIR / "pass",
        JOB_POSTINGS_DIR / "conditional",
        JOB_POSTINGS_DIR / "conditional" / "high",
        JOB_POSTINGS_DIR / "conditional" / "hold",
        JOB_POSTINGS_DIR / "conditional" / "middle",
        JOB_POSTINGS_DIR / "conditional" / "low",
        JOB_POSTINGS_DIR / "applied",
        JOB_POSTINGS_DIR / "rejected",
        JOB_POSTINGS_DIR / "high_priority",
        JOB_POSTINGS_DIR / "on_going",
    ]

    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        for file in search_dir.glob(f"{job_id}-*.md"):
            return file
        for file in search_dir.glob(f"*-{job_id}-*.md"):
            return file

    return None


def find_jd_anywhere(job_id: str) -> Optional[Path]:
    """Find existing JD by job_id including unprocessed/.

    RESOLUTION PATHS ONLY — do not use for dedup checks (unprocessed JDs are
    not yet classified and should not be treated as "already processed").
    """
    search_dirs = [
        JOB_POSTINGS_DIR,
        JOB_POSTINGS_DIR / "pass",
        JOB_POSTINGS_DIR / "conditional",
        JOB_POSTINGS_DIR / "conditional" / "high",
        JOB_POSTINGS_DIR / "conditional" / "hold",
        JOB_POSTINGS_DIR / "conditional" / "middle",
        JOB_POSTINGS_DIR / "conditional" / "low",
        JOB_POSTINGS_DIR / "applied",
        JOB_POSTINGS_DIR / "rejected",
        JOB_POSTINGS_DIR / "high_priority",
        JOB_POSTINGS_DIR / "on_going",
        JOB_POSTINGS_DIR / "unprocessed",
    ]

    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        for file in search_dir.glob(f"{job_id}-*.md"):
            return file
        for file in search_dir.glob(f"*-{job_id}-*.md"):
            return file

    return None


def is_duplicate(job_id: str) -> Tuple[bool, Optional[Path]]:
    """Check if JD already exists and return the path if found."""
    existing = find_existing_jd(job_id)
    return (existing is not None, existing)
