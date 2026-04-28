#!/usr/bin/env python3
"""Bulk TheVC enrichment for existing company_info markdown files."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

try:
    from .auto_company import (
        _append_enrichment_queue,
        _append_thevc_source_note,
        _has_thevc_source,
        _inject_thevc_into_file,
        is_headhunting_company,
    )
    from .ce_thevc import extract_thevc
    from .company_validator import COMPANY_INFO_DIR, CompanyData, parse_company_file, validate_company
except ImportError:
    from auto_company import (
        _append_enrichment_queue,
        _append_thevc_source_note,
        _has_thevc_source,
        _inject_thevc_into_file,
        is_headhunting_company,
    )
    from ce_thevc import extract_thevc
    from company_validator import COMPANY_INFO_DIR, CompanyData, parse_company_file, validate_company


BASE_DIR = Path(__file__).parent.parent.parent
REPORT_PATH = BASE_DIR / "private" / "build" / "thevc_enrichment_report.md"

POSITIVE_STARTUP_TOKENS = (
    "seed",
    "pre-a",
    "pre-b",
    "series",
    "시리즈",
    "스타트업",
    "벤처",
    "투자 유치",
    "인원 급성장",
    "설립3년이하",
)
NEGATIVE_STARTUP_TOKENS = (
    "ipo",
    "m&a",
    "상장기업",
    "코스피 상장",
    "코스닥 상장",
    "대기업",
    "글로벌 기업",
    "한국법인",
    "계열",
    "계열사",
    "일반기업",
    "해당 없음",
    "해당없음",
)
NEGATIVE_ROUND_TOKENS = ("ipo", "m&a", "상장", "대기업", "글로벌", "한국법인", "계열사", "일반기업", "해당 없음")


@dataclass
class Candidate:
    file_path: Path
    company: str
    completeness: float
    investment_round: str | None
    investment_total: float | None


@dataclass
class EnrichmentResult:
    candidate: Candidate
    status: str
    source_url: str = ""
    message: str = ""


def _explicit_startup_no(text: str) -> bool:
    lowered = text.lower()
    return "| 스타트업 여부 | no |" in lowered or "| 스타트업 여부 | 아니오 |" in lowered


def _explicit_startup_yes(text: str) -> bool:
    lowered = text.lower()
    return "| 스타트업 여부 | yes |" in lowered or "| 스타트업 여부 | 예 |" in lowered


def _real_investment_round(round_value: str | None) -> bool:
    if not round_value:
        return False
    lowered = round_value.lower()
    if lowered in {"정보 없음", "정보없음", "-"}:
        return False
    return not any(token in lowered for token in NEGATIVE_ROUND_TOKENS)


def is_high_confidence_startup(data: CompanyData, text: str) -> bool:
    lowered = text.lower()
    if _explicit_startup_no(text):
        return False
    if any(token in lowered for token in NEGATIVE_STARTUP_TOKENS):
        return False
    if _explicit_startup_yes(text):
        return True
    if _real_investment_round(data.investment_round):
        return True
    if data.investment_total:
        return True
    return any(token in lowered for token in POSITIVE_STARTUP_TOKENS)


def scan_candidates(
    company_info_dir: Path = COMPANY_INFO_DIR,
    *,
    min_completeness: float = 70.0,
) -> list[Candidate]:
    candidates: list[Candidate] = []
    for file_path in sorted(company_info_dir.glob("*.md")):
        if file_path.name.startswith("_"):
            continue

        text = file_path.read_text(encoding="utf-8")
        data = parse_company_file(file_path)
        completeness = validate_company(data, file_path).completeness_score

        company = data.name or file_path.stem
        if completeness < min_completeness:
            continue
        if is_headhunting_company(company):
            continue
        if _has_thevc_source(text):
            continue
        if not is_high_confidence_startup(data, text):
            continue

        candidates.append(
            Candidate(
                file_path=file_path,
                company=company,
                completeness=completeness,
                investment_round=data.investment_round,
                investment_total=data.investment_total,
            )
        )

    return candidates


def _platform_data_to_investment(data) -> dict:
    return {
        "round": data.investment_round or "정보 없음",
        "total": data.investment_total or "정보 없음",
        "investors": data.investors or [],
        "source": data.source_url,
    }


def enrich_candidate(candidate: Candidate, context) -> EnrichmentResult:
    try:
        data = extract_thevc(candidate.company, context)
    except Exception as exc:
        _append_enrichment_queue(candidate.company)
        return EnrichmentResult(candidate, "error", message=str(exc))

    if not data:
        _append_enrichment_queue(candidate.company)
        return EnrichmentResult(candidate, "not_found", message="TheVC search returned no company")

    has_investment = bool(data.investment_round or data.investment_total or data.investors)
    if has_investment:
        _inject_thevc_into_file(candidate.file_path, _platform_data_to_investment(data))
        return EnrichmentResult(candidate, "enriched", source_url=data.source_url)

    _append_thevc_source_note(
        candidate.file_path,
        data.source_url,
        "TheVC 확인: 공개 투자정보 추출 실패.",
    )
    return EnrichmentResult(candidate, "source_only", source_url=data.source_url)


def write_report(candidates: list[Candidate], results: list[EnrichmentResult]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1

    lines = [
        "# TheVC Enrichment Report",
        "",
        f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
        "",
        f"- Candidates: {len(candidates)}",
    ]
    for status in sorted(counts):
        lines.append(f"- {status}: {counts[status]}")

    lines.extend(["", "## Results", "", "| Status | Company | File | Source | Message |", "|------|------|------|------|------|"])
    for result in results:
        c = result.candidate
        lines.append(
            f"| {result.status} | {c.company} | {c.file_path.name} | {result.source_url or '-'} | {result.message or '-'} |"
        )

    untouched = [c for c in candidates if all(r.candidate.file_path != c.file_path for r in results)]
    if untouched:
        lines.extend(["", "## Untouched Candidates", "", "| Company | File | Completeness | Investment |", "|------|------|------|------|"])
        for c in untouched:
            inv = f"{c.investment_round or '-'} / {c.investment_total or '-'}"
            lines.append(f"| {c.company} | {c.file_path.name} | {c.completeness:.0f}% | {inv} |")

    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _print_candidates(candidates: list[Candidate]) -> None:
    print(f"후보 수: {len(candidates)}")
    for c in candidates:
        total = f"{c.investment_total:g}억원" if c.investment_total else "-"
        print(f"- {c.file_path.name}: {c.company}, {c.completeness:.0f}%, {c.investment_round or '-'} / {total}, TheVC lookup needed")


def main() -> None:
    parser = argparse.ArgumentParser(description="TheVC 누락 스타트업 회사정보 보강")
    parser.add_argument("--min-completeness", type=float, default=70.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    candidates = scan_candidates(min_completeness=args.min_completeness)
    if args.limit:
        candidates = candidates[: args.limit]

    if args.dry_run:
        _print_candidates(candidates)
        write_report(candidates, [])
        print(f"리포트: {REPORT_PATH}")
        return

    from playwright.sync_api import sync_playwright

    results: list[EnrichmentResult] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        try:
            for candidate in candidates:
                result = enrich_candidate(candidate, context)
                results.append(result)
                write_report(candidates, results)
                print(f"{result.status}: {candidate.company} {result.source_url or result.message}")
        finally:
            browser.close()

    write_report(candidates, results)
    print(f"리포트: {REPORT_PATH}")


if __name__ == "__main__":
    main()
