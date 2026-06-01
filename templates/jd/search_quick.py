#!/usr/bin/env python3
"""
JD Search Quick - Fast job posting discovery with single browser instance.

Optimized for cron execution:
- Single browser instance for all queries
- Minimal processing (URL collection only)
- Outputs to queue.json for worker processing

Usage:
    python3 templates/jd/search_quick.py              # Run search, update queue
    python3 templates/jd/search_quick.py --dry-run    # Preview without saving
    python3 templates/jd/search_quick.py --status     # Show queue status
"""

import argparse
import json
import logging
import re
import sys
import time
from datetime import datetime
from typing import List, Set
from urllib.parse import quote, urljoin

try:
    from .constants import CONFIG_PATH, JOB_POSTINGS_DIR
    from .experience_filter import filter_experience
    from .groupby_client import GroupByAPIError, fetch_positions as groupby_fetch_positions
    from .jd_content import get_rejected_companies, is_rejected_company, parse_remember_experience
    from .path_utils import is_duplicate
    from .queue_utils import QUEUE_PATH, QueueItem, QueueStatus, load_queue, save_queue
    from .search_helpers import (
        SearchPageConfig,
        _read_search_config,
        convert_groupby_to_raw_results,
        filter_and_dedup,
        groupby_experience_values,
        quick_filter_title as _filter_title_full,
        load_and_scrape_wanted,
        load_and_scrape_remember,
    )
except ImportError:
    from constants import CONFIG_PATH, JOB_POSTINGS_DIR
    from experience_filter import filter_experience
    from groupby_client import GroupByAPIError, fetch_positions as groupby_fetch_positions
    from jd_content import get_rejected_companies, is_rejected_company, parse_remember_experience
    from path_utils import is_duplicate
    from queue_utils import QUEUE_PATH, QueueItem, QueueStatus, load_queue, save_queue
    from search_helpers import (
        SearchPageConfig,
        _read_search_config,
        convert_groupby_to_raw_results,
        filter_and_dedup,
        groupby_experience_values,
        quick_filter_title as _filter_title_full,
        load_and_scrape_wanted,
        load_and_scrape_remember,
    )

logger = logging.getLogger(__name__)

# Paths
STATE_PATH = JOB_POSTINGS_DIR / ".search_state.json"


def load_config() -> dict:
    """Load search configuration."""
    result = _read_search_config(CONFIG_PATH)
    if result is None:
        return {"search_queries": ["백엔드 시니어"]}
    return result


def load_seen_ids() -> Set[str]:
    """Load seen job IDs from state file."""
    if not STATE_PATH.exists():
        return set()
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return set(data.get("seen_job_ids", []))
    except Exception as e:
        logger.debug(f"Failed to load seen_ids: {e}")
        return set()


def save_seen_ids(seen_ids: Set[str]) -> None:
    """Save seen job IDs to state file."""
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    # Load existing state
    state = {}
    if STATE_PATH.exists():
        try:
            with open(STATE_PATH, "r", encoding="utf-8") as f:
                state = json.load(f)
        except Exception as e:
            logger.debug(f"Failed to load state for update: {e}")
    
    state["seen_job_ids"] = list(seen_ids)
    state["last_run"] = datetime.now().isoformat()
    
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def quick_filter_title(title: str, config: dict) -> bool:
    """Quick filter — returns True if should be skipped."""
    return _filter_title_full(title, config) == "pass"


def run_quick_search(dry_run: bool = False) -> tuple[List[QueueItem], dict]:
    """
    Run fast search across all queries with single browser.
    Returns (new_items, stats).
    """
    try:
        from .browser_utils import sync_playwright
    except ImportError:
        from browser_utils import sync_playwright

    config = load_config()
    queries = config.get("search_queries", ["백엔드 시니어"])

    platforms_config = config.get("platforms", {})
    wanted_enabled = platforms_config.get("wanted", {}).get("enabled", True)
    remember_enabled = platforms_config.get("remember", {}).get("enabled", False)
    groupby_enabled = platforms_config.get("groupby", {}).get("enabled", False)

    wanted_base_url = platforms_config.get("wanted", {}).get("base_url", "https://www.wanted.co.kr")
    remember_base_url = platforms_config.get("remember", {}).get("base_url", "https://career.rememberapp.co.kr")

    execution = config.get("execution", {})
    scroll_count = execution.get("scroll_count", 2)
    request_delay = execution.get("request_delay", 1)

    # Load rejected companies
    rejected_companies = get_rejected_companies()
    config_excludes = config.get("quick_filters", {}).get("company_exclude", [])

    # Load existing data
    seen_ids = load_seen_ids()
    existing_queue = load_queue()
    queued_ids = {item["job_id"] for item in existing_queue if item.get("status") == QueueStatus.PENDING}

    new_items: List[QueueItem] = []
    stats = {
        "queries": len(queries),
        "total_found": 0,
        "new": 0,
        "duplicates": 0,
        "filtered": 0,
        "errors": 0,
    }

    enabled_names = []
    if wanted_enabled:
        enabled_names.append("Wanted")
    if remember_enabled:
        enabled_names.append("Remember")
    if groupby_enabled:
        enabled_names.append("GroupBy")

    print("=" * 60)
    print(f"🚀 JD Quick Search - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   Queries: {len(queries)} | Platforms: {', '.join(enabled_names)}")
    print("=" * 60)

    start_time = time.time()

    # Merge seen_ids + queued_ids for unified dedup
    combined_seen = seen_ids | queued_ids

    def _collect_accepted(fr, query: str, platform: str = "wanted") -> int:
        """Convert FilterResult accepted items to QueueItems, return count."""
        count = 0
        for raw in fr.accepted:
            new_items.append(QueueItem(
                job_id=raw.canonical_id,
                url=raw.url,
                title=raw.title,
                company=raw.company,
                experience=raw.experience,
                query=query,
                platform=platform,
                discovered_at=datetime.now().isoformat(),
            ))
            queued_ids.add(raw.canonical_id)
            count += 1
        return count

    # --- GroupBy prefetch (API-based, no browser needed) ---
    if groupby_enabled:
        groupby_cfg = platforms_config.get("groupby", {})
        position_types = groupby_cfg.get("position_types", [2])
        base_url = groupby_cfg.get("base_url", "https://groupby.kr")
        print(f"\n🔍 검색 (GroupBy): positionTypes={position_types}")

        try:
            gb_items = groupby_fetch_positions(position_types)
            gb_outcome = convert_groupby_to_raw_results(gb_items, base_url)

            # Pre-filter GroupBy experience with API min/max values; text-only platforms use the common parser.
            exp_filtered = []
            gb_exp_dropped = 0
            for raw in gb_outcome.results:
                orig_item = next((it for it in gb_items if f"groupby-{it['id']}" == raw.canonical_id), None)
                if orig_item:
                    exp_min, exp_max = groupby_experience_values(orig_item)
                    if filter_experience(raw.experience, config, min_years=exp_min, max_years=exp_max):
                        gb_exp_dropped += 1
                        continue
                elif filter_experience(raw.experience, config):
                    gb_exp_dropped += 1
                    continue
                exp_filtered.append(raw)

            fr = filter_and_dedup(
                exp_filtered, config=config, seen_ids=combined_seen,
                rejected_companies=rejected_companies, config_excludes=config_excludes,
            )
            gb_new = _collect_accepted(fr, "(groupby)", "groupby")

            stats["total_found"] += fr.total_found + gb_exp_dropped
            stats["new"] += gb_new
            stats["duplicates"] += fr.duplicates
            stats["filtered"] += fr.filtered_out + gb_exp_dropped
            print(f"   📊 결과: 발견 {fr.total_found + gb_exp_dropped}개, 신규 {gb_new}개, 중복 {fr.duplicates}개, 필터 {fr.filtered_out + gb_exp_dropped}개")
        except GroupByAPIError as e:
            logger.warning("GroupBy API error: %s", e)
            print(f"   ⚠️  GroupBy API 오류: {e}")
            stats["errors"] += 1

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )

        try:
            for query in queries:
                # --- Wanted search ---
                if wanted_enabled:
                    search_url = f"{wanted_base_url}/search?query={quote(query)}&tab=position"
                    print(f"\n🔍 검색 (Wanted): {query}")

                    page = context.new_page()
                    try:
                        wanted_cfg = SearchPageConfig(
                            base_url=wanted_base_url, timeout_ms=8000,
                            post_load_delay=request_delay, scroll_count=scroll_count,
                            scroll_sleep=0.5,
                        )
                        outcome = load_and_scrape_wanted(page, search_url, wanted_cfg)

                        if outcome.timed_out:
                            print(f"   📊 결과: 0개 (타임아웃)")
                            stats["errors"] += 1
                        elif outcome.no_results:
                            print(f"   📊 결과: 0개 (검색 결과 없음)")
                        else:
                            if outcome.error:
                                print(f"   ⚠️  Partial error: {outcome.error}")
                                stats["errors"] += 1
                            fr = filter_and_dedup(
                                outcome.results, config=config, seen_ids=combined_seen,
                                rejected_companies=rejected_companies, config_excludes=config_excludes,
                            )
                            q_new = _collect_accepted(fr, query)
                            stats["total_found"] += fr.total_found
                            stats["new"] += q_new
                            stats["duplicates"] += fr.duplicates
                            stats["filtered"] += fr.filtered_out
                            print(f"   📊 결과: {fr.total_found}개 (새: {q_new}, 중복: {fr.duplicates}, 필터: {fr.filtered_out})")
                    except Exception as e:
                        print(f"   ❌ Error: {e}")
                        stats["errors"] += 1
                    finally:
                        page.close()

                # --- Remember search ---
                if remember_enabled:
                    search_params = json.dumps({
                        "includeAppliedJobPosting": False,
                        "leaderPosition": False,
                        "organizationType": "all",
                        "applicationType": "all",
                        "keywords": [query],
                    }, ensure_ascii=False)
                    search_url = f"{remember_base_url}/job/postings?search={quote(search_params)}"
                    print(f"\n🔍 검색 (Remember): {query}")

                    page = context.new_page()
                    try:
                        remember_cfg = SearchPageConfig(
                            base_url=remember_base_url, timeout_ms=8000,
                            post_load_delay=request_delay, scroll_count=scroll_count,
                            scroll_sleep=0.5,
                        )
                        outcome = load_and_scrape_remember(page, search_url, remember_cfg)

                        if outcome.timed_out:
                            print(f"   📊 결과: 0개 (타임아웃)")
                            stats["errors"] += 1
                        elif outcome.no_results:
                            print(f"   📊 결과: 0개 (검색 결과 없음)")
                        else:
                            if outcome.error:
                                print(f"   ⚠️  Partial error: {outcome.error}")
                                stats["errors"] += 1
                            fr = filter_and_dedup(
                                outcome.results, config=config, seen_ids=combined_seen,
                                rejected_companies=rejected_companies, config_excludes=config_excludes,
                            )
                            q_new = _collect_accepted(fr, query, "remember")
                            stats["total_found"] += fr.total_found
                            stats["new"] += q_new
                            stats["duplicates"] += fr.duplicates
                            stats["filtered"] += fr.filtered_out
                            print(f"   📊 결과: {fr.total_found}개 (새: {q_new}, 중복: {fr.duplicates}, 필터: {fr.filtered_out})")
                    except Exception as e:
                        print(f"   ❌ Error: {e}")
                        stats["errors"] += 1
                    finally:
                        page.close()

        finally:
            browser.close()

    # Sync combined_seen back to seen_ids (filter_and_dedup mutated combined_seen)
    seen_ids.update(combined_seen)
    
    elapsed = time.time() - start_time
    stats["elapsed_seconds"] = round(elapsed, 1)
    
    print("\n" + "=" * 60)
    print(f"✅ 완료: {elapsed:.1f}초")
    print(f"   총 발견: {stats['total_found']}개")
    print(f"   새 공고: {stats['new']}개")
    print(f"   중복: {stats['duplicates']}개")
    print(f"   필터링: {stats['filtered']}개")
    
    if not dry_run:
        # Save state
        save_seen_ids(seen_ids)
        
        # Add new items to queue
        all_items = existing_queue + [item.to_dict() for item in new_items]
        save_queue(all_items, stats)
        print(f"\n📁 큐 저장: {QUEUE_PATH}")
        print(f"   대기 중: {len([i for i in all_items if i.get('status') == QueueStatus.PENDING])}개")
    
    if new_items:
        print(f"\n📋 새로 발견된 공고:")
        for item in new_items[:10]:
            print(f"   • [{item.job_id}] {item.title}")
            print(f"     {item.company} | {item.experience}")
        if len(new_items) > 10:
            print(f"   ... 외 {len(new_items) - 10}개")
    
    return new_items, stats


def show_status():
    """Show queue status."""
    queue = load_queue()
    
    pending = [i for i in queue if i.get("status") == QueueStatus.PENDING]
    done = [i for i in queue if i.get("status") == QueueStatus.DONE]
    failed = [i for i in queue if i.get("status") == QueueStatus.FAILED]
    
    print("📊 Queue Status")
    print(f"   대기: {len(pending)}개")
    print(f"   완료: {len(done)}개")
    print(f"   실패: {len(failed)}개")
    
    if pending:
        print("\n📋 대기 중인 공고:")
        for item in pending[:5]:
            print(f"   • [{item['job_id']}] {item['title']} - {item['company']}")
        if len(pending) > 5:
            print(f"   ... 외 {len(pending) - 5}개")


def main():
    parser = argparse.ArgumentParser(description="JD Quick Search - 빠른 채용공고 검색")
    parser.add_argument("--dry-run", action="store_true", help="미리보기 (저장 안 함)")
    parser.add_argument("--status", action="store_true", help="큐 상태 확인")
    
    args = parser.parse_args()
    
    if args.status:
        show_status()
        return
    
    new_items, stats = run_quick_search(dry_run=args.dry_run)
    
    # Return exit code based on results (for cron integration)
    if stats.get("errors", 0) > stats.get("queries", 1) / 2:
        sys.exit(1)  # Too many errors
    sys.exit(0)


if __name__ == "__main__":
    main()
