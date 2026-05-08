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
import fcntl
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

try:
    from .auto_company import ENRICHMENT_QUEUE_PATH, ensure_company_info
    from .auto_extractors import extract_jd_from_url
    from .auto_screening import run_screening
    from .constants import JOB_POSTINGS_DIR
    from .naming import slugify_company
    from .path_utils import extract_job_id, find_existing_jd, find_jd_anywhere
    from .pipeline import ProcessResult, classify_file
    from .search import JobPosting, load_config, run_search
    from .notifications import format_notification, send_notification
    from .verdict import move_to_folder
    from .pre_screen_helpers import (
        _CLOSED_MARKERS, _PRIOR_HISTORY_FOLDERS, _PRIOR_HISTORY_DAYS,
        _is_closed_jd, _extract_company_slug, _check_prior_application,
    )
    from .pre_screen import pre_screen_jd
except ImportError:
    from auto_company import ENRICHMENT_QUEUE_PATH, ensure_company_info
    from auto_extractors import extract_jd_from_url
    from auto_screening import run_screening
    from constants import JOB_POSTINGS_DIR
    from naming import slugify_company
    from notifications import format_notification, send_notification
    from path_utils import extract_job_id, find_existing_jd, find_jd_anywhere
    from pipeline import ProcessResult, classify_file
    from search import JobPosting, load_config, run_search
    from verdict import move_to_folder
    from pre_screen_helpers import (
        _CLOSED_MARKERS, _PRIOR_HISTORY_FOLDERS, _PRIOR_HISTORY_DAYS,
        _is_closed_jd, _extract_company_slug, _check_prior_application,
    )
    from pre_screen import pre_screen_jd

BASE_DIR = Path(__file__).parent.parent.parent
RESULTS_DIR = BASE_DIR / "private" / "job_postings" / "auto_results"
STATE_DIR = RESULTS_DIR
DEFAULT_MIN_COMPLETENESS = 70.0


def _state_path(run_id: str) -> Path:
    return STATE_DIR / f".auto_state_{run_id}.json"


def _save_state(run_id: str, items: dict) -> None:
    """Atomically save pipeline state using temp file + os.replace."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = _state_path(run_id)
    payload = {"run_id": run_id, "updated_at": datetime.now().isoformat(), "items": items}

    fd, tmp_path = tempfile.mkstemp(dir=str(STATE_DIR), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, str(path))
        dir_fd = os.open(str(STATE_DIR), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except Exception:
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
        with open(path, "r", encoding="utf-8") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)
            try:
                data = json.load(f)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        return data.get("items", {})
    except (json.JSONDecodeError, KeyError):
        return {}


def _find_latest_state() -> Optional[str]:
    if not STATE_DIR.exists():
        return None
    state_files = sorted(STATE_DIR.glob(".auto_state_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for sf in state_files:
        try:
            with open(sf, "r", encoding="utf-8") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                try:
                    data = json.load(f)
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            items = data.get("items", {})
            if any(v.get("status") != "done" for v in items.values()):
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
    closed: int = 0            # pre-screen 마감 감지
    rejected_prior: int = 0    # pre-screen 직전 6개월 지원 이력
    prescreened: int = 0       # pre-screen 컷 (closed/prior 제외, 실제 LLM 절감 건수)
    prescreen_review: int = 0  # pre-screen counter_indicator 격리 (수동 검토 대기)

    def to_dict(self) -> dict:
        return asdict(self)



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
    return find_jd_anywhere(job_id)


def _classify(jd_path: Path, dry_run: bool) -> tuple[str, str]:
    if _is_closed_jd(jd_path):
        if dry_run:
            return "지원 비추천", "closed"
        moved = move_to_folder(jd_path, "closed")
        return "지원 비추천", str(moved.parent.relative_to(JOB_POSTINGS_DIR))

    prior = _check_prior_application(jd_path)
    if prior is not None:
        if dry_run:
            return "지원 비추천", "rejected"
        moved = move_to_folder(jd_path, "rejected")
        return "지원 비추천", str(moved.parent.relative_to(JOB_POSTINGS_DIR))

    result = classify_file(jd_path, dry_run=dry_run)
    if result.result == ProcessResult.SUCCESS:
        return result.verdict or "", result.target_folder or ""

    # Protected status — don't move, keep in current location
    if result.result == ProcessResult.SKIPPED and result.protected_status:
        return "", str(jd_path.parent.relative_to(JOB_POSTINGS_DIR)) if not dry_run else ""

    # Missing verdict or other non-fatal case -> default hold
    if result.result in {ProcessResult.SKIPPED, ProcessResult.ERROR}:
        if dry_run:
            return "", "conditional/hold"
        moved = move_to_folder(jd_path, "conditional/hold")
        return "", str(moved.parent.relative_to(JOB_POSTINGS_DIR))

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
    min_completeness: float = DEFAULT_MIN_COMPLETENESS,
    allow_incomplete_company_info: bool = False,
    resume: bool = False,
    no_prescreen: bool = False,
) -> tuple[List[AutoTaskResult], RunSummary]:
    config = load_config()

    if company_enrichment_only:
        return _build_results_from_enrichment(
            thevc_mode=thevc_mode, dry_run=dry_run, min_completeness=min_completeness
        )

    prev_state: dict = {}
    if resume:
        prev_run_id = _find_latest_state()
        if prev_run_id:
            prev_state = _load_state(prev_run_id)
            run_id = prev_run_id
            print(f"🔄 이전 실행 재개: run_id={prev_run_id}, 미완료 {sum(1 for v in prev_state.values() if v.get('status') != 'done')}건")

    run_id = run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    summary = RunSummary(run_id=run_id)

    print("=" * 70)
    print(f"🤖 JD Auto Pipeline - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   run_id={run_id}")
    print("=" * 70)

    results: List[AutoTaskResult] = []
    state_items: dict = dict(prev_state)

    if from_urls:
        urls = _load_urls_from_file(from_urls, max_urls=max_urls)
        postings: List[JobPosting] = []
    elif resume and prev_state:
        urls = [v["url"] for v in prev_state.values() if v.get("status") != "done"]
        postings = []
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

        # Preserve existing state on resume (don't overwrite saved jd_path/screening_path)
        if job_id not in state_items or state_items[job_id].get("status") == "done":
            state_items[job_id] = {"url": url, "stage": "pending", "status": "pending", "error": ""}

        saved = state_items[job_id]
        saved_stage = saved.get("stage", "pending")

        print(f"\n[{idx}/{len(urls)}] {url}")
        if resume and saved_stage != "pending":
            print(f"   ♻️  Resume: stage={saved_stage}")

        # Resolve jd_path from state or filesystem
        saved_jd_path = saved.get("jd_path", "")
        if saved_jd_path and Path(saved_jd_path).exists():
            resolved_jd_path = Path(saved_jd_path)
        else:
            resolved_jd_path = find_existing_jd(job_id)

        # Duplicate/protection skip logic:
        # - New items (not in state): skip if JD already exists anywhere
        # - Resume items (in state with incomplete status): continue processing,
        #   UNLESS file has been moved to a non-reprocessable folder
        # - Done items: should not appear (filtered out when building URL list)
        is_resume_item = resume and saved_stage not in ("pending",) and saved.get("status") != "done"

        # Even resume items should not be reprocessed if they've been moved
        # to a non-conditional folder (pass, applied, rejected, on_going, high_priority)
        if is_resume_item and resolved_jd_path:
            non_reprocessable = {"pass", "applied", "rejected", "on_going", "high_priority"}
            if any(part in non_reprocessable for part in resolved_jd_path.parts):
                is_resume_item = False

        if resolved_jd_path and not screening_only and not is_resume_item:
            summary.duplicates += 1
            row.status = "duplicate"
            row.jd_path = str(resolved_jd_path)
            state_items[job_id].update(stage="done", status="skipped")
            _save_state(run_id, state_items)
            results.append(row)
            print(f"   ⏭️ 중복 스킵: {resolved_jd_path.name}")
            continue

        try:
            jd_path: Optional[Path] = None

            # 1) JD extraction — skip if already done (resume or screening_only)
            if saved_stage in ("company_info", "screening", "classifying") and resolved_jd_path:
                jd_path = resolved_jd_path
                row.jd_path = str(jd_path)
                print(f"   ⏩ Extraction 스킵 (이미 완료)")
            elif screening_only:
                state_items[job_id].update(stage="extracting", status="in_progress")
                _save_state(run_id, state_items)
                jd_path = _resolve_jd_path_for_screening(url)
                if not jd_path:
                    raise RuntimeError(
                        "screening-only 모드에서 기존 JD를 찾지 못했습니다"
                    )
                row.jd_path = str(jd_path)
                row.status = "existing_jd"
            else:
                state_items[job_id].update(stage="extracting", status="in_progress")
                _save_state(run_id, state_items)
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

            # Persist jd_path in state
            state_items[job_id]["jd_path"] = str(jd_path)

            # 1.5) Pre-screening hook — short-circuit before company_info + LLM
            # Skip when:
            #  - --no-prescreen flag (CLI override)
            #  - --screening-only mode (사용자가 LLM 재실행을 명시적 요청)
            #  - --dry-run
            #  - resume: saved_stage가 이미 pre-screen 이후 단계로 진입한 경우
            if (
                not no_prescreen
                and not screening_only
                and not dry_run
                and saved_stage not in ("company_info", "screening", "classifying")
            ):
                state_items[job_id].update(stage="prescreening", status="in_progress")
                _save_state(run_id, state_items)
                pre = pre_screen_jd(jd_path, config)
                if pre.hit:
                    target = pre.target_folder
                    moved = move_to_folder(jd_path, target)
                    row.jd_path = str(moved)
                    row.classified_folder = target
                    row.error_stage = "prescreening"
                    row.error_reason = pre.reason_detail

                    if pre.reason_code == "closed":
                        row.status = "prescreen_filtered"
                        row.verdict = "지원 비추천"
                        summary.closed += 1
                    elif pre.reason_code == "prior_application":
                        row.status = "prescreen_filtered"
                        row.verdict = "지원 비추천"
                        summary.rejected_prior += 1
                    elif pre.is_review:
                        row.status = "prescreen_review"
                        row.verdict = "지원 보류"
                        summary.prescreen_review += 1
                    else:
                        row.status = "prescreen_filtered"
                        row.verdict = "지원 비추천"
                        summary.prescreened += 1
                        summary.passed += 1

                    summary.processed += 1
                    state_items[job_id].update(
                        stage="done", status="done",
                        jd_path=row.jd_path,
                        prescreen_reason=pre.reason_code,
                    )
                    _save_state(run_id, state_items)
                    results.append(row)
                    print(f"   ⚡ Pre-screen 컷: {pre.reason_code} → {target}")
                    continue

            # 2) company info (idempotent — reuses existing file)
            state_items[job_id].update(stage="company_info", status="in_progress")
            _save_state(run_id, state_items)

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

            if (
                not allow_incomplete_company_info
                and not dry_run
                and company_info.completeness < min_completeness
                and company_info.investment_data_source != "headhunting_excluded"
            ):
                row.status = "blocked_company_info"
                row.error_stage = "company_info"
                row.error_reason = (
                    f"회사정보 완성도 {company_info.completeness:.0f}% "
                    f"< 기준 {min_completeness:.0f}%"
                )
                summary.failed += 1
                state_items[job_id].update(
                    stage="company_info",
                    status="blocked",
                    error=row.error_reason,
                    company_file=row.company_file,
                )
                _save_state(run_id, state_items)
                results.append(row)
                print(f"   ⛔ 회사정보 보완 필요: {row.error_reason}")
                continue

            # 3) screening — skip if already done and saved in state
            saved_screening_path = saved.get("screening_path", "")
            saved_verdict = saved.get("verdict", "")
            if (
                saved_stage == "classifying"
                and saved_screening_path
                and Path(saved_screening_path).exists()
                and saved_verdict
            ):
                row.screening_path = saved_screening_path
                row.verdict = saved_verdict
                summary.screened += 1
                print(f"   ⏩ Screening 스킵 (이미 완료: {saved_verdict})")
            else:
                state_items[job_id].update(stage="screening", status="in_progress")
                _save_state(run_id, state_items)

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

                # Persist screening results in state
                state_items[job_id]["screening_path"] = row.screening_path
                state_items[job_id]["verdict"] = row.verdict

            # 4) classify
            state_items[job_id].update(stage="classifying", status="in_progress")
            _save_state(run_id, state_items)

            if no_classify:
                classified = ""
            else:
                verdict, classified = _classify(jd_path, dry_run=dry_run)
                if verdict:
                    row.verdict = verdict
                row.classified_folder = classified
                if classified:
                    new_path = find_existing_jd(job_id)
                    if new_path:
                        row.jd_path = str(new_path)
                        state_items[job_id]["jd_path"] = str(new_path)

            _update_verdict_count(summary, row.verdict)

            row.status = "processed"
            summary.processed += 1
            state_items[job_id].update(stage="done", status="done")
            _save_state(run_id, state_items)
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
            state_items[job_id].update(status="failed", error=str(exc))
            _save_state(run_id, state_items)
            results.append(row)
            print(f"   ❌ 실패: {exc}")
            if not continue_on_error:
                break

    if summary.failed == 0:
        _cleanup_state(run_id)

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
        default=DEFAULT_MIN_COMPLETENESS,
        help=f"회사정보 completeness가 이 값 미만이면 스크리닝 중단 (0~100, 기본 {DEFAULT_MIN_COMPLETENESS:.0f})",
    )
    parser.add_argument(
        "--allow-incomplete-company-info",
        action="store_true",
        help="플랫폼 장애/접근 제한 등 불가항력일 때만 회사정보 기준 미달 스크리닝 허용",
    )
    parser.add_argument("--notify-test", action="store_true", help="알림 테스트")
    parser.add_argument(
        "--no-prescreen", action="store_true",
        help="Pre-screening 단계 비활성화 (LLM 진입 전 빠른 컷 안 함)",
    )
    parser.add_argument(
        "--resume", action="store_true", help="마지막 실행에서 미완료 항목만 재처리"
    )

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
        allow_incomplete_company_info=args.allow_incomplete_company_info,
        resume=args.resume,
        no_prescreen=args.no_prescreen,
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
    print(f"Pre-screen 컷: {summary.prescreened} | Pre-screen 보류: {summary.prescreen_review}")
    print(f"마감: {summary.closed} | 직전지원: {summary.rejected_prior}")
    print(f"결과 파일: {result_file}")


if __name__ == "__main__":
    main()
