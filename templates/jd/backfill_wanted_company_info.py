#!/usr/bin/env python3
"""Backfill fully-empty company_info files from Wanted JD/company pages."""

from __future__ import annotations

import argparse
import re
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

try:
    from .auto_company import is_headhunting_company
    from .ce_merge import build_enriched_markdown, merge_platform_data
    from .ce_types import PlatformData
    from .ce_wanted import extract_wanted_from_text, find_query_data, parse_next_data_company
    from .enrich_company_fields import BASE_DIR, BUILD_DIR, scan_empty_files
    from .wanted_extract import extract_company_id, fetch_wanted_posting
except ImportError:
    from auto_company import is_headhunting_company
    from ce_merge import build_enriched_markdown, merge_platform_data
    from ce_types import PlatformData
    from ce_wanted import extract_wanted_from_text, find_query_data, parse_next_data_company
    from enrich_company_fields import BASE_DIR, BUILD_DIR, scan_empty_files
    from wanted_extract import extract_company_id, fetch_wanted_posting


REPORT_PATH = BUILD_DIR / "wanted_company_backfill_report.md"
COMPANY_INFO_DIR = BASE_DIR / "private" / "company_info"
WANTED_JD_RE = re.compile(r"https://www\.wanted\.co\.kr/wd/(\d+)")


@dataclass
class BackfillResult:
    status: str
    file_name: str
    company: str
    jd_url: str = ""
    source_url: str = ""
    message: str = ""


def _fetch_html(url: str, timeout: int = 15) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read(2 * 1024 * 1024).decode("utf-8", errors="ignore")


def _wanted_jd_id(url: str | None) -> str | None:
    if not url:
        return None
    m = WANTED_JD_RE.search(url)
    return m.group(1) if m else None


def _query_state(company_id: str) -> tuple[str, list[dict], str]:
    company_url = f"https://www.wanted.co.kr/company/{company_id}"
    html = _fetch_html(company_url)
    next_data = parse_next_data_company(html)
    if not next_data:
        return company_url, [], re.sub(r"<[^>]+>", " ", html)

    page_props = next_data.get("props", {}).get("pageProps", {})
    dh_state = page_props.get("dehydrateState") or page_props.get("dehydratedState") or {}
    queries = dh_state.get("queries", [])
    body_text = re.sub(r"<[^>]+>", " ", html)
    return company_url, queries, body_text


def _platform_data_from_wanted(company_name: str, company_id: str) -> PlatformData:
    company_url, queries, body_text = _query_state(company_id)
    data = PlatformData(platform="wanted", source_url=company_url, company_name=company_name)
    data.raw_extra["company_id"] = company_id

    company_info = find_query_data(queries, "companyInfo")
    company_summary = find_query_data(queries, "companySummary")

    if company_info:
        data.company_name = company_info.get("name") or company_name
        data.industry = company_info.get("industryName")
        data.founded_year = company_info.get("foundedYear")
        data.description = company_info.get("description")
        data.raw_extra["location"] = company_info.get("location")

        for tag_list_key in ("companyTags", "mainTags"):
            tags_raw = company_info.get(tag_list_key, [])
            if isinstance(tags_raw, list):
                for tag in tags_raw:
                    title = tag.get("title", "") if isinstance(tag, dict) else str(tag)
                    if title and title not in data.tags:
                        data.tags.append(title)

    if company_summary:
        detail = company_summary.get("detail", {})
        salary_obj = company_summary.get("salary", {})
        emp_obj = company_summary.get("employee", {})
        sales_obj = company_summary.get("sales", {})

        best_emp = detail.get("npsEmployeeCount") or emp_obj.get("total") or detail.get("eiEmployeeCount")
        if isinstance(best_emp, (int, float)) and best_emp > 0:
            data.employee_count = int(best_emp)

        salary_raw = salary_obj.get("salary") or detail.get("salary")
        if isinstance(salary_raw, (int, float)) and salary_raw > 0:
            data.avg_salary = int(salary_raw / 10000)

        rate = salary_obj.get("rate")
        if isinstance(rate, (int, float)) and 0 < rate < 1:
            data.salary_percentile = str(round(rate * 100))

        hired = emp_obj.get("hired") or detail.get("hiredCount")
        left = emp_obj.get("left") or detail.get("leftCount")
        if isinstance(hired, (int, float)):
            data.employee_joined_1y = int(hired)
        if isinstance(left, (int, float)):
            data.employee_left_1y = int(left)

        total_sales = sales_obj.get("total") or detail.get("totalSales")
        if isinstance(total_sales, (int, float)) and total_sales > 0:
            data.revenue = [{"year": "latest", "amount_억": round(total_sales / 100_000_000, 1)}]

    extract_wanted_from_text(body_text, data)
    return data


def backfill_target(target, dry_run: bool = False) -> BackfillResult:
    if is_headhunting_company(target.company_name):
        return BackfillResult("skipped_headhunting", target.file_name, target.company_name, message="headhunting company")

    job_id = _wanted_jd_id(target.jd_source_url)
    if not job_id:
        return BackfillResult("deferred_non_wanted", target.file_name, target.company_name, target.jd_source_url or "-", message="no Wanted JD source")

    file_path = COMPANY_INFO_DIR / target.file_name
    if not file_path.exists():
        return BackfillResult("missing_file", target.file_name, target.company_name, target.jd_source_url or "-", message="target company_info file not found")

    try:
        job = fetch_wanted_posting(job_id)
    except Exception as exc:
        return BackfillResult("error", target.file_name, target.company_name, target.jd_source_url or "-", message=f"JD fetch failed: {exc}")
    if not job:
        return BackfillResult("error", target.file_name, target.company_name, target.jd_source_url or "-", message="JD fetch returned no data")

    company = job.get("company", {}) or {}
    company_id = extract_company_id(company)
    if not company_id:
        return BackfillResult("no_company_id", target.file_name, target.company_name, target.jd_source_url or "-", message="Wanted JD has no company_id")

    wanted_name = company.get("company_name") or target.company_name
    try:
        data = _platform_data_from_wanted(wanted_name, str(company_id))
    except Exception as exc:
        return BackfillResult("error", target.file_name, target.company_name, target.jd_source_url or "-", message=f"company fetch failed: {exc}")

    has_core = data.founded_year or data.employee_count or data.avg_salary or data.industry
    if not has_core:
        return BackfillResult("no_data", target.file_name, target.company_name, target.jd_source_url or "-", data.source_url, "Wanted page had no extractable core fields")

    merged = merge_platform_data([data])
    source_urls = list(dict.fromkeys([data.source_url, target.jd_source_url or ""]))
    source_urls = [u for u in source_urls if u]
    markdown = build_enriched_markdown(merged, wanted_name, source_urls)
    if not dry_run:
        file_path.write_text(markdown, encoding="utf-8")

    return BackfillResult("backfilled", file_path.name, wanted_name, target.jd_source_url or "-", data.source_url)


def write_report(results: list[BackfillResult]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1

    lines = [
        "# Wanted Company Backfill Report",
        "",
        f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
        "",
        f"- Results: {len(results)}",
    ]
    for status in sorted(counts):
        lines.append(f"- {status}: {counts[status]}")

    lines.extend(["", "## Results", "", "| Status | File | Company | JD | Source | Message |", "|---|---|---|---|---|---|"])
    for result in results:
        lines.append(
            f"| {result.status} | {result.file_name} | {result.company} | {result.jd_url or '-'} | {result.source_url or '-'} | {result.message or '-'} |"
        )

    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill fully-empty company info files from Wanted")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    targets = scan_empty_files(empty_only=True)
    if args.limit:
        targets = targets[: args.limit]

    results: list[BackfillResult] = []
    for target in targets:
        result = backfill_target(target, dry_run=args.dry_run)
        results.append(result)
        write_report(results)
        print(f"{result.status}: {result.file_name} {result.source_url or result.message}")

    write_report(results)
    print(f"리포트: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
