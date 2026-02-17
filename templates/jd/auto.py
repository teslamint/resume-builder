#!/usr/bin/env python3
"""JD Auto - end-to-end automation pipeline.

Usage:
    python3 templates/jd/auto.py
    python3 templates/jd/auto.py --search-only
    python3 templates/jd/auto.py --from-urls job_postings/unprocessed/search_20260217_1000.txt
    python3 templates/jd/auto.py --screening-only
"""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

try:
    from .auto_company import ENRICHMENT_QUEUE_PATH, ensure_company_info
    from .auto_extractors import extract_jd_from_url
    from .auto_screening import run_screening
    from .pipeline import ProcessResult, classify_file
    from .search import JobPosting, load_config, run_search
    from .utils import (
        JOB_POSTINGS_DIR,
        extract_job_id,
        find_existing_jd,
        move_to_folder,
    )
except ImportError:
    from auto_company import ENRICHMENT_QUEUE_PATH, ensure_company_info
    from auto_extractors import extract_jd_from_url
    from auto_screening import run_screening
    from pipeline import ProcessResult, classify_file
    from search import JobPosting, load_config, run_search
    from utils import JOB_POSTINGS_DIR, extract_job_id, find_existing_jd, move_to_folder

BASE_DIR = Path(__file__).parent.parent.parent
RESULTS_DIR = BASE_DIR / "job_postings" / "auto_results"


@dataclass
class AutoTaskResult:
    url: str
    job_id: str
    status: str
    company: str = ""
    title: str = ""
    jd_path: str = ""
    screening_path: str = ""
    company_file: str = ""
    verdict: str = ""
    classified_folder: str = ""
    error_stage: str = ""
    error_reason: str = ""
    thevc_attempted: bool = False
    thevc_status: str = "skipped"
    investment_data_source: str = "none"
    used_fallback: bool = False


@dataclass
class RunSummary:
    run_id: str
    new: int = 0
    processed: int = 0
    duplicates: int = 0
    failed: int = 0
    extracted: int = 0
    screened: int = 0
    recommended: int = 0
    hold: int = 0
    passed: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


def send_notification(message: str, config: dict) -> bool:
    notifications = config.get("notifications", {})
    channel = notifications.get("channel")
    target = notifications.get("target")
    account = notifications.get("account")
    if not channel:
        print("   ⚠️  알림 채널 미설정")
        return False
    if not target:
        print("   ⚠️  알림 대상 미설정 (notifications.target)")
        return False

    try:
        command = [
            "openclaw",
            "message",
            "send",
            "--channel",
            channel,
            "--target",
            str(target),
            "--message",
            message,
        ]
        if account:
            command.extend(["--account", str(account)])
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            print(f"   ✅ 알림 전송 완료 ({channel}:{target})")
            return True
        error_output = result.stderr.strip() or result.stdout.strip() or "unknown error"
        print(f"   ⚠️  알림 전송 실패: {error_output}")
        return False
    except FileNotFoundError:
        print("   ⚠️  clawdbot 명령 없음 - 알림 스킵")
        return False
    except Exception as exc:
        print(f"   ⚠️  알림 오류: {exc}")
        return False


def format_notification(results: List[AutoTaskResult], summary: RunSummary) -> str:
    lines = [
        "🔔 **JD 자동 파이프라인 결과**",
        f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        f"✨ 신규 URL: {summary.new}개",
        f"✅ 처리 완료: {summary.processed}개",
        f"🟢 추천: {summary.recommended}개",
        f"🟡 보류: {summary.hold}개",
        f"🔴 패스: {summary.passed}개",
        "",
    ]

    recommended = [r for r in results if r.verdict == "지원 추천"]
    if recommended:
        lines.append("**🟢 지원 추천 공고:**")
        for row in recommended[:5]:
            title = row.title or row.job_id
            company = row.company or "unknown"
            lines.append(f"• [{company}] {title}")
            lines.append(f"  {row.url}")
        if len(recommended) > 5:
            lines.append(f"  ... 외 {len(recommended) - 5}개")

    return "\n".join(lines)


def _load_urls_from_file(path: Path, max_urls: Optional[int] = None) -> List[str]:
    if not path.exists():
        raise FileNotFoundError(f"URL 파일을 찾을 수 없습니다: {path}")

    urls = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    if max_urls is not None:
        urls = urls[:max_urls]
    return urls


def _resolve_jd_path_for_screening(url: str) -> Optional[Path]:
    job_id = extract_job_id(url)
    if not job_id:
        return None
    return find_existing_jd(job_id)


def _classify(jd_path: Path, dry_run: bool) -> tuple[str, str]:
    result = classify_file(jd_path, dry_run=dry_run)
    if result.result == ProcessResult.SUCCESS:
        return result.verdict or "", result.target_folder or ""

    # Missing verdict or other non-fatal case -> default hold
    if result.result in {ProcessResult.SKIPPED, ProcessResult.ERROR}:
        if dry_run:
            return "지원 보류", "conditional/hold"
        moved = move_to_folder(jd_path, "conditional/hold")
        return "지원 보류", str(moved.parent.relative_to(JOB_POSTINGS_DIR))

    return "", ""


def _update_verdict_count(summary: RunSummary, verdict: str) -> None:
    if verdict == "지원 추천":
        summary.recommended += 1
    elif verdict == "지원 비추천":
        summary.passed += 1
    else:
        summary.hold += 1


def save_results(
    results: List[AutoTaskResult], summary: RunSummary, dry_run: bool
) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    result_file = RESULTS_DIR / f"auto_{summary.run_id}.json"

    payload = {
        "timestamp": datetime.now().isoformat(),
        "dry_run": dry_run,
        "summary": summary.to_dict(),
        "results": [asdict(r) for r in results],
    }

    result_file.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return result_file


def _build_results_from_enrichment(
    thevc_mode: str, dry_run: bool, min_completeness: float = 0.0
) -> tuple[List[AutoTaskResult], RunSummary]:
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    summary = RunSummary(run_id=run_id)
    results: List[AutoTaskResult] = []

    if not ENRICHMENT_QUEUE_PATH.exists():
        print("ℹ️ TheVC 보완 큐가 비어있습니다.")
        return results, summary

    companies = [
        line.strip()
        for line in ENRICHMENT_QUEUE_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    for company in companies:
        summary.new += 1
        temp_jd = JOB_POSTINGS_DIR / "unprocessed" / f"private-{company}-enrichment.md"
        if not dry_run:
            temp_jd.parent.mkdir(parents=True, exist_ok=True)
            temp_jd.write_text(
                f"# Company Enrichment\n\n## 기본 정보\n\n| 항목 | 내용 |\n|------|------|\n| 회사명 | {company} |\n| 출처 | [manual](https://thevc.kr) |\n",
                encoding="utf-8",
            )

        try:
            info = ensure_company_info(
                jd_path=temp_jd,
                jd_url="https://thevc.kr",
                company_name=company,
                thevc_mode=thevc_mode,
                dry_run=dry_run,
                min_completeness=min_completeness,
            )
            summary.processed += 1
            results.append(
                AutoTaskResult(
                    url="https://thevc.kr",
                    job_id=f"enrich-{company}",
                    status="processed",
                    company=company,
                    company_file=str(info.file_path),
                    thevc_attempted=info.thevc_attempted,
                    thevc_status=info.thevc_status,
                    investment_data_source=info.investment_data_source,
                )
            )
        except Exception as exc:
            summary.failed += 1
            results.append(
                AutoTaskResult(
                    url="https://thevc.kr",
                    job_id=f"enrich-{company}",
                    status="failed",
                    company=company,
                    error_stage="company_info",
                    error_reason=str(exc),
                )
            )

        if temp_jd.exists() and not dry_run:
            temp_jd.unlink()

    return results, summary


def run_auto(
    *,
    dry_run: bool = False,
    search_only: bool = False,
    max_urls: Optional[int] = None,
    run_id: Optional[str] = None,
    from_urls: Optional[Path] = None,
    screening_only: bool = False,
    continue_on_error: bool = True,
    llm_timeout: int = 120,
    no_classify: bool = False,
    thevc_mode: str = "auto",
    company_enrichment_only: bool = False,
    min_completeness: float = 0.0,
) -> tuple[List[AutoTaskResult], RunSummary]:
    config = load_config()

    if company_enrichment_only:
        return _build_results_from_enrichment(
            thevc_mode=thevc_mode, dry_run=dry_run, min_completeness=min_completeness
        )

    run_id = run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    summary = RunSummary(run_id=run_id)

    print("=" * 70)
    print(f"🤖 JD Auto Pipeline - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   run_id={run_id}")
    print("=" * 70)

    results: List[AutoTaskResult] = []

    if from_urls:
        urls = _load_urls_from_file(from_urls, max_urls=max_urls)
        postings: List[JobPosting] = []
    else:
        postings = run_search(dry_run=dry_run, max_urls=max_urls)
        urls = [p.url for p in postings]

    summary.new = len(urls)
    if not urls:
        print("\n✅ 처리할 URL 없음")
        return results, summary

    if search_only:
        print("\n🔍 검색만 모드 - 추출/스크리닝/분류 생략")
        for posting in postings:
            results.append(
                AutoTaskResult(
                    url=posting.url,
                    job_id=posting.job_id,
                    status="searched",
                    company=posting.company,
                    title=posting.title,
                )
            )
        return results, summary

    print(f"\n📍 URL 처리 시작: {len(urls)}건")

    for idx, url in enumerate(urls, 1):
        job_id = extract_job_id(url) or f"unknown-{idx}"
        row = AutoTaskResult(url=url, job_id=job_id, status="pending")

        print(f"\n[{idx}/{len(urls)}] {url}")

        existing = find_existing_jd(job_id)
        if existing and not screening_only:
            summary.duplicates += 1
            row.status = "duplicate"
            row.jd_path = str(existing)
            results.append(row)
            print(f"   ⏭️ 중복 스킵: {existing.name}")
            continue

        try:
            # 1) JD extraction
            jd_path: Optional[Path] = None
            if screening_only:
                jd_path = _resolve_jd_path_for_screening(url)
                if not jd_path:
                    raise RuntimeError(
                        "screening-only 모드에서 기존 JD를 찾지 못했습니다"
                    )
                row.jd_path = str(jd_path)
                row.status = "existing_jd"
            else:
                extracted = extract_jd_from_url(url) if not dry_run else None
                if extracted:
                    jd_path = extracted.output_path
                    row.company = extracted.company
                    row.title = extracted.title
                    row.jd_path = str(jd_path)
                    summary.extracted += 1
                else:
                    jd_path = _resolve_jd_path_for_screening(url)
                    if jd_path:
                        row.jd_path = str(jd_path)

            if not jd_path:
                raise RuntimeError("JD 파일 경로를 확보하지 못했습니다")

            # 2) company info
            company_info = ensure_company_info(
                jd_path=jd_path,
                jd_url=url,
                company_name=row.company or None,
                thevc_mode=thevc_mode,
                dry_run=dry_run,
                min_completeness=min_completeness,
            )
            row.company = row.company or company_info.company
            row.company_file = str(company_info.file_path)
            row.thevc_attempted = company_info.thevc_attempted
            row.thevc_status = company_info.thevc_status
            row.investment_data_source = company_info.investment_data_source

            # 3) screening
            screening = run_screening(
                jd_path=jd_path,
                company_file=Path(company_info.file_path) if row.company_file else None,
                llm_timeout=llm_timeout,
                dry_run=dry_run,
            )
            row.screening_path = str(screening.screening_path)
            row.verdict = screening.verdict
            row.used_fallback = screening.used_fallback
            summary.screened += 1

            # 4) classify
            if no_classify:
                classified = ""
            else:
                verdict, classified = _classify(jd_path, dry_run=dry_run)
                if verdict:
                    row.verdict = verdict
                row.classified_folder = classified

            _update_verdict_count(summary, row.verdict)

            row.status = "processed"
            summary.processed += 1
            results.append(row)
            print(
                f"   ✅ 완료: verdict={row.verdict or 'N/A'} folder={row.classified_folder or '-'}"
            )

        except Exception as exc:
            row.status = "failed"
            if not row.error_stage:
                row.error_stage = "pipeline"
            row.error_reason = str(exc)
            summary.failed += 1
            results.append(row)
            print(f"   ❌ 실패: {exc}")
            if not continue_on_error:
                break

    notifications = config.get("notifications", {})
    if notifications.get("on_recommended") and summary.recommended > 0 and not dry_run:
        print("\n📍 알림 전송")
        send_notification(format_notification(results, summary), config)

    return results, summary


def main() -> None:
    parser = argparse.ArgumentParser(description="JD Auto - 채용공고 자동화 파이프라인")
    parser.add_argument(
        "--dry-run", action="store_true", help="미리보기 (파일 저장/이동 최소화)"
    )
    parser.add_argument("--search-only", action="store_true", help="검색만 실행")
    parser.add_argument("--from-urls", type=Path, help="검색 대신 URL 목록 파일 사용")
    parser.add_argument("--max-urls", type=int, help="최대 URL 수")
    parser.add_argument("--run-id", help="실행 ID")
    parser.add_argument(
        "--screening-only",
        action="store_true",
        help="기존 JD 대상으로 스크리닝/분류만 수행",
    )
    parser.add_argument(
        "--stop-on-error", action="store_true", help="첫 오류에서 실행 중단"
    )
    parser.add_argument(
        "--max-retries", type=int, default=1, help="(향후 예약) 단계별 재시도 횟수"
    )
    parser.add_argument(
        "--llm-timeout", type=int, default=120, help="LLM CLI 호출 타임아웃(초)"
    )
    parser.add_argument(
        "--no-classify", action="store_true", help="분류(파일 이동) 생략"
    )
    parser.add_argument(
        "--thevc-mode",
        choices=["auto", "skip", "require"],
        default="auto",
        help="TheVC 추출 모드",
    )
    parser.add_argument(
        "--company-enrichment-only", action="store_true", help="TheVC 보완 큐만 재처리"
    )
    parser.add_argument(
        "--min-completeness",
        type=float,
        default=0.0,
        help="기존 파일 completeness가 이 값 미만이면 재수집 (0~100, 기본 0.0)",
    )
    parser.add_argument("--notify-test", action="store_true", help="알림 테스트")

    args = parser.parse_args()

    if args.notify_test:
        config = load_config()
        msg = "🔔 JD Auto 알림 테스트\n테스트 메시지입니다."
        send_notification(msg, config)
        return

    if args.max_retries != 1:
        print("ℹ️ 현재 버전은 --max-retries를 예약 옵션으로만 수용합니다.")

    results, summary = run_auto(
        dry_run=args.dry_run,
        search_only=args.search_only,
        max_urls=args.max_urls,
        run_id=args.run_id,
        from_urls=args.from_urls,
        screening_only=args.screening_only,
        continue_on_error=not args.stop_on_error,
        llm_timeout=args.llm_timeout,
        no_classify=args.no_classify,
        thevc_mode=args.thevc_mode,
        company_enrichment_only=args.company_enrichment_only,
        min_completeness=args.min_completeness,
    )

    result_file = save_results(results, summary, dry_run=args.dry_run)
    print("\n" + "=" * 70)
    print("📊 최종 요약")
    print("=" * 70)
    print(f"run_id: {summary.run_id}")
    print(
        f"신규: {summary.new} | 처리: {summary.processed} | 중복: {summary.duplicates} | 실패: {summary.failed}"
    )
    print(f"추출: {summary.extracted} | 스크리닝: {summary.screened}")
    print(
        f"추천: {summary.recommended} | 보류: {summary.hold} | 패스: {summary.passed}"
    )
    print(f"결과 파일: {result_file}")


if __name__ == "__main__":
    main()
