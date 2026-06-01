#!/usr/bin/env python3
"""Remember 채용공고 일괄 추출 스크립트"""
import json
import logging
import re
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

try:
    from .http_client_base import DEFAULT_USER_AGENT, http_text_request
    from .naming import slugify_company as _slugify
except ImportError:
    from http_client_base import DEFAULT_USER_AGENT, http_text_request
    from naming import slugify_company as _slugify

logger = logging.getLogger(__name__)

def _fetch_with_urllib(url):
    return http_text_request(url, timeout=15)


def _fetch_with_curl(url):
    result = subprocess.run(
        ['curl', '-sS', '-m', '15', '-H', f'User-Agent: {DEFAULT_USER_AGENT}', url],
        capture_output=True, text=True, timeout=20,
    )
    if result.returncode != 0:
        raise RuntimeError(f'curl failed: {result.stderr.strip()}')
    return result.stdout


def fetch_posting(posting_id):
    url = f'https://career.rememberapp.co.kr/job/posting/{posting_id}'
    try:
        html = _fetch_with_urllib(url)
    except OSError:
        html = _fetch_with_curl(url)
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>([\s\S]*?)</script>', html)
    if not m:
        return None
    data = json.loads(m.group(1))
    return data['props']['pageProps']['dehydratedState']['queries'][0]['state']['data']['data']

def extract_posting_id(url):
    for pattern in (r'/job/posting/(\d+)(?:[/?#]|$)', r'/job/(\d+)(?:[/?#]|$)'):
        m = re.search(pattern, url)
        if m:
            return m.group(1)
    return None

def format_experience(d):
    min_exp = d.get('minExperience')
    max_exp = d.get('maxExperience')
    if min_exp and max_exp:
        return f"{min_exp}~{max_exp}년"
    elif min_exp:
        return f"{min_exp}년 이상"
    return "경력"

def format_salary(d):
    min_s = d.get('minSalary')
    max_s = d.get('maxSalary')
    if min_s and max_s:
        return f"{min_s}~{max_s}만원"
    elif min_s:
        return f"{min_s}만원 이상"
    elif max_s:
        return f"~{max_s}만원"
    return "협의"

def format_address(d):
    addrs = d.get('addresses', [])
    if addrs:
        return ', '.join(f"{a.get('addressLevel1','')} {a.get('addressLevel2','')}" for a in addrs)
    return ""

def to_markdown(d, posting_id):
    org = d.get('organization', {})
    company_name = org.get('name', '').replace('(주)', '').replace('(주 )', '').strip()
    title = d.get('title', '')
    intro = d.get('introduction', '') or ''
    desc = d.get('jobDescription', '') or ''
    quals = d.get('qualifications', '') or ''
    pref = d.get('preferredQualifications', '') or ''
    process = d.get('recruitingProcess', '') or ''
    additional = d.get('additionalInformation', '') or ''
    skills = d.get('desiredProfileCondition', {}).get('skills', [])
    skill_names = [s['name'] for s in skills] if skills else []
    chips = d.get('chips', [])
    chip_values = [c['value'] for c in chips] if chips else []
    tags = d.get('classifiedTags', [])
    tag_values = [t['value'] for t in tags] if tags else []
    leader = d.get('leaderPosition', False)
    rank = d.get('jobRankCategory', '')

    lines = []
    lines.append(f"# {title} - {company_name}")
    lines.append("")
    lines.append(f"- **회사**: {company_name}")
    lines.append(f"- **위치**: {format_address(d)}")
    lines.append(f"- **경력**: {format_experience(d)}")
    lines.append(f"- **연봉**: {format_salary(d)}")
    if rank:
        lines.append(f"- **직급**: {rank}")
    if leader:
        lines.append(f"- **리더 포지션**: 예")
    lines.append(f"- **URL**: https://career.rememberapp.co.kr/job/posting/{posting_id}")
    if skill_names:
        lines.append(f"- **기술스택**: {', '.join(skill_names)}")
    if chip_values:
        lines.append(f"- **기업정보**: {', '.join(chip_values)}")
    if tag_values:
        lines.append(f"- **복지**: {', '.join(tag_values)}")
    lines.append("")

    if intro:
        lines.append("## 회사 소개")
        lines.append("")
        lines.append(intro)
        lines.append("")

    if desc:
        lines.append("## 주요업무")
        lines.append("")
        lines.append(desc)
        lines.append("")

    if quals:
        lines.append("## 자격 요건")
        lines.append("")
        lines.append(quals)
        lines.append("")

    if pref:
        lines.append("## 우대사항")
        lines.append("")
        lines.append(pref)
        lines.append("")

    if process:
        lines.append("## 채용 절차")
        lines.append("")
        lines.append(process)
        lines.append("")

    if additional:
        lines.append("## 기타 안내")
        lines.append("")
        lines.append(additional)
        lines.append("")

    return '\n'.join(lines)

def main():
    url_file = sys.argv[1] if len(sys.argv) > 1 else None
    if not url_file:
        print("Usage: python remember_batch_extract.py <url_file>")
        sys.exit(1)

    urls = Path(url_file).read_text().strip().splitlines()
    unprocessed_dir = PROJECT_ROOT / 'private' / 'job_postings' / 'unprocessed'
    unprocessed_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for url in urls:
        url = url.strip()
        if not url:
            continue
        posting_id = extract_posting_id(url)
        if not posting_id:
            print(f"SKIP: invalid URL {url}")
            continue

        try:
            d = fetch_posting(posting_id)
            if not d:
                logger.error("ERR: %s - no data", posting_id)
                results.append({'id': posting_id, 'status': 'error', 'reason': 'no_data'})
                continue

            org = d.get('organization', {})
            company_raw = org.get('name', '')
            company_name = company_raw.replace('(주)', '').replace('(주 )', '').strip()
            title = d.get('title', '')
            company_slug = _slugify(company_name, max_len=50, fallback="")
            title_slug = _slugify(title, max_len=50, fallback="")[:30]

            filename = f"{posting_id}-{company_slug}-{title_slug}.md"
            filepath = unprocessed_dir / filename

            md = to_markdown(d, posting_id)
            filepath.write_text(md, encoding='utf-8')

            info = {
                'id': posting_id,
                'company': company_name,
                'title': title,
                'file': filename,
                'status': 'ok',
                'minExp': d.get('minExperience'),
                'maxExp': d.get('maxExperience'),
                'minSalary': d.get('minSalary'),
                'maxSalary': d.get('maxSalary'),
                'leader': d.get('leaderPosition', False),
                'rank': d.get('jobRankCategory', ''),
                'orgId': org.get('id'),
            }
            results.append(info)
            print(f"OK: {posting_id} -> {filename}")
            time.sleep(0.5)

        except (OSError, json.JSONDecodeError, KeyError, RuntimeError, subprocess.SubprocessError, TypeError, ValueError) as e:
            logger.error("ERR: %s - %s", posting_id, e)
            results.append({'id': posting_id, 'status': 'error', 'reason': str(e)})

    # Save results as JSON for further processing
    results_file = unprocessed_dir / 'batch_results.json'
    results_file.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"\n총 {len(results)}건 처리 완료. 결과: {results_file}")

if __name__ == '__main__':
    main()
