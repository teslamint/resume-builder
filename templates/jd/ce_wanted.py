from __future__ import annotations

import json
import re
import time
from urllib.parse import quote

try:
    from .ce_types import PlatformData
except ImportError:
    from ce_types import PlatformData

REQUEST_DELAY = 1.5


def search_company_id(company_name: str, context) -> str | None:
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


def parse_next_data_company(html: str) -> dict | None:
    """Extract __NEXT_DATA__ JSON from Wanted company page HTML."""
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>([\s\S]*?)</script>', html)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def extract_wanted_from_text(body_text: str, data: PlatformData) -> None:
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


def find_query_data(queries: list, prefix: str) -> dict | None:
    """Find query data by queryKey prefix in dehydrateState.queries."""
    for q in queries:
        qk = q.get("queryKey", [])
        if qk and isinstance(qk[0], str) and qk[0] == prefix:
            qdata = q.get("state", {}).get("data", {})
            if isinstance(qdata, dict):
                return qdata
    return None


def extract_wanted(company_name: str, context) -> PlatformData | None:
    """Extract company info from Wanted company page via __NEXT_DATA__."""
    company_id = search_company_id(company_name, context)
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

    next_data = parse_next_data_company(html)
    if not next_data:
        print(f"   [wanted] __NEXT_DATA__ 파싱 실패, 텍스트 fallback: {company_url}")
        extract_wanted_from_text(body_text, data)
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
        company_info = find_query_data(queries, "companyInfo")
        # companySummary query — salary, employee, sales detail
        company_summary = find_query_data(queries, "companySummary")

        if not company_info and not company_summary:
            print(f"   [wanted] 회사 데이터 구조를 찾지 못함, 텍스트 fallback")
            extract_wanted_from_text(body_text, data)
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
        extract_wanted_from_text(body_text, data)

        print(f"   [wanted] 추출 완료: {data.company_name} (id={company_id})")
    except Exception as e:
        print(f"   [wanted] 데이터 파싱 오류: {e}")
        extract_wanted_from_text(body_text, data)

    return data
