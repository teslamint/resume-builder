#!/usr/bin/env python3
import argparse
import glob
import json
import re
import sys
from datetime import datetime
from pathlib import Path

_BASE_DIR = Path(__file__).parent.parent
BASE_DIR = _BASE_DIR  # Will be updated if --example is used
_GLOBAL_TARGET: str | None = None
_EXAMPLE_MODE: bool = False

VARIANT_CONFIG = {
    'public': {
        'companies': ['company1', 'company2', 'co3', 'co4', 'company5', 'company6'],
        'include_certificates': True,
        'company_detail': {
            'company5': 'full',
            'company6': 'full',
        },
    },
    'job': {
        'companies': ['company1', 'company2', 'co3', 'co4', 'company5'],
        'include_certificates': False,
        'company_detail': {
            'co4': 'summary',
            'company5': 'summary',
        },
    },
}

EXAMPLE_VARIANT_CONFIG = {
    'public': {
        'companies': ['techcorp'],
        'include_certificates': True,
        'company_detail': {},
    },
    'job': {
        'companies': ['techcorp'],
        'include_certificates': False,
        'company_detail': {},
    },
}

def get_variant_config():
    """Return appropriate config based on example mode"""
    return EXAMPLE_VARIANT_CONFIG if _EXAMPLE_MODE else VARIANT_CONFIG

def load_target_config(target: str | None, variant: str) -> dict:
    """Load target-specific config overrides from overrides/<target>/config.json"""
    config = get_variant_config()
    base_config = config.get(variant, config['job']).copy()
    if not target:
        return base_config

    config_path = BASE_DIR / 'overrides' / target / 'config.json'
    if not config_path.exists():
        return base_config

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            target_config = json.load(f)

        # Merge target config into base config
        variant_overrides = target_config.get(variant, {})
        if 'company_detail' in variant_overrides:
            base_config['company_detail'] = {
                **base_config.get('company_detail', {}),
                **variant_overrides['company_detail']
            }
        if 'companies' in variant_overrides:
            base_config['companies'] = variant_overrides['companies']
        if 'include_certificates' in variant_overrides:
            base_config['include_certificates'] = variant_overrides['include_certificates']
        if 'include_awards' in variant_overrides:
            base_config['include_awards'] = variant_overrides['include_awards']
        if 'include_languages' in variant_overrides:
            base_config['include_languages'] = variant_overrides['include_languages']

        return base_config
    except (json.JSONDecodeError, IOError):
        return base_config

def resolve_path(base_path: Path, target: str | None) -> Path:
    """target override 파일이 있으면 그 경로, 없으면 원본 경로 반환"""
    if not target:
        return base_path
    if not base_path.exists():
        return base_path
    try:
        relpath = base_path.relative_to(BASE_DIR)
    except ValueError:
        return base_path
    override = BASE_DIR / 'overrides' / target / relpath
    if override.exists():
        return override
    return base_path


def read_file(path, target=None):
    t = target if target is not None else _GLOBAL_TARGET
    resolved = resolve_path(Path(path), t)
    with open(resolved, 'r', encoding='utf-8') as f:
        return f.read()


def filter_content(content, variant):
    """Filter content based on variant tags.

    Tags:
    - <!-- job-only:start --> ... <!-- job-only:end -->
    - <!-- public-only:start --> ... <!-- public-only:end -->
    - <!-- common:start --> ... <!-- common:end -->

    Rules:
    - job variant: includes job-only, common, untagged content; excludes public-only
    - public variant: includes public-only, common, untagged content; excludes job-only
    - Tag lines are removed from output
    - Unclosed tags raise ValueError
    """
    lines = content.split('\n')
    result = []
    current_block = None
    block_start_line = None

    include_map = {
        'job': {'job-only', 'common'},
        'public': {'public-only', 'common'},
    }
    include_tags = include_map.get(variant, {'common'})

    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        if stripped == '<!-- job-only:start -->':
            if current_block is not None:
                raise ValueError(f"Line {i}: nested tag '<!-- job-only:start -->' inside '{current_block}' block")
            current_block = 'job-only'
            block_start_line = i
            continue
        elif stripped == '<!-- job-only:end -->':
            if current_block != 'job-only':
                raise ValueError(f"Line {i}: '<!-- job-only:end -->' without matching start tag")
            current_block = None
            block_start_line = None
            continue
        elif stripped == '<!-- public-only:start -->':
            if current_block is not None:
                raise ValueError(f"Line {i}: nested tag '<!-- public-only:start -->' inside '{current_block}' block")
            current_block = 'public-only'
            block_start_line = i
            continue
        elif stripped == '<!-- public-only:end -->':
            if current_block != 'public-only':
                raise ValueError(f"Line {i}: '<!-- public-only:end -->' without matching start tag")
            current_block = None
            block_start_line = None
            continue
        elif stripped == '<!-- common:start -->':
            if current_block is not None:
                raise ValueError(f"Line {i}: nested tag '<!-- common:start -->' inside '{current_block}' block")
            current_block = 'common'
            block_start_line = i
            continue
        elif stripped == '<!-- common:end -->':
            if current_block != 'common':
                raise ValueError(f"Line {i}: '<!-- common:end -->' without matching start tag")
            current_block = None
            block_start_line = None
            continue

        if current_block is None or current_block in include_tags:
            result.append(line)

    if current_block is not None:
        raise ValueError(f"Unclosed '{current_block}' block starting at line {block_start_line}")

    return '\n'.join(result)

def extract_overview(content):
    """Extract Overview section from company profile"""
    lines = content.split('\n')
    result = []
    in_overview = False
    for line in lines:
        if line.startswith('# '):
            result.append(line)
        elif line.startswith('## Overview'):
            in_overview = True
        elif line.startswith('## ') and in_overview:
            break
        elif in_overview:
            result.append(line)
    return '\n'.join(result).strip()

def build_profile(variant):
    config = load_target_config(_GLOBAL_TARGET, variant)
    parts = []
    profile_dir = BASE_DIR / 'profile'

    contact = profile_dir / 'contact.md'
    if contact.exists():
        parts.append(read_file(contact))

    summary = profile_dir / f'summary-{variant}.md'
    if summary.exists():
        parts.append(read_file(summary))

    skills = profile_dir / f'skills-{variant}.md'
    if skills.exists():
        parts.append(read_file(skills))

    education = profile_dir / 'education.md'
    if education.exists():
        parts.append(read_file(education))

    if config.get('include_awards', True):
        awards = profile_dir / 'awards.md'
        if awards.exists():
            parts.append(read_file(awards))

    if config.get('include_languages', True):
        languages = profile_dir / 'languages.md'
        if languages.exists():
            parts.append(read_file(languages))

    return parts

def build_profile_short(variant):
    parts = []
    profile_dir = BASE_DIR / 'profile'

    contact = profile_dir / 'contact.md'
    if contact.exists():
        parts.append(read_file(contact))

    summary = profile_dir / f'summary-{variant}.md'
    if summary.exists():
        parts.append(read_file(summary))

    skills = profile_dir / f'skills-{variant}.md'
    if skills.exists():
        content = read_file(skills)
        lines = content.split('\n')
        header = lines[0] if lines else '# Skills'
        techs = []
        for line in lines:
            if line.startswith('- '):
                tech = line[2:].strip()
                tech = re.sub(r'\s*\([^)]*\)', '', tech)
                if tech:
                    techs.append(tech)
        condensed = [header, ', '.join(techs)]
        parts.append('\n'.join(condensed))

    return parts

def build_company(company_dir, variant, target=None):
    t = target if target is not None else _GLOBAL_TARGET
    config = load_target_config(t, variant)
    company_name = company_dir.name
    detail_level = config.get('company_detail', {}).get(company_name, 'full')

    parts = []
    profile = company_dir / 'profile.md'

    if detail_level == 'summary':
        if profile.exists():
            content = filter_content(read_file(profile), variant)
            overview = extract_overview(content)
            if overview:
                parts.append(overview)
    else:
        if profile.exists():
            parts.append(filter_content(read_file(profile), variant))
        for p in sorted(glob.glob(str(company_dir / 'projects' / '*.md'))):
            if not p.endswith('CLAUDE.md'):
                content = filter_content(read_file(p), variant)
                if content.strip():
                    parts.append(content)
        for a in sorted(glob.glob(str(company_dir / 'achievements' / '*.md'))):
            if not a.endswith('CLAUDE.md'):
                content = filter_content(read_file(a), variant)
                if content.strip():
                    parts.append(content)

    return parts

def build_company_short(company_dir):
    """Build condensed company entry (overview only)"""
    profile = company_dir / 'profile.md'
    if profile.exists():
        content = read_file(profile)
        return extract_overview(content)
    return None

def extract_company_info(content):
    """Extract company name, period, role from profile"""
    lines = content.split('\n')
    name = ""
    period = ""
    role = ""
    for line in lines:
        if line.startswith('# '):
            name = line[2:].strip()
        elif line.startswith('- Period:'):
            period = line.split(':', 1)[1].strip()
        elif line.startswith('- Role:'):
            role = line.split(':', 1)[1].strip()
    return name, period, role


def extract_company_info_full(content):
    """Extract full company info including employment and position"""
    lines = content.split('\n')
    info = {'name': '', 'period': '', 'role': '', 'employment': '정규직', 'position': ''}
    for line in lines:
        if line.startswith('# '):
            info['name'] = line[2:].strip()
        elif line.startswith('- Period:'):
            info['period'] = line.split(':', 1)[1].strip()
        elif line.startswith('- Role:'):
            info['role'] = line.split(':', 1)[1].strip()
        elif line.startswith('- Employment:'):
            info['employment'] = line.split(':', 1)[1].strip()
        elif line.startswith('- Position:'):
            info['position'] = line.split(':', 1)[1].strip()
    return info


def calculate_tenure(period_str):
    """Calculate tenure from period string like '2023.10 - 현재' or '2020.09 - 2022.09'"""
    parts = period_str.split(' - ')
    if len(parts) != 2:
        return period_str

    start_str = parts[0].strip()
    end_str = parts[1].strip()

    try:
        start_parts = start_str.split('.')
        start_year = int(start_parts[0])
        start_month = int(start_parts[1]) if len(start_parts) > 1 else 1

        if end_str == '현재':
            end_date = datetime.now()
            end_year = end_date.year
            end_month = end_date.month
            end_label = '재직중'
        else:
            end_parts = end_str.split('.')
            end_year = int(end_parts[0])
            end_month = int(end_parts[1]) if len(end_parts) > 1 else 12
            end_label = end_str

        total_months = (end_year - start_year) * 12 + (end_month - start_month) + 1
        years = total_months // 12
        months = total_months % 12

        if years > 0 and months > 0:
            tenure = f"{years}년 {months}개월"
        elif years > 0:
            tenure = f"{years}년"
        else:
            tenure = f"{months}개월"

        return f"{start_str} - {end_label} ({tenure})"
    except (ValueError, IndexError):
        return period_str


def extract_section(content, section_name):
    """Extract content from a specific section (## or ###)"""
    lines = content.split('\n')
    result = []
    in_section = False
    section_level = 0

    for line in lines:
        if line.startswith('## ') or line.startswith('### '):
            current_level = 2 if line.startswith('## ') else 3
            section_title = line.lstrip('#').strip()
            if section_title == section_name:
                in_section = True
                section_level = current_level
                continue
            elif in_section and current_level <= section_level:
                break
        elif in_section:
            result.append(line)

    return '\n'.join(result).strip()


def extract_project_info(content):
    """Extract project info: title, period, tech_stack, achievements"""
    lines = content.split('\n')
    info = {'title': '', 'period': '', 'tech_stack': [], 'achievements': [], 'responsibilities': []}

    for line in lines:
        if line.startswith('## '):
            info['title'] = line[3:].strip()
            break

    info['period'] = extract_section(content, 'Period')

    tech_section = extract_section(content, 'Tech Stack')
    for line in tech_section.split('\n'):
        if line.startswith('- '):
            info['tech_stack'].append(line[2:].strip())

    ach_section = extract_section(content, 'Achievements')
    for line in ach_section.split('\n'):
        if line.startswith('- '):
            info['achievements'].append(line[2:].strip())
        elif line.startswith('**') and not line.startswith('- '):
            info['achievements'].append(line.strip())

    resp_section = extract_section(content, 'Responsibilities')
    for line in resp_section.split('\n'):
        if line.startswith('- '):
            info['responsibilities'].append(line[2:].strip())

    return info


def build_wanted(variant):
    """Build resume in Wanted format (plain text)"""
    variant_config = get_variant_config()
    config = variant_config.get(variant, variant_config['job'])
    profile_dir = BASE_DIR / 'profile'
    companies_dir = BASE_DIR / 'companies'
    lines = []

    # 1. Header: name + contact
    contact = profile_dir / 'contact.md'
    name = ""
    phone = ""
    email = ""
    github = ""
    if contact.exists():
        for line in read_file(contact).split('\n'):
            if line.startswith('- Name:'):
                name = line.split(':', 1)[1].strip()
            elif line.startswith('- Phone:'):
                phone = line.split(':', 1)[1].strip()
            elif line.startswith('- Email:'):
                email = line.split(':', 1)[1].strip()
            elif line.startswith('- GitHub:'):
                github = line.split(':', 1)[1].strip()

    lines.append(name)
    lines.append(f"📞 {phone}  @ {email}")
    lines.append("")

    # 2. Summary (intro)
    summary = profile_dir / f'summary-{variant}.md'
    if summary.exists():
        content = filter_content(read_file(summary), variant)
        for line in content.split('\n'):
            if line.startswith('# ') or line.startswith('## '):
                continue
            if line.strip():
                lines.append(line.strip())
        lines.append("")

    # 3. Experience
    lines.append("경력")
    lines.append("")

    for company_name in config['companies']:
        company_dir = companies_dir / company_name
        profile = company_dir / 'profile.md'
        if not profile.exists():
            continue

        content = filter_content(read_file(profile), variant)
        info = extract_company_info_full(content)

        # Company header
        lines.append(info['name'])
        tenure_str = calculate_tenure(info['period'])
        position_str = f" | {info['position']}" if info['position'] else ""
        lines.append(f"{tenure_str} | {info['employment']} | {info['role']}{position_str}")
        lines.append("")

        # Summary from profile (or inline text in Overview for summary companies)
        summary_text = extract_section(content, 'Summary')
        if summary_text:
            for line in summary_text.split('\n'):
                if line.strip() and not line.startswith('**'):
                    lines.append(line.strip())
            lines.append("")

        # Check for inline summary in Overview (for companies like CO4, Lee&Company)
        overview_text = extract_section(content, 'Overview')
        inline_summary_lines = []
        for line in overview_text.split('\n'):
            stripped = line.strip()
            if stripped and not stripped.startswith('- ') and not stripped.startswith('**'):
                inline_summary_lines.append(stripped)
        if inline_summary_lines and not summary_text:
            for line in inline_summary_lines:
                lines.append(line)
            lines.append("")

        # Key Responsibilities as bullet points
        key_resp = extract_section(content, 'Key Responsibilities')
        if key_resp:
            for line in key_resp.split('\n'):
                if line.strip():
                    # Remove markdown bold syntax
                    clean_line = line.replace('**', '')
                    lines.append(clean_line)
            lines.append("")

        # Key Experience (for summary companies)
        key_exp_in_overview = []
        in_key_exp = False
        for line in overview_text.split('\n'):
            if '**Key Experience**' in line:
                in_key_exp = True
                continue
            if in_key_exp and line.strip():
                key_exp_in_overview.append(line)
        if key_exp_in_overview:
            lines.append("Key Experience")
            for line in key_exp_in_overview:
                lines.append(line)
            lines.append("")

        # Projects
        detail_level = config.get('company_detail', {}).get(company_name, 'full')
        if detail_level == 'full':
            for p in sorted(glob.glob(str(company_dir / 'projects' / '*.md'))):
                if p.endswith('CLAUDE.md'):
                    continue
                proj_content = filter_content(read_file(p), variant)
                proj_info = extract_project_info(proj_content)

                if proj_info['title']:
                    lines.append(proj_info['title'])
                    if proj_info['period']:
                        lines.append(proj_info['period'])

                    # 기술스택: bullet 없이 출력
                    if proj_info['tech_stack']:
                        tech_str = ', '.join(proj_info['tech_stack'])
                        lines.append(f"기술스택: {tech_str}")

                    # Responsibilities: 문장 연결 (서술형)
                    if proj_info['responsibilities']:
                        resp_text = ' '.join(proj_info['responsibilities'])
                        lines.append(resp_text)

                    if proj_info['achievements']:
                        for ach in proj_info['achievements']:
                            # Remove markdown bold syntax
                            clean_ach = ach.replace('**', '')
                            if ach.startswith('**'):
                                lines.append(clean_ach)
                            else:
                                lines.append(f"- {clean_ach}")

                    lines.append("")

        lines.append("")

    # 4. Education
    lines.append("학력")
    lines.append("")
    education = profile_dir / 'education.md'
    if education.exists():
        content = read_file(education)
        school = ""
        period = ""
        major = ""
        status = ""
        for line in content.split('\n'):
            if line.startswith('## '):
                school = line[3:].strip()
            elif line.startswith('- Period:'):
                period = line.split(':', 1)[1].strip()
            elif line.startswith('- Major:'):
                major = line.split(':', 1)[1].strip()
            elif line.startswith('- Status:'):
                status = line.split(':', 1)[1].strip()
        lines.append(school)
        lines.append(f"{period} | {status} | {major}")
    lines.append("")

    # 5. Skills
    lines.append("스킬")
    lines.append("")
    skills = profile_dir / f'skills-{variant}.md'
    if skills.exists():
        content = read_file(skills)
        techs = []
        for line in content.split('\n'):
            if line.startswith('- '):
                tech = line[2:].strip()
                tech = re.sub(r'\s*\([^)]*\)', '', tech)
                if tech:
                    techs.append(tech)
        lines.append(' | '.join(techs))
    lines.append("")

    # 6. Awards/Certifications
    awards = profile_dir / 'awards.md'
    if awards.exists():
        lines.append("수상/자격증/기타")
        lines.append("")
        content = read_file(awards)
        award_name = ""
        award_period = ""
        award_desc = ""
        for line in content.split('\n'):
            if line.startswith('## '):
                award_name = line[3:].strip()
            elif line.startswith('- Period:'):
                award_period = line.split(':', 1)[1].strip()
            elif line.startswith('- Description:'):
                award_desc = line.split(':', 1)[1].strip()
        if award_name:
            lines.append(award_name)
            lines.append(award_period)
            if award_desc:
                lines.append(award_desc)
        lines.append("")

    # 7. Languages
    languages = profile_dir / 'languages.md'
    if languages.exists():
        lines.append("언어")
        lines.append("")
        content = read_file(languages)
        for line in content.split('\n'):
            if line.startswith('- '):
                lines.append(line[2:].strip())
        lines.append("")

    # 8. Links
    if github:
        lines.append("링크")
        lines.append("")
        lines.append(f"GitHub: {github}")
        lines.append("")

    return '\n'.join(lines)

def build_full(variant):
    config = load_target_config(_GLOBAL_TARGET, variant)
    parts = build_profile(variant)
    parts.append('# Experience')
    companies_dir = BASE_DIR / 'companies'

    for company in config['companies']:
        company_dir = companies_dir / company
        if company_dir.exists():
            parts.extend(build_company(company_dir, variant))

    return "\n\n---\n\n".join(parts)


def build_full_pdf(variant):
    """PDF layout for job variant: summary (includes name/title) → skills → experience → footer"""
    if variant != 'job':
        return build_full(variant)

    config = load_target_config(_GLOBAL_TARGET, variant)
    parts = []

    summary = BASE_DIR / 'profile' / f'summary-{variant}.md'
    if summary.exists():
        content = filter_content(read_file(summary), variant)
        if content.strip():
            parts.append(content)

    skills = BASE_DIR / 'profile' / f'skills-{variant}.md'
    if skills.exists():
        content = filter_content(read_file(skills), variant)
        if content.strip():
            parts.append(content)

    parts.append('# Experience')
    companies_dir = BASE_DIR / 'companies'
    for company in config['companies']:
        company_dir = companies_dir / company
        if company_dir.exists():
            company_parts = build_company(company_dir, variant)
            for part in company_parts:
                if part and part.strip():
                    parts.append(part)

    education = BASE_DIR / 'profile' / 'education.md'
    if education.exists():
        content = filter_content(read_file(education), variant)
        if content.strip():
            parts.append(content)

    if config.get('include_languages', True):
        languages = BASE_DIR / 'profile' / 'languages.md'
        if languages.exists():
            content = filter_content(read_file(languages), variant)
            if content.strip():
                parts.append(content)

    if config.get('include_awards', True):
        awards = BASE_DIR / 'profile' / 'awards.md'
        if awards.exists():
            content = filter_content(read_file(awards), variant)
            if content.strip():
                parts.append(content)

    return "\n\n".join(parts)

def build_short(variant):
    """Build 1-page summary resume"""
    variant_config = get_variant_config()
    config = variant_config.get(variant, variant_config['public'])
    parts = build_profile_short(variant)
    parts.append('# Experience\n')

    companies_dir = BASE_DIR / 'companies'

    table = ['| 회사 | 기간 | 역할 |', '|------|------|------|']
    for company in config['companies']:
        company_dir = companies_dir / company
        profile = company_dir / 'profile.md'
        if profile.exists():
            content = filter_content(read_file(profile), variant)
            name, period, role = extract_company_info(content)
            table.append(f'| {name} | {period} | {role} |')

    parts.append('\n'.join(table))

    education = BASE_DIR / 'profile' / 'education.md'
    if education.exists():
        content = read_file(education)
        lines = content.split('\n')
        edu_parts = ['# Education']
        school = ""
        period = ""
        major = ""
        for line in lines:
            if line.startswith('## '):
                school = line[3:].strip()
            elif line.startswith('- Period:'):
                period = line.split(':', 1)[1].strip()
            elif line.startswith('- Major:'):
                major = line.split(':', 1)[1].strip()
        edu_parts.append(f'{school} | {major} ({period})')
        parts.append('\n'.join(edu_parts))

    return '\n\n'.join(parts)


def build_short_pdf(variant):
    """PDF short layout for job variant: summary (includes name/title) → skills → experience table → education"""
    if variant != 'job':
        return build_short(variant)

    config = get_variant_config()['job']
    parts = []

    summary = BASE_DIR / 'profile' / f'summary-{variant}.md'
    if summary.exists():
        content = filter_content(read_file(summary), variant)
        if content.strip():
            parts.append(content)

    skills = BASE_DIR / 'profile' / f'skills-{variant}.md'
    if skills.exists():
        content = filter_content(read_file(skills), variant)
        lines = content.split('\n')
        techs = []
        for line in lines:
            if line.startswith('- '):
                tech = line[2:].strip()
                tech = re.sub(r'\s*\([^)]*\)', '', tech)
                tech = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', tech)
                tech = tech.replace('**', '').replace('`', '')
                if tech:
                    techs.append(tech)
        if techs:
            parts.append(f"# Skills\n{', '.join(techs)}")

    parts.append('# Experience\n')
    table = ['| 회사 | 기간 | 역할 |', '|------|------|------|']
    companies_dir = BASE_DIR / 'companies'
    for company in config['companies']:
        company_dir = companies_dir / company
        profile = company_dir / 'profile.md'
        if profile.exists():
            content = filter_content(read_file(profile), variant)
            name, period, role = extract_company_info(content)
            table.append(f'| {name} | {period} | {role} |')
    parts.append('\n'.join(table))

    education = BASE_DIR / 'profile' / 'education.md'
    if education.exists():
        content = filter_content(read_file(education), variant)
        lines = content.split('\n')
        school = period = major = ""
        for line in lines:
            if line.startswith('## '):
                school = line[3:].strip()
            elif line.startswith('- Period:'):
                period = line.split(':', 1)[1].strip()
            elif line.startswith('- Major:'):
                major = line.split(':', 1)[1].strip()
        if school:
            parts.append(f'# Education\n{school} | {major} ({period})')

    return '\n\n'.join(parts)

def build_for_company(company, variant):
    parts = build_profile(variant)
    parts.append('# Experience')
    company_dir = BASE_DIR / 'companies' / company
    if not company_dir.exists():
        raise ValueError(f"Company '{company}' not found")
    parts.extend(build_company(company_dir, variant))
    return "\n\n---\n\n".join(parts)

def main():
    parser = argparse.ArgumentParser(description='Build resume from modular markdown files')
    parser.add_argument('--variant', '-v', required=True, choices=['public', 'job'],
                        help='Resume variant (public or job)')
    parser.add_argument('company', nargs='?', help='Company name (optional, builds full resume if not specified)')
    parser.add_argument('-o', '--output', help='Output file (default: stdout)')
    parser.add_argument('--list', action='store_true', help='List available companies')
    parser.add_argument('--short', action='store_true', help='Build 1-page summary resume')
    parser.add_argument('--format', choices=['md', 'pdf', 'wanted'], default='md',
                        help='Output format (md: standard, pdf: PDF-optimized, wanted: Wanted site format)')
    parser.add_argument('--target', '-t', help='Target company for override files')
    parser.add_argument('--example', action='store_true',
                        help='Use example data from example/ directory')
    args = parser.parse_args()

    global _GLOBAL_TARGET, _EXAMPLE_MODE, BASE_DIR
    _GLOBAL_TARGET = args.target

    if args.example:
        _EXAMPLE_MODE = True
        BASE_DIR = _BASE_DIR / 'example'

    if args.list:
        variant_config = get_variant_config()
        config = variant_config.get(args.variant, variant_config['public'])
        companies_dir = BASE_DIR / 'companies'
        for company in config['companies']:
            company_dir = companies_dir / company
            if company_dir.is_dir() and (company_dir / 'profile.md').exists():
                print(company)
        return

    if args.format == 'wanted':
        result = build_wanted(args.variant)
    elif args.format == 'pdf':
        if args.short:
            result = build_short_pdf(args.variant)
        else:
            result = build_full_pdf(args.variant)
    elif args.short:
        result = build_short(args.variant)
    elif args.company:
        result = build_for_company(args.company, args.variant)
    else:
        result = build_full(args.variant)

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(result)
        print(f"Written to {args.output}")
    else:
        print(result)

if __name__ == "__main__":
    main()
