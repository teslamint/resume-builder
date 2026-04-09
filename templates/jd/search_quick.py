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
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import List, Set
from urllib.parse import quote, urljoin

import yaml

# Paths
BASE_DIR = Path(__file__).parent.parent.parent
CONFIG_PATH = BASE_DIR / "private" / "job_postings" / "search_config.yaml"
STATE_PATH = BASE_DIR / "private" / "job_postings" / ".search_state.json"

try:
    from .jd_content import get_rejected_companies, is_rejected_company, parse_remember_experience
    from .path_utils import is_duplicate
    from .queue_utils import QUEUE_PATH, QueueItem, load_queue, save_queue
    from .search_helpers import SearchPageConfig, load_and_scrape_wanted, load_and_scrape_remember
except ImportError:
    from jd_content import get_rejected_companies, is_rejected_company, parse_remember_experience
    from path_utils import is_duplicate
    from queue_utils import QUEUE_PATH, QueueItem, load_queue, save_queue
    from search_helpers import SearchPageConfig, load_and_scrape_wanted, load_and_scrape_remember

logger = logging.getLogger(__name__)


def load_config() -> dict:
    """Load search configuration."""
    if not CONFIG_PATH.exists():
        return {"search_queries": ["백엔드 시니어"]}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


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
    """
    Quick filter - returns True if should be skipped.
    """
    filters = config.get("quick_filters", {})
    title_lower = title.lower()

    for keyword in filters.get("title_exclude", []):
        if keyword.lower() in title_lower:
            return True

    include_keywords = filters.get("title_include", [])
    if include_keywords:
        if not any(kw.lower() in title_lower for kw in include_keywords):
            return True

    return False


def parse_experience_range(exp_str: str) -> tuple[int | None, int | None]:
    """
    Parse experience string like "경력 5-10년" or "경력 3년↑"
    Returns (min_years, max_years). None means no limit.
    """
    import re
    
    if not exp_str:
        return None, None
    
    # "경력 5-10년" or "5-10년"
    range_match = re.search(r'(\d+)\s*[-~]\s*(\d+)\s*년', exp_str)
    if range_match:
        return int(range_match.group(1)), int(range_match.group(2))
    
    # "경력 3년↑" or "3년 이상"
    min_match = re.search(r'(\d+)\s*년\s*[↑이상]', exp_str)
    if min_match:
        return int(min_match.group(1)), None
    
    # "경력 3년" (exact)
    exact_match = re.search(r'(\d+)\s*년', exp_str)
    if exact_match:
        years = int(exact_match.group(1))
        return years, years
    
    return None, None


def filter_experience(exp_str: str, config: dict) -> bool:
    """
    Filter by experience range - returns True if should be skipped.
    
    Config options:
      filters.min_experience_upper: minimum upper limit (e.g., 10 means skip if max < 10)
      filters.my_experience: my years of experience
    """
    filters = config.get("filters", {})
    min_upper = filters.get("min_experience_upper", 10)  # 경력 상한 최소값
    
    min_years, max_years = parse_experience_range(exp_str)
    
    # 상한이 있고 그 상한이 min_upper보다 작으면 스킵
    if max_years is not None and max_years < min_upper:
        return True
    
    return False



def run_quick_search(dry_run: bool = False) -> tuple[List[QueueItem], dict]:
    """
    Run fast search across all queries with single browser.
    Returns (new_items, stats).
    """
    from playwright.sync_api import sync_playwright

    config = load_config()
    queries = config.get("search_queries", ["백엔드 시니어"])

    platforms_config = config.get("platforms", {})
    wanted_enabled = platforms_config.get("wanted", {}).get("enabled", True)
    remember_enabled = platforms_config.get("remember", {}).get("enabled", False)

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
    queued_ids = {item["job_id"] for item in existing_queue if item.get("status") == "pending"}

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

    print("=" * 60)
    print(f"🚀 JD Quick Search - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   Queries: {len(queries)} | Platforms: {', '.join(enabled_names)}")
    print("=" * 60)

    start_time = time.time()

    with sync_playwright() as p:
        # Single browser instance for all queries
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
                    query_found = 0
                    query_new = 0
                    query_dup = 0
                    query_filtered = 0

                    try:
                        wanted_config = SearchPageConfig(
                            base_url=wanted_base_url,
                            timeout_ms=8000,
                            post_load_delay=request_delay,
                            scroll_count=scroll_count,
                            scroll_sleep=0.5,
                        )
                        outcome = load_and_scrape_wanted(page, search_url, wanted_config)

                        if outcome.timed_out:
                            print(f"   📊 결과: 0개 (타임아웃)")
                            stats["errors"] += 1
                        elif outcome.no_results:
                            print(f"   📊 결과: 0개 (검색 결과 없음)")
                        else:
                            if outcome.error:
                                print(f"   ⚠️  Partial error: {outcome.error}")
                                stats["errors"] += 1
                            for raw in outcome.results:
                                query_found += 1

                                if quick_filter_title(raw.title, config):
                                    query_filtered += 1
                                    continue

                                if is_rejected_company(raw.company, rejected_companies, config_excludes):
                                    query_filtered += 1
                                    continue

                                if filter_experience(raw.experience, config):
                                    query_filtered += 1
                                    continue

                                if raw.canonical_id in seen_ids or raw.canonical_id in queued_ids:
                                    query_dup += 1
                                    continue

                                is_dup, _ = is_duplicate(raw.canonical_id)
                                if is_dup:
                                    query_dup += 1
                                    seen_ids.add(raw.canonical_id)
                                    continue

                                item = QueueItem(
                                    job_id=raw.canonical_id,
                                    url=raw.url,
                                    title=raw.title,
                                    company=raw.company,
                                    experience=raw.experience,
                                    query=query,
                                    discovered_at=datetime.now().isoformat(),
                                )
                                new_items.append(item)
                                seen_ids.add(raw.canonical_id)
                                queued_ids.add(raw.canonical_id)
                                query_new += 1

                            print(f"   📊 결과: {query_found}개 (새: {query_new}, 중복: {query_dup}, 필터: {query_filtered})")

                    except Exception as e:
                        print(f"   ❌ Error: {e}")
                        stats["errors"] += 1
                    finally:
                        page.close()

                    stats["total_found"] += query_found
                    stats["new"] += query_new
                    stats["duplicates"] += query_dup
                    stats["filtered"] += query_filtered

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
                    query_found = 0
                    query_new = 0
                    query_dup = 0
                    query_filtered = 0

                    try:
                        remember_config = SearchPageConfig(
                            base_url=remember_base_url,
                            timeout_ms=8000,
                            post_load_delay=request_delay,
                            scroll_count=scroll_count,
                            scroll_sleep=0.5,
                        )
                        outcome = load_and_scrape_remember(page, search_url, remember_config)

                        if outcome.timed_out:
                            print(f"   📊 결과: 0개 (타임아웃)")
                            stats["errors"] += 1
                        elif outcome.no_results:
                            print(f"   📊 결과: 0개 (검색 결과 없음)")
                        else:
                            if outcome.error:
                                print(f"   ⚠️  Partial error: {outcome.error}")
                                stats["errors"] += 1
                            for raw in outcome.results:
                                query_found += 1

                                if quick_filter_title(raw.title, config):
                                    query_filtered += 1
                                    continue

                                if is_rejected_company(raw.company, rejected_companies, config_excludes):
                                    query_filtered += 1
                                    continue

                                if filter_experience(raw.experience, config):
                                    query_filtered += 1
                                    continue

                                dup_keys = raw.duplicate_keys()
                                if any(k in seen_ids or k in queued_ids for k in dup_keys):
                                    query_dup += 1
                                    continue

                                is_dup, _ = is_duplicate(raw.canonical_id)
                                if is_dup:
                                    query_dup += 1
                                    seen_ids.add(raw.canonical_id)
                                    continue
                                is_dup, _ = is_duplicate(raw.raw_id)
                                if is_dup:
                                    query_dup += 1
                                    seen_ids.add(raw.canonical_id)
                                    continue

                                item = QueueItem(
                                    job_id=raw.canonical_id,
                                    url=raw.url,
                                    title=raw.title,
                                    company=raw.company,
                                    experience=raw.experience,
                                    query=query,
                                    discovered_at=datetime.now().isoformat(),
                                    platform="remember",
                                )
                                new_items.append(item)
                                seen_ids.add(raw.canonical_id)
                                queued_ids.add(raw.canonical_id)
                                query_new += 1

                            print(f"   📊 결과: {query_found}개 (새: {query_new}, 중복: {query_dup}, 필터: {query_filtered})")

                    except Exception as e:
                        print(f"   ❌ Error: {e}")
                        stats["errors"] += 1
                    finally:
                        page.close()

                    stats["total_found"] += query_found
                    stats["new"] += query_new
                    stats["duplicates"] += query_dup
                    stats["filtered"] += query_filtered

        finally:
            browser.close()
    
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
        all_items = existing_queue + [asdict(item) for item in new_items]
        save_queue(all_items, stats)
        print(f"\n📁 큐 저장: {QUEUE_PATH}")
        print(f"   대기 중: {len([i for i in all_items if i.get('status') == 'pending'])}개")
    
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
    
    pending = [i for i in queue if i.get("status") == "pending"]
    done = [i for i in queue if i.get("status") == "done"]
    failed = [i for i in queue if i.get("status") == "failed"]
    
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
