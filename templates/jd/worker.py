#!/usr/bin/env python3
"""
JD Worker - Background processor for queued job postings.

Processes items from queue.json:
- Extracts detailed JD information
- Runs screening (if configured)
- Updates queue status

Usage:
    python3 templates/jd/worker.py                    # Process all pending
    python3 templates/jd/worker.py --limit 5          # Process up to 5 items
    python3 templates/jd/worker.py --job-id 123456    # Process specific job
    python3 templates/jd/worker.py --status           # Show queue status
    python3 templates/jd/worker.py --clear-done       # Remove completed items
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import yaml

# Paths
BASE_DIR = Path(__file__).parent.parent.parent
JOB_POSTINGS_DIR = BASE_DIR / "private" / "job_postings"
UNPROCESSED_DIR = JOB_POSTINGS_DIR / "unprocessed"
CONFIG_PATH = JOB_POSTINGS_DIR / "search_config.yaml"

try:
    from .queue_utils import load_queue, save_queue, update_item_status, QUEUE_PATH
except ImportError:
    from queue_utils import load_queue, save_queue, update_item_status, QUEUE_PATH

logger = logging.getLogger(__name__)

# Constants
MAX_DESCRIPTION_LENGTH = 5000
MAX_REQUIREMENTS_LENGTH = 2000


def load_config() -> dict:
    """Load search configuration for timeouts."""
    if not CONFIG_PATH.exists():
        return {}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        logger.debug(f"Failed to load config: {e}")
        return {}


def extract_job_details(item: dict, context, config: dict) -> Optional[dict]:
    """
    Extract detailed job information from URL.
    Returns extracted data or None on failure.

    Args:
        item: Queue item with job info
        context: Playwright browser context (reused across calls)
        config: Configuration dict with timeout settings
    """
    url = item["url"]
    print(f"   📥 추출 중: {url}")

    execution = config.get("execution", {})
    page_timeout = execution.get("page_timeout", 30000)
    selector_timeout = execution.get("selector_timeout", 10000)

    page = None
    try:
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=page_timeout)
        page.wait_for_selector('[class*="JobDescription"]', timeout=selector_timeout)

        # Extract key information
        data = {
            "job_id": item["job_id"],
            "url": url,
            "title": item["title"],
            "company": item["company"],
            "extracted_at": datetime.now().isoformat(),
        }

        # Try to get job description text
        try:
            desc_elem = page.query_selector('[class*="JobDescription"]')
            if desc_elem:
                data["description"] = desc_elem.inner_text()[:MAX_DESCRIPTION_LENGTH]
        except Exception as e:
            logger.debug(f"Failed to extract description: {e}")

        # Try to get requirements
        try:
            req_elem = page.query_selector('[class*="Requirements"], [class*="Qualification"]')
            if req_elem:
                data["requirements"] = req_elem.inner_text()[:MAX_REQUIREMENTS_LENGTH]
        except Exception as e:
            logger.debug(f"Failed to extract requirements: {e}")

        return data

    except Exception as e:
        logger.debug(f"Job extraction failed for {item['job_id']}: {e}")
        print(f"   ❌ 추출 실패: {e}")
        return None
    finally:
        if page:
            try:
                page.close()
            except Exception:
                pass


def save_extracted_job(data: dict) -> Path:
    """Save extracted job data to file."""
    UNPROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    
    job_id = data["job_id"]
    filename = f"wanted_{job_id}.json"
    filepath = UNPROCESSED_DIR / filename
    
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    return filepath


def process_item(item: dict, context, config: dict) -> tuple[bool, str]:
    """
    Process a single queue item.
    Returns (success, message).

    Args:
        item: Queue item with job info
        context: Playwright browser context (reused)
        config: Configuration dict
    """
    job_id = item["job_id"]
    print(f"\n🔄 처리 중: [{job_id}] {item['title']}")
    print(f"   회사: {item['company']}")

    # Extract details
    data = extract_job_details(item, context, config)

    if data:
        filepath = save_extracted_job(data)
        print(f"   ✅ 저장: {filepath.name}")
        return True, str(filepath)
    else:
        return False, "extraction_failed"


def process_queue(
    limit: Optional[int] = None,
    job_id: Optional[str] = None,
) -> dict:
    """
    Process pending items in queue.
    Returns processing stats.

    Uses single browser instance for all items (performance optimization).
    """
    from playwright.sync_api import sync_playwright

    items, stats = load_queue(with_stats=True)

    if not items:
        print("📭 큐가 비어있습니다.")
        return {"processed": 0}

    # Filter items to process
    if job_id:
        pending = [i for i in items if i["job_id"] == job_id]
    else:
        pending = [i for i in items if i.get("status") == "pending"]

    if not pending:
        print("✅ 처리할 항목이 없습니다.")
        return {"processed": 0}

    if limit:
        pending = pending[:limit]

    print("=" * 60)
    print(f"🔧 JD Worker - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   처리 예정: {len(pending)}개")
    print("=" * 60)

    config = load_config()
    processed = 0
    succeeded = 0
    failed = 0

    # Single browser instance for all items
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )

        try:
            for item in pending:
                success, result = process_item(item, context, config)

                # Update item status atomically with file locking
                status = "done" if success else "failed"
                update_item_status(item["job_id"], status, result)

                processed += 1
                if success:
                    succeeded += 1
                else:
                    failed += 1

        finally:
            browser.close()

    print("\n" + "=" * 60)
    print(f"✅ 완료: {processed}개 처리")
    print(f"   성공: {succeeded}개")
    print(f"   실패: {failed}개")

    return {
        "processed": processed,
        "succeeded": succeeded,
        "failed": failed,
    }


def show_status():
    """Show queue status."""
    items, stats = load_queue(with_stats=True)
    
    pending = [i for i in items if i.get("status") == "pending"]
    done = [i for i in items if i.get("status") == "done"]
    failed = [i for i in items if i.get("status") == "failed"]
    
    print("=" * 60)
    print("📊 Queue Status")
    print("=" * 60)
    print(f"   총 항목: {len(items)}개")
    print(f"   대기: {len(pending)}개")
    print(f"   완료: {len(done)}개")
    print(f"   실패: {len(failed)}개")
    
    if stats:
        print(f"\n📈 마지막 검색:")
        print(f"   총 발견: {stats.get('total_found', 'N/A')}개")
        print(f"   새 공고: {stats.get('new', 'N/A')}개")
        print(f"   소요시간: {stats.get('elapsed_seconds', 'N/A')}초")
    
    if pending:
        print(f"\n📋 대기 중 ({len(pending)}개):")
        for item in pending[:10]:
            print(f"   • [{item['job_id']}] {item['title']}")
            print(f"     {item['company']} | {item.get('experience', '')}")
        if len(pending) > 10:
            print(f"   ... 외 {len(pending) - 10}개")
    
    if failed:
        print(f"\n❌ 실패 ({len(failed)}개):")
        for item in failed[:5]:
            print(f"   • [{item['job_id']}] {item['title']} - {item.get('result', 'unknown')}")


def clear_done():
    """Remove completed items from queue."""
    items, stats = load_queue(with_stats=True)
    
    before = len(items)
    items = [i for i in items if i.get("status") != "done"]
    after = len(items)
    
    save_queue(items, stats)
    print(f"🧹 {before - after}개 완료 항목 제거")
    print(f"   남은 항목: {after}개")


def main():
    parser = argparse.ArgumentParser(description="JD Worker - 큐 처리기")
    parser.add_argument("--limit", type=int, help="최대 처리 개수")
    parser.add_argument("--job-id", type=str, help="특정 job ID만 처리")
    parser.add_argument("--status", action="store_true", help="큐 상태 확인")
    parser.add_argument("--clear-done", action="store_true", help="완료 항목 제거")
    
    args = parser.parse_args()
    
    if args.status:
        show_status()
        return
    
    if args.clear_done:
        clear_done()
        return
    
    result = process_queue(limit=args.limit, job_id=args.job_id)
    
    # Exit code based on results
    if result.get("failed", 0) > result.get("processed", 0) / 2:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
