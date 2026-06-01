#!/usr/bin/env python3
"""JD Pipeline Constants — paths, mappings, and type definitions."""

from pathlib import Path
from typing import Any, Literal, TypeAlias

PROTECTED_STATUSES = {"rejected", "applied", "interview", "offer"}

BASE_DIR = Path(__file__).parent.parent.parent
PRIVATE_DIR = BASE_DIR / "private"
JOB_POSTINGS_DIR = PRIVATE_DIR / "job_postings"
JD_ANALYSIS_DIR = PRIVATE_DIR / "jd_analysis"
COMPANY_INFO_DIR = PRIVATE_DIR / "company_info"
SCREENING_DIR = JD_ANALYSIS_DIR / "screening"
SUMMARY_PATH = SCREENING_DIR / "SUMMARY.md"
CONFIG_PATH = JOB_POSTINGS_DIR / "search_config.yaml"

VERDICT_FOLDER_MAP = {
    "지원 추천": "conditional/high",
    "지원 보류": "conditional/hold",
    "지원 비추천": "pass",
}

VerdictType: TypeAlias = Literal["지원 추천", "지원 보류", "지원 비추천"]

VERDICT_PRIORITY = {"지원 비추천": 0, "지원 보류": 1, "지원 추천": 2}

STATUS_ALIASES = {
    "pending": "pending",
    "보류": "pending",
    "조건부": "pending",
    "조건부(상)": "pending",
    "조건부(중)": "pending",
    "조건부(하)": "pending",
    "조건부(보류)": "pending",
    "우선": "pending",
    "보류 / 패스": "pending",
    "pass": "rejected",
    "패스": "rejected",
    "rejected": "rejected",
    "applied": "applied",
    "지원": "applied",
    "interview": "interview",
    "면접": "interview",
    "offer": "offer",
    "오퍼": "offer",
}


def load_search_config(path: Path | None = None) -> dict[str, Any]:
    """Load the shared JD search config, returning an empty dict on failure."""
    config_path = path or CONFIG_PATH
    if not config_path.exists():
        return {}

    try:
        import yaml
    except ImportError:
        return {}

    try:
        with config_path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    except (OSError, yaml.YAMLError):
        return {}

    return data if isinstance(data, dict) else {}


def get_rate_limit(platform: str, default: float, *, path: Path | None = None) -> float:
    """Read a per-platform request delay from search_config.yaml."""
    config = load_search_config(path)
    raw_value = config.get("rate_limits", {}).get(platform)
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return default
