from __future__ import annotations

import re
from pathlib import Path

try:
    from .ce_types import PlatformData
    from .constants import JOB_POSTINGS_DIR
except ImportError:
    from ce_types import PlatformData
    from constants import JOB_POSTINGS_DIR


def normalize_company_name(name: str) -> str:
    """Normalize company name for fuzzy matching."""
    name = re.sub(r"\(주\)|\(유\)|\(사\)", "", name)
    name = re.sub(r"\s+", "", name).lower()
    return name


def extract_from_jd_files(company_name: str) -> PlatformData | None:
    """Extract investment/revenue info from existing JD files.

    Scans job_postings/ subdirectories for files mentioning the company,
    then extracts investment round, total, investors, and revenue via regex.
    Returns a PlatformData with platform="jd" or None if nothing found.
    """
    if not JOB_POSTINGS_DIR.exists():
        return None

    norm_name = normalize_company_name(company_name)
    matching_files: list[Path] = []

    for md_file in JOB_POSTINGS_DIR.rglob("*.md"):
        if md_file.name.startswith("jd-screening"):
            continue
        try:
            content = md_file.read_text(encoding="utf-8")
        except Exception:
            continue
        norm_content = normalize_company_name(content[:500])
        if norm_name in norm_content:
            matching_files.append(md_file)

    if not matching_files:
        return None

    data = PlatformData(
        platform="jd",
        source_url="local:job_postings",
        company_name=company_name,
    )

    for md_file in matching_files:
        try:
            content = md_file.read_text(encoding="utf-8")
        except Exception:
            continue

        # Investment round
        if not data.investment_round:
            m = re.search(
                r"(Seed|Pre-?[AB]|Series\s*[A-Z]\+?|시리즈\s*[A-Z]|브릿지|Pre\s*IPO)",
                content,
                re.IGNORECASE,
            )
            if m:
                data.investment_round = m.group(1).strip()

        # Cumulative investment amount — "누적 투자 300억", "130억을 투자", "총 1,140억원"
        if not data.investment_total:
            patterns = [
                r"누적\s*(?:투자\s*(?:금액?\s*)?)?[:\s]*(?:약\s*)?([\d,]+(?:\.\d+)?)\s*억",
                r"([\d,]+(?:\.\d+)?)\s*억\s*(?:원?\s*)?(?:의\s*)?투자(?:를\s*)?(?:유치|받)",
                r"총\s*([\d,]+(?:\.\d+)?)\s*억\s*원?\s*(?:의\s*)?투자",
            ]
            for pat in patterns:
                m = re.search(pat, content)
                if m:
                    data.investment_total = f"{m.group(1)}억원"
                    break

        # Investors — "투자사: A, B, C" or inline mention
        if not data.investors:
            m = re.search(r"투자사[:\s]*([^\n]+)", content)
            if m:
                raw = m.group(1).strip()
                data.investors = [
                    inv.strip()
                    for inv in re.split(r"[,、·]", raw)
                    if inv.strip() and len(inv.strip()) < 30
                ]

        # Revenue — "매출 300억", "매출액 1,356억원", "연매출 300억 원"
        if not data.revenue:
            m = re.search(r"(?:연?매출(?:액)?)\s*(?:약\s*)?([\d,]+(?:\.\d+)?)\s*억", content)
            if m:
                amount = float(m.group(1).replace(",", ""))
                data.revenue = [{"year": "latest", "amount_억": amount}]

    has_info = data.investment_round or data.investment_total or data.investors or data.revenue
    if has_info:
        print(f"   [jd] JD 파일에서 보충 정보 추출: round={data.investment_round}, total={data.investment_total}")
        return data
    return None
