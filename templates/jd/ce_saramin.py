from __future__ import annotations

import re
import time
from urllib.parse import quote

try:
    from .ce_types import PlatformData
except ImportError:
    from ce_types import PlatformData

REQUEST_DELAY = 1.5


def search_csn(company_name: str, context) -> str | None:
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


def parse_benefits(body_text: str) -> list[str]:
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


def extract_saramin(company_name: str, context) -> PlatformData | None:
    """Extract company info from Saramin company page via text parsing."""
    csn = search_csn(company_name, context)
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
    data.benefits = parse_benefits(body_text)

    has_info = data.industry or data.employee_count or data.avg_salary
    if has_info:
        print(f"   [saramin] 추출 완료: {company_name} (csn={csn})")
    else:
        print(f"   [saramin] 데이터 부족: {company_name} (csn={csn})")

    return data
