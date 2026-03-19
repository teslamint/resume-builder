#!/usr/bin/env python3
"""Detect and report company info files with empty/placeholder fields.

Usage:
    python3 templates/jd/enrich_company_fields.py --scan
    python3 templates/jd/enrich_company_fields.py --scan --threshold 3
    python3 templates/jd/enrich_company_fields.py --scan --empty-only
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import quote_plus

from recollect_company_info import (
    extract_urls,
    list_company_files,
    parse_company_name,
)
from company_validator import parse_company_file, validate_company

BASE_DIR = Path(__file__).resolve().parents[2]
BUILD_DIR = BASE_DIR / "private" / "build"
REPORT_PATH = BUILD_DIR / "empty_company_targets.md"

EMPTY_MARKER = "정보 없음"
HEADHUNTING_MARKER = "헤드헌팅/서치펌"

# Template minimum count: non-startup (8) + startup adds 2 more.
# Files with all template fields still as placeholder have empty_count >= 8.
FULLY_EMPTY_MIN_COUNT = 8


@dataclass
class TargetInfo:
    file_name: str
    company_name: str
    empty_count: int
    completeness: float
    wanted_url: str | None
    jd_source_url: str | None


def count_empty_fields(content: str) -> int:
    return content.count(EMPTY_MARKER)


def find_wanted_company_url(urls: list[str]) -> str | None:
    for u in urls:
        if "wanted.co.kr/company/" in u:
            return u
    return None


def find_jd_source_url(content: str) -> str | None:
    m = re.search(r"\*JD 출처:\s*\[([^\]]+)\]", content)
    if m:
        return m.group(1).strip()
    return None


def make_wanted_search_url(company_name: str) -> str:
    q = quote_plus(company_name)
    return f"https://www.wanted.co.kr/search?query={q}&tab=company"


def scan_empty_files(threshold: int = 5, empty_only: bool = False) -> list[TargetInfo]:
    targets: list[TargetInfo] = []

    for file_path in list_company_files():
        content = file_path.read_text(encoding="utf-8")
        if HEADHUNTING_MARKER in content:
            continue
        empty_count = count_empty_fields(content)

        data = parse_company_file(file_path)
        result = validate_company(data, file_path)
        completeness = result.completeness_score

        if empty_only:
            if empty_count < FULLY_EMPTY_MIN_COUNT:
                continue
        elif empty_count < threshold and completeness >= 70:
            continue

        company_name = parse_company_name(content, file_path.stem)
        urls = extract_urls(content)
        wanted_url = find_wanted_company_url(urls)
        jd_source = find_jd_source_url(content)

        targets.append(
            TargetInfo(
                file_name=file_path.name,
                company_name=company_name,
                empty_count=empty_count,
                completeness=completeness,
                wanted_url=wanted_url,
                jd_source_url=jd_source,
            )
        )

    targets.sort(key=lambda t: (-t.empty_count, t.company_name))
    return targets


def write_report(targets: list[TargetInfo], threshold: int, empty_only: bool) -> None:
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()

    mode = "완전 빈 파일" if empty_only else f"threshold={threshold}"
    lines = [
        "# Empty Company Info Targets",
        "",
        f"*생성일: {today}*",
        f"*모드: {mode}*",
        f"*대상 수: {len(targets)}*",
        "",
        "| 파일명 | 회사명 | 빈 필드 수 | completeness% | Wanted URL | JD 출처 |",
        "|--------|--------|-----------|---------------|------------|---------|",
    ]

    for t in targets:
        if t.wanted_url:
            url_cell = f"[회사 페이지]({t.wanted_url})"
        else:
            search_url = make_wanted_search_url(t.company_name)
            url_cell = f"[검색]({search_url})"

        jd_cell = f"[링크]({t.jd_source_url})" if t.jd_source_url else "-"
        lines.append(
            f"| {t.file_name} | {t.company_name} | {t.empty_count} "
            f"| {t.completeness:.0f}% | {url_cell} | {jd_cell} |"
        )

    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Detect empty company info files")
    parser.add_argument("--scan", action="store_true", required=True, help="Scan and report empty files")
    parser.add_argument(
        "--threshold",
        type=int,
        default=5,
        help="Minimum '정보 없음' count to include (default: 5)",
    )
    parser.add_argument(
        "--empty-only",
        action="store_true",
        help=f"Only include fully-empty files (all template fields still placeholder, empty_count>={FULLY_EMPTY_MIN_COUNT})",
    )
    args = parser.parse_args()

    all_files = list_company_files()
    targets = scan_empty_files(threshold=args.threshold, empty_only=args.empty_only)

    fully_empty = [t for t in targets if t.empty_count >= FULLY_EMPTY_MIN_COUNT]
    write_report(targets, threshold=args.threshold, empty_only=args.empty_only)

    print(f"[scan] empty={len(fully_empty)} partial={len(targets) - len(fully_empty)} total={len(all_files)}")
    print(f"[scan] report={REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
