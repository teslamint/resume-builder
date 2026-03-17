#!/usr/bin/env python3
"""Recollect company info sources and enforce minimum source URLs."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qs, quote_plus, unquote_plus, urlparse

BASE_DIR = Path(__file__).resolve().parents[2]
COMPANY_INFO_DIR = BASE_DIR / "company_info"
BUILD_DIR = BASE_DIR / "build"
TARGETS_PATH = BUILD_DIR / "company_info_recollect_targets.txt"
REPORT_PATH = BUILD_DIR / "company_info_recollect_report.md"
REFINE_REPORT_PATH = BUILD_DIR / "company_info_refine_direct_report.md"

EXCLUDED_EXACT = {
    "CLAUDE.md",
    "_schema.md",
    "_validation_report.md",
}

URL_RE = re.compile(r"https?://[^\s\)\]>\"']+")


@dataclass
class TargetResult:
    file_name: str
    company_name: str
    before_count: int
    after_count: int
    added_sources: list[str]
    changed: bool


@dataclass
class RefineResult:
    file_name: str
    company_name: str
    replaced_count: int
    remaining_search_count: int
    changed: bool


def normalize_url(url: str) -> str:
    return url.strip().rstrip(".,;:*")


def extract_urls(text: str) -> list[str]:
    seen = set()
    result = []
    for raw in URL_RE.findall(text):
        url = normalize_url(raw)
        if url and url not in seen:
            seen.add(url)
            result.append(url)
    return result


def list_company_files() -> list[Path]:
    files = []
    for path in sorted(COMPANY_INFO_DIR.glob("*.md")):
        name = path.name
        if name in EXCLUDED_EXACT:
            continue
        if name.startswith("_"):
            continue
        files.append(path)
    return files


def parse_company_name(content: str, fallback: str) -> str:
    m = re.search(r"^#\s+(.+)$", content, flags=re.MULTILINE)
    if not m:
        return fallback
    title = m.group(1).strip()
    title = re.sub(r"\s*\(.+?\)\s*$", "", title).strip()
    return title or fallback


def normalize_name_key(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"\(주\)|주식회사|\(.*?\)", " ", text)
    text = re.sub(r"[^a-z0-9가-힣]+", "", text)
    return text.strip()


def fallback_sources(company_name: str) -> list[str]:
    q = quote_plus(company_name)
    return [
        f"https://www.wanted.co.kr/search?query={q}&tab=company",
        f"https://www.saramin.co.kr/zf_user/search/company?searchword={q}",
        f"https://www.jobkorea.co.kr/Search/?stext={q}",
        f"https://thevc.kr/search?query={q}",
    ]


def is_search_url(url: str) -> bool:
    return (
        "wanted.co.kr/search" in url
        or "saramin.co.kr/zf_user/search/company" in url
        or "jobkorea.co.kr/Search/" in url
        or "thevc.kr/search?query=" in url
    )


def is_direct_company_url(url: str) -> bool:
    if is_search_url(url):
        return False
    if "wanted.co.kr/company/" in url:
        return True
    if "saramin.co.kr/zf_user/company-info/view" in url:
        return True
    if "jobkorea.co.kr/Recruit/Co_Read/" in url or "jobkorea.co.kr/recruit/co_read/" in url:
        return True
    if "thevc.kr/" in url and "search?query=" not in url:
        return True
    if "innoforest.co.kr/company/" in url:
        return True
    if "rocketpunch.com/companies/" in url:
        return True
    return False


def extract_homepage_candidates(content: str) -> list[str]:
    candidates: list[str] = []
    seen = set()
    # Table rows like: | 홈페이지 | www.example.com |
    for m in re.finditer(r"^\|\s*홈페이지\s*\|\s*([^|]+)\|", content, flags=re.MULTILINE):
        raw = m.group(1).strip()
        raw = raw.replace("**", "").strip()
        if raw in {"-", "정보 없음", "없음"}:
            continue
        # split multiple urls in one cell
        parts = re.split(r"[,\s/]+", raw)
        for part in parts:
            part = part.strip().strip("()[]")
            if not part:
                continue
            if not re.match(r"^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", part) and not part.startswith("http"):
                continue
            if part.startswith("http://") or part.startswith("https://"):
                u = part
            else:
                u = f"https://{part}"
            u = normalize_url(u)
            if u not in seen:
                seen.add(u)
                candidates.append(u)
    return candidates


def infer_name_from_search_url(url: str) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    if "query" in query and query["query"]:
        return unquote_plus(query["query"][0]).strip()
    if "searchword" in query and query["searchword"]:
        return unquote_plus(query["searchword"][0]).strip()
    if "stext" in query and query["stext"]:
        return unquote_plus(query["stext"][0]).strip()
    return ""


def build_direct_source_index() -> dict[str, list[str]]:
    idx: dict[str, list[str]] = {}
    for file_path in list_company_files():
        content = file_path.read_text(encoding="utf-8")
        keys = {
            normalize_name_key(parse_company_name(content, file_path.stem)),
            normalize_name_key(file_path.stem),
        }
        urls = [u for u in extract_urls(content) if is_direct_company_url(u)]
        for key in keys:
            if not key:
                continue
            bucket = idx.setdefault(key, [])
            for u in urls:
                if u not in bucket:
                    bucket.append(u)
    return idx


def collect_best_direct_urls(company_name: str, urls: list[str], index: dict[str, list[str]]) -> list[str]:
    keys = {normalize_name_key(company_name)}
    for u in urls:
        if not is_search_url(u):
            continue
        inferred = infer_name_from_search_url(u)
        if inferred:
            keys.add(normalize_name_key(inferred))

    direct_urls = [u for u in urls if is_direct_company_url(u)]
    seen = set(direct_urls)
    merged = list(direct_urls)
    for key in keys:
        if not key:
            continue
        for u in index.get(key, []):
            if u in seen:
                continue
            merged.append(u)
            seen.add(u)
    return merged


def ensure_min_sources(existing: list[str], company_name: str, minimum: int) -> tuple[list[str], list[str]]:
    merged = list(existing)
    added = []
    existing_set = set(existing)

    for candidate in fallback_sources(company_name):
        if len(merged) >= minimum:
            break
        if candidate in existing_set:
            continue
        merged.append(candidate)
        added.append(candidate)
        existing_set.add(candidate)
    return merged, added


def strip_existing_footer(content: str) -> str:
    m = re.search(r"\n---\n[\s\S]*\Z", content)
    if not m:
        return content.rstrip()

    footer = m.group(0)
    markers = ("추출일", "출처", "JD 출처", "자동 생성일")
    if any(marker in footer for marker in markers):
        return content[: m.start()].rstrip()
    return content.rstrip()


def rebuild_content(content: str, sources: Iterable[str]) -> str:
    body = strip_existing_footer(content)
    today = date.today().isoformat()
    source_lines = "\n".join(f"- {s}" for s in sources)
    return f"{body}\n\n---\n\n*추출일: {today}*\n\n*출처:*\n{source_lines}\n"


def collect_targets(minimum: int) -> list[tuple[Path, str, list[str]]]:
    targets: list[tuple[Path, str, list[str]]] = []
    for file_path in list_company_files():
        content = file_path.read_text(encoding="utf-8")
        company_name = parse_company_name(content, file_path.stem)
        urls = extract_urls(content)
        if len(urls) < minimum:
            targets.append((file_path, company_name, urls))
    return targets


def write_targets_file(targets: list[tuple[Path, str, list[str]]]) -> None:
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    lines = [f"{p.name}|{name}|{len(urls)}" for p, name, urls in targets]
    TARGETS_PATH.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def write_report(results: list[TargetResult], minimum: int) -> None:
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    lines = [
        "# Company Info Recollect Report",
        "",
        f"*생성일: {today}*",
        "",
        f"- 최소 출처 기준: {minimum}개",
        f"- 처리 파일 수: {len(results)}",
        "",
        "| 파일 | 회사명 | 기존 출처 | 적용 후 출처 | 추가 출처 수 | 상태 |",
        "|------|--------|-----------|--------------|--------------|------|",
    ]

    for r in results:
        status = "updated" if r.changed else "unchanged"
        lines.append(
            f"| {r.file_name} | {r.company_name} | {r.before_count} | {r.after_count} | {len(r.added_sources)} | {status} |"
        )

    lines.extend(["", "## 추가된 출처 상세", ""])
    for r in results:
        if not r.added_sources:
            continue
        lines.append(f"### {r.file_name}")
        for src in r.added_sources:
            lines.append(f"- {src}")
        lines.append("")

    REPORT_PATH.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_refine_report(results: list[RefineResult]) -> None:
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    lines = [
        "# Company Info Direct Source Refinement Report",
        "",
        f"*생성일: {today}*",
        "",
        f"- 처리 파일 수: {len(results)}",
        "",
        "| 파일 | 회사명 | 치환된 검색 URL 수 | 남은 검색 URL 수 | 상태 |",
        "|------|--------|--------------------|------------------|------|",
    ]
    for r in results:
        status = "updated" if r.changed else "unchanged"
        lines.append(
            f"| {r.file_name} | {r.company_name} | {r.replaced_count} | {r.remaining_search_count} | {status} |"
        )
    REFINE_REPORT_PATH.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def run(scan_only: bool, minimum: int) -> int:
    targets = collect_targets(minimum=minimum)
    write_targets_file(targets)

    if scan_only:
        print(f"[scan] targets={len(targets)}")
        print(f"[scan] targets_file={TARGETS_PATH}")
        return 0

    results: list[TargetResult] = []
    for file_path, company_name, urls in targets:
        merged_sources, added = ensure_min_sources(urls, company_name, minimum)
        before_content = file_path.read_text(encoding="utf-8")
        after_content = rebuild_content(before_content, merged_sources)
        changed = before_content != after_content
        if changed:
            file_path.write_text(after_content, encoding="utf-8")

        results.append(
            TargetResult(
                file_name=file_path.name,
                company_name=company_name,
                before_count=len(urls),
                after_count=len(merged_sources),
                added_sources=added,
                changed=changed,
            )
        )

    write_report(results, minimum=minimum)
    updated = sum(1 for r in results if r.changed)
    print(f"[apply] targets={len(targets)} updated={updated}")
    print(f"[apply] targets_file={TARGETS_PATH}")
    print(f"[apply] report_file={REPORT_PATH}")
    return 0


def run_refine_direct(minimum: int) -> int:
    index = build_direct_source_index()
    results: list[RefineResult] = []

    for file_path in list_company_files():
        before = file_path.read_text(encoding="utf-8")
        company_name = parse_company_name(before, file_path.stem)
        urls = extract_urls(before)
        before_search = [u for u in urls if is_search_url(u)]

        if not before_search:
            results.append(
                RefineResult(
                    file_name=file_path.name,
                    company_name=company_name,
                    replaced_count=0,
                    remaining_search_count=0,
                    changed=False,
                )
            )
            continue

        # Keep existing non-search sources first (including JD URLs),
        # then add direct company URLs discovered from local index.
        non_search_existing = [u for u in urls if not is_search_url(u)]
        final_sources = []
        seen = set()
        for u in non_search_existing:
            if u not in seen:
                final_sources.append(u)
                seen.add(u)

        for u in collect_best_direct_urls(company_name, urls, index):
            if u not in seen:
                final_sources.append(u)
                seen.add(u)

        for u in extract_homepage_candidates(before):
            if u not in seen:
                final_sources.append(u)
                seen.add(u)

        # Only keep original search URLs when absolutely needed for min sources.
        if len(final_sources) < minimum:
            for u in before_search:
                if u not in seen:
                    final_sources.append(u)
                    seen.add(u)
                if len(final_sources) >= minimum:
                    break

        after = rebuild_content(before, final_sources)
        changed = after != before
        if changed:
            file_path.write_text(after, encoding="utf-8")

        remaining_search = sum(1 for u in final_sources if is_search_url(u))
        replaced = max(0, len(before_search) - remaining_search)
        results.append(
            RefineResult(
                file_name=file_path.name,
                company_name=company_name,
                replaced_count=replaced,
                remaining_search_count=remaining_search,
                changed=changed,
            )
        )

    write_refine_report(results)
    updated = sum(1 for r in results if r.changed)
    total_replaced = sum(r.replaced_count for r in results)
    remaining = sum(r.remaining_search_count for r in results)
    print(f"[refine] files={len(results)} updated={updated}")
    print(f"[refine] replaced_search_urls={total_replaced} remaining_search_urls={remaining}")
    print(f"[refine] report_file={REFINE_REPORT_PATH}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Recollect company_info sources")
    parser.add_argument("--scan-only", action="store_true", help="Only scan targets and write target list")
    parser.add_argument("--min-sources", type=int, default=2, help="Minimum source URLs per file")
    parser.add_argument("--refine-direct", action="store_true", help="Replace search URLs with direct company URLs when possible")
    args = parser.parse_args()
    minimum = max(1, args.min_sources)
    if args.refine_direct:
        return run_refine_direct(minimum=minimum)
    return run(scan_only=args.scan_only, minimum=minimum)


if __name__ == "__main__":
    raise SystemExit(main())
