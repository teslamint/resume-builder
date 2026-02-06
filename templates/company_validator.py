#!/usr/bin/env python3
"""
Company Info Validator - 기업정보 검증 및 리스크 플래깅

Usage:
    python3 templates/company_validator.py                     # 전체 검증
    python3 templates/company_validator.py --file company.md   # 단일 파일
    python3 templates/company_validator.py --fix               # 자동 수정
    python3 templates/company_validator.py --report            # 리포트 생성
    python3 templates/company_validator.py --json              # 기계 처리용 JSON 출력
"""

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Paths
BASE_DIR = Path(__file__).parent.parent
COMPANY_INFO_DIR = BASE_DIR / "company_info"
REPORT_PATH = BASE_DIR / "company_info" / "_validation_report.md"


@dataclass
class CompanyData:
    """Parsed company data."""
    name: str = ""
    name_en: str = ""
    industry: str = ""
    founded_year: Optional[int] = None
    employee_current: Optional[int] = None
    employee_joined_1y: Optional[int] = None
    employee_left_1y: Optional[int] = None
    employee_mom_change: Optional[float] = None  # Month-over-month %
    avg_salary: Optional[int] = None  # 만원
    salary_percentile: Optional[str] = None
    revenue: Optional[float] = None  # 억원
    investment_round: Optional[str] = None
    investment_total: Optional[float] = None  # 억원
    investors: List[str] = field(default_factory=list)
    is_startup: bool = False
    sources: List[str] = field(default_factory=list)


@dataclass
class ValidationIssue:
    """Validation issue."""
    field: str
    severity: str  # "error", "warning", "info"
    message: str


@dataclass 
class RiskFlag:
    """Risk flag for screening."""
    code: str
    severity: str  # "critical", "high", "medium", "low"
    message: str
    value: Optional[str] = None


@dataclass
class ValidationResult:
    """Validation result for a company file."""
    file_path: Path
    company_name: str
    data: CompanyData
    issues: List[ValidationIssue] = field(default_factory=list)
    risk_flags: List[RiskFlag] = field(default_factory=list)
    completeness_score: float = 0.0


# Required fields for completeness check
REQUIRED_FIELDS = [
    ("employee_current", "현재 인원"),
    ("avg_salary", "평균 연봉"),
    ("founded_year", "설립연도"),
]

STARTUP_REQUIRED_FIELDS = [
    ("investment_round", "투자 라운드"),
    ("investment_total", "누적 투자금"),
    ("employee_joined_1y", "1년간 입사자"),
    ("employee_left_1y", "1년간 퇴사자"),
]

# Risk thresholds
RISK_THRESHOLDS = {
    "turnover_critical": 0.5,   # 50% 이상 퇴사
    "turnover_high": 0.3,       # 30% 이상 퇴사
    "turnover_medium": 0.2,     # 20% 이상 퇴사
    "shrinking_high": -0.1,     # 10% 이상 감소 (MoM)
    "salary_low_percentile": 50, # 상위 50% 미만
    "company_young": 3,          # 설립 3년 미만
}


def parse_number(text: str) -> Optional[int]:
    """Extract number from text like '59명', '5,619만원', '약 1,220명', '2,774명 (국민연금)'."""
    if not text:
        return None
    # Skip if explicitly marked as unavailable
    if '비공개' in text or '정보없음' in text:
        return None
    # Remove "약", commas, and extract first number
    cleaned = text.replace('약', '').replace(',', '')
    match = re.search(r'(\d+)', cleaned)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


def parse_percentage(text: str) -> Optional[float]:
    """Extract percentage from text like '상위 7%' or '-3%'."""
    if not text:
        return None
    match = re.search(r'[-+]?\d+(?:\.\d+)?%?', text)
    if match:
        try:
            return float(match.group().replace('%', ''))
        except ValueError:
            return None
    return None


def parse_money_billions(text: str) -> Optional[float]:
    """Extract money in 억원 from text like '298억원' or '130억원'."""
    if not text:
        return None
    match = re.search(r'([\d,]+(?:\.\d+)?)\s*억', text)
    if match:
        try:
            return float(match.group(1).replace(',', ''))
        except ValueError:
            return None
    return None


def parse_company_file(file_path: Path) -> CompanyData:
    """Parse company info markdown file."""
    content = file_path.read_text(encoding='utf-8')
    data = CompanyData()
    startup_status_locked = False
    
    # Extract company name from title
    title_match = re.search(r'^#\s+(.+?)(?:\s*\((.+?)\))?\s*$', content, re.MULTILINE)
    if title_match:
        data.name = title_match.group(1).strip()
        if title_match.group(2):
            data.name_en = title_match.group(2).strip()
    
    # Extract from tables
    # 기업 정보 테이블
    info_section = re.search(r'## 기업 정보.*?(?=##|\Z)', content, re.DOTALL)
    if info_section:
        section_text = info_section.group()
        
        # 설립연도
        year_match = re.search(r'설립.*?\|\s*(\d{4})년', section_text)
        if year_match:
            data.founded_year = int(year_match.group(1))
        
        # 직원수 - handles "2,774명 (국민연금) / 4,411명 (고용보험)"
        emp_match = re.search(r'직원수.*?\|\s*([\d,]+)명', section_text)
        if emp_match:
            data.employee_current = int(emp_match.group(1).replace(',', ''))
        
        # 업종
        industry_match = re.search(r'업종.*?\|\s*([^|]+)', section_text)
        if industry_match:
            data.industry = industry_match.group(1).strip()
    
    # 인원 통계 or 인원 현황 (stops at next ## but not ###)
    staff_section = re.search(r'## 인원 (?:통계|현황).*?(?=\n## [^#]|\Z)', content, re.DOTALL)
    if staff_section:
        section_text = staff_section.group()
        
        # 현재 인원 or 총 인원 - handles "2,774명", "약 100명", "2,774명 (국민연금)"
        current_match = re.search(r'(?:현재 인원|총 인원).*?\|\s*약?\s*([\d,]+)명', section_text)
        if current_match:
            data.employee_current = int(current_match.group(1).replace(',', ''))
        
        # 1년간 입사자 - handles "약 1,220명", table or list format
        joined_match = re.search(r'(?:1년간 입사자.*?\|\s*|입사[:\s]+)약?\s*([\d,]+)명', section_text)
        if joined_match:
            data.employee_joined_1y = int(joined_match.group(1).replace(',', ''))
        
        # 1년간 퇴사자 - handles table or list format ("- 퇴사: 14명")
        left_match = re.search(r'(?:1년간 퇴사자.*?\|\s*|퇴사[:\s]+)약?\s*([\d,]+)명', section_text)
        if left_match:
            data.employee_left_1y = int(left_match.group(1).replace(',', ''))
        
        # MoM 변동
        mom_match = re.search(r'MoM\s*([-+]?\d+(?:\.\d+)?)\s*%', section_text)
        if mom_match:
            data.employee_mom_change = float(mom_match.group(1))
    
    # 연봉 정보
    salary_section = re.search(r'## 연봉 정보.*?(?=##|\Z)', content, re.DOTALL)
    if salary_section:
        section_text = salary_section.group()
        
        # 평균 연봉
        salary_match = re.search(r'평균 연봉.*?\*\*(\d[\d,]*)만원\*\*', section_text)
        if salary_match:
            data.avg_salary = int(salary_match.group(1).replace(',', ''))
        
        # 상위 퍼센트
        percentile_match = re.search(r'상위\s*(\d+)%', section_text)
        if percentile_match:
            data.salary_percentile = percentile_match.group(1)
    
    # 투자 정보
    investment_section = re.search(r'## 투자 정보.*?(?=##|\Z)', content, re.DOTALL)
    if investment_section:
        section_text = investment_section.group()
        data.is_startup = True
        
        # 현재 라운드 or 상태 (handles "Series C", "상장기업", "M&A")
        round_match = re.search(r'(?:현재 라운드|현재 상태).*?\|\s*([^\n|]+)', section_text)
        if round_match:
            round_val = round_match.group(1).strip()
            round_upper = round_val.upper()
            if '상장' in round_val:
                data.investment_round = "IPO"
                data.is_startup = False  # Listed company, not a startup for screening
                startup_status_locked = True
            elif "M&A" in round_upper or "MNA" in round_upper:
                data.investment_round = "M&A"
                data.is_startup = False  # Acquired company, not a startup for screening
                startup_status_locked = True
            else:
                data.investment_round = round_val
        
        # 누적 투자금 - handles "100억원", "100억 이상", "약 130억원"
        total_match = re.search(r'누적 투자.*?\|\s*(?:약\s*)?([\d,]+(?:\.\d+)?)\s*억', section_text)
        if total_match:
            data.investment_total = float(total_match.group(1).replace(',', ''))
    
    # TheVC 언급 확인
    if not startup_status_locked and ('TheVC' in content or 'thevc.kr' in content):
        data.is_startup = True
    
    # 스타트업 키워드 확인
    startup_keywords = ['스타트업', 'Series', '시리즈', '벤처', '투자 유치']
    if not startup_status_locked and any(kw in content for kw in startup_keywords):
        data.is_startup = True
    
    # 매출
    revenue_section = re.search(r'## 매출.*?(?=##|\Z)', content, re.DOTALL)
    if revenue_section:
        section_text = revenue_section.group()
        revenue_match = re.search(r'매출액.*?([\d,]+(?:\.\d+)?)\s*억', section_text)
        if revenue_match:
            data.revenue = float(revenue_match.group(1).replace(',', ''))
    
    # 출처 URLs
    sources = re.findall(r'https?://[^\s\)]+', content)
    data.sources = list(set(sources))
    
    return data


def validate_company(data: CompanyData, file_path: Path) -> ValidationResult:
    """Validate company data and generate risk flags."""
    result = ValidationResult(
        file_path=file_path,
        company_name=data.name,
        data=data,
    )
    
    # Check required fields
    fields_present = 0
    total_fields = len(REQUIRED_FIELDS)
    
    for field_name, display_name in REQUIRED_FIELDS:
        value = getattr(data, field_name, None)
        if value is None:
            result.issues.append(ValidationIssue(
                field=field_name,
                severity="warning",
                message=f"{display_name} 누락"
            ))
        else:
            fields_present += 1
    
    # Startup-specific fields
    if data.is_startup:
        total_fields += len(STARTUP_REQUIRED_FIELDS)
        for field_name, display_name in STARTUP_REQUIRED_FIELDS:
            value = getattr(data, field_name, None)
            if value is None:
                result.issues.append(ValidationIssue(
                    field=field_name,
                    severity="warning",
                    message=f"[스타트업] {display_name} 누락"
                ))
            else:
                fields_present += 1
    
    # Calculate completeness
    result.completeness_score = (fields_present / total_fields * 100) if total_fields > 0 else 0
    
    # === RISK FLAGS ===
    
    # 1. Turnover rate
    if data.employee_current and data.employee_left_1y:
        turnover_rate = data.employee_left_1y / data.employee_current
        
        if turnover_rate >= RISK_THRESHOLDS["turnover_critical"]:
            result.risk_flags.append(RiskFlag(
                code="TURNOVER_CRITICAL",
                severity="critical",
                message=f"퇴사율 {turnover_rate:.0%} - 1년간 {data.employee_left_1y}명 퇴사 (현재 {data.employee_current}명)",
                value=f"{turnover_rate:.0%}"
            ))
        elif turnover_rate >= RISK_THRESHOLDS["turnover_high"]:
            result.risk_flags.append(RiskFlag(
                code="TURNOVER_HIGH",
                severity="high",
                message=f"퇴사율 {turnover_rate:.0%} - 조직 불안정 우려",
                value=f"{turnover_rate:.0%}"
            ))
        elif turnover_rate >= RISK_THRESHOLDS["turnover_medium"]:
            result.risk_flags.append(RiskFlag(
                code="TURNOVER_MEDIUM",
                severity="medium",
                message=f"퇴사율 {turnover_rate:.0%}",
                value=f"{turnover_rate:.0%}"
            ))
    
    # 2. Net headcount change
    if data.employee_joined_1y is not None and data.employee_left_1y is not None:
        net_change = data.employee_joined_1y - data.employee_left_1y
        if data.employee_current:
            net_change_pct = net_change / data.employee_current
            if net_change_pct < -0.2:
                result.risk_flags.append(RiskFlag(
                    code="SHRINKING_FAST",
                    severity="high",
                    message=f"순감소 {net_change}명 ({net_change_pct:.0%}) - 조직 축소 중",
                    value=f"{net_change}"
                ))
            elif net_change_pct < -0.1:
                result.risk_flags.append(RiskFlag(
                    code="SHRINKING",
                    severity="medium",
                    message=f"순감소 {net_change}명 - 인원 감소 추세",
                    value=f"{net_change}"
                ))
    
    # 3. MoM change
    if data.employee_mom_change is not None:
        if data.employee_mom_change <= RISK_THRESHOLDS["shrinking_high"] * 100:
            result.risk_flags.append(RiskFlag(
                code="MOM_DECLINE",
                severity="medium",
                message=f"월간 인원 {data.employee_mom_change:+.1f}% 변동",
                value=f"{data.employee_mom_change:+.1f}%"
            ))
    
    # 4. Salary percentile
    if data.salary_percentile:
        try:
            pct = int(data.salary_percentile)
            if pct > RISK_THRESHOLDS["salary_low_percentile"]:
                result.risk_flags.append(RiskFlag(
                    code="SALARY_LOW",
                    severity="medium",
                    message=f"평균연봉 상위 {pct}% - 업계 평균 이하",
                    value=f"상위 {pct}%"
                ))
        except ValueError:
            pass
    
    # 5. Young company (startup)
    if data.is_startup and data.founded_year:
        company_age = datetime.now().year - data.founded_year
        if company_age < RISK_THRESHOLDS["company_young"]:
            result.risk_flags.append(RiskFlag(
                code="EARLY_STAGE",
                severity="low",
                message=f"설립 {company_age}년차 - 초기 스타트업",
                value=f"{company_age}년"
            ))
    
    # 6. Missing critical data for startups
    if data.is_startup:
        if data.investment_round is None and data.investment_total is None:
            result.risk_flags.append(RiskFlag(
                code="NO_INVESTMENT_DATA",
                severity="medium",
                message="투자 정보 없음 - 검증 필요",
                value=None
            ))
    
    return result


def generate_report(results: List[ValidationResult]) -> str:
    """Generate validation report."""
    lines = [
        "# 기업정보 검증 리포트",
        f"\n*생성일: {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
        f"\n총 {len(results)}개 기업 분석\n",
        "---\n",
    ]
    
    # Summary
    critical_count = sum(1 for r in results if any(f.severity == "critical" for f in r.risk_flags))
    high_count = sum(1 for r in results if any(f.severity == "high" for f in r.risk_flags))
    incomplete_count = sum(1 for r in results if r.completeness_score < 70)
    
    lines.extend([
        "## 요약\n",
        f"| 항목 | 수치 |",
        f"|------|------|",
        f"| 🚨 Critical 리스크 | {critical_count}개 |",
        f"| ⚠️ High 리스크 | {high_count}개 |",
        f"| 📝 불완전 데이터 (<70%) | {incomplete_count}개 |",
        f"| ✅ 완전 데이터 (≥70%) | {len(results) - incomplete_count}개 |",
        "\n---\n",
    ])
    
    # Critical/High risk companies
    risky = [r for r in results if any(f.severity in ("critical", "high") for f in r.risk_flags)]
    if risky:
        lines.extend([
            "## 🚨 주의 필요 기업\n",
        ])
        for r in sorted(risky, key=lambda x: -len([f for f in x.risk_flags if f.severity in ("critical", "high")])):
            flags = [f for f in r.risk_flags if f.severity in ("critical", "high")]
            lines.append(f"### {r.company_name}\n")
            for flag in flags:
                icon = "🚨" if flag.severity == "critical" else "⚠️"
                lines.append(f"- {icon} **{flag.code}**: {flag.message}")
            lines.append("")
    
    # Incomplete data
    incomplete = [r for r in results if r.completeness_score < 70]
    if incomplete:
        lines.extend([
            "\n## 📝 데이터 보완 필요\n",
            "| 기업 | 완성도 | 누락 필드 |",
            "|------|--------|----------|",
        ])
        for r in sorted(incomplete, key=lambda x: x.completeness_score):
            missing = [i.message for i in r.issues if i.severity == "warning"]
            lines.append(f"| {r.company_name} | {r.completeness_score:.0f}% | {', '.join(missing[:3])}{'...' if len(missing) > 3 else ''} |")
    
    # All companies summary
    lines.extend([
        "\n---\n",
        "## 전체 기업 현황\n",
        "| 기업 | 완성도 | 리스크 | 스타트업 |",
        "|------|--------|--------|----------|",
    ])
    for r in sorted(results, key=lambda x: x.company_name):
        risk_icons = ""
        if any(f.severity == "critical" for f in r.risk_flags):
            risk_icons += "🚨"
        if any(f.severity == "high" for f in r.risk_flags):
            risk_icons += "⚠️"
        if any(f.severity == "medium" for f in r.risk_flags):
            risk_icons += "⚡"
        startup = "✓" if r.data.is_startup else ""
        lines.append(f"| {r.company_name} | {r.completeness_score:.0f}% | {risk_icons or '✅'} | {startup} |")
    
    return "\n".join(lines)


def add_risk_section_to_file(file_path: Path, result: ValidationResult) -> str:
    """Generate risk section to add to company file."""
    if not result.risk_flags:
        return ""
    
    lines = [
        "\n## ⚠️ 리스크 플래그\n",
        "| 수준 | 코드 | 내용 |",
        "|------|------|------|",
    ]
    
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    severity_icons = {"critical": "🚨", "high": "⚠️", "medium": "⚡", "low": "ℹ️"}
    
    for flag in sorted(result.risk_flags, key=lambda x: severity_order.get(x.severity, 99)):
        icon = severity_icons.get(flag.severity, "")
        lines.append(f"| {icon} {flag.severity.upper()} | {flag.code} | {flag.message} |")
    
    lines.append(f"\n*자동 생성: {datetime.now().strftime('%Y-%m-%d')}*\n")
    
    return "\n".join(lines)


def validation_result_to_dict(result: ValidationResult) -> dict:
    """Convert validation result to JSON-serializable dict."""
    data = asdict(result)
    data["file_path"] = str(result.file_path)
    return data


def main():
    parser = argparse.ArgumentParser(description="기업정보 검증 및 리스크 플래깅")
    parser.add_argument("--file", "-f", help="단일 파일 검증")
    parser.add_argument("--fix", action="store_true", help="리스크 섹션 자동 추가")
    parser.add_argument("--report", action="store_true", help="전체 리포트 생성")
    parser.add_argument("--json", action="store_true", help="JSON 출력")
    
    args = parser.parse_args()
    
    # Get files to process
    if args.file:
        files = [Path(args.file)]
        if not files[0].exists():
            files = [COMPANY_INFO_DIR / args.file]
    else:
        files = list(COMPANY_INFO_DIR.glob("*.md"))
        files = [f for f in files if not f.name.startswith("_")]  # Exclude meta files
    
    results = []
    errors = []
    fixed_files = []
    for file_path in files:
        try:
            data = parse_company_file(file_path)
            result = validate_company(data, file_path)
            results.append(result)
            
            # Print individual result
            if not args.json and (args.file or not args.report):
                print(f"\n{'='*60}")
                print(f"📊 {result.company_name} ({file_path.name})")
                print(f"{'='*60}")
                print(f"완성도: {result.completeness_score:.0f}%")
                print(f"스타트업: {'Yes' if data.is_startup else 'No'}")
                
                if result.issues:
                    print(f"\n📝 누락 필드:")
                    for issue in result.issues:
                        print(f"   - {issue.message}")
                
                if result.risk_flags:
                    print(f"\n⚠️ 리스크 플래그:")
                    for flag in result.risk_flags:
                        icon = {"critical": "🚨", "high": "⚠️", "medium": "⚡", "low": "ℹ️"}.get(flag.severity, "")
                        print(f"   {icon} [{flag.code}] {flag.message}")
                
                # Fix mode - add risk section
                if args.fix and result.risk_flags:
                    risk_section = add_risk_section_to_file(file_path, result)
                    content = file_path.read_text(encoding='utf-8')
                    
                    # Remove existing risk section if present
                    content = re.sub(r'\n## ⚠️ 리스크 플래그.*?(?=\n## |\n---|\Z)', '', content, flags=re.DOTALL)
                    
                    # Add before sources section or at end
                    if '\n---\n\n*추출일:' in content:
                        content = content.replace('\n---\n\n*추출일:', f'{risk_section}\n---\n\n*추출일:')
                    else:
                        content += risk_section
                    
                    file_path.write_text(content, encoding='utf-8')
                    fixed_files.append(str(file_path))
                    if not args.json:
                        print(f"\n✅ 리스크 섹션 추가됨")
                    
        except Exception as e:
            errors.append({"file": str(file_path), "error": str(e)})
            if not args.json:
                print(f"❌ Error processing {file_path}: {e}")
    
    # Generate report
    report_path = None
    if args.report and results:
        report = generate_report(results)
        REPORT_PATH.write_text(report, encoding='utf-8')
        report_path = str(REPORT_PATH)
        if not args.json:
            print(f"\n📄 리포트 생성: {REPORT_PATH}")
            print(report)

    if args.json:
        payload = {
            "generated_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "summary": {
                "processed_files": len(results),
                "error_files": len(errors),
                "critical_risk_companies": sum(1 for r in results if any(f.severity == "critical" for f in r.risk_flags)),
                "high_risk_companies": sum(1 for r in results if any(f.severity == "high" for f in r.risk_flags)),
                "incomplete_companies": sum(1 for r in results if r.completeness_score < 70),
            },
            "results": [validation_result_to_dict(r) for r in results],
            "errors": errors,
            "fixed_files": fixed_files,
            "report_path": report_path,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
