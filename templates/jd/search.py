#!/usr/bin/env python3
"""
JD Search - Automated job posting search and discovery.

Usage:
    python3 templates/jd/search.py                    # Run full search
    python3 templates/jd/search.py --query "백엔드"   # Single query search
    python3 templates/jd/search.py --dry-run          # Preview without processing
    python3 templates/jd/search.py --status           # Show search state
"""

import argparse
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Set
from urllib.parse import quote, urljoin

import yaml

try:
    from .utils import is_duplicate, extract_job_id, JOB_POSTINGS_DIR, get_rejected_companies, is_rejected_company
    from .company_validator import parse_company_file, validate_company, COMPANY_INFO_DIR
except ImportError:
    from utils import is_duplicate, extract_job_id, JOB_POSTINGS_DIR, get_rejected_companies, is_rejected_company
    from company_validator import parse_company_file, validate_company, COMPANY_INFO_DIR

# Paths
BASE_DIR = Path(__file__).parent.parent.parent
CONFIG_PATH = BASE_DIR / "job_postings" / "search_config.yaml"
STATE_PATH = BASE_DIR / "job_postings" / ".search_state.json"


@dataclass
class JobPosting:
    """Represents a discovered job posting."""
    job_id: str
    url: str
    title: str
    company: str
    experience: str
    is_new: bool = True
    quick_filter_result: Optional[str] = None  # 'pass', 'prefer', None


@dataclass
class SearchResult:
    """Result of a search operation."""
    query: str
    total_found: int
    new_postings: List[JobPosting] = field(default_factory=list)
    duplicates: int = 0
    filtered_out: int = 0


@dataclass
class SearchState:
    """Persistent search state."""
    last_run: Optional[str] = None
    seen_job_ids: Set[str] = field(default_factory=set)
    total_searches: int = 0
    total_new_found: int = 0

    def to_dict(self) -> dict:
        return {
            "last_run": self.last_run,
            "seen_job_ids": list(self.seen_job_ids),
            "total_searches": self.total_searches,
            "total_new_found": self.total_new_found,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SearchState":
        return cls(
            last_run=data.get("last_run"),
            seen_job_ids=set(data.get("seen_job_ids", [])),
            total_searches=data.get("total_searches", 0),
            total_new_found=data.get("total_new_found", 0),
        )


def load_config() -> dict:
    """Load search configuration."""
    if not CONFIG_PATH.exists():
        print(f"⚠️  Config not found: {CONFIG_PATH}")
        return {}
    
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_state() -> SearchState:
    """Load persistent search state."""
    if not STATE_PATH.exists():
        return SearchState()
    
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return SearchState.from_dict(data)
    except Exception as e:
        print(f"⚠️  Error loading state: {e}")
        return SearchState()


def save_state(state: SearchState) -> None:
    """Save search state."""
    state.last_run = datetime.now().isoformat()
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state.to_dict(), f, indent=2, ensure_ascii=False)


def check_company_risks(company_name: str) -> Optional[dict]:
    """
    Check company info and return risk summary.
    Returns dict with completeness and risks, or None if not found.
    """
    # Normalize company name for matching
    company_lower = company_name.lower().strip()
    
    # Search for matching files
    for f in COMPANY_INFO_DIR.glob("*.md"):
        if f.name.startswith("_"):
            continue
        
        # Check if company name is in filename or file content
        if company_lower in f.stem.lower():
            try:
                data = parse_company_file(f)
                result = validate_company(data, f)
                
                critical_risks = [r for r in result.risk_flags if r.severity in ("critical", "high")]
                
                return {
                    "file": f.name,
                    "completeness": result.completeness_score,
                    "risks": critical_risks,
                    "incomplete": result.completeness_score < 70,
                }
            except Exception:
                return None
    
    return None


def quick_filter_title(title: str, config: dict) -> Optional[str]:
    """
    Quick filter based on title keywords.
    Returns: 'pass' (skip), 'prefer' (prioritize), None (neutral)
    """
    filters = config.get("quick_filters", {})
    title_lower = title.lower()

    # 1. Exclude 최우선
    for keyword in filters.get("title_exclude", []):
        if keyword.lower() in title_lower:
            return "pass"

    # 2. Include 게이트 (비어있지 않으면 하나 이상 매칭 필요)
    include_keywords = filters.get("title_include", [])
    if include_keywords:
        if not any(kw.lower() in title_lower for kw in include_keywords):
            return "pass"

    # 3. Prefer 우선 마킹
    for keyword in filters.get("title_prefer", []):
        if keyword.lower() in title_lower:
            return "prefer"

    return None


def search_wanted(query: str, config: dict, state: SearchState) -> SearchResult:
    """
    Search Wanted for job postings.
    Uses Playwright for browser automation.
    """
    from playwright.sync_api import sync_playwright
    
    result = SearchResult(query=query, total_found=0)
    rejected_companies = get_rejected_companies()
    config_excludes = config.get("quick_filters", {}).get("company_exclude", [])
    base_url = config.get("platforms", {}).get("wanted", {}).get("base_url", "https://www.wanted.co.kr")
    search_url = f"{base_url}/search?query={quote(query)}&tab=position"
    
    execution = config.get("execution", {})
    scroll_count = execution.get("scroll_count", 3)
    request_delay = execution.get("request_delay", 2)
    
    print(f"\n🔍 검색 중: {query}")
    print(f"   URL: {search_url}")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        page = context.new_page()
        
        try:
            page.goto(search_url, wait_until="domcontentloaded", timeout=30000)

            has_results = page.locator('a[href*="/wd/"]')
            no_results = page.locator('text=검색 결과가 없습니다').or_(
                page.locator('[class*="EmptyContent"]')
            ).or_(page.locator('text=일치하는 결과가 없'))

            try:
                has_results.first.or_(no_results.first).wait_for(state="attached", timeout=15000)
            except Exception:
                print(f"   📊 결과: 0개 (타임아웃)")
                browser.close()
                return result

            if no_results.count() > 0 or has_results.count() == 0:
                print(f"   📊 결과: 0개 (검색 결과 없음)")
                browser.close()
                return result

            time.sleep(request_delay + 2)
            
            # Scroll to load more results
            for i in range(scroll_count):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(1)
            
            # Extract job listings
            # Selector: links containing /wd/{id} pattern
            job_links = page.query_selector_all('a[href*="/wd/"]')
            
            seen_ids = set()
            for link in job_links:
                try:
                    href = link.get_attribute("href")
                    if not href or "/wd/" not in href:
                        continue
                    
                    # Extract job ID
                    match = re.search(r"/wd/(\d+)", href)
                    if not match:
                        continue
                    
                    job_id = match.group(1)
                    if job_id in seen_ids:
                        continue
                    seen_ids.add(job_id)
                    
                    # Get text content
                    text = link.inner_text()
                    lines = [l.strip() for l in text.split("\n") if l.strip()]
                    
                    if len(lines) < 2:
                        continue
                    
                    title = lines[0]
                    company = lines[1] if len(lines) > 1 else "Unknown"
                    experience = lines[2] if len(lines) > 2 else ""
                    
                    result.total_found += 1
                    
                    # Quick filter
                    filter_result = quick_filter_title(title, config)
                    if filter_result == "pass":
                        result.filtered_out += 1
                        continue

                    # Company filter - skip rejected companies
                    if is_rejected_company(company, rejected_companies, config_excludes):
                        result.filtered_out += 1
                        continue

                    # Check if already seen in this session's state
                    if job_id in state.seen_job_ids:
                        result.duplicates += 1
                        continue
                    
                    # Check if already exists in job_postings
                    is_dup, existing_path = is_duplicate(job_id)
                    if is_dup:
                        result.duplicates += 1
                        state.seen_job_ids.add(job_id)
                        continue
                    
                    # New posting found
                    full_url = urljoin(base_url, href)
                    posting = JobPosting(
                        job_id=job_id,
                        url=full_url,
                        title=title,
                        company=company,
                        experience=experience,
                        is_new=True,
                        quick_filter_result=filter_result,
                    )
                    result.new_postings.append(posting)
                    state.seen_job_ids.add(job_id)
                    
                except Exception as e:
                    continue
            
        except Exception as e:
            print(f"   ❌ Error: {e}")
        finally:
            browser.close()
    
    return result


def run_search(
    queries: Optional[List[str]] = None,
    dry_run: bool = False,
    max_urls: Optional[int] = None,
) -> List[JobPosting]:
    """
    Run job search with configured queries.
    Returns list of new job postings found.
    """
    config = load_config()
    state = load_state()
    
    if not queries:
        queries = config.get("search_queries", ["백엔드 시니어"])
    
    if max_urls is None:
        max_urls = config.get("execution", {}).get("max_urls_per_run", 20)
    
    all_new_postings: List[JobPosting] = []
    total_found = 0
    total_duplicates = 0
    total_filtered = 0
    
    print("=" * 60)
    print(f"🚀 JD Search 시작 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"   검색 키워드: {len(queries)}개")
    print(f"   최대 처리: {max_urls}개")
    print("=" * 60)
    
    for query in queries:
        if len(all_new_postings) >= max_urls:
            print(f"\n⚠️  최대 URL 수 도달 ({max_urls}), 검색 중단")
            break
        
        result = search_wanted(query, config, state)
        total_found += result.total_found
        total_duplicates += result.duplicates
        total_filtered += result.filtered_out
        
        # Add new postings (up to limit)
        remaining = max_urls - len(all_new_postings)
        new_to_add = result.new_postings[:remaining]
        all_new_postings.extend(new_to_add)
        
        # Print result summary
        print(f"   📊 결과: 총 {result.total_found}개 발견")
        print(f"      - 새 공고: {len(result.new_postings)}개")
        print(f"      - 중복: {result.duplicates}개")
        print(f"      - 필터링: {result.filtered_out}개")
        
        # Rate limiting
        time.sleep(config.get("execution", {}).get("request_delay", 2))
    
    # Summary
    print("\n" + "=" * 60)
    print("📈 검색 완료 요약")
    print("=" * 60)
    print(f"   총 발견: {total_found}개")
    print(f"   새 공고: {len(all_new_postings)}개")
    print(f"   중복 스킵: {total_duplicates}개")
    print(f"   필터링: {total_filtered}개")
    
    # List new postings with company risk check
    if all_new_postings:
        print("\n📋 새로 발견된 공고:")
        companies_with_risks = []
        companies_incomplete = []
        companies_missing = []
        
        for i, posting in enumerate(all_new_postings, 1):
            priority = "⭐" if posting.quick_filter_result == "prefer" else "  "
            print(f"   {priority} {i}. [{posting.job_id}] {posting.title}")
            print(f"       {posting.company} | {posting.experience}")
            print(f"       {posting.url}")
            
            # Check company risks
            company_info = check_company_risks(posting.company)
            if company_info:
                completeness = company_info["completeness"]
                risks = company_info["risks"]
                
                # Show completeness status
                if completeness >= 70:
                    print(f"       ✅ 기업정보 {completeness:.0f}%")
                else:
                    print(f"       ⚠️ 기업정보 불완전 ({completeness:.0f}%)")
                    companies_incomplete.append(posting.company)
                
                # Show critical/high risks
                for risk in risks:
                    icon = "🚨" if risk.severity == "critical" else "⚠️"
                    print(f"       {icon} {risk.code}: {risk.message}")
                    if posting.company not in companies_with_risks:
                        companies_with_risks.append(posting.company)
            else:
                print(f"       ❓ 기업정보 없음")
                companies_missing.append(posting.company)
        
        # Summary warnings
        if companies_with_risks:
            print(f"\n   ⚠️ 리스크 주의 기업: {', '.join(companies_with_risks[:5])}")
        if companies_incomplete:
            print(f"   📝 정보 보완 필요: {', '.join(companies_incomplete[:5])}")
        if companies_missing:
            print(f"   ❓ 정보 추출 권장: {', '.join(companies_missing[:5])}")
    
    # Save state
    if not dry_run:
        state.total_searches += 1
        state.total_new_found += len(all_new_postings)
        save_state(state)
        
        # Output URLs for pipeline processing
        if all_new_postings:
            urls_file = JOB_POSTINGS_DIR / "unprocessed" / f"search_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
            urls_file.parent.mkdir(parents=True, exist_ok=True)
            with open(urls_file, "w", encoding="utf-8") as f:
                for posting in all_new_postings:
                    f.write(f"{posting.url}\n")
            print(f"\n📁 URL 목록 저장: {urls_file}")
    else:
        print("\n🔍 Dry-run 모드 - 상태 저장 안 함")
    
    return all_new_postings


def show_status() -> None:
    """Show current search state."""
    state = load_state()
    config = load_config()
    
    print("=" * 60)
    print("📊 JD Search 상태")
    print("=" * 60)
    print(f"   마지막 실행: {state.last_run or '없음'}")
    print(f"   총 검색 횟수: {state.total_searches}")
    print(f"   총 새 공고 발견: {state.total_new_found}")
    print(f"   추적 중인 Job ID: {len(state.seen_job_ids)}개")
    print(f"\n   설정된 키워드:")
    for q in config.get("search_queries", [])[:5]:
        print(f"      - {q}")
    if len(config.get("search_queries", [])) > 5:
        print(f"      ... 외 {len(config.get('search_queries', [])) - 5}개")


def main():
    parser = argparse.ArgumentParser(description="JD Search - 채용공고 자동 검색")
    parser.add_argument("--query", "-q", help="단일 검색어")
    parser.add_argument("--dry-run", action="store_true", help="미리보기 (저장 안 함)")
    parser.add_argument("--status", action="store_true", help="상태 확인")
    parser.add_argument("--max-urls", type=int, help="최대 URL 수")
    parser.add_argument("--reset-state", action="store_true", help="상태 초기화")
    
    args = parser.parse_args()
    
    if args.status:
        show_status()
        return
    
    if args.reset_state:
        if STATE_PATH.exists():
            STATE_PATH.unlink()
            print("✅ 상태 초기화 완료")
        return
    
    queries = [args.query] if args.query else None
    run_search(queries=queries, dry_run=args.dry_run, max_urls=args.max_urls)


if __name__ == "__main__":
    main()
