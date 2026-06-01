from __future__ import annotations

import argparse
import fcntl
import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    from .auto_company import ENRICHMENT_QUEUE_PATH, ensure_company_info
    from .constants import JOB_POSTINGS_DIR
    from .naming import slugify_company
except ImportError:
    from auto_company import ENRICHMENT_QUEUE_PATH, ensure_company_info
    from constants import JOB_POSTINGS_DIR
    from naming import slugify_company

BASE_DIR = Path(__file__).parent.parent.parent
RESULTS_DIR = BASE_DIR / "private" / "job_postings" / "auto_results"
STATE_DIR = RESULTS_DIR
logger = logging.getLogger(__name__)


def _state_path(run_id: str) -> Path:
    return STATE_DIR / f".auto_state_{run_id}.json"


def _save_state(run_id: str, items: dict) -> None:
    """Atomically save pipeline state using temp file + os.replace."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = _state_path(run_id)
    payload = {"run_id": run_id, "updated_at": datetime.now().isoformat(), "items": items}
    fd, tmp_path = tempfile.mkstemp(dir=str(STATE_DIR), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file_obj:
            json.dump(payload, file_obj, indent=2, ensure_ascii=False)
            file_obj.flush()
            os.fsync(file_obj.fileno())
        os.replace(tmp_path, str(path))
        dir_fd = os.open(str(STATE_DIR), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except Exception as exc:
        logger.warning("Failed to save state for %s: %s", run_id, exc)
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _load_state(run_id: str) -> dict:
    path = _state_path(run_id)
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as file_obj:
            fcntl.flock(file_obj.fileno(), fcntl.LOCK_SH)
            try:
                data = json.load(file_obj)
            finally:
                fcntl.flock(file_obj.fileno(), fcntl.LOCK_UN)
        return data.get("items", {})
    except (json.JSONDecodeError, KeyError):
        return {}


def _find_latest_state() -> Optional[str]:
    if not STATE_DIR.exists():
        return None
    state_files = sorted(
        STATE_DIR.glob(".auto_state_*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for state_file in state_files:
        try:
            with open(state_file, "r", encoding="utf-8") as file_obj:
                fcntl.flock(file_obj.fileno(), fcntl.LOCK_SH)
                try:
                    data = json.load(file_obj)
                finally:
                    fcntl.flock(file_obj.fileno(), fcntl.LOCK_UN)
            items = data.get("items", {})
            if any(item.get("status") != "done" for item in items.values()):
                return data.get("run_id")
        except (json.JSONDecodeError, KeyError):
            continue
    return None


def _cleanup_state(run_id: str) -> None:
    path = _state_path(run_id)
    if path.exists():
        path.unlink()


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
    closed: int = 0
    rejected_prior: int = 0
    prescreened: int = 0
    prescreen_review: int = 0
    search_urls_file: Optional[Path] = None

    def to_dict(self) -> dict:
        data = asdict(self)
        if data.get("search_urls_file") is not None:
            data["search_urls_file"] = str(data["search_urls_file"])
        return data


def save_results(results: list[AutoTaskResult], summary: RunSummary, dry_run: bool) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    result_file = RESULTS_DIR / f"auto_{summary.run_id}.json"
    payload = {
        "timestamp": datetime.now().isoformat(),
        "dry_run": dry_run,
        "summary": summary.to_dict(),
        "results": [asdict(result) for result in results],
    }
    result_file.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return result_file


def print_final_summary(summary: RunSummary, result_file: Path) -> None:
    print("\n" + "=" * 70)
    print("📊 최종 요약")
    print("=" * 70)
    print(f"run_id: {summary.run_id}")
    print(
        f"신규: {summary.new} | 처리: {summary.processed} | 중복: {summary.duplicates} | 실패: {summary.failed}"
    )
    print(f"추출: {summary.extracted} | 스크리닝: {summary.screened}")
    print(f"추천: {summary.recommended} | 보류: {summary.hold} | 패스: {summary.passed}")
    print(f"Pre-screen 컷: {summary.prescreened} | Pre-screen 보류: {summary.prescreen_review}")
    print(f"마감: {summary.closed} | 직전지원: {summary.rejected_prior}")
    print(f"결과 파일: {result_file}")


def _build_results_from_enrichment(
    thevc_mode: str,
    dry_run: bool,
    min_completeness: float = 0.0,
) -> tuple[list[AutoTaskResult], RunSummary]:
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    summary = RunSummary(run_id=run_id)
    results: list[AutoTaskResult] = []
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
        slug = slugify_company(company)
        temp_jd = JOB_POSTINGS_DIR / "unprocessed" / f"private-{slug}-enrichment.md"
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
            logger.error("Company enrichment failed for %s: %s", company, exc)
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
        finally:
            if temp_jd.exists() and not dry_run:
                temp_jd.unlink()
    return results, summary


def build_search_results(postings, summary: RunSummary) -> tuple[list[AutoTaskResult], RunSummary]:
    print("\n🔍 검색만 모드 - 추출/스크리닝/분류 생략")
    return [
        AutoTaskResult(
            url=posting.url,
            job_id=posting.job_id,
            status="searched",
            company=posting.company,
            title=posting.title,
        )
        for posting in postings
    ], summary


def build_cli_parser(default_min_completeness: float) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="JD Auto - 채용공고 자동화 파이프라인")
    parser.add_argument("--dry-run", action="store_true", help="미리보기 (파일 저장/이동 최소화)")
    parser.add_argument("--search-only", action="store_true", help="검색만 실행")
    parser.add_argument("--from-urls", type=Path, help="검색 대신 URL 목록 파일 사용")
    parser.add_argument("--max-urls", type=int, help="최대 URL 수")
    parser.add_argument("--run-id", help="실행 ID")
    parser.add_argument("--screening-only", action="store_true", help="기존 JD 대상으로 스크리닝/분류만 수행")
    parser.add_argument("--stop-on-error", action="store_true", help="첫 오류에서 실행 중단")
    parser.add_argument("--max-retries", type=int, default=1, help="(향후 예약) 단계별 재시도 횟수")
    parser.add_argument("--llm-timeout", type=int, default=120, help="LLM CLI 호출 타임아웃(초)")
    parser.add_argument("--no-classify", action="store_true", help="분류(파일 이동) 생략")
    parser.add_argument("--thevc-mode", choices=["auto", "skip", "require"], default="auto", help="TheVC 추출 모드")
    parser.add_argument("--company-enrichment-only", action="store_true", help="TheVC 보완 큐만 재처리")
    parser.add_argument("--min-completeness", type=float, default=default_min_completeness, help=f"회사정보 completeness가 이 값 미만이면 스크리닝 중단 (0~100, 기본 {default_min_completeness:.0f})")
    parser.add_argument("--allow-incomplete-company-info", action="store_true", help="플랫폼 장애/접근 제한 등 불가항력일 때만 회사정보 기준 미달 스크리닝 허용")
    parser.add_argument("--notify-test", action="store_true", help="알림 테스트")
    parser.add_argument("--no-prescreen", action="store_true", help="Pre-screening 단계 비활성화 (LLM 진입 전 빠른 컷 안 함)")
    parser.add_argument("--resume", action="store_true", help="마지막 실행에서 미완료 항목만 재처리")
    parser.add_argument("--verbose", "-v", action="store_true", help="상세 로그 출력 (DEBUG level)")
    return parser


def execute_cli(args, *, run_auto_fn, save_results_fn, print_summary_fn) -> None:
    split_default_run = not any((
        args.dry_run, args.search_only, args.from_urls, args.screening_only,
        args.company_enrichment_only, args.resume,
    ))
    if split_default_run:
        base_run_id = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        print("\n" + "=" * 70)
        print("1단계: 검색만 실행")
        print("=" * 70)
        search_results, search_summary = run_auto_fn(
            dry_run=args.dry_run,
            search_only=True,
            max_urls=args.max_urls,
            run_id=f"{base_run_id}_search",
            continue_on_error=not args.stop_on_error,
            thevc_mode=args.thevc_mode,
            min_completeness=args.min_completeness,
        )
        search_result_file = save_results_fn(search_results, search_summary, dry_run=args.dry_run)
        print_summary_fn(search_summary, search_result_file)
        urls_file = search_summary.search_urls_file
        if not urls_file or search_summary.new == 0:
            print("\n✅ 2단계로 넘길 신규 URL 없음")
            return
        print("\n" + "=" * 70)
        print(f"2단계: URL 파일 기반 추출/스크리닝/분류 실행 - {urls_file}")
        print("=" * 70)
        results, summary = run_auto_fn(
            dry_run=args.dry_run,
            max_urls=args.max_urls,
            run_id=f"{base_run_id}_screening",
            from_urls=urls_file,
            continue_on_error=not args.stop_on_error,
            llm_timeout=args.llm_timeout,
            no_classify=args.no_classify,
            thevc_mode=args.thevc_mode,
            min_completeness=args.min_completeness,
            allow_incomplete_company_info=args.allow_incomplete_company_info,
            no_prescreen=args.no_prescreen,
        )
        result_file = save_results_fn(results, summary, dry_run=args.dry_run)
        print_summary_fn(summary, result_file)
        return
    results, summary = run_auto_fn(
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
        allow_incomplete_company_info=args.allow_incomplete_company_info,
        resume=args.resume,
        no_prescreen=args.no_prescreen,
    )
    result_file = save_results_fn(results, summary, dry_run=args.dry_run)
    print_summary_fn(summary, result_file)
