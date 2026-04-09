#!/usr/bin/env python3
"""Verdict parsing, normalization, classification, and file movement."""

import re
import shutil
from pathlib import Path
from typing import Optional, List

try:
    from .constants import VERDICT_FOLDER_MAP, VerdictType, VERDICT_PRIORITY, JOB_POSTINGS_DIR
except ImportError:
    from constants import VERDICT_FOLDER_MAP, VerdictType, VERDICT_PRIORITY, JOB_POSTINGS_DIR


def normalize_verdict(verdict: str) -> Optional[VerdictType]:
    """Normalize many verdict variants to canonical 3-state values."""
    if not verdict:
        return None

    verdict_clean = re.sub(r"[\*\`_#>\[\]\(\)]", "", verdict).strip()
    verdict_clean = re.sub(r"\s+", " ", verdict_clean)
    verdict_lower = verdict_clean.lower()

    if verdict_clean in {"| 포지션 | 판정 | 사유 |", "포지션 판정 사유", "판정"}:
        return None

    if any(token in verdict_lower for token in ("비추천", "pass", "지원 안 함", "지원안함", "컷", "패스")):
        return "지원 비추천"

    if any(token in verdict_lower for token in ("조건부", "보류", "hold", "검토", "킵", "keep", "우선")):
        return "지원 보류"

    if verdict_clean == "\uc9c0\uc6d0":
        return "\uc9c0\uc6d0 \ucd94\ucc9c"

    if any(token in verdict_lower for token in ("\uac15\ub825 \ucd94\ucc9c", "\uc9c0\uc6d0 \ucd94\ucc9c", "\uc989\uc2dc \uc9c0\uc6d0", "\ucd94\ucc9c")):
        return "\uc9c0\uc6d0 \ucd94\ucc9c"

    return None


def _pick_worst_case_verdict(verdicts: List[str]) -> Optional[VerdictType]:
    """For multi-position tables, keep conservative (worst-case) verdict."""
    normalized = [normalize_verdict(v) for v in verdicts]
    candidates = [v for v in normalized if v is not None]
    if not candidates:
        return None
    return min(candidates, key=lambda v: VERDICT_PRIORITY[v])


def _extract_verdict_from_section(section: str) -> Optional[VerdictType]:
    """Extract verdict from a dedicated section body."""
    candidates: List[str] = []

    for line in section.splitlines():
        line_stripped = line.strip()
        if not line_stripped:
            continue
        heading_match = re.match(r"^#{2,6}\s*(.+)$", line_stripped)
        if heading_match:
            candidates.append(heading_match.group(1))

        quote_match = re.match(r"^>?\s*판정\s*[:：]\s*(.+)$", line_stripped, re.IGNORECASE)
        if quote_match:
            candidates.append(quote_match.group(1))

        if line_stripped.startswith("|") and line_stripped.endswith("|"):
            cells = [c.strip() for c in line_stripped.strip("|").split("|")]
            if len(cells) >= 2:
                if cells[0] in {"포지션", "position"} and cells[1] in {"판정", "verdict"}:
                    continue
                if re.fullmatch(r"[-:\s]+", cells[0]) and re.fullmatch(r"[-:\s]+", cells[1]):
                    continue
                candidates.append(cells[1])

    return _pick_worst_case_verdict(candidates)


def classify_by_verdict(verdict: str) -> Optional[str]:
    """Map verdict string to target folder path."""
    normalized = normalize_verdict(verdict)
    if not normalized:
        return None
    return VERDICT_FOLDER_MAP.get(normalized)


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


def parse_verdict_from_screening(screening_content: str) -> Optional[VerdictType]:
    """Extract canonical verdict from screening analysis content."""
    single_line_patterns = [
        r"^\s*#{1,6}\s*최종\s*판정\s*[:：\-]\s*(.+?)\s*$",
        r"^\s*#{1,6}\s*최종\s*판정\s+(.+?)\s*$",
        r"^\s*>\s*판정\s*[:：]\s*(.+?)\s*$",
        r"^\s*>\s*최종\s*판정\s*[:：]\s*(.+?)\s*$",
        r"^\s*\|\s*최종\s*판단\s*\|\s*(.+?)\s*\|",
        r"^\s*\*\*결론\*\*\s*[:：]\s*(.+?)\s*$",
        r"^\s*-\s*\*\*최종\s*판정\*\*\s*[:：]\s*(.+?)\s*$",
    ]
    for pattern in single_line_patterns:
        match = re.search(pattern, screening_content, re.IGNORECASE | re.MULTILINE)
        if match:
            verdict = normalize_verdict(match.group(1))
            if verdict:
                return verdict

    section_patterns = [
        r"(?is)^##\s*최종\s*판정\s*\n(.*?)(?=^##\s|\Z)",
        r"(?is)^##\s*판정\s*\n(.*?)(?=^##\s|\Z)",
    ]
    for pattern in section_patterns:
        section_match = re.search(pattern, screening_content, re.MULTILINE)
        if section_match:
            verdict = _extract_verdict_from_section(section_match.group(1))
            if verdict:
                return verdict

    heading_candidates = re.findall(r"^\s*#{2,6}\s*(.+?)\s*$", screening_content, re.MULTILINE)
    return _pick_worst_case_verdict(heading_candidates)
