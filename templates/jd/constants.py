#!/usr/bin/env python3
"""JD Pipeline Constants — paths, mappings, and type definitions."""

from pathlib import Path
from typing import Literal

PROTECTED_STATUSES = {"rejected", "applied", "interview", "offer"}

BASE_DIR = Path(__file__).parent.parent.parent
PRIVATE_DIR = BASE_DIR / "private"
JOB_POSTINGS_DIR = PRIVATE_DIR / "job_postings"
JD_ANALYSIS_DIR = PRIVATE_DIR / "jd_analysis"
COMPANY_INFO_DIR = PRIVATE_DIR / "company_info"
SCREENING_DIR = JD_ANALYSIS_DIR / "screening"

VERDICT_FOLDER_MAP = {
    "지원 추천": "conditional/high",
    "지원 보류": "conditional/hold",
    "지원 비추천": "pass",
}

VerdictType = Literal["지원 추천", "지원 보류", "지원 비추천"]

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
