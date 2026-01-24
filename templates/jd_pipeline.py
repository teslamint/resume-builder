#!/usr/bin/env python3
"""
JD Pipeline - Job posting extraction and screening automation.

Usage:
    python3 templates/jd_pipeline.py --url "https://wanted.co.kr/wd/123456"
    python3 templates/jd_pipeline.py --file urls.txt
    python3 templates/jd_pipeline.py --rescreen job_postings/pass/
    python3 templates/jd_pipeline.py --classify job_postings/unprocessed/
    python3 templates/jd_pipeline.py --status
"""

import argparse
import sys
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass
from enum import Enum

from jd_utils import (
    extract_job_id,
    get_platform_from_url,
    is_duplicate,
    find_existing_jd,
    load_screening_rules,
    load_company_info,
    classify_by_verdict,
    move_to_folder,
    parse_verdict_from_screening,
    update_summary,
    extract_metadata_from_jd,
    JOB_POSTINGS_DIR,
    SCREENING_DIR,
)


class ProcessResult(Enum):
    SUCCESS = "success"
    DUPLICATE = "duplicate"
    SKIPPED = "skipped"
    ERROR = "error"
    NEEDS_MANUAL = "needs_manual"


@dataclass
class ProcessedItem:
    url_or_path: str
    job_id: Optional[str]
    result: ProcessResult
    message: str
    target_folder: Optional[str] = None


def check_url(url: str) -> ProcessedItem:
    """Check a single URL for duplicates."""
    job_id = extract_job_id(url)

    if not job_id:
        return ProcessedItem(
            url_or_path=url,
            job_id=None,
            result=ProcessResult.ERROR,
            message="URL에서 job_id를 추출할 수 없습니다.",
        )

    is_dup, existing_path = is_duplicate(job_id)
    if is_dup:
        return ProcessedItem(
            url_or_path=url,
            job_id=job_id,
            result=ProcessResult.DUPLICATE,
            message=f"이미 존재: {existing_path.name if existing_path else 'unknown'}",
            target_folder=str(existing_path.parent.relative_to(JOB_POSTINGS_DIR)) if existing_path else None,
        )

    platform = get_platform_from_url(url)
    return ProcessedItem(
        url_or_path=url,
        job_id=job_id,
        result=ProcessResult.NEEDS_MANUAL,
        message=f"추출 필요 (플랫폼: {platform or 'unknown'})",
    )


def classify_file(file_path: Path, dry_run: bool = False) -> ProcessedItem:
    """Classify a JD file based on its screening result or embedded verdict."""
    if not file_path.exists():
        return ProcessedItem(
            url_or_path=str(file_path),
            job_id=None,
            result=ProcessResult.ERROR,
            message="파일이 존재하지 않습니다.",
        )

    content = file_path.read_text(encoding="utf-8")
    metadata = extract_metadata_from_jd(content)

    # Try to find verdict from the file itself
    verdict = parse_verdict_from_screening(content)

    # If not found in JD, check screening file
    if not verdict:
        job_id = file_path.stem.split("-")[0] if "-" in file_path.stem else None
        if job_id:
            for screening_file in SCREENING_DIR.glob(f"{job_id}-*.md"):
                screening_content = screening_file.read_text(encoding="utf-8")
                verdict = parse_verdict_from_screening(screening_content)
                if verdict:
                    break

    if not verdict:
        return ProcessedItem(
            url_or_path=str(file_path),
            job_id=metadata.get("job_id"),
            result=ProcessResult.SKIPPED,
            message="판정 결과를 찾을 수 없습니다. 스크리닝이 필요합니다.",
        )

    target_folder = classify_by_verdict(verdict)

    if dry_run:
        return ProcessedItem(
            url_or_path=str(file_path),
            job_id=metadata.get("job_id"),
            result=ProcessResult.SUCCESS,
            message=f"[DRY-RUN] {verdict} → {target_folder}",
            target_folder=target_folder,
        )

    new_path = move_to_folder(file_path, target_folder)

    return ProcessedItem(
        url_or_path=str(file_path),
        job_id=metadata.get("job_id"),
        result=ProcessResult.SUCCESS,
        message=f"{verdict} → {new_path.relative_to(JOB_POSTINGS_DIR)}",
        target_folder=target_folder,
    )


def get_status() -> dict:
    """Get current status of job postings folders."""
    status = {
        "pass": 0,
        "conditional/high": 0,
        "conditional/hold": 0,
        "conditional/middle": 0,
        "conditional/low": 0,
        "applied": 0,
        "rejected": 0,
        "unprocessed": 0,
    }

    for folder, count in status.items():
        folder_path = JOB_POSTINGS_DIR / folder
        if folder_path.exists():
            status[folder] = len(list(folder_path.glob("*.md")))

    # Count root level MD files (unprocessed)
    status["unprocessed"] = len(
        [f for f in JOB_POSTINGS_DIR.glob("*.md") if f.name != "CLAUDE.md" and f.name != "jd-screening-rules.md"]
    )

    return status


def process_urls_from_file(file_path: Path) -> List[ProcessedItem]:
    """Process URLs from a text file (one URL per line)."""
    results = []

    if not file_path.exists():
        print(f"파일을 찾을 수 없습니다: {file_path}")
        return results

    with open(file_path, encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    for url in urls:
        result = check_url(url)
        results.append(result)

    return results


def rescreen_folder(folder_path: Path, dry_run: bool = False) -> List[ProcessedItem]:
    """Classify all MD files in a folder based on screening results."""
    results = []

    if not folder_path.exists():
        print(f"폴더를 찾을 수 없습니다: {folder_path}")
        return results

    for md_file in folder_path.glob("*.md"):
        if md_file.name in ("CLAUDE.md", "jd-screening-rules.md"):
            continue
        result = classify_file(md_file, dry_run)
        results.append(result)

    return results


def print_results(results: List[ProcessedItem]) -> None:
    """Print processing results in a formatted table."""
    if not results:
        print("처리할 항목이 없습니다.")
        return

    print("\n" + "=" * 70)
    print(f"{'결과':<12} {'ID':<10} {'메시지'}")
    print("=" * 70)

    counts = {r: 0 for r in ProcessResult}

    for item in results:
        icon = {
            ProcessResult.SUCCESS: "✅",
            ProcessResult.DUPLICATE: "⏭️",
            ProcessResult.SKIPPED: "⚠️",
            ProcessResult.ERROR: "❌",
            ProcessResult.NEEDS_MANUAL: "📝",
        }.get(item.result, "?")

        job_id = item.job_id or "-"
        print(f"{icon} {item.result.value:<10} {job_id:<10} {item.message}")
        counts[item.result] += 1

    print("=" * 70)
    print(f"총 {len(results)}건: ", end="")
    summary_parts = []
    if counts[ProcessResult.SUCCESS]:
        summary_parts.append(f"성공 {counts[ProcessResult.SUCCESS]}")
    if counts[ProcessResult.DUPLICATE]:
        summary_parts.append(f"중복 {counts[ProcessResult.DUPLICATE]}")
    if counts[ProcessResult.SKIPPED]:
        summary_parts.append(f"스킵 {counts[ProcessResult.SKIPPED]}")
    if counts[ProcessResult.NEEDS_MANUAL]:
        summary_parts.append(f"수동필요 {counts[ProcessResult.NEEDS_MANUAL]}")
    if counts[ProcessResult.ERROR]:
        summary_parts.append(f"에러 {counts[ProcessResult.ERROR]}")
    print(", ".join(summary_parts))


def print_status(status: dict) -> None:
    """Print current folder status."""
    print("\n📊 JD 현황")
    print("=" * 40)

    total = 0
    for folder, count in status.items():
        if count > 0:
            icon = {
                "pass": "🔴",
                "conditional/high": "🟢",
                "conditional/hold": "🟡",
                "conditional/middle": "🟠",
                "conditional/low": "🔵",
                "applied": "✅",
                "rejected": "❌",
                "unprocessed": "📋",
            }.get(folder, "📁")
            print(f"  {icon} {folder:<20} {count:>3}건")
            total += count

    print("=" * 40)
    print(f"  총계: {total}건")


def main():
    parser = argparse.ArgumentParser(
        description="JD Pipeline - Job posting extraction and screening automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Check single URL for duplicates
  python3 templates/jd_pipeline.py --url "https://wanted.co.kr/wd/123456"

  # Check multiple URLs from file
  python3 templates/jd_pipeline.py --file urls.txt

  # Classify files in a folder based on screening results
  python3 templates/jd_pipeline.py --classify job_postings/unprocessed/

  # Re-classify files (dry run)
  python3 templates/jd_pipeline.py --rescreen job_postings/pass/ --dry-run

  # Show current status
  python3 templates/jd_pipeline.py --status
        """,
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--url", help="Single URL to process")
    group.add_argument("--file", help="File containing URLs (one per line)")
    group.add_argument("--rescreen", help="Folder to rescreen/reclassify")
    group.add_argument("--classify", help="Folder to classify based on verdict")
    group.add_argument("--status", action="store_true", help="Show current folder status")

    parser.add_argument("--dry-run", action="store_true", help="Preview changes without moving files")

    args = parser.parse_args()

    if args.status:
        status = get_status()
        print_status(status)
        return

    if args.url:
        result = check_url(args.url)
        print_results([result])

        if result.result == ProcessResult.NEEDS_MANUAL:
            print("\n💡 추출하려면 Claude Code에서 다음 명령을 실행하세요:")
            print(f"   /extract-job-posting {args.url}")
            print("\n   추출 후 스크리닝:")
            print(f"   /jd-screening job_postings/<filename>.md")

    elif args.file:
        results = process_urls_from_file(Path(args.file))
        print_results(results)

        needs_manual = [r for r in results if r.result == ProcessResult.NEEDS_MANUAL]
        if needs_manual:
            print(f"\n💡 {len(needs_manual)}개 URL을 수동으로 추출해야 합니다.")
            print("   Claude Code에서 /extract-job-posting 스킬을 사용하세요.")

    elif args.rescreen or args.classify:
        folder = Path(args.rescreen or args.classify)
        results = rescreen_folder(folder, dry_run=args.dry_run)
        print_results(results)

        if args.dry_run:
            print("\n⚠️ DRY-RUN 모드: 실제 파일 이동 없음")
            print("   실제 이동하려면 --dry-run 옵션을 제거하세요.")


if __name__ == "__main__":
    main()
