#!/usr/bin/env python3
"""JD content handling — metadata, frontmatter, status, company rejection."""

import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict

try:
    from . import constants
    from .naming import normalize_company_name
except ImportError:
    import constants
    from naming import normalize_company_name


def load_screening_rules() -> str:
    """Load screening rules from file."""
    rules_path = constants.JOB_POSTINGS_DIR / "jd-screening-rules.md"
    if rules_path.exists():
        return rules_path.read_text(encoding="utf-8")
    return ""


def load_company_info(company: str) -> Optional[str]:
    """Load company info if available."""
    normalized = company.lower().replace(" ", "-").replace("_", "-")

    for pattern in [f"{normalized}.md", f"{company}.md"]:
        path = constants.COMPANY_INFO_DIR / pattern
        if path.exists():
            return path.read_text(encoding="utf-8")

    if constants.COMPANY_INFO_DIR.exists():
        for file in constants.COMPANY_INFO_DIR.glob("*.md"):
            if normalized in file.stem.lower():
                return file.read_text(encoding="utf-8")

    return None


def generate_jd_filename(job_id: str, company: str, position: str) -> str:
    """Generate standardized JD filename."""
    company_slug = re.sub(r"[^a-zA-Z0-9\uac00-\ud7a3]", "-", company.lower())
    position_slug = re.sub(r"[^a-zA-Z0-9\uac00-\ud7a3]", "-", position.lower())

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
    summary_path = constants.SCREENING_DIR / "SUMMARY.md"

    today = datetime.now().strftime("%Y-%m-%d")
    entry = f"| {today} | {job_id} | {company} | {position} | {verdict} | `{folder}` |\n"

    if not summary_path.exists():
        header = "# JD \uc2a4\ud06c\ub9ac\ub2dd \uc694\uc57d\n\n| \ub0a0\uc9dc | ID | \ud68c\uc0ac | \ud3ec\uc9c0\uc158 | \ud310\uc815 | \ubd84\ub958 |\n|------|-----|------|--------|------|------|\n"
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(header + entry, encoding="utf-8")
    else:
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write(entry)


def extract_metadata_from_jd(jd_content: str) -> dict:
    """Extract metadata from JD file content."""
    metadata = {}

    patterns = {
        "company": r"\|\s*\ud68c\uc0ac\uba85\s*\|\s*([^|]+)\|",
        "position": r"\|\s*\ud3ec\uc9c0\uc158\s*\|\s*([^|]+)\|",
        "experience": r"\|\s*\uacbd\ub825\s*\|\s*([^|]+)\|",
        "location": r"\|\s*\uadfc\ubb34\uc9c0\uc5ed?\s*\|\s*([^|]+)\|",
        "employment_type": r"\|\s*\uace0\uc6a9\ud615\ud0dc\s*\|\s*([^|]+)\|",
    }

    for key, pattern in patterns.items():
        match = re.search(pattern, jd_content)
        if match:
            metadata[key] = match.group(1).strip()

    url_match = re.search(r"\ucd9c\ucc98:\s*\[.*?\]\((https?://[^\)]+)\)", jd_content)
    if url_match:
        metadata["url"] = url_match.group(1)

    return metadata


def parse_frontmatter(content: str) -> Dict[str, str]:
    """Parse YAML frontmatter from file content."""
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
    """Get user-defined status from file content."""
    frontmatter = parse_frontmatter(content)
    return frontmatter.get("status")


def normalize_status(status: Optional[str]) -> Optional[str]:
    """Normalize legacy/Korean status labels to canonical status keys."""
    if status is None:
        return None
    status_clean = str(status).strip().strip("'\"")
    if not status_clean:
        return None

    if status_clean in {"pending", "applied", "rejected", "interview", "offer"}:
        return status_clean

    status_lower = status_clean.lower()
    if status_lower in constants.STATUS_ALIASES:
        return constants.STATUS_ALIASES[status_lower]
    return constants.STATUS_ALIASES.get(status_clean, status_clean)


def is_protected_status(status: Optional[str]) -> bool:
    """Check if status is protected from auto-reclassification."""
    normalized = normalize_status(status)
    if normalized is None:
        return False
    return normalized in constants.PROTECTED_STATUSES


def add_frontmatter_status(
    content: str,
    status: str,
    reason: Optional[str] = None,
) -> str:
    """Add or update status in file frontmatter."""
    today = datetime.now().strftime("%Y-%m-%d")
    existing = parse_frontmatter(content)
    normalized_status = normalize_status(status) or status

    new_fields = dict(existing)
    new_fields["status"] = normalized_status
    new_fields["status_updated"] = today
    if reason:
        new_fields["status_reason"] = reason

    fm_lines = ["---"]
    for key, value in new_fields.items():
        fm_lines.append(f"{key}: {value}")
    fm_lines.append("---")
    frontmatter_block = "\n".join(fm_lines)

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

    return frontmatter_block + "\n" + content


def get_rejected_companies() -> set:
    """Collect normalized company names from rejected/passed JD files."""
    rejected = set()

    for dirname in ("rejected", "pass"):
        target_dir = constants.JOB_POSTINGS_DIR / dirname
        if not target_dir.exists():
            continue
        for f in target_dir.glob("*.md"):
            content = f.read_text(encoding="utf-8")
            meta = extract_metadata_from_jd(content)
            company = meta.get("company", "")
            if company:
                rejected.add(normalize_company_name(company))

    for folder in constants.JOB_POSTINGS_DIR.iterdir():
        if not folder.is_dir() or folder.name in ("rejected", "pass", "unprocessed", "auto_results", "examples"):
            continue
        for f in folder.rglob("*.md"):
            content = f.read_text(encoding="utf-8")
            status = normalize_status(get_user_status(content))
            if status == "rejected":
                meta = extract_metadata_from_jd(content)
                company = meta.get("company", "")
                if company:
                    rejected.add(normalize_company_name(company))

    return rejected


def is_rejected_company(
    company: str,
    rejected_companies: set,
    config_excludes: list | None = None,
) -> bool:
    """Check if company is in the rejected set (exact match after normalization)."""
    normalized = normalize_company_name(company)
    if not normalized:
        return False
    if normalized in rejected_companies:
        return True
    if config_excludes:
        config_normalized = {normalize_company_name(c) for c in config_excludes}
        if normalized in config_normalized:
            return True
    return False
