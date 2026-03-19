#!/usr/bin/env python3
"""경력기술서(Career Description) 빌더.

이력서와 별도로 모든 경력을 상세하게 기재한 경력기술서를 생성한다.
- 모든 회사/프로젝트 포함 (variant_config 무시)
- public variant 콘텐츠 사용 (구체적 수치/성과 포함)
- 최신순 정렬
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

try:
    from resume_builder import (
        _BASE_DIR,
        filter_content,
        extract_company_info_full,
        extract_section,
        calculate_tenure,
    )
except ImportError:
    from templates.build.resume_builder import (
        _BASE_DIR,
        filter_content,
        extract_company_info_full,
        extract_section,
        calculate_tenure,
    )

VARIANT = 'public'

CONTACT_LABELS = {
    'Name': '이름',
    'Email': '이메일',
    'Phone': '연락처',
    'GitHub': 'GitHub',
    'LinkedIn': 'LinkedIn',
}


def discover_all_companies(base_dir: Path) -> list[Path]:
    """companies/ 디렉토리의 모든 회사를 Period 기준 최신순 정렬."""
    companies_dir = base_dir / 'companies'
    if not companies_dir.exists():
        return []

    company_dirs = [
        d for d in sorted(companies_dir.iterdir())
        if d.is_dir() and (d / 'profile.md').exists()
    ]

    def parse_start_date(company_dir: Path) -> datetime:
        with open(company_dir / 'profile.md', 'r', encoding='utf-8') as f:
            content = f.read()
        info = extract_company_info_full(content)
        period = info.get('period', '')
        parts = period.split(' - ')
        if not parts:
            return datetime.min
        try:
            date_parts = parts[0].strip().split('.')
            year = int(date_parts[0])
            month = int(date_parts[1]) if len(date_parts) > 1 else 1
            return datetime(year, month, 1)
        except (ValueError, IndexError):
            return datetime.min

    company_dirs.sort(key=parse_start_date, reverse=True)
    return company_dirs


def build_contact(base_dir: Path) -> str:
    """인적사항 섹션 생성."""
    contact_path = base_dir / 'profile' / 'contact.md'
    if not contact_path.exists():
        return ''

    with open(contact_path, 'r', encoding='utf-8') as f:
        content = f.read()

    parts = ['## 인적사항']
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith('# ') or not stripped:
            continue
        if stripped.startswith('- '):
            field = stripped[2:]
            key, _, value = field.partition(':')
            key = key.strip()
            value = value.strip()
            label = CONTACT_LABELS.get(key, key)
            parts.append(f'- {label}: {value}')

    return '\n'.join(parts) if len(parts) > 1 else ''


def build_career_project(project_path: Path, index: int) -> str:
    """프로젝트 상세 섹션 생성."""
    with open(project_path, 'r', encoding='utf-8') as f:
        raw_content = f.read()

    content = filter_content(raw_content, VARIANT)

    title = ''
    for line in content.splitlines():
        if line.startswith('# '):
            title = line[2:].strip()
            break

    parts = [f'### 프로젝트 {index}: {title}']

    overview = extract_section(content, 'Overview')
    for line in overview.splitlines():
        stripped = line.strip()
        if stripped.startswith('- Period:'):
            parts.append(f'- 기간: {stripped.split(":", 1)[1].strip()}')
        elif stripped.startswith('- Type:'):
            parts.append(f'- 유형: {stripped.split(":", 1)[1].strip()}')

    summary = extract_section(content, 'Summary')
    if summary.strip():
        summary_oneline = ' '.join(summary.strip().splitlines())
        parts.append(f'- 개요: {summary_oneline}')

    tech_section = extract_section(content, 'Tech Stack')
    if tech_section.strip():
        tech_items = [l[2:].strip() for l in tech_section.splitlines() if l.strip().startswith('- ')]
        if tech_items:
            parts.append(f'- 기술스택: {", ".join(tech_items)}')

    resp_section = extract_section(content, 'Key Responsibilities')
    if resp_section.strip():
        parts.append('- 상세 업무:')
        for line in resp_section.splitlines():
            if line.strip():
                parts.append(f'  {line}')

    ach_section = extract_section(content, 'Achievements')
    if ach_section.strip():
        parts.append('- 성과:')
        for line in ach_section.splitlines():
            if line.strip():
                parts.append(f'  {line}')

    return '\n'.join(parts)


def build_career_company(company_dir: Path) -> str:
    """회사별 경력기술 섹션 생성."""
    with open(company_dir / 'profile.md', 'r', encoding='utf-8') as f:
        raw_profile = f.read()

    profile_content = filter_content(raw_profile, VARIANT)
    info = extract_company_info_full(profile_content)

    parts = [f'## {info["name"]}']

    tenure = calculate_tenure(info['period'])
    parts.append(f'- 기간: {tenure}')
    parts.append(f'- 역할: {info["role"]}')
    if info.get('employment'):
        parts.append(f'- 고용형태: {info["employment"]}')
    if info.get('position'):
        parts.append(f'- 직급: {info["position"]}')

    for line in profile_content.splitlines():
        if line.strip().startswith('- Department:'):
            parts.append(f'- 부서: {line.strip().split(":", 1)[1].strip()}')
            break

    summary = extract_section(profile_content, 'Summary')
    if summary.strip():
        summary_oneline = ' '.join(summary.strip().splitlines())
        parts.append(f'- 담당업무: {summary_oneline}')

    resp = extract_section(profile_content, 'Key Responsibilities')
    if resp.strip():
        parts.append('- 주요 책임:')
        for line in resp.splitlines():
            if line.strip():
                parts.append(f'  {line}')

    tech = extract_section(profile_content, 'Tech Stack')
    if tech.strip():
        tech_items = [l[2:].strip() for l in tech.splitlines() if l.strip().startswith('- ')]
        if tech_items:
            parts.append(f'- 기술스택: {", ".join(tech_items)}')

    projects_dir = company_dir / 'projects'
    if projects_dir.exists():
        project_files = sorted(
            (p for p in projects_dir.glob('*.md') if p.name != 'CLAUDE.md'),
            key=lambda p: p.name,
        )
        for i, project_file in enumerate(project_files, 1):
            parts.append('')
            parts.append(build_career_project(project_file, i))

    return '\n'.join(parts)


def build_career(base_dir: Path, format_type: str = 'md') -> str:
    """전체 경력기술서 조합."""
    parts = ['# 경력기술서']

    contact = build_contact(base_dir)
    if contact:
        parts.append(contact)

    companies = discover_all_companies(base_dir)
    if not companies:
        parts.append('\n(등록된 경력 없음)')
        return '\n\n'.join(parts)

    for company_dir in companies:
        parts.append(build_career_company(company_dir))

    separator = '\n\n' if format_type == 'pdf' else '\n\n---\n\n'
    return separator.join(parts)


def main():
    parser = argparse.ArgumentParser(description='경력기술서 빌더')
    parser.add_argument('-o', '--output', help='출력 파일 (기본: stdout)')
    parser.add_argument('--format', choices=['md', 'pdf'], default='md',
                        help='출력 포맷 (md: 표준, pdf: PDF 최적화)')
    parser.add_argument('--example', action='store_true',
                        help='example/ 디렉토리 데이터 사용')
    args = parser.parse_args()

    if args.example:
        base_dir = _BASE_DIR / 'example'
    else:
        base_dir = _BASE_DIR

    result = build_career(base_dir, args.format)

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(result)
        print(f"Written to {args.output}", file=sys.stderr)
    else:
        print(result)


if __name__ == '__main__':
    main()
