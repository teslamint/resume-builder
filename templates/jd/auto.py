#!/usr/bin/env python3
"""
JD Auto - Full automation: Search → Extract → Screen → Classify → Notify

Usage:
    python3 templates/jd/auto.py                    # Full pipeline
    python3 templates/jd/auto.py --search-only      # Search + extract only
    python3 templates/jd/auto.py --dry-run          # Preview without changes
    python3 templates/jd/auto.py --notify-test      # Test notification
"""

import argparse
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

try:
    from .search import run_search, load_config, JobPosting
    from .utils import (
        JOB_POSTINGS_DIR,
        SCREENING_DIR,
        find_existing_jd,
        is_duplicate,
    )
    from .company_validator import (
        parse_company_file,
        validate_company,
        ValidationResult,
        COMPANY_INFO_DIR,
    )
except ImportError:
    from search import run_search, load_config, JobPosting
    from utils import (
        JOB_POSTINGS_DIR,
        SCREENING_DIR,
        find_existing_jd,
        is_duplicate,
    )
    from company_validator import (
        parse_company_file,
        validate_company,
        ValidationResult,
        COMPANY_INFO_DIR,
    )

# Paths
BASE_DIR = Path(__file__).parent.parent.parent
RESULTS_DIR = BASE_DIR / "job_postings" / "auto_results"


def send_notification(message: str, config: dict) -> bool:
    """
    Send notification via configured channel.
    Uses Clawdbot's message tool if available.
    """
    notifications = config.get("notifications", {})
    channel = notifications.get("channel")
    
    if not channel:
        print("   ⚠️  알림 채널 미설정")
        return False
    
    # Try Clawdbot message command
    try:
        # Format for Clawdbot
        result = subprocess.run(
            ["clawdbot", "message", "--channel", channel, "--message", message],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            print(f"   ✅ 알림 전송 완료 ({channel})")
            return True
        else:
            print(f"   ⚠️  알림 전송 실패: {result.stderr}")
            return False
    except FileNotFoundError:
        print("   ⚠️  clawdbot 명령 없음 - 알림 스킵")
        return False
    except Exception as e:
        print(f"   ⚠️  알림 오류: {e}")
        return False


def format_notification(postings: List[dict], summary: dict) -> str:
    """Format notification message."""
    lines = [
        "🔔 **JD 자동 검색 결과**",
        f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        f"✨ 새 공고: {summary['new']}개",
        f"🟢 추천: {summary['recommended']}개",
        f"🟡 보류: {summary['hold']}개",
        f"🔴 패스: {summary['pass']}개",
        "",
    ]
    
    # Add recommended postings
    recommended = [p for p in postings if p.get("verdict") == "지원 추천"]
    if recommended:
        lines.append("**🟢 지원 추천 공고:**")
        for p in recommended[:5]:  # Limit to 5
            lines.append(f"• [{p['company']}] {p['title']}")
            lines.append(f"  {p['url']}")
        if len(recommended) > 5:
            lines.append(f"  ... 외 {len(recommended) - 5}개")
    
    return "\n".join(lines)


def check_company_info(company_name: str) -> Optional[dict]:
    """
    Check company info file and return validation results.
    Returns dict with completeness, risks, and warnings.
    """
    # Try to find company file (fuzzy match)
    company_slug = company_name.lower().replace(" ", "-").replace("(", "").replace(")", "")
    
    # Search for matching files
    matches = []
    for f in COMPANY_INFO_DIR.glob("*.md"):
        if f.name.startswith("_"):
            continue
        if company_slug in f.stem.lower() or company_name.lower() in f.stem.lower():
            matches.append(f)
    
    if not matches:
        return {
            "found": False,
            "message": f"⚠️ 기업정보 없음: {company_name}",
            "completeness": 0,
            "risks": [],
        }
    
    # Use first match
    file_path = matches[0]
    try:
        data = parse_company_file(file_path)
        result = validate_company(data, file_path)
        
        # Extract critical/high risks
        critical_risks = [f for f in result.risk_flags if f.severity in ("critical", "high")]
        
        return {
            "found": True,
            "file": file_path.name,
            "completeness": result.completeness_score,
            "risks": [
                {"code": r.code, "severity": r.severity, "message": r.message}
                for r in critical_risks
            ],
            "is_startup": data.is_startup,
            "incomplete_warning": result.completeness_score < 70,
        }
    except Exception as e:
        return {
            "found": True,
            "file": file_path.name,
            "error": str(e),
            "completeness": 0,
            "risks": [],
        }


def run_extraction(url: str, dry_run: bool = False) -> Optional[Path]:
    """
    Extract JD from URL using jd_pipeline.
    Returns path to extracted file or None.
    """
    if dry_run:
        print(f"   [DRY-RUN] Would extract: {url}")
        return None
    
    # Use existing pipeline for extraction (manual step for now)
    # This would integrate with /extract-job-posting skill
    print(f"   📥 추출 필요: {url}")
    return None


def run_screening(jd_path: Path, dry_run: bool = False) -> Optional[str]:
    """
    Run screening on JD file.
    Returns verdict or None.
    """
    if dry_run:
        print(f"   [DRY-RUN] Would screen: {jd_path.name}")
        return None
    
    # This would integrate with /jd-screening skill
    print(f"   🔍 스크리닝 필요: {jd_path.name}")
    return None


def save_results(postings: List[JobPosting], summary: dict) -> Path:
    """Save search results to file."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    result_file = RESULTS_DIR / f"search_{timestamp}.json"
    
    data = {
        "timestamp": datetime.now().isoformat(),
        "summary": summary,
        "postings": [
            {
                "job_id": p.job_id,
                "url": p.url,
                "title": p.title,
                "company": p.company,
                "experience": p.experience,
                "quick_filter": p.quick_filter_result,
            }
            for p in postings
        ],
    }
    
    with open(result_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    return result_file


def run_auto(
    dry_run: bool = False,
    search_only: bool = False,
    max_urls: Optional[int] = None,
) -> Tuple[List[JobPosting], dict]:
    """
    Run full automation pipeline.
    Returns (postings, summary).
    """
    config = load_config()
    
    print("=" * 60)
    print(f"🤖 JD Auto Pipeline - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)
    
    # Step 1: Search
    print("\n📍 Step 1: 검색")
    postings = run_search(dry_run=dry_run, max_urls=max_urls)
    
    summary = {
        "new": len(postings),
        "recommended": 0,
        "hold": 0,
        "pass": 0,
        "extracted": 0,
        "screened": 0,
    }
    
    if not postings:
        print("\n✅ 새로운 공고 없음")
        return postings, summary
    
    if search_only:
        print("\n🔍 검색만 모드 - 추출/스크리닝 스킵")
        if not dry_run:
            result_file = save_results(postings, summary)
            print(f"📁 결과 저장: {result_file}")
        return postings, summary
    
    # Step 2: Extract (for new postings)
    print("\n📍 Step 2: JD 추출")
    print("   ℹ️  추출은 수동 또는 Claude skill로 진행")
    # Find the latest search URL file
    unprocessed_dir = JOB_POSTINGS_DIR / "unprocessed"
    search_files = sorted(unprocessed_dir.glob("search_*.txt")) if unprocessed_dir.exists() else []
    if search_files:
        latest_file = search_files[-1]
        print("   다음 명령으로 추출:")
        print(f"   python3 templates/jd/pipeline.py --file {latest_file}")
    else:
        print("   ⚠️  추출할 URL 파일 없음")
    
    # Step 3: Screen (would be automated with LLM)
    print("\n📍 Step 3: 스크리닝")
    print("   ℹ️  스크리닝은 /jd-screening 스킬로 진행")
    
    # Save results
    if not dry_run:
        result_file = save_results(postings, summary)
        print(f"\n📁 결과 저장: {result_file}")
    
    # Step 4: Notify (if configured and has recommendations)
    notifications = config.get("notifications", {})
    if notifications.get("on_recommended") and summary["recommended"] > 0:
        print("\n📍 Step 4: 알림")
        message = format_notification(
            [{"title": p.title, "company": p.company, "url": p.url, "verdict": "지원 추천"} 
             for p in postings if p.quick_filter_result == "prefer"],
            summary
        )
        if not dry_run:
            send_notification(message, config)
    
    return postings, summary


def main():
    parser = argparse.ArgumentParser(description="JD Auto - 채용공고 자동화 파이프라인")
    parser.add_argument("--dry-run", action="store_true", help="미리보기 (저장 안 함)")
    parser.add_argument("--search-only", action="store_true", help="검색만 실행")
    parser.add_argument("--max-urls", type=int, help="최대 URL 수")
    parser.add_argument("--notify-test", action="store_true", help="알림 테스트")
    
    args = parser.parse_args()
    
    if args.notify_test:
        config = load_config()
        test_msg = "🔔 JD Auto 알림 테스트\n테스트 메시지입니다."
        send_notification(test_msg, config)
        return
    
    run_auto(
        dry_run=args.dry_run,
        search_only=args.search_only,
        max_urls=args.max_urls,
    )


if __name__ == "__main__":
    main()
