"""Pure computation: merge multi-platform company data and generate markdown.

Zero I/O. All functions are pure — given inputs, produce outputs.
The markdown format is coupled with company_validator.parse_company_file regex.
See test_ce_merge_roundtrip.py for format contract verification.
"""
from __future__ import annotations

from datetime import date

try:
    from .ce_types import PlatformData
except ImportError:
    from ce_types import PlatformData


def merge_platform_data(data_list: list[PlatformData]) -> dict:
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


def fmt(value, suffix: str = "") -> str:
    """Format value for markdown table, returning '정보 없음' for None."""
    if value is None:
        return "정보 없음"
    return f"{value}{suffix}"


def build_enriched_markdown(merged: dict, company_name: str, source_urls: list[str]) -> str:
    """Build company info markdown compatible with company_validator.py parsing."""
    name = merged.get("company_name") or company_name
    name_en = merged.get("company_name_en")
    title = f"# {name}" + (f" ({name_en})" if name_en else "")

    industry = fmt(merged.get("industry"))
    founded = fmt(merged.get("founded_year"), "년") if merged.get("founded_year") else "정보 없음"
    emp_count = fmt(merged.get("employee_count"), "명") if merged.get("employee_count") else "정보 없음"

    # Salary
    avg_salary = merged.get("avg_salary")
    salary_pct = merged.get("salary_percentile")
    if avg_salary:
        salary_str = f"**{avg_salary:,}만원**"
        if salary_pct:
            salary_str += f" (상위 {salary_pct}%)"
        salary_source = merged.get("salary_source") or "Wanted"
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
    tags = merged.get("tags", [])
    startup = has_investment or any(
        token in tag
        for tag in tags
        for token in ("스타트업", "Series", "시리즈", "벤처", "투자 유치", "설립3년이하", "인원 급성장", "누적 투자", "투자 라운드")
    )

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
| 스타트업 여부 | {'Yes' if has_investment else 'No'} |
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
