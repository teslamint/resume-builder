"""Shared data types for company extractor modules.

Leaf module — stdlib only, no local imports.
Prevents circular imports when company_extractor.py and ce_*.py need the same types.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PlatformData:
    """Data extracted from a single platform."""

    platform: str  # "wanted" | "saramin" | "thevc" | "jd"
    source_url: str
    company_name: str
    company_name_en: str | None = None
    industry: str | None = None
    founded_year: int | None = None
    employee_count: int | None = None
    employee_joined_1y: int | None = None
    employee_left_1y: int | None = None
    avg_salary: int | None = None  # 만원
    salary_percentile: str | None = None
    revenue: list[dict] | None = None  # [{year, amount_억}]
    investment_round: str | None = None
    investment_total: str | None = None  # "N억원"
    investors: list[str] = field(default_factory=list)
    benefits: list[str] = field(default_factory=list)
    description: str | None = None
    tags: list[str] = field(default_factory=list)
    raw_extra: dict = field(default_factory=dict)


@dataclass
class ExtractionResult:
    """Result of a company info extraction run."""

    company: str
    file_path: Path
    completeness: float
    platforms_used: list[str]
    platforms_failed: list[str]
    source_urls: list[str]
