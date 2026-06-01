from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

try:
    from .auto_company import ensure_company_info
    from .auto_extractors import extract_jd_from_url
    from .auto_screening import run_screening
    from .auto_state import AutoTaskResult, RunSummary, _cleanup_state, _save_state
    from .constants import JOB_POSTINGS_DIR
    from .notifications import format_notification, send_notification
    from .path_utils import extract_job_id, find_existing_jd, find_jd_anywhere
    from .pipeline import ProcessResult, classify_file
    from .pre_screen import pre_screen_jd
    from .pre_screen_helpers import _check_prior_application, _is_closed_jd
    from .search import JobPosting, run_search
    from .verdict import move_to_folder
except ImportError:
    from auto_company import ensure_company_info
    from auto_extractors import extract_jd_from_url
    from auto_screening import run_screening
    from auto_state import AutoTaskResult, RunSummary, _cleanup_state, _save_state
    from constants import JOB_POSTINGS_DIR
    from notifications import format_notification, send_notification
    from path_utils import extract_job_id, find_existing_jd, find_jd_anywhere
    from pipeline import ProcessResult, classify_file
    from pre_screen import pre_screen_jd
    from pre_screen_helpers import _check_prior_application, _is_closed_jd
    from search import JobPosting, run_search
    from verdict import move_to_folder

DEFAULT_MIN_COMPLETENESS = 70.0
logger = logging.getLogger(__name__)
_NON_REPROCESSABLE_FOLDERS = {
    "pass", "applied", "rejected", "on_going", "high_priority", "closed",
}


def _load_urls_from_file(path: Path, max_urls: Optional[int] = None) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"URL 파일을 찾을 수 없습니다: {path}")
    urls = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    return urls[:max_urls] if max_urls is not None else urls


def _resolve_jd_path_for_screening(url: str) -> Optional[Path]:
    job_id = extract_job_id(url)
    return find_jd_anywhere(job_id) if job_id else None


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
    if result.result == ProcessResult.SKIPPED and result.protected_status:
        return "", str(jd_path.parent.relative_to(JOB_POSTINGS_DIR)) if not dry_run else ""
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
def _build_url_list(
    *,
    from_urls: Optional[Path],
    max_urls: Optional[int],
    resume: bool,
    prev_state: dict,
    dry_run: bool,
    summary: RunSummary,
) -> tuple[list[str], list[JobPosting]]:
    if from_urls:
        return _load_urls_from_file(from_urls, max_urls=max_urls), []
    if resume and prev_state:
        return [item["url"] for item in prev_state.values() if item.get("status") != "done"], []
    postings, search_urls_path = run_search(dry_run=dry_run, max_urls=max_urls)
    summary.search_urls_file = search_urls_path
    return [posting.url for posting in postings], postings


def _handle_prescreen_hit(pre, row: AutoTaskResult, jd_path: Path, no_classify: bool, summary: RunSummary) -> None:
    target = pre.target_folder
    if not no_classify:
        moved = move_to_folder(jd_path, target)
        row.jd_path = str(moved)
        row.classified_folder = target
    else:
        row.classified_folder = ""
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


def _resolve_jd_and_check_dup(
    job_id: str,
    saved: dict,
    *,
    resume: bool,
    screening_only: bool,
) -> tuple[Optional[Path], bool]:
    saved_jd_path = saved.get("jd_path", "")
    resolved = Path(saved_jd_path) if saved_jd_path and Path(saved_jd_path).exists() else find_existing_jd(job_id)
    saved_stage = saved.get("stage", "pending")
    is_resume_item = resume and saved_stage != "pending" and saved.get("status") != "done"
    if is_resume_item and resolved and any(part in _NON_REPROCESSABLE_FOLDERS for part in resolved.parts):
        is_resume_item = False
    return resolved, bool(resolved and not screening_only and not is_resume_item)
def _process_urls(
    *,
    urls: list[str],
    run_id: str,
    config: dict,
    summary: RunSummary,
    state_items: dict,
    dry_run: bool,
    screening_only: bool,
    continue_on_error: bool,
    llm_timeout: int,
    no_classify: bool,
    thevc_mode: str,
    min_completeness: float,
    allow_incomplete_company_info: bool,
    resume: bool,
    no_prescreen: bool,
) -> tuple[list[AutoTaskResult], RunSummary]:
    results: list[AutoTaskResult] = []
    print(f"\n📍 URL 처리 시작: {len(urls)}건")
    for idx, url in enumerate(urls, 1):
        job_id = extract_job_id(url) or f"unknown-{idx}"
        row = AutoTaskResult(url=url, job_id=job_id, status="pending")
        if job_id not in state_items or state_items[job_id].get("status") == "done":
            state_items[job_id] = {"url": url, "stage": "pending", "status": "pending", "error": ""}
        saved = state_items[job_id]
        saved_stage = saved.get("stage", "pending")
        print(f"\n[{idx}/{len(urls)}] {url}")
        if resume and saved_stage != "pending":
            print(f"   ♻️  Resume: stage={saved_stage}")
        resolved_jd_path, is_dup = _resolve_jd_and_check_dup(
            job_id, saved, resume=resume, screening_only=screening_only,
        )
        if is_dup:
            if resolved_jd_path is None:
                raise RuntimeError("duplicate JD path not resolved")
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
            if saved_stage in ("prescreening", "company_info", "screening", "classifying") and resolved_jd_path:
                jd_path = resolved_jd_path
                row.jd_path = str(jd_path)
                print("   ⏩ Extraction 스킵 (이미 완료)")
            elif screening_only:
                state_items[job_id].update(stage="extracting", status="in_progress")
                _save_state(run_id, state_items)
                jd_path = _resolve_jd_path_for_screening(url)
                if not jd_path:
                    raise RuntimeError("screening-only 모드에서 기존 JD를 찾지 못했습니다")
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
            state_items[job_id]["jd_path"] = str(jd_path)
            if (
                not no_prescreen and not screening_only and not dry_run
                and saved_stage not in ("company_info", "screening", "classifying")
            ):
                state_items[job_id].update(stage="prescreening", status="in_progress")
                _save_state(run_id, state_items)
                pre = pre_screen_jd(jd_path, config)
                if pre.hit:
                    _handle_prescreen_hit(pre, row, jd_path, no_classify, summary)
                    state_items[job_id].update(
                        stage="done",
                        status="done",
                        jd_path=row.jd_path,
                        prescreen_reason=pre.reason_code,
                    )
                    _save_state(run_id, state_items)
                    results.append(row)
                    print(f"   ⚡ Pre-screen 컷: {pre.reason_code} → {pre.target_folder}")
                    continue
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
                not allow_incomplete_company_info and not dry_run
                and company_info.completeness < min_completeness
                and company_info.investment_data_source != "headhunting_excluded"
            ):
                row.status = "blocked_company_info"
                row.error_stage = "company_info"
                row.error_reason = (
                    f"회사정보 완성도 {company_info.completeness:.0f}% < 기준 {min_completeness:.0f}%"
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
            saved_screening_path = saved.get("screening_path", "")
            saved_verdict = saved.get("verdict", "")
            if (
                saved_stage in ("screening", "classifying")
                and saved_screening_path and Path(saved_screening_path).exists() and saved_verdict
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
                state_items[job_id]["screening_path"] = row.screening_path
                state_items[job_id]["verdict"] = row.verdict
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
            print(f"   ✅ 완료: verdict={row.verdict or 'N/A'} folder={row.classified_folder or '-'}")
        except Exception as exc:
            logger.error("Pipeline failed for %s: %s", job_id, exc)
            row.status = "failed"
            row.error_stage = row.error_stage or "pipeline"
            row.error_reason = str(exc)
            summary.failed += 1
            state_items[job_id].update(status="failed", error=str(exc))
            _save_state(run_id, state_items)
            results.append(row)
            if not continue_on_error:
                break
    if summary.failed == 0:
        _cleanup_state(run_id)
    notifications = config.get("notifications", {})
    if notifications.get("on_recommended") and summary.recommended > 0 and not dry_run:
        print("\n📍 알림 전송")
        send_notification(format_notification(results, summary), config)
    return results, summary
