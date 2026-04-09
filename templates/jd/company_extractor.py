#!/usr/bin/env python3
"""Playwright-based company info extraction from Wanted + Saramin + TheVC.

Usage:
    python3 templates/jd/company_extractor.py --company "김캐디"
    python3 templates/jd/company_extractor.py --company "김캐디" --platforms wanted,saramin,thevc
    python3 templates/jd/company_extractor.py --company "김캐디" --dry-run
"""

from __future__ import annotations

import argparse
import json
import re
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional
from urllib.parse import quote

try:
    from .company_validator import COMPANY_INFO_DIR, parse_company_file, validate_company
    from .naming import slugify_company as _slugify_company
except ImportError:
    from company_validator import COMPANY_INFO_DIR, parse_company_file, validate_company
    from naming import slugify_company as _slugify_company


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
REQUEST_DELAY = 1.5  # seconds between page navigations
ALL_PLATFORMS = ("wanted", "saramin", "thevc")

BASE_DIR = Path(__file__).parent.parent.parent
JOB_POSTINGS_DIR = BASE_DIR / "private" / "job_postings"


@dataclass
class PlatformData:
    platform: str  # "wanted" | "saramin" | "thevc"
    source_url: str
    company_name: str
    company_name_en: str | None = None
    industry: str | None = None
    founded_year: int | None = None
    employee_count: int | None = None
    employee_joined_1y: int | None = None
    employee_left_1y: int | None = None
    avg_salary: int | None = None  # 만원
    salary_percentile: str | None = None
    revenue: list[dict] | None = None  # [{year, amount_억}]
    investment_round: str | None = None
    investment_total: str | None = None  # "N억원"
    investors: list[str] = field(default_factory=list)
    benefits: list[str] = field(default_factory=list)
    description: str | None = None
    tags: list[str] = field(default_factory=list)
    raw_extra: dict = field(default_factory=dict)


@dataclass
class ExtractionResult:
    company: str
    file_path: Path
    completeness: float
    platforms_used: list[str]
    platforms_failed: list[str]
    source_urls: list[str]


# ---------------------------------------------------------------------------
# JD file extraction (offline, no browser needed)
# ---------------------------------------------------------------------------

def _normalize_company_name(name: str) -> str:
    """Normalize company name for fuzzy matching."""
    name = re.sub(r"\(주\)|\(유\)|\(사\)", "", name)
    name = re.sub(r"\s+", "", name).lower()
    return name


def _extract_from_jd_files(company_name: str) -> PlatformData | None:
    """Extract investment/revenue info from existing JD files.

    Scans job_postings/ subdirectories for files mentioning the company,
    then extracts investment round, total, investors, and revenue via regex.
    Returns a PlatformData with platform="jd" or None if nothing found.
    """
    if not JOB_POSTINGS_DIR.exists():
        return None

    norm_name = _normalize_company_name(company_name)
    matching_files: list[Path] = []

    for md_file in JOB_POSTINGS_DIR.rglob("*.md"):
        if md_file.name.startswith("jd-screening"):
            continue
        try:
            content = md_file.read_text(encoding="utf-8")
        except Exception:
            continue
        norm_content = _normalize_company_name(content[:500])
        if norm_name in norm_content:
            matching_files.append(md_file)

    if not matching_files:
        return None

    data = PlatformData(
        platform="jd",
        source_url="local:job_postings",
        company_name=company_name,
    )

    for md_file in matching_files:
        try:
            content = md_file.read_text(encoding="utf-8")
        except Exception:
            continue

        # Investment round
        if not data.investment_round:
            m = re.search(
                r"(Seed|Pre-?[AB]|Series\s*[A-Z]\+?|시리즈\s*[A-Z]|브릿지|Pre\s*IPO)",
                content,
                re.IGNORECASE,
            )
            if m:
                data.investment_round = m.group(1).strip()

        # Cumulative investment amount — "누적 투자 300억", "130억을 투자", "총 1,140억원"
        if not data.investment_total:
            patterns = [
                r"누적\s*(?:투자\s*(?:금액?\s*)?)?[:\s]*(?:약\s*)?([\d,]+(?:\.\d+)?)\s*억",
                r"([\d,]+(?:\.\d+)?)\s*억\s*(?:원?\s*)?(?:의\s*)?투자(?:를\s*)?(?:유치|받)",
                r"총\s*([\d,]+(?:\.\d+)?)\s*억\s*원?\s*(?:의\s*)?투자",
            ]
            for pat in patterns:
                m = re.search(pat, content)
                if m:
                    data.investment_total = f"{m.group(1)}억원"
                    break

        # Investors — "투자사: A, B, C" or inline mention
        if not data.investors:
            m = re.search(r"투자사[:\s]*([^\n]+)", content)
            if m:
                raw = m.group(1).strip()
                data.investors = [
                    inv.strip()
                    for inv in re.split(r"[,、·]", raw)
                    if inv.strip() and len(inv.strip()) < 30
                ]

        # Revenue — "매출 300억", "매출액 1,356억원", "연매출 300억 원"
        if not data.revenue:
            m = re.search(r"(?:연?매출(?:액)?)\s*(?:약\s*)?([\d,]+(?:\.\d+)?)\s*억", content)
            if m:
                amount = float(m.group(1).replace(",", ""))
                data.revenue = [{"year": "latest", "amount_억": amount}]

    has_info = data.investment_round or data.investment_total or data.investors or data.revenue
    if has_info:
        print(f"   [jd] JD 파일에서 보충 정보 추출: round={data.investment_round}, total={data.investment_total}")
        return data
    return None


# ---------------------------------------------------------------------------
# Wanted extraction
# ---------------------------------------------------------------------------

def _search_wanted_company_id(company_name: str, context) -> str | None:
    """Search Wanted for company ID."""
    search_url = f"https://www.wanted.co.kr/search?query={quote(company_name)}&tab=company"
    page = context.new_page()
    try:
        page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(2000)

        links = page.query_selector_all('a[href*="/company/"]')
        for link in links:
            href = link.get_attribute("href") or ""
            m = re.search(r"/company/(\d+)", href)
            if m:
                return m.group(1)
        return None
    finally:
        page.close()


def _parse_next_data_company(html: str) -> dict | None:
    """Extract __NEXT_DATA__ JSON from Wanted company page HTML."""
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>([\s\S]*?)</script>', html)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def _extract_wanted_from_text(body_text: str, data: PlatformData) -> None:
    """Fallback: extract company info from page body text via regex."""
    if not data.avg_salary:
        m = re.search(r"평균\s*연봉\s*([\d,]+)\s*만원", body_text)
        if m:
            data.avg_salary = int(m.group(1).replace(",", ""))
    if not data.salary_percentile:
        m = re.search(r"상위\s*(\d+)%", body_text)
        if m:
            data.salary_percentile = m.group(1)
    if not data.employee_count:
        # "301~1,000명" or "50명" style
        m = re.search(r"([\d,]+)(?:~[\d,]+)?\s*명", body_text)
        if m:
            data.employee_count = int(m.group(1).replace(",", ""))
    if not data.founded_year:
        # "8년차 (2019)" or "설립 2019년"
        m = re.search(r"\((\d{4})\)", body_text)
        if m:
            data.founded_year = int(m.group(1))
        else:
            m = re.search(r"설립\s*(\d{4})년?", body_text)
            if m:
                data.founded_year = int(m.group(1))


def _find_query_data(queries: list, prefix: str) -> dict | None:
    """Find query data by queryKey prefix in dehydrateState.queries."""
    for q in queries:
        qk = q.get("queryKey", [])
        if qk and isinstance(qk[0], str) and qk[0] == prefix:
            qdata = q.get("state", {}).get("data", {})
            if isinstance(qdata, dict):
                return qdata
    return None


def _extract_wanted(company_name: str, context) -> PlatformData | None:
    """Extract company info from Wanted company page via __NEXT_DATA__."""
    company_id = _search_wanted_company_id(company_name, context)
    if not company_id:
        print(f"   [wanted] 회사 검색 실패: {company_name}")
        return None

    time.sleep(REQUEST_DELAY)

    company_url = f"https://www.wanted.co.kr/company/{company_id}"
    page = context.new_page()
    try:
        page.goto(company_url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(3000)
        html = page.content()
        body_text = page.inner_text("body")
    finally:
        page.close()

    data = PlatformData(platform="wanted", source_url=company_url, company_name=company_name)
    data.raw_extra["company_id"] = company_id

    next_data = _parse_next_data_company(html)
    if not next_data:
        print(f"   [wanted] __NEXT_DATA__ 파싱 실패, 텍스트 fallback: {company_url}")
        _extract_wanted_from_text(body_text, data)
        return data

    try:
        page_props = next_data.get("props", {}).get("pageProps", {})
        data.raw_extra["pageProps_keys"] = list(page_props.keys())

        # Wanted uses "dehydrateState" (not "dehydratedState")
        dh_state = (
            page_props.get("dehydrateState")
            or page_props.get("dehydratedState")
            or {}
        )
        queries = dh_state.get("queries", [])

        # companyInfo query — basic company data
        company_info = _find_query_data(queries, "companyInfo")
        # companySummary query — salary, employee, sales detail
        company_summary = _find_query_data(queries, "companySummary")

        if not company_info and not company_summary:
            print(f"   [wanted] 회사 데이터 구조를 찾지 못함, 텍스트 fallback")
            _extract_wanted_from_text(body_text, data)
            return data

        # --- companyInfo fields ---
        if company_info:
            data.company_name = company_info.get("name", company_name)
            data.industry = company_info.get("industryName")
            data.founded_year = company_info.get("foundedYear")
            data.description = company_info.get("description")
            data.raw_extra["location"] = company_info.get("location")

            # Tags from companyTags
            for tag_list_key in ("companyTags", "mainTags"):
                tags_raw = company_info.get(tag_list_key, [])
                if isinstance(tags_raw, list):
                    for t in tags_raw:
                        title = t.get("title", "") if isinstance(t, dict) else str(t)
                        if title and title not in data.tags:
                            data.tags.append(title)

        # --- companySummary fields ---
        if company_summary:
            detail = company_summary.get("detail", {})
            salary_obj = company_summary.get("salary", {})
            emp_obj = company_summary.get("employee", {})
            sales_obj = company_summary.get("sales", {})

            # Employee count: npsEmployeeCount > eiEmployeeCount
            nps_emp = detail.get("npsEmployeeCount")
            ei_emp = detail.get("eiEmployeeCount")
            emp_total = emp_obj.get("total")
            best_emp = nps_emp or emp_total or ei_emp
            if best_emp and isinstance(best_emp, (int, float)) and best_emp > 0:
                data.employee_count = int(best_emp)

            # Salary (원 → 만원)
            salary_raw = salary_obj.get("salary") or detail.get("salary")
            if salary_raw and isinstance(salary_raw, (int, float)) and salary_raw > 0:
                data.avg_salary = int(salary_raw / 10000)

            # Salary percentile (rate is a ratio, e.g. 0.0419 = top 4.19%)
            rate = salary_obj.get("rate")
            if rate and isinstance(rate, (int, float)) and 0 < rate < 1:
                data.salary_percentile = str(round(rate * 100))

            # Employee joined/left
            hired = emp_obj.get("hired") or detail.get("hiredCount")
            left = emp_obj.get("left") or detail.get("leftCount")
            if hired and isinstance(hired, (int, float)):
                data.employee_joined_1y = int(hired)
            if left and isinstance(left, (int, float)):
                data.employee_left_1y = int(left)

            # Revenue (원 → 억원)
            total_sales = sales_obj.get("total") or detail.get("totalSales")
            if total_sales and isinstance(total_sales, (int, float)) and total_sales > 0:
                amount_억 = round(total_sales / 100_000_000, 1)
                data.revenue = [{"year": "latest", "amount_억": amount_억}]

        # Text fallback for fields not found in __NEXT_DATA__
        _extract_wanted_from_text(body_text, data)

        print(f"   [wanted] 추출 완료: {data.company_name} (id={company_id})")
    except Exception as e:
        print(f"   [wanted] 데이터 파싱 오류: {e}")
        _extract_wanted_from_text(body_text, data)

    return data


# ---------------------------------------------------------------------------
# Saramin extraction
# ---------------------------------------------------------------------------

def _search_saramin_csn(company_name: str, context) -> str | None:
    """Search Saramin for company CSN (company serial number)."""
    search_url = f"https://www.saramin.co.kr/zf_user/search/company?searchword={quote(company_name)}"
    page = context.new_page()
    try:
        page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(2000)

        links = page.query_selector_all('a[href*="/company-info/view"]')
        for link in links:
            href = link.get_attribute("href") or ""
            m = re.search(r"csn=([A-Za-z0-9+/=]+)", href)
            if m:
                return m.group(1)
        return None
    finally:
        page.close()


def _parse_saramin_benefits(body_text: str) -> list[str]:
    """Extract categorized benefits from Saramin page text."""
    benefits_match = re.search(r"복지.*?(?=기업문화|면접|연봉정보|기업리뷰|$)", body_text, re.DOTALL)
    if not benefits_match:
        return []
    section = benefits_match.group(0)
    benefit_keywords = [
        "4대 보험", "퇴직금", "연차", "인센티브", "상여금", "자기계발",
        "건강검진", "경조사", "교통비", "식비", "주차", "통근버스",
        "휴게실", "카페", "동호회", "워크샵", "자율출퇴근", "재택근무",
        "스톡옵션", "우리사주", "학자금", "도서구입비", "교육비",
        "생일", "명절", "출산", "육아", "보육", "의료비",
    ]
    found = []
    for kw in benefit_keywords:
        if kw in section:
            found.append(kw)
    return found


def _extract_saramin(company_name: str, context) -> PlatformData | None:
    """Extract company info from Saramin company page via text parsing."""
    csn = _search_saramin_csn(company_name, context)
    if not csn:
        print(f"   [saramin] 회사 검색 실패: {company_name}")
        return None

    time.sleep(REQUEST_DELAY)

    company_url = f"https://www.saramin.co.kr/zf_user/company-info/view?csn={csn}"
    page = context.new_page()
    try:
        page.goto(company_url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(2000)

        for _ in range(3):
            page.mouse.wheel(0, 3000)
            page.wait_for_timeout(1000)

        body_text = page.inner_text("body")
    finally:
        page.close()

    data = PlatformData(platform="saramin", source_url=company_url, company_name=company_name)
    data.raw_extra["csn"] = csn

    # Industry
    m = re.search(r"업종\s*[:|]\s*(.+?)(?:\n|$)", body_text)
    if m:
        data.industry = m.group(1).strip()

    # Founded year
    m = re.search(r"설립\s*[:|]?\s*(\d{4})년", body_text)
    if m:
        data.founded_year = int(m.group(1))

    # Employee count
    m = re.search(r"(?:사원수|직원수)\s*[:|]?\s*([\d,]+)\s*명", body_text)
    if m:
        data.employee_count = int(m.group(1).replace(",", ""))

    # Average salary
    m = re.search(r"평균\s*연봉\s*[:|]?\s*([\d,]+)\s*만원", body_text)
    if m:
        data.avg_salary = int(m.group(1).replace(",", ""))

    # Salary percentile
    m = re.search(r"상위\s*(\d+)%", body_text)
    if m:
        data.salary_percentile = m.group(1)

    # Employee joined/left in 1 year
    m = re.search(r"입사\S*\s*([\d,]+)\s*명", body_text)
    if m:
        data.employee_joined_1y = int(m.group(1).replace(",", ""))
    m = re.search(r"퇴사\S*\s*([\d,]+)\s*명", body_text)
    if m:
        data.employee_left_1y = int(m.group(1).replace(",", ""))

    # Revenue
    m = re.search(r"매출액?\s*[:|]?\s*([\d,]+(?:\.\d+)?)\s*억", body_text)
    if m:
        data.raw_extra["revenue_latest"] = f"{m.group(1)}억원"

    # CEO
    m = re.search(r"대표자?\s*[:|]\s*(\S+)", body_text)
    if m:
        data.raw_extra["ceo"] = m.group(1).strip()

    # Location
    m = re.search(r"(?:주소|위치)\s*[:|]\s*(.+?)(?:\n|$)", body_text)
    if m:
        data.raw_extra["location"] = m.group(1).strip()

    # Company type (기업형태)
    m = re.search(r"기업형태\s*[:|]\s*(.+?)(?:\n|$)", body_text)
    if m:
        data.raw_extra["company_type"] = m.group(1).strip()

    # Benefits
    data.benefits = _parse_saramin_benefits(body_text)

    has_info = data.industry or data.employee_count or data.avg_salary
    if has_info:
        print(f"   [saramin] 추출 완료: {company_name} (csn={csn})")
    else:
        print(f"   [saramin] 데이터 부족: {company_name} (csn={csn})")

    return data


# ---------------------------------------------------------------------------
# TheVC extraction
# ---------------------------------------------------------------------------

def _search_thevc_slug_single(keyword: str, context) -> str | None:
    """Search TheVC for company slug with a single keyword."""
    search_url = f"https://thevc.kr/integrated-search/overview?keyword={quote(keyword)}"
    page = context.new_page()
    try:
        page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(3000)

        links = page.query_selector_all("a[href]")
        for link in links:
            href = link.get_attribute("href") or ""
            if (
                href.startswith("/")
                and not href.startswith("/integrated-search")
                and not href.startswith("/login")
                and not href.startswith("/search")
                and not href.startswith("/api")
                and not href.startswith("/static")
                and "/" not in href[1:]
            ):
                return href.lstrip("/")
        return None
    finally:
        page.close()


def _get_english_name_from_company_info(company_name: str) -> str | None:
    """Extract English name from existing company_info file H1 title."""
    slug = _slugify_company(company_name)
    info_path = COMPANY_INFO_DIR / f"{slug}.md"
    if not info_path.exists():
        return None
    try:
        content = info_path.read_text(encoding="utf-8")
        m = re.search(r"^#\s+.+?\(([A-Za-z][\w\s&.-]*)\)", content, re.MULTILINE)
        if m:
            return m.group(1).strip()
    except Exception:
        pass
    return None


def _search_thevc_slug(company_name: str, context) -> str | None:
    """Search TheVC for company slug with retry: original → English name → short name."""
    # Attempt 1: original Korean name
    slug = _search_thevc_slug_single(company_name, context)
    if slug:
        return slug

    # Attempt 2: English name from company_info file
    en_name = _get_english_name_from_company_info(company_name)
    if en_name:
        print(f"   [thevc] 한글명 실패, 영문명 재시도: {en_name}")
        time.sleep(REQUEST_DELAY)
        slug = _search_thevc_slug_single(en_name, context)
        if slug:
            return slug

    # Attempt 3: short name (first 2 words)
    words = company_name.split()
    if len(words) > 2:
        short_name = " ".join(words[:2])
        print(f"   [thevc] 짧은 이름 재시도: {short_name}")
        time.sleep(REQUEST_DELAY)
        slug = _search_thevc_slug_single(short_name, context)
        if slug:
            return slug

    return None


def _extract_thevc(company_name: str, context) -> PlatformData | None:
    """Extract investment info from TheVC SPA via Playwright."""
    slug = _search_thevc_slug(company_name, context)
    if not slug:
        print(f"   [thevc] 회사 검색 실패: {company_name}")
        return None

    time.sleep(REQUEST_DELAY)

    company_url = f"https://thevc.kr/{slug}"
    page = context.new_page()
    try:
        page.goto(company_url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(3000)

        # Login wall detection
        body_text = page.inner_text("body")
        login_signals = ["로그인이 필요합니다", "Sign in to continue", "로그인 후 확인"]
        if any(sig in body_text for sig in login_signals):
            print(f"   [thevc] 로그인 wall 감지 — 가용 데이터만 추출")

        data = PlatformData(
            platform="thevc", source_url=company_url, company_name=company_name
        )

        # Try to click investment tab if available
        inv_tabs = page.query_selector_all('a, button, [role="tab"]')
        for tab in inv_tabs:
            tab_text = (tab.inner_text() or "").strip()
            if "투자" in tab_text:
                try:
                    tab.click()
                    page.wait_for_timeout(2000)
                except Exception:
                    pass
                break

        body_text = page.inner_text("body")

        # Investment round
        round_match = re.search(
            r"(Seed|Pre-A|Pre-B|Series\s*[A-Z]\+?|IPO|M&A)",
            body_text,
            re.IGNORECASE,
        )
        if round_match:
            data.investment_round = round_match.group(1).strip()

        # Investment total — e.g., "누적 130억원", "총 투자금 298억원"
        total_match = re.search(r"(?:누적|총\s*투자[금액]?)\s*([\d,]+(?:\.\d+)?)\s*억", body_text)
        if total_match:
            data.investment_total = f"{total_match.group(1)}억원"
        else:
            # Fallback: any N억원 near investment context
            inv_match = re.search(r"([\d,]+(?:\.\d+)?)\s*억\s*원?", body_text)
            if inv_match:
                data.investment_total = f"{inv_match.group(1)}억원"

        # Investors
        investor_patterns = [
            r"투자자[:\s]*(.*)",
            r"참여\s*(?:투자자|기관)[:\s]*(.*)",
        ]
        for pat in investor_patterns:
            m = re.search(pat, body_text)
            if m:
                raw = m.group(1).strip()
                data.investors = [inv.strip() for inv in re.split(r"[,、·]", raw) if inv.strip()]
                break

        # Founded year from body text
        founded_match = re.search(r"설립[:\s]*(\d{4})", body_text)
        if founded_match:
            data.founded_year = int(founded_match.group(1))

        if data.investment_round or data.investment_total:
            print(f"   [thevc] 추출 완료: round={data.investment_round}, total={data.investment_total}")
        else:
            print(f"   [thevc] 투자정보 추출 실패 (접근 제한 가능)")

        return data

    finally:
        page.close()


# ---------------------------------------------------------------------------
# Merge + Markdown generation
# ---------------------------------------------------------------------------

def _merge_platform_data(data_list: list[PlatformData]) -> dict:
    """Merge multiple PlatformData into a single dict.

    Priority:
    - 연봉/직원수/입퇴사: Wanted > Saramin (Wanted=국민연금 기반 실시간)
    - 투자: TheVC > Wanted (TheVC 전문)
    - 복지/업종: Saramin > Wanted (Saramin이 가장 풍부/표준 분류)
    - 위치/대표자: Saramin only
    """
    merged: dict = {
        "company_name": "",
        "company_name_en": None,
        "industry": None,
        "founded_year": None,
        "employee_count": None,
        "employee_joined_1y": None,
        "employee_left_1y": None,
        "avg_salary": None,
        "salary_percentile": None,
        "revenue": None,
        "investment_round": None,
        "investment_total": None,
        "investors": [],
        "benefits": [],
        "description": None,
        "tags": [],
        "source_urls": [],
        "raw_extra": {},
    }

    wanted_data = [d for d in data_list if d.platform == "wanted"]
    saramin_data = [d for d in data_list if d.platform == "saramin"]
    thevc_data = [d for d in data_list if d.platform == "thevc"]

    jd_data = [d for d in data_list if d.platform == "jd"]

    # General fields: Wanted > Saramin > TheVC > JD (first-write-wins)
    ordered = wanted_data + saramin_data + thevc_data + jd_data

    for d in ordered:
        if not merged["company_name"]:
            merged["company_name"] = d.company_name
        if d.company_name_en and not merged["company_name_en"]:
            merged["company_name_en"] = d.company_name_en
        if d.founded_year and not merged["founded_year"]:
            merged["founded_year"] = d.founded_year
        if d.employee_count and not merged["employee_count"]:
            merged["employee_count"] = d.employee_count
        if d.employee_joined_1y and not merged["employee_joined_1y"]:
            merged["employee_joined_1y"] = d.employee_joined_1y
        if d.employee_left_1y and not merged["employee_left_1y"]:
            merged["employee_left_1y"] = d.employee_left_1y
        if d.avg_salary and not merged["avg_salary"]:
            merged["avg_salary"] = d.avg_salary
        if d.salary_percentile and not merged["salary_percentile"]:
            merged["salary_percentile"] = d.salary_percentile
        if d.revenue and not merged["revenue"]:
            merged["revenue"] = d.revenue
        if d.description and not merged["description"]:
            merged["description"] = d.description
        merged["tags"] = merged["tags"] or d.tags
        merged["source_urls"].append(d.source_url)

    # Industry: Saramin > Wanted (Saramin uses standard classification)
    for d in saramin_data:
        if d.industry:
            merged["industry"] = d.industry
            break
    if not merged["industry"]:
        for d in wanted_data:
            if d.industry:
                merged["industry"] = d.industry
                break

    # Benefits: Saramin > Wanted (Saramin is richest)
    for d in saramin_data:
        if d.benefits:
            merged["benefits"] = d.benefits
            break
    if not merged["benefits"]:
        for d in wanted_data:
            if d.benefits:
                merged["benefits"] = d.benefits
                break

    # Investment: TheVC > Wanted
    for d in thevc_data:
        if d.investment_round:
            merged["investment_round"] = d.investment_round
        if d.investment_total:
            merged["investment_total"] = d.investment_total
        if d.investors:
            merged["investors"] = d.investors

    if not merged["investment_round"]:
        for d in wanted_data:
            if d.investment_round:
                merged["investment_round"] = d.investment_round
    if not merged["investment_total"]:
        for d in wanted_data:
            if d.investment_total:
                merged["investment_total"] = d.investment_total

    # JD fallback for investment (lowest priority)
    if not merged["investment_round"]:
        for d in jd_data:
            if d.investment_round:
                merged["investment_round"] = d.investment_round
                break
    if not merged["investment_total"]:
        for d in jd_data:
            if d.investment_total:
                merged["investment_total"] = d.investment_total
                break
    if not merged["investors"]:
        for d in jd_data:
            if d.investors:
                merged["investors"] = d.investors
                break
    if not merged["revenue"]:
        for d in jd_data:
            if d.revenue:
                merged["revenue"] = d.revenue
                break

    # Saramin-only fields via raw_extra
    for d in saramin_data:
        for key in ("ceo", "location", "company_type", "revenue_latest"):
            if d.raw_extra.get(key) and key not in merged["raw_extra"]:
                merged["raw_extra"][key] = d.raw_extra[key]

    return merged


def _fmt(value, suffix: str = "") -> str:
    """Format value for markdown table, returning '정보 없음' for None."""
    if value is None:
        return "정보 없음"
    return f"{value}{suffix}"


def _build_enriched_markdown(merged: dict, company_name: str, source_urls: list[str]) -> str:
    """Build company info markdown compatible with company_validator.py parsing."""
    name = merged.get("company_name") or company_name
    name_en = merged.get("company_name_en")
    title = f"# {name}" + (f" ({name_en})" if name_en else "")

    industry = _fmt(merged.get("industry"))
    founded = _fmt(merged.get("founded_year"), "년") if merged.get("founded_year") else "정보 없음"
    emp_count = _fmt(merged.get("employee_count"), "명") if merged.get("employee_count") else "정보 없음"

    # Salary
    avg_salary = merged.get("avg_salary")
    salary_pct = merged.get("salary_percentile")
    if avg_salary:
        salary_str = f"**{avg_salary:,}만원**"
        if salary_pct:
            salary_str += f" (상위 {salary_pct}%)"
        salary_source = "Wanted"
    else:
        salary_str = "정보 없음"
        salary_source = "정보 없음"

    # Employee stats
    emp_current = merged.get("employee_count")
    emp_joined = merged.get("employee_joined_1y")
    emp_left = merged.get("employee_left_1y")

    # Investment
    inv_round = merged.get("investment_round")
    inv_total = merged.get("investment_total")
    investors = merged.get("investors", [])
    has_investment = inv_round or inv_total

    # Revenue
    revenue_list = merged.get("revenue")

    # Build sections
    sections = []

    raw_extra = merged.get("raw_extra", {})
    location = raw_extra.get("location")
    ceo = raw_extra.get("ceo")
    company_type = raw_extra.get("company_type")

    company_table = f"""{title}

## 기업 정보

| 항목 | 내용 |
|------|------|
| 회사명 | {name} |
| 업종 | {industry} |
| 설립 | {founded} |
| 직원수 | {emp_count} |"""
    if location:
        company_table += f"\n| 위치 | {location} |"
    if ceo:
        company_table += f"\n| 대표자 | {ceo} |"
    if company_type:
        company_table += f"\n| 기업형태 | {company_type} |"

    sections.append(company_table)

    sections.append(f"""
## 연봉 정보

| 항목 | 금액 | 출처 |
|------|------|------|
| 평균 연봉 | {salary_str} | {salary_source} |""")

    # Employee stats section
    joined_str = f"{emp_joined}명" if emp_joined else "정보 없음"
    left_str = f"{emp_left}명" if emp_left else "정보 없음"
    current_str = f"{emp_current}명" if emp_current else "정보 없음"

    sections.append(f"""
## 인원 통계

| 항목 | 수치 |
|------|------|
| 현재 인원 | {current_str} |
| 1년간 입사자 | {joined_str} |
| 1년간 퇴사자 | {left_str} |""")

    # Investment section
    if has_investment:
        inv_round_str = inv_round or "정보 없음"
        inv_total_str = inv_total or "정보 없음"

        inv_section = f"""
## 투자 정보

| 항목 | 내용 |
|------|------|
| 현재 라운드 | {inv_round_str} |
| 누적 투자금 | {inv_total_str} |"""

        if investors:
            inv_section += f"\n| 주요 투자자 | {', '.join(investors[:5])} |"

        sections.append(inv_section)

    # Revenue section
    if revenue_list:
        rev_lines = ["\n## 매출 추이\n", "| 연도 | 매출 |", "|------|------|"]
        for r in sorted(revenue_list, key=lambda x: x.get("year", 0), reverse=True):
            rev_lines.append(f"| {r.get('year', '?')} | {r.get('amount_억', '?')}억원 |")
        sections.append("\n".join(rev_lines))

    # Benefits
    benefits = merged.get("benefits", [])
    if benefits:
        sections.append("\n## 복지/혜택\n\n" + "\n".join(f"- {b}" for b in benefits[:20]))

    # Tags
    tags = merged.get("tags", [])
    if tags:
        sections.append("\n## 태그\n" + "\n".join(f"- {t}" for t in tags))

    # Description
    desc = merged.get("description")
    if desc:
        # Truncate very long descriptions
        if len(desc) > 500:
            desc = desc[:500] + "..."
        sections.append(f"\n## 회사 소개\n\n{desc}")

    # Footer
    source_lines = "\n".join(f"- {url}" for url in source_urls)
    sections.append(f"""
---

*추출일: {date.today().isoformat()}*
*출처:*
{source_lines}""")

    return "\n".join(sections) + "\n"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def extract_company_info(
    company_name: str,
    *,
    browser_context=None,
    platforms: tuple[str, ...] | list[str] | None = None,
    is_startup: bool = False,
    jd_url: str = "",
    existing_file: Path | None = None,
    dry_run: bool = False,
) -> ExtractionResult:
    """Main entry point for Playwright-based company info extraction."""
    platforms = tuple(platforms or ALL_PLATFORMS)
    slug = _slugify_company(company_name)
    output_path = COMPANY_INFO_DIR / f"{slug}.md"

    own_playwright = browser_context is None
    pw_instance = None
    browser = None

    if own_playwright:
        from playwright.sync_api import sync_playwright
        pw_instance = sync_playwright().start()
        browser = pw_instance.chromium.launch(headless=True)
        browser_context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=USER_AGENT,
        )

    platforms_used: list[str] = []
    platforms_failed: list[str] = []
    source_urls: list[str] = []
    data_list: list[PlatformData] = []

    try:
        if "wanted" in platforms:
            try:
                result = _extract_wanted(company_name, browser_context)
                if result:
                    data_list.append(result)
                    platforms_used.append("wanted")
                    source_urls.append(result.source_url)
                else:
                    platforms_failed.append("wanted")
            except Exception as e:
                print(f"   [wanted] 예외: {e}")
                platforms_failed.append("wanted")

            time.sleep(REQUEST_DELAY)

        if "saramin" in platforms:
            try:
                result = _extract_saramin(company_name, browser_context)
                if result:
                    data_list.append(result)
                    platforms_used.append("saramin")
                    source_urls.append(result.source_url)
                else:
                    platforms_failed.append("saramin")
            except Exception as e:
                print(f"   [saramin] 예외: {e}")
                platforms_failed.append("saramin")

            time.sleep(REQUEST_DELAY)

        if "thevc" in platforms:
            try:
                result = _extract_thevc(company_name, browser_context)
                if result:
                    data_list.append(result)
                    platforms_used.append("thevc")
                    source_urls.append(result.source_url)
                else:
                    platforms_failed.append("thevc")
            except Exception as e:
                print(f"   [thevc] 예외: {e}")
                platforms_failed.append("thevc")
    finally:
        if own_playwright:
            if browser:
                browser.close()
            if pw_instance:
                pw_instance.stop()

    # JD file extraction (no browser needed, always attempted)
    try:
        jd_result = _extract_from_jd_files(company_name)
        if jd_result:
            data_list.append(jd_result)
            platforms_used.append("jd")
    except Exception as e:
        print(f"   [jd] 예외: {e}")

    # Build markdown
    if data_list:
        merged = _merge_platform_data(data_list)
        markdown = _build_enriched_markdown(merged, company_name, source_urls)
    else:
        # All platforms failed — return minimal result
        return ExtractionResult(
            company=company_name,
            file_path=output_path,
            completeness=0.0,
            platforms_used=[],
            platforms_failed=platforms_failed,
            source_urls=[],
        )

    if not dry_run:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8")

    completeness = 0.0
    if not dry_run and output_path.exists():
        try:
            parsed = parse_company_file(output_path)
            val_result = validate_company(parsed, output_path)
            completeness = val_result.completeness_score
        except Exception:
            pass

    return ExtractionResult(
        company=company_name,
        file_path=output_path,
        completeness=completeness,
        platforms_used=platforms_used,
        platforms_failed=platforms_failed,
        source_urls=source_urls,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Playwright 기반 회사 정보 추출")
    parser.add_argument("--company", required=True, help="회사명")
    parser.add_argument(
        "--platforms",
        default="wanted,saramin,thevc",
        help="추출 플랫폼 (쉼표 구분, 기본: wanted,saramin,thevc)",
    )
    parser.add_argument("--dry-run", action="store_true", help="파일 저장 안함")
    args = parser.parse_args()

    platforms = tuple(p.strip() for p in args.platforms.split(","))
    print(f"🏢 회사 정보 추출: {args.company}")
    print(f"   플랫폼: {', '.join(platforms)}")

    result = extract_company_info(
        args.company,
        platforms=platforms,
        dry_run=args.dry_run,
    )

    print(f"\n{'=' * 50}")
    print(f"결과: {result.company}")
    print(f"파일: {result.file_path}")
    print(f"완성도: {result.completeness:.0f}%")
    print(f"사용 플랫폼: {', '.join(result.platforms_used) or '없음'}")
    print(f"실패 플랫폼: {', '.join(result.platforms_failed) or '없음'}")
    print(f"출처: {', '.join(result.source_urls) or '없음'}")

    if args.dry_run:
        print("\n(dry-run 모드 — 파일 미저장)")


if __name__ == "__main__":
    main()
