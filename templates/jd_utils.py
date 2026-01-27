#!/usr/bin/env python3
"""JD Pipeline Utilities - Common functions for job posting processing."""

import os
import re
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple, Literal, Dict

# Protected statuses that should not be auto-reclassified
PROTECTED_STATUSES = {"rejected", "applied", "interview", "offer"}

# Base paths
BASE_DIR = Path(__file__).parent.parent
JOB_POSTINGS_DIR = BASE_DIR / "job_postings"
JD_ANALYSIS_DIR = BASE_DIR / "jd_analysis"
COMPANY_INFO_DIR = BASE_DIR / "company_info"
SCREENING_DIR = JD_ANALYSIS_DIR / "screening"

# Verdict to folder mapping
VERDICT_FOLDER_MAP = {
    "지원 추천": "conditional/high",
    "지원 보류": "conditional/hold",
    "지원 비추천": "pass",
    "조건부 상": "conditional/high",
    "조건부 중": "conditional/middle",
    "조건부 하": "conditional/low",
    "조건부 보류": "conditional/hold",
}

VerdictType = Literal["지원 추천", "지원 보류", "지원 비추천"]


def extract_job_id(url: str) -> Optional[str]:
    """Extract job ID from various recruitment platform URLs.

    Supports:
    - Wanted: wanted.co.kr/wd/{id}
    - Remember: rememberapp.co.kr/job/{id}, career.rememberapp.co.kr/job/posting/{id}
    - Saramin: saramin.co.kr/zf_user/jobs/relay/view?rec_idx={id}
    - JobKorea: jobkorea.co.kr/Recruit/GI_Read/{id}
    - Jumpit: jumpit.saramin.co.kr/position/{id}
    """
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
    - "private-company-position.md" -> "private"
    """
    stem = Path(filename).stem if "." in filename else filename
    parts = stem.split("-")

    if not parts:
        return None

    # First part is numeric -> job_id
    if parts[0].isdigit():
        return parts[0]

    # First part is prefix (e.g., "remember"), check second part
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
    return None


def find_existing_jd(job_id: str) -> Optional[Path]:
    """Find existing JD file by job_id in any folder."""
    search_dirs = [
        JOB_POSTINGS_DIR,
        JOB_POSTINGS_DIR / "pass",
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


def is_duplicate(job_id: str) -> Tuple[bool, Optional[Path]]:
    """Check if JD already exists and return the path if found."""
    existing = find_existing_jd(job_id)
    return (existing is not None, existing)


def load_screening_rules() -> str:
    """Load screening rules from file."""
    rules_path = JOB_POSTINGS_DIR / "jd-screening-rules.md"
    if rules_path.exists():
        return rules_path.read_text(encoding="utf-8")
    return ""


def load_company_info(company: str) -> Optional[str]:
    """Load company info if available."""
    normalized = company.lower().replace(" ", "-").replace("_", "-")

    for pattern in [f"{normalized}.md", f"{company}.md"]:
        path = COMPANY_INFO_DIR / pattern
        if path.exists():
            return path.read_text(encoding="utf-8")

    # Try fuzzy match
    if COMPANY_INFO_DIR.exists():
        for file in COMPANY_INFO_DIR.glob("*.md"):
            if normalized in file.stem.lower():
                return file.read_text(encoding="utf-8")

    return None


def classify_by_verdict(verdict: str) -> str:
    """Map verdict string to target folder path."""
    # Normalize verdict
    verdict_clean = verdict.strip()

    # Direct match
    if verdict_clean in VERDICT_FOLDER_MAP:
        return VERDICT_FOLDER_MAP[verdict_clean]

    # Fuzzy match
    verdict_lower = verdict_clean.lower()
    if "추천" in verdict_lower and "비" not in verdict_lower:
        return "conditional/high"
    elif "보류" in verdict_lower:
        return "conditional/hold"
    elif "비추천" in verdict_lower or "패스" in verdict_lower:
        return "pass"

    # Default to hold if unclear
    return "conditional/hold"


def move_to_folder(file_path: Path, target_folder: str, dry_run: bool = False) -> Path:
    """Move file to target folder under job_postings/."""
    target_dir = JOB_POSTINGS_DIR / target_folder
    target_dir.mkdir(parents=True, exist_ok=True)

    dest = target_dir / file_path.name

    if dry_run:
        return dest

    if file_path != dest:
        shutil.move(str(file_path), str(dest))

    return dest


def parse_verdict_from_screening(screening_content: str) -> Optional[str]:
    """Extract verdict from screening analysis file."""
    # Pattern: ### 최종 판정: {verdict}
    match = re.search(r"###?\s*최종\s*판정[:\s]+([^\n]+)", screening_content)
    if match:
        return match.group(1).strip()

    # Alternative pattern: | 최종 판단 | **{verdict}** |
    match = re.search(r"\|\s*최종\s*판단\s*\|\s*\*?\*?([^|*\n]+)", screening_content)
    if match:
        return match.group(1).strip()

    # Pattern: **결론**: {verdict}
    match = re.search(r"\*\*결론\*\*[:\s]+([^\n]+)", screening_content)
    if match:
        return match.group(1).strip()

    return None


def generate_jd_filename(job_id: str, company: str, position: str) -> str:
    """Generate standardized JD filename."""
    # Normalize company and position
    company_slug = re.sub(r"[^a-zA-Z0-9가-힣]", "-", company.lower())
    position_slug = re.sub(r"[^a-zA-Z0-9가-힣]", "-", position.lower())

    # Remove multiple dashes
    company_slug = re.sub(r"-+", "-", company_slug).strip("-")
    position_slug = re.sub(r"-+", "-", position_slug).strip("-")

    return f"{job_id}-{company_slug}-{position_slug}.md"


def update_summary(
    job_id: str,
    company: str,
    position: str,
    verdict: str,
    folder: str,
) -> None:
    """Append entry to SUMMARY.md in screening directory."""
    summary_path = SCREENING_DIR / "SUMMARY.md"

    today = datetime.now().strftime("%Y-%m-%d")
    entry = f"| {today} | {job_id} | {company} | {position} | {verdict} | `{folder}` |\n"

    if not summary_path.exists():
        header = """# JD 스크리닝 요약

| 날짜 | ID | 회사 | 포지션 | 판정 | 분류 |
|------|-----|------|--------|------|------|
"""
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(header + entry, encoding="utf-8")
    else:
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write(entry)


def extract_metadata_from_jd(jd_content: str) -> dict:
    """Extract metadata from JD file content."""
    metadata = {}

    # Extract from table: | 회사명 | {company} |
    patterns = {
        "company": r"\|\s*회사명\s*\|\s*([^|]+)\|",
        "position": r"\|\s*포지션\s*\|\s*([^|]+)\|",
        "experience": r"\|\s*경력\s*\|\s*([^|]+)\|",
        "location": r"\|\s*근무지역?\s*\|\s*([^|]+)\|",
        "employment_type": r"\|\s*고용형태\s*\|\s*([^|]+)\|",
    }

    for key, pattern in patterns.items():
        match = re.search(pattern, jd_content)
        if match:
            metadata[key] = match.group(1).strip()

    # Extract URL from source line
    url_match = re.search(r"출처:\s*\[.*?\]\((https?://[^\)]+)\)", jd_content)
    if url_match:
        metadata["url"] = url_match.group(1)

    return metadata


def parse_frontmatter(content: str) -> Dict[str, str]:
    """Parse YAML frontmatter from file content.

    Returns a dict of key-value pairs from the frontmatter block.
    Returns empty dict if no frontmatter found.
    """
    if not content.startswith("---"):
        return {}

    lines = content.split("\n")
    if len(lines) < 2:
        return {}

    end_idx = -1
    for i, line in enumerate(lines[1:], 1):
        if line.strip() == "---":
            end_idx = i
            break

    if end_idx == -1:
        return {}

    result = {}
    for line in lines[1:end_idx]:
        if ":" in line:
            key, value = line.split(":", 1)
            result[key.strip()] = value.strip()

    return result


def get_user_status(content: str) -> Optional[str]:
    """Get user-defined status from file content.

    Returns the status value if found in frontmatter, None otherwise.
    """
    frontmatter = parse_frontmatter(content)
    return frontmatter.get("status")


def is_protected_status(status: Optional[str]) -> bool:
    """Check if status is protected from auto-reclassification.

    Protected statuses: rejected, applied, interview, offer
    Non-protected: pending, None
    """
    if status is None:
        return False
    return status in PROTECTED_STATUSES


def add_frontmatter_status(
    content: str,
    status: str,
    reason: Optional[str] = None,
) -> str:
    """Add or update status in file frontmatter.

    If frontmatter exists, updates status field.
    If no frontmatter, creates new frontmatter block.
    Always updates status_updated timestamp.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    existing = parse_frontmatter(content)

    # Build new frontmatter
    new_fields = dict(existing)
    new_fields["status"] = status
    new_fields["status_updated"] = today
    if reason:
        new_fields["status_reason"] = reason

    # Generate frontmatter block
    fm_lines = ["---"]
    for key, value in new_fields.items():
        fm_lines.append(f"{key}: {value}")
    fm_lines.append("---")
    frontmatter_block = "\n".join(fm_lines)

    # Remove existing frontmatter if present
    if content.startswith("---"):
        lines = content.split("\n")
        end_idx = -1
        for i, line in enumerate(lines[1:], 1):
            if line.strip() == "---":
                end_idx = i
                break
        if end_idx != -1:
            body = "\n".join(lines[end_idx + 1 :])
            return frontmatter_block + "\n" + body.lstrip("\n")

    # No existing frontmatter
    return frontmatter_block + "\n" + content


if __name__ == "__main__":
    # Test utilities
    test_urls = [
        "https://www.wanted.co.kr/wd/254599",
        "https://rememberapp.co.kr/job/12345",
        "https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx=67890",
    ]

    for url in test_urls:
        job_id = extract_job_id(url)
        platform = get_platform_from_url(url)
        print(f"{url} -> ID: {job_id}, Platform: {platform}")
