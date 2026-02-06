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
import json
import sys
from pathlib import Path
from collections import Counter
from datetime import datetime
from typing import List, Optional, Dict
from dataclasses import dataclass
from enum import Enum

from jd_utils import (
    extract_job_id,
    extract_job_id_from_filename,
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
    get_user_status,
    normalize_status,
    is_protected_status,
    add_frontmatter_status,
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
    current_folder: Optional[str] = None
    verdict: Optional[str] = None
    verdict_source: Optional[str] = None
    skip_reason: Optional[str] = None
    protected_status: Optional[str] = None


def _relative_folder(file_path: Path) -> str:
    """Return file's folder relative to job_postings directory when possible."""
    try:
        parent = file_path.resolve().parent.relative_to(JOB_POSTINGS_DIR.resolve())
        return str(parent) if str(parent) != "." else "root"
    except ValueError:
        return file_path.parent.name or "unknown"


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
    """Classify a JD file based on its screening result or embedded verdict.

    Protected status files (applied, rejected, interview, offer) are skipped.
    """
    job_id = extract_job_id_from_filename(file_path.name)
    current_folder = _relative_folder(file_path)

    if not file_path.exists():
        return ProcessedItem(
            url_or_path=str(file_path),
            job_id=job_id,
            result=ProcessResult.ERROR,
            message="파일이 존재하지 않습니다.",
            current_folder=current_folder,
            skip_reason="missing_file",
        )

    content = file_path.read_text(encoding="utf-8")

    # Check for protected status
    user_status = get_user_status(content)
    normalized_status = normalize_status(user_status)
    if is_protected_status(user_status):
        status_label = f"{user_status} → {normalized_status}" if user_status != normalized_status else str(user_status)
        return ProcessedItem(
            url_or_path=str(file_path),
            job_id=job_id,
            result=ProcessResult.SKIPPED,
            message=f"보호된 상태 ({status_label}): 재분류 스킵",
            current_folder=current_folder,
            skip_reason="protected_status",
            protected_status=status_label,
        )

    # Try to find verdict from the file itself
    verdict = parse_verdict_from_screening(content)
    verdict_source = "jd"

    # If not found in JD, check screening file
    if not verdict and job_id:
        for screening_file in SCREENING_DIR.glob(f"{job_id}-*.md"):
            screening_content = screening_file.read_text(encoding="utf-8")
            verdict = parse_verdict_from_screening(screening_content)
            if verdict:
                verdict_source = f"screening:{screening_file.name}"
                break

    if not verdict:
        return ProcessedItem(
            url_or_path=str(file_path),
            job_id=job_id,
            result=ProcessResult.SKIPPED,
            message="판정 결과를 찾을 수 없습니다. 스크리닝이 필요합니다.",
            current_folder=current_folder,
            skip_reason="missing_verdict",
        )

    target_folder = classify_by_verdict(verdict)
    if not target_folder:
        return ProcessedItem(
            url_or_path=str(file_path),
            job_id=job_id,
            result=ProcessResult.SKIPPED,
            message=f"판정 결과를 분류할 수 없습니다: {verdict}",
            current_folder=current_folder,
            verdict=verdict,
            verdict_source=verdict_source,
            skip_reason="unmapped_verdict",
        )

    if dry_run:
        return ProcessedItem(
            url_or_path=str(file_path),
            job_id=job_id,
            result=ProcessResult.SUCCESS,
            message=f"[DRY-RUN] {verdict} → {target_folder}",
            target_folder=target_folder,
            current_folder=current_folder,
            verdict=verdict,
            verdict_source=verdict_source,
        )

    new_path = move_to_folder(file_path, target_folder)

    return ProcessedItem(
        url_or_path=str(file_path),
        job_id=job_id,
        result=ProcessResult.SUCCESS,
        message=f"{verdict} → {new_path.relative_to(JOB_POSTINGS_DIR)}",
        target_folder=target_folder,
        current_folder=current_folder,
        verdict=verdict,
        verdict_source=verdict_source,
    )


def migrate_status(base_dir: Path, dry_run: bool = False) -> List[ProcessedItem]:
    """Migrate files in applied/rejected folders to have frontmatter status.

    This adds status field to files based on their folder location,
    allowing them to be protected from auto-reclassification.
    """
    results = []

    folder_status_map = {
        "applied": "applied",
        "rejected": "rejected",
    }

    for folder_name, status_value in folder_status_map.items():
        folder_path = base_dir / folder_name
        if not folder_path.exists():
            continue

        for md_file in folder_path.glob("*.md"):
            if md_file.name in ("CLAUDE.md", "jd-screening-rules.md"):
                continue

            content = md_file.read_text(encoding="utf-8")
            existing_status = get_user_status(content)

            # Skip if already has a status
            if existing_status:
                results.append(
                    ProcessedItem(
                        url_or_path=str(md_file),
                        job_id=extract_job_id_from_filename(md_file.name),
                        result=ProcessResult.SKIPPED,
                        message=f"이미 상태 존재: {existing_status}",
                    )
                )
                continue

            if dry_run:
                results.append(
                    ProcessedItem(
                        url_or_path=str(md_file),
                        job_id=extract_job_id_from_filename(md_file.name),
                        result=ProcessResult.SUCCESS,
                        message=f"[DRY-RUN] status: {status_value} 추가 예정",
                    )
                )
                continue

            # Add frontmatter status
            new_content = add_frontmatter_status(content, status_value)
            md_file.write_text(new_content, encoding="utf-8")

            results.append(
                ProcessedItem(
                    url_or_path=str(md_file),
                    job_id=extract_job_id_from_filename(md_file.name),
                    result=ProcessResult.SUCCESS,
                    message=f"status: {status_value} 추가됨",
                )
            )

    return results


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
        "unprocessed_files": 0,
    }

    for folder, count in status.items():
        folder_path = JOB_POSTINGS_DIR / folder
        if folder_path.exists():
            status[folder] = len(list(folder_path.glob("*.md")))

    # Count root level MD files (legacy unprocessed format)
    status["unprocessed"] = len(
        [f for f in JOB_POSTINGS_DIR.glob("*.md") if f.name != "CLAUDE.md" and f.name != "jd-screening-rules.md"]
    )
    unprocessed_dir = JOB_POSTINGS_DIR / "unprocessed"
    if unprocessed_dir.exists():
        status["unprocessed_files"] = len([f for f in unprocessed_dir.glob("*") if f.is_file()])

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

    md_files = list(folder_path.glob("*.md"))
    if not md_files:
        non_md_files = [f for f in folder_path.glob("*") if f.is_file() and f.suffix != ".md"]
        if non_md_files:
            print(f"ℹ️ {folder_path}에는 md 파일이 없습니다. (기타 파일 {len(non_md_files)}개)")
            print("   txt/json은 먼저 JD markdown으로 추출한 뒤 분류하세요.")
        return results

    for md_file in md_files:
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
                "unprocessed_files": "🗂️",
            }.get(folder, "📁")
            print(f"  {icon} {folder:<20} {count:>3}건")
            total += count

    print("=" * 40)
    print(f"  총계: {total}건")


def build_dry_run_report(results: List[ProcessedItem], folder: Path, action: str) -> Dict:
    """Build structured dry-run report data."""
    counts = Counter(item.result.value for item in results)
    skip_reasons = Counter(item.skip_reason for item in results if item.skip_reason)
    target_counts = Counter(item.target_folder for item in results if item.target_folder)
    move_candidates = [
        item
        for item in results
        if item.result == ProcessResult.SUCCESS and item.target_folder and item.target_folder != item.current_folder
    ]
    no_change = [
        item
        for item in results
        if item.result == ProcessResult.SUCCESS and item.target_folder and item.target_folder == item.current_folder
    ]
    skipped_items = [item for item in results if item.result == ProcessResult.SKIPPED]

    items = []
    for item in results:
        items.append(
            {
                "job_id": item.job_id,
                "path": item.url_or_path,
                "current_folder": item.current_folder,
                "predicted_folder": item.target_folder,
                "verdict": item.verdict,
                "verdict_source": item.verdict_source,
                "result": item.result.value,
                "message": item.message,
                "skip_reason": item.skip_reason,
                "protected_status": item.protected_status,
            }
        )

    return {
        "generated_at": datetime.now().isoformat(),
        "action": action,
        "folder": str(folder),
        "summary": {
            "total": len(results),
            "success": counts.get(ProcessResult.SUCCESS.value, 0),
            "skipped": counts.get(ProcessResult.SKIPPED.value, 0),
            "error": counts.get(ProcessResult.ERROR.value, 0),
            "duplicate": counts.get(ProcessResult.DUPLICATE.value, 0),
            "needs_manual": counts.get(ProcessResult.NEEDS_MANUAL.value, 0),
            "move_candidates": len(move_candidates),
            "no_change": len(no_change),
        },
        "target_folders": dict(sorted(target_counts.items())),
        "skip_reasons": dict(sorted(skip_reasons.items())),
        "recommendations": {
            "next_command": f"python3 templates/jd_pipeline.py --{action} {folder}",
            "review_focus": [
                "move_candidates: 실제 이동 후보",
                "skip_reasons: 보호 상태/미판정 원인 확인",
                "items: 고위험 판정 변경 케이스 점검",
            ],
        },
        "move_candidates": [item.job_id for item in move_candidates if item.job_id],
        "skipped_job_ids": [item.job_id for item in skipped_items if item.job_id],
        "items": items,
    }


def _resolve_report_base_path(folder: Path, report_out: Optional[str]) -> Path:
    """Resolve base path (without suffix) for dry-run reports."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    folder_label = str(folder).replace("/", "-")
    default_name = f"jd-rescreen-report-{folder_label}-{timestamp}"

    if not report_out:
        base_dir = JOB_POSTINGS_DIR.parent / "build"
        base_dir.mkdir(parents=True, exist_ok=True)
        return base_dir / default_name

    report_path = Path(report_out)
    if report_path.suffix in {".json", ".md"}:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        return report_path.with_suffix("")

    if not report_path.suffix:
        report_path.mkdir(parents=True, exist_ok=True)
        return report_path / default_name

    report_path.parent.mkdir(parents=True, exist_ok=True)
    return report_path


def write_dry_run_report(report: Dict, folder: Path, report_out: Optional[str], report_format: str) -> List[Path]:
    """Write dry-run report files and return created paths."""
    base_path = _resolve_report_base_path(folder, report_out)
    created: List[Path] = []

    if report_format in ("json", "both"):
        json_path = base_path.with_suffix(".json")
        json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        created.append(json_path)

    if report_format in ("md", "both"):
        md_path = base_path.with_suffix(".md")
        summary = report["summary"]
        lines = [
            "# JD Rescreen Dry-Run Report",
            "",
            f"- 생성시각: {report['generated_at']}",
            f"- 액션: `{report['action']}`",
            f"- 대상 폴더: `{report['folder']}`",
            "",
            "## 요약",
            f"- 총계: {summary['total']}건",
            f"- 성공: {summary['success']}건",
            f"- 스킵: {summary['skipped']}건",
            f"- 에러: {summary['error']}건",
            f"- 이동 후보: {summary['move_candidates']}건",
            f"- 폴더 변경 없음: {summary['no_change']}건",
            "",
            "## 대상 폴더 분포",
        ]

        if report["target_folders"]:
            for folder_name, count in report["target_folders"].items():
                lines.append(f"- `{folder_name}`: {count}건")
        else:
            lines.append("- 없음")

        lines.extend(["", "## 스킵 사유", ""])
        if report["skip_reasons"]:
            for reason, count in report["skip_reasons"].items():
                lines.append(f"- `{reason}`: {count}건")
        else:
            lines.append("- 없음")

        lines.extend(["", "## 실행 가이드", ""])
        lines.append(f"- 추천 명령: `{report['recommendations']['next_command']}`")
        lines.append("- dry-run 리포트 확인 후 `--dry-run` 제거하여 실제 실행")

        md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        created.append(md_path)

    return created


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

  # Classify extracted markdown files in a folder based on screening results
  python3 templates/jd_pipeline.py --classify job_postings/conditional/hold/

  # Re-classify files (dry run)
  python3 templates/jd_pipeline.py --rescreen job_postings/pass/ --dry-run

  # Show current status
  python3 templates/jd_pipeline.py --status

  # Set status on a file
  python3 templates/jd_pipeline.py --set-status rejected path/to/file.md --reason "면접 거절"

  # Migrate applied/rejected folders to have frontmatter status
  python3 templates/jd_pipeline.py --migrate-status --dry-run
        """,
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--url", help="Single URL to process")
    group.add_argument("--file", help="File containing URLs (one per line)")
    group.add_argument("--rescreen", help="Folder to rescreen/reclassify")
    group.add_argument("--classify", help="Folder to classify based on verdict")
    group.add_argument("--status", action="store_true", help="Show current folder status")
    group.add_argument(
        "--set-status",
        nargs=2,
        metavar=("STATUS", "FILE"),
        help="Set status on a file (pending|applied|rejected|interview|offer)",
    )
    group.add_argument(
        "--migrate-status",
        action="store_true",
        help="Migrate files in applied/rejected folders to have frontmatter status",
    )

    parser.add_argument("--dry-run", action="store_true", help="Preview changes without moving files")
    parser.add_argument("--reason", help="Reason for status change (used with --set-status)")
    parser.add_argument("--report-out", help="Dry-run report output path (directory or file prefix)")
    parser.add_argument(
        "--report-format",
        choices=["json", "md", "both"],
        default="both",
        help="Dry-run report format (json|md|both)",
    )

    args = parser.parse_args()

    if (args.report_out or args.report_format != "both") and not args.dry_run:
        print("❌ --report-out/--report-format 옵션은 --dry-run과 함께 사용해야 합니다.")
        sys.exit(1)

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
        action_name = "rescreen" if args.rescreen else "classify"
        folder = Path(args.rescreen or args.classify)
        results = rescreen_folder(folder, dry_run=args.dry_run)
        print_results(results)

        if args.dry_run:
            report = build_dry_run_report(results, folder, action_name)
            report_paths = write_dry_run_report(report, folder, args.report_out, args.report_format)
            if report_paths:
                print("\n📝 Dry-run 리포트:")
                for report_path in report_paths:
                    print(f"   - {report_path}")
            print("\n⚠️ DRY-RUN 모드: 실제 파일 이동 없음")
            print("   실제 이동하려면 --dry-run 옵션을 제거하세요.")

    elif args.set_status:
        status_value, file_path = args.set_status
        valid_statuses = ["pending", "applied", "rejected", "interview", "offer"]

        if status_value not in valid_statuses:
            print(f"❌ 유효하지 않은 상태: {status_value}")
            print(f"   유효한 상태: {', '.join(valid_statuses)}")
            sys.exit(1)

        path = Path(file_path)
        if not path.exists():
            print(f"❌ 파일을 찾을 수 없습니다: {path}")
            sys.exit(1)

        content = path.read_text(encoding="utf-8")

        if args.dry_run:
            print(f"[DRY-RUN] {path.name}: status -> {status_value}")
            if args.reason:
                print(f"[DRY-RUN] reason: {args.reason}")
        else:
            new_content = add_frontmatter_status(content, status_value, args.reason)
            path.write_text(new_content, encoding="utf-8")
            print(f"✅ {path.name}: status -> {status_value}")
            if args.reason:
                print(f"   reason: {args.reason}")

    elif args.migrate_status:
        results = migrate_status(JOB_POSTINGS_DIR, dry_run=args.dry_run)
        print_results(results)

        if args.dry_run:
            print("\n⚠️ DRY-RUN 모드: 실제 파일 수정 없음")
            print("   실제 마이그레이션하려면 --dry-run 옵션을 제거하세요.")


if __name__ == "__main__":
    main()
