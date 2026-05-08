#!/usr/bin/env python3
"""Domain filter — detect and remove non-backend JD files.

Rule source alignment (drift prevention):
  1. Python taxonomy (this file): pre-screening fast filter, filename/position based
  2. LLM prompt (jd-screening-rules.md §0): authoritative source, boundary cases
  3. quick_filter.py title_exclude: search-stage filter
  When adding new domains, update all 3 sources.
"""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, List

try:
    from .constants import JOB_POSTINGS_DIR, SCREENING_DIR
    from .jd_content import extract_metadata_from_jd, get_user_status, is_protected_status
    from .path_utils import extract_job_id_from_filename
except ImportError:
    from constants import JOB_POSTINGS_DIR, SCREENING_DIR
    from jd_content import extract_metadata_from_jd, get_user_status, is_protected_status
    from path_utils import extract_job_id_from_filename


DOMAIN_TAXONOMY = {
    "mobile": {
        "filename_patterns": [r"(?:^|-)ios(?:-|$)", r"(?:^|-)android(?:-|$)",
                              r"(?:^|-)flutter(?:-|$)", r"(?:^|-)react-native(?:-|$)",
                              r"(?:^|-)모바일(?:-|$)"],
        "position_patterns": [r"\biOS\b", r"\bAndroid\b", r"\bFlutter\b",
                              r"모바일\s*(앱\s*)?(개발|엔지니어)"],
        "counter_indicators": ["backend", "server", "백엔드", "서버"],
    },
    "ai_ml": {
        "filename_patterns": [r"(?:^|-)mlops(?:-|$)", r"(?:^|-)ml-engineer(?:-|$)",
                              r"(?:^|-)ai-engineer(?:-|$)", r"(?:^|-)llm(?:-|$)",
                              r"(?:^|-)machine-learning(?:-|$)"],
        "position_patterns": [r"\bML\s*Engineer\b", r"\bMLOps\b", r"\bAI\s*Engineer\b",
                              r"\bLLM\b", r"\bMachine\s*Learning\b"],
        "counter_indicators": ["backend", "server", "백엔드", "서버"],
    },
    "hardware_embedded": {
        "filename_patterns": [r"(?:^|-)soc(?:-|$)", r"(?:^|-)hardware(?:-|$)",
                              r"(?:^|-)fpga(?:-|$)", r"(?:^|-)embedded(?:-|$)",
                              r"(?:^|-)반도체(?:-|$)", r"(?:^|-)firmware(?:-|$)"],
        "position_patterns": [r"\bSoC\b", r"\bFPGA\b", r"\bEmbedded\b",
                              r"\bHardware\b", r"반도체", r"\bFirmware\b"],
        "counter_indicators": [],
    },
    "devops_sre": {
        "filename_patterns": [r"(?:^|-)devops(?:-|$)", r"(?:^|-)sre(?:-|$)",
                              r"(?:^|-)cloud-eng(?:-|$)", r"(?:^|-)platform-eng(?:-|$)",
                              r"(?:^|-)infra-eng(?:-|$)"],
        "position_patterns": [r"\bDevOps\b", r"\bSRE\b", r"Cloud\s*Engineer",
                              r"Platform\s*Engineer", r"인프라\s*엔지니어"],
        "counter_indicators": ["backend", "server", "백엔드", "서버"],
    },
    "frontend": {
        "filename_patterns": [r"(?:^|-)frontend(?:-|$)", r"(?:^|-)front-end(?:-|$)",
                              r"(?:^|-)프론트(?:-|$)"],
        "position_patterns": [r"\bFrontend\b", r"\bFront[\s-]?end\b", r"프론트엔드",
                              r"프론트\s*개발"],
        "counter_indicators": ["fullstack", "full-stack", "풀스택"],
    },
    "non_sw": {
        "filename_patterns": [r"(?:^|-)mechanical(?:-|$)", r"(?:^|-)electrical(?:-|$)",
                              r"(?:^|-)civil(?:-|$)", r"(?:^|-)rf-eng(?:-|$)",
                              r"(?:^|-)mooring(?:-|$)"],
        "position_patterns": [r"기구설계", r"기계\s*엔지니어", r"전기\s*엔지니어",
                              r"토목", r"\bRF\s*Engineer\b"],
        "counter_indicators": [],
    },
    "data_engineering": {
        "filename_patterns": [r"(?:^|-)data-engineer(?:-|$)",
                              r"(?:^|-)데이터-엔지니어(?:-|$)",
                              r"(?:^|-)dataops(?:-|$)"],
        "position_patterns": [r"\bData\s*Engineer\b", r"데이터\s*엔지니어",
                              r"\bDataOps\b"],
        "counter_indicators": ["backend", "server", "백엔드", "서버"],
    },
    "qa_pm": {
        "filename_patterns": [r"(?:^|-)qa-engineer(?:-|$)", r"(?:^|-)기획자(?:-|$)",
                              r"(?:^|-)product-manager(?:-|$)"],
        "position_patterns": [r"\bQA\s*Engineer\b", r"\bProduct\s*Manager\b",
                              r"기획자", r"프로덕트\s*매니저"],
        "counter_indicators": [],
    },
}

SCREENING_MISMATCH_PATTERNS = [
    re.compile(r"도메인\s*불일치"),
    re.compile(r"도메인\s*자체가\s*다름"),
    re.compile(r"도메인\s*컷"),
]

GLOBAL_COUNTER_INDICATORS = re.compile(
    r"(?:^|-)(?:backend|server|백엔드|서버)(?:-|$)", re.IGNORECASE
)


@dataclass
class DomainMatch:
    category: str
    matched_pattern: str


@dataclass
class DomainClassification:
    category: Optional[str]
    action: str  # "delete", "skip", "needs_manual"
    tier_used: Optional[int]
    reason: str


@dataclass
class FilteredItem:
    jd_path: str
    screening_path: Optional[str]
    category: Optional[str]
    tier: Optional[int]
    reason: str
    action: str  # "delete", "skip", "needs_manual"


def detect_from_screening(screening_content: str) -> Optional[str]:
    """Tier 1: detect domain mismatch text in screening file."""
    for pattern in SCREENING_MISMATCH_PATTERNS:
        if pattern.search(screening_content):
            return "domain_mismatch"
    return None


def detect_from_position(position: str) -> Optional[DomainMatch]:
    """Tier 2: match position text against taxonomy patterns."""
    for category, rules in DOMAIN_TAXONOMY.items():
        for pattern in rules["position_patterns"]:
            if re.search(pattern, position, re.IGNORECASE):
                return DomainMatch(category=category, matched_pattern=pattern)
    return None


def detect_from_filename(filename: str) -> Optional[DomainMatch]:
    """Tier 3: match filename slug against taxonomy patterns."""
    stem = Path(filename).stem.lower() if "." in filename else filename.lower()
    for category, rules in DOMAIN_TAXONOMY.items():
        for pattern in rules["filename_patterns"]:
            if re.search(pattern, stem):
                return DomainMatch(category=category, matched_pattern=pattern)
    return None


def has_counter_indicator(filename: str, position: Optional[str],
                          category: Optional[str] = None) -> bool:
    """Check for backend/server keywords that override domain classification."""
    stem = Path(filename).stem.lower() if "." in filename else filename.lower()

    if GLOBAL_COUNTER_INDICATORS.search(stem):
        return True
    if position and re.search(r"backend|server|백엔드|서버", position, re.IGNORECASE):
        return True

    if category and category in DOMAIN_TAXONOMY:
        cat_indicators = DOMAIN_TAXONOMY[category].get("counter_indicators", [])
        if not cat_indicators:
            return False
        cat_pattern = "|".join(re.escape(ci) for ci in cat_indicators)
        if re.search(cat_pattern, stem, re.IGNORECASE):
            return True
        if position and re.search(cat_pattern, position, re.IGNORECASE):
            return True

    return False


def _find_screening_file(job_id: str) -> Optional[Path]:
    """Find screening file by job_id, avoiding prefix collisions."""
    if not SCREENING_DIR.exists():
        return None
    for f in SCREENING_DIR.glob(f"{job_id}-*.md"):
        file_job_id = extract_job_id_from_filename(f.name)
        if file_job_id == job_id:
            return f
    return None


def classify_domain(jd_path: Path) -> DomainClassification:
    """Orchestrate 3-tier detection. Returns classification with action."""
    filename = jd_path.name
    job_id = extract_job_id_from_filename(filename)

    content = jd_path.read_text(encoding="utf-8")

    user_status = get_user_status(content)
    if is_protected_status(user_status):
        return DomainClassification(
            category=None, action="skip", tier_used=None,
            reason=f"보호된 상태: {user_status}",
        )

    metadata = extract_metadata_from_jd(content)
    position = metadata.get("position")

    screening_category = None
    screening_path = None
    if job_id:
        sf = _find_screening_file(job_id)
        if sf:
            screening_path = sf
            screening_content = sf.read_text(encoding="utf-8")
            screening_category = detect_from_screening(screening_content)

    position_match = detect_from_position(position) if position else None
    filename_match = detect_from_filename(filename)

    tier_used = None
    category = None
    reason_detail = ""

    if screening_category:
        tier_used = 1
        category = position_match.category if position_match else (
            filename_match.category if filename_match else "domain_mismatch"
        )
        reason_detail = "screening 도메인 불일치"
    elif position_match:
        tier_used = 2
        category = position_match.category
        reason_detail = f"position: {position} ({position_match.matched_pattern})"
    elif filename_match:
        tier_used = 3
        category = filename_match.category
        reason_detail = f"filename: {filename_match.matched_pattern}"

    if category is None:
        return DomainClassification(
            category=None, action="skip", tier_used=None,
            reason="백엔드/도메인 일치",
        )

    effective_category = category if category != "domain_mismatch" else None
    check_category = position_match.category if position_match else (
        filename_match.category if filename_match else category
    )

    if has_counter_indicator(filename, position, check_category):
        return DomainClassification(
            category=effective_category or check_category,
            action="needs_manual",
            tier_used=tier_used,
            reason=f"{reason_detail} + counter-indicator 감지",
        )

    return DomainClassification(
        category=effective_category or check_category,
        action="delete",
        tier_used=tier_used,
        reason=reason_detail,
    )


def scan_folder(folder: Path, dry_run: bool = False,
                delete: bool = False) -> List[FilteredItem]:
    """Scan folder for non-backend JDs. Returns list of FilteredItem."""
    results: List[FilteredItem] = []

    if not folder.exists():
        print(f"폴더를 찾을 수 없습니다: {folder}")
        return results

    md_files = sorted(folder.glob("*.md"))
    for md_file in md_files:
        if md_file.name in ("CLAUDE.md", "jd-screening-rules.md", "SUMMARY.md"):
            continue

        classification = classify_domain(md_file)

        if classification.action == "skip":
            continue

        job_id = extract_job_id_from_filename(md_file.name)
        screening_file = _find_screening_file(job_id) if job_id else None

        item = FilteredItem(
            jd_path=str(md_file),
            screening_path=str(screening_file) if screening_file else None,
            category=classification.category,
            tier=classification.tier_used,
            reason=classification.reason,
            action=classification.action,
        )
        results.append(item)

        if classification.action == "delete" and not dry_run and delete:
            md_file.unlink()
            if screening_file and screening_file.exists():
                screening_file.unlink()

    return results


def build_manifest(items: List[FilteredItem], action_label: str) -> dict:
    """Build audit manifest JSON."""
    return {
        "timestamp": datetime.now().isoformat(),
        "action": action_label,
        "total": len(items),
        "items": [
            {
                "jd_path": item.jd_path,
                "screening_path": item.screening_path,
                "category": item.category,
                "tier": item.tier,
                "reason": item.reason,
                "action": item.action,
            }
            for item in items
        ],
    }


def write_manifest(manifest: dict, output_dir: Optional[Path] = None) -> Path:
    """Write manifest JSON to file."""
    if output_dir is None:
        output_dir = JOB_POSTINGS_DIR.parent / "build"
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = output_dir / f"domain-filter-{timestamp}.json"
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
