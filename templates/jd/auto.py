#!/usr/bin/env python3
"""JD Auto - end-to-end automation pipeline."""
from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

if __package__ in {None, ""}:
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    __package__ = "templates.jd"

try:
    from .auto_processor import DEFAULT_MIN_COMPLETENESS, _build_url_list, _process_urls
    from .auto_state import (
        RunSummary, _build_results_from_enrichment, _find_latest_state, _load_state,
        build_cli_parser, build_search_results, execute_cli, print_final_summary, save_results,
    )
    from .notifications import send_notification
    from .search import load_config
except ImportError:
    from auto_processor import DEFAULT_MIN_COMPLETENESS, _build_url_list, _process_urls
    from auto_state import (
        RunSummary, _build_results_from_enrichment, _find_latest_state, _load_state,
        build_cli_parser, build_search_results, execute_cli, print_final_summary, save_results,
    )
    from notifications import send_notification
    from search import load_config

_handle_company_enrichment_only = _build_results_from_enrichment
_handle_search_only = build_search_results


def _handle_screening_only(**kwargs): return _process_urls(screening_only=True, **kwargs)


def _handle_full_pipeline(**kwargs): return _process_urls(screening_only=False, **kwargs)


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
):
    config, prev_state = load_config(), {}
    if company_enrichment_only:
        return _handle_company_enrichment_only(thevc_mode=thevc_mode, dry_run=dry_run, min_completeness=min_completeness)
    if resume and (prev_run_id := _find_latest_state()):
        prev_state, run_id = _load_state(prev_run_id), prev_run_id
        pending = sum(1 for item in prev_state.values() if item.get("status") != "done")
        print(f"🔄 이전 실행 재개: run_id={prev_run_id}, 미완료 {pending}건")
    run_id = run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    summary = RunSummary(run_id=run_id)
    print("=" * 70)
    print(f"🤖 JD Auto Pipeline - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   run_id={run_id}")
    print("=" * 70)
    urls, postings = _build_url_list(from_urls=from_urls, max_urls=max_urls, resume=resume, prev_state=prev_state, dry_run=dry_run, summary=summary)
    summary.new = len(urls)
    if not urls:
        print("\n✅ 처리할 URL 없음")
        return [], summary
    if search_only:
        return _handle_search_only(postings, summary)
    handler = _handle_screening_only if screening_only else _handle_full_pipeline
    return handler(urls=urls, run_id=run_id, config=config, summary=summary, state_items=dict(prev_state), dry_run=dry_run, continue_on_error=continue_on_error, llm_timeout=llm_timeout, no_classify=no_classify, thevc_mode=thevc_mode, min_completeness=min_completeness, allow_incomplete_company_info=allow_incomplete_company_info, resume=resume, no_prescreen=no_prescreen)


def main() -> None:
    args = build_cli_parser(DEFAULT_MIN_COMPLETENESS).parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING, format="%(name)s %(levelname)s: %(message)s")
    if args.notify_test:
        send_notification("🔔 JD Auto 알림 테스트\n테스트 메시지입니다.", load_config())
        return
    if args.max_retries != 1:
        print("ℹ️ 현재 버전은 --max-retries를 예약 옵션으로만 수용합니다.")
    execute_cli(args, run_auto_fn=run_auto, save_results_fn=save_results, print_summary_fn=print_final_summary)


if __name__ == "__main__":
    main()
