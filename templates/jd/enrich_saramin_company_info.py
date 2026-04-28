#!/usr/bin/env python3
"""Bulk Saramin enrichment for existing company_info markdown files.

Reads from the Saramin enrichment queue (company_enrichment_saramin.txt),
attempts extraction via Patchright (falling back to Playwright), and
fills in empty fields in existing company_info files.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

try:
    from .auto_company import SARAMIN_ENRICHMENT_QUEUE_PATH, _append_saramin_enrichment_queue, is_headhunting_company
    from .ce_merge import build_enriched_markdown
    from .ce_saramin import extract_saramin
    from .ce_types import PlatformData
    from .company_validator import COMPANY_INFO_DIR, CompanyData, parse_company_file, validate_company
    from .naming import slugify_company
except ImportError:
    from auto_company import SARAMIN_ENRICHMENT_QUEUE_PATH, _append_saramin_enrichment_queue, is_headhunting_company
    from ce_merge import build_enriched_markdown
    from ce_saramin import extract_saramin
    from ce_types import PlatformData
    from company_validator import COMPANY_INFO_DIR, CompanyData, parse_company_file, validate_company
    from naming import slugify_company


BASE_DIR = Path(__file__).parent.parent.parent
REPORT_PATH = BASE_DIR / "private" / "build" / "saramin_enrichment_report.md"

_EMPTY_SENTINEL = frozenset({"정보 없음", "정보없음", "-", ""})


def _is_empty(val) -> bool:
    if val is None:
        return True
    if isinstance(val, str):
        return val.strip() in _EMPTY_SENTINEL
    if isinstance(val, (list, tuple)):
        return len(val) == 0
    return False


def _extract_source_urls(content: str) -> list[str]:
    return re.findall(r"- (https?://\S+)", content)


@dataclass
class SaraminCandidate:
    company: str
    file_path: Path | None
    completeness: float


@dataclass
class SaraminEnrichmentResult:
    candidate: SaraminCandidate
    status: str
    source_url: str = ""
    message: str = ""


def scan_candidates(queue_path: Path = SARAMIN_ENRICHMENT_QUEUE_PATH) -> list[SaraminCandidate]:
    if not queue_path.exists():
        return []

    companies = [
        line.strip()
        for line in queue_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    candidates: list[SaraminCandidate] = []
    for company in companies:
        if is_headhunting_company(company):
            continue
        slug = slugify_company(company)
        file_path = COMPANY_INFO_DIR / f"{slug}.md"
        if not file_path.exists():
            file_path = COMPANY_INFO_DIR / f"{Path(company).name}.md"
        if not file_path.exists():
            file_path = None

        completeness = 0.0
        if file_path and file_path.exists():
            try:
                data = parse_company_file(file_path)
                completeness = validate_company(data, file_path).completeness_score
            except Exception:
                pass

        candidates.append(SaraminCandidate(company=company, file_path=file_path, completeness=completeness))

    return candidates


def _build_merged_dict(existing: CompanyData, saramin: PlatformData, existing_urls: list[str]) -> dict:
    """Build merged dict: existing value wins; saramin fills empty slots only."""
    # investment_total: existing is float (억원), saramin is str ("N억원")
    inv_total: str | None
    if not _is_empty(existing.investment_total):
        inv_total = f"{existing.investment_total:g}억원"
    elif not _is_empty(saramin.investment_total):
        inv_total = saramin.investment_total
    else:
        inv_total = None

    return {
        "company_name": existing.name or saramin.company_name,
        "company_name_en": existing.name_en if not _is_empty(existing.name_en) else saramin.company_name_en,
        "industry": existing.industry if not _is_empty(existing.industry) else saramin.industry,
        "founded_year": existing.founded_year if not _is_empty(existing.founded_year) else saramin.founded_year,
        "employee_count": existing.employee_current if not _is_empty(existing.employee_current) else saramin.employee_count,
        "employee_joined_1y": existing.employee_joined_1y if not _is_empty(existing.employee_joined_1y) else saramin.employee_joined_1y,
        "employee_left_1y": existing.employee_left_1y if not _is_empty(existing.employee_left_1y) else saramin.employee_left_1y,
        "avg_salary": existing.avg_salary if not _is_empty(existing.avg_salary) else saramin.avg_salary,
        "salary_percentile": existing.salary_percentile if not _is_empty(existing.salary_percentile) else saramin.salary_percentile,
        "revenue": None,
        "investment_round": existing.investment_round if not _is_empty(existing.investment_round) else saramin.investment_round,
        "investment_total": inv_total,
        "investors": existing.investors if not _is_empty(existing.investors) else (saramin.investors or []),
        "benefits": saramin.benefits or [],
        "description": None,
        "tags": [],
        "source_urls": list(dict.fromkeys([*existing_urls, saramin.source_url])),
        "raw_extra": dict(saramin.raw_extra),
    }


def enrich_candidate(candidate: SaraminCandidate, context) -> SaraminEnrichmentResult:
    try:
        saramin_data = extract_saramin(candidate.company, context)
    except Exception as exc:
        _append_saramin_enrichment_queue(candidate.company)
        return SaraminEnrichmentResult(candidate, "error", message=str(exc))

    if not saramin_data:
        _append_saramin_enrichment_queue(candidate.company)
        return SaraminEnrichmentResult(candidate, "not_found", message="Saramin search returned no company")

    has_data = saramin_data.industry or saramin_data.employee_count or saramin_data.avg_salary
    if not has_data:
        _append_saramin_enrichment_queue(candidate.company)
        return SaraminEnrichmentResult(candidate, "no_data", source_url=saramin_data.source_url, message="Saramin page yielded no extractable fields")

    file_path = candidate.file_path
    if file_path and file_path.exists():
        try:
            existing_data = parse_company_file(file_path)
            existing_content = file_path.read_text(encoding="utf-8")
            existing_urls = _extract_source_urls(existing_content)
            merged = _build_merged_dict(existing_data, saramin_data, existing_urls)
            new_markdown = build_enriched_markdown(merged, candidate.company, merged["source_urls"])
            file_path.write_text(new_markdown, encoding="utf-8")
        except Exception as exc:
            return SaraminEnrichmentResult(candidate, "merge_error", source_url=saramin_data.source_url, message=str(exc))
    else:
        slug = slugify_company(candidate.company)
        file_path = COMPANY_INFO_DIR / f"{slug}.md"
        merged = _build_merged_dict(
            CompanyData(name=candidate.company),
            saramin_data,
            [],
        )
        new_markdown = build_enriched_markdown(merged, candidate.company, [saramin_data.source_url])
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(new_markdown, encoding="utf-8")

    return SaraminEnrichmentResult(candidate, "enriched", source_url=saramin_data.source_url)


def _remove_from_queue(company: str, queue_path: Path) -> None:
    if not queue_path.exists():
        return
    lines = [
        line
        for line in queue_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and line.strip() != company
    ]
    queue_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def write_report(candidates: list[SaraminCandidate], results: list[SaraminEnrichmentResult]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1

    lines = [
        "# Saramin Enrichment Report",
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
        fname = c.file_path.name if c.file_path else "-"
        lines.append(
            f"| {result.status} | {c.company} | {fname} | {result.source_url or '-'} | {result.message or '-'} |"
        )

    untouched = [c for c in candidates if all(r.candidate.company != c.company for r in results)]
    if untouched:
        lines.extend(["", "## Untouched Candidates", "", "| Company | File | Completeness |", "|------|------|------|"])
        for c in untouched:
            fname = c.file_path.name if c.file_path else "-"
            lines.append(f"| {c.company} | {fname} | {c.completeness:.0f}% |")

    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Saramin 회사정보 백필 (anti-bot 우회)")
    parser.add_argument("--headed", action="store_true", help="GUI 창 열기 (headless 비활성화)")
    parser.add_argument("--limit", type=int, default=0, help="처리 건수 제한 (0=전체)")
    parser.add_argument("--dry-run", action="store_true", help="큐 후보만 출력, 추출 안함")
    parser.add_argument("--company", help="단일 회사 강제 실행")
    args = parser.parse_args()

    if args.company:
        slug = slugify_company(args.company)
        file_path = COMPANY_INFO_DIR / f"{slug}.md"
        candidates = [SaraminCandidate(
            company=args.company,
            file_path=file_path if file_path.exists() else None,
            completeness=0.0,
        )]
    else:
        candidates = scan_candidates()
        if args.limit:
            candidates = candidates[: args.limit]

    if args.dry_run:
        print(f"후보 수: {len(candidates)}")
        for c in candidates:
            print(f"- {c.company} (file={c.file_path.name if c.file_path else '없음'}, {c.completeness:.0f}%)")
        write_report(candidates, [])
        print(f"리포트: {REPORT_PATH}")
        return

    try:
        from patchright.sync_api import sync_playwright as _sync_pw
        use_patchright = True
    except ImportError:
        from playwright.sync_api import sync_playwright as _sync_pw
        use_patchright = False

    if use_patchright:
        print("Patchright 사용 (CDP leak 우회)")
    else:
        print("Playwright fallback (patchright 미설치)")

    results: list[SaraminEnrichmentResult] = []
    with _sync_pw() as pw:
        browser = pw.chromium.launch(
            headless=not args.headed,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        try:
            for candidate in candidates:
                result = enrich_candidate(candidate, context)
                results.append(result)
                write_report(candidates, results)
                print(f"{result.status}: {candidate.company} {result.source_url or result.message}")
                if result.status == "enriched":
                    _remove_from_queue(candidate.company, SARAMIN_ENRICHMENT_QUEUE_PATH)
        finally:
            browser.close()

    write_report(candidates, results)
    print(f"리포트: {REPORT_PATH}")


if __name__ == "__main__":
    main()
