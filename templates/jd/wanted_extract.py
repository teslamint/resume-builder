#!/usr/bin/env python3
"""Wanted 채용공고 추출 스크립트"""
import json
import re
import sys
import urllib.request
from pathlib import Path

def slugify(text):
    text = re.sub(r'\(주\)|\(주 \)', '', text).strip()
    text = re.sub(r'[^a-zA-Z0-9가-힣]', ' ', text).strip()
    parts = text.lower().split()
    return '-'.join(parts)[:50]

def fetch_wanted_posting(job_id):
    """Wanted 채용공고 API 호출"""
    url = f'https://www.wanted.co.kr/wd/{job_id}'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=15) as resp:
        html = resp.read().decode('utf-8')

    # __NEXT_DATA__ JSON 추출
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>([\s\S]*?)</script>', html)
    if not m:
        return None

    data = json.loads(m.group(1))

    # Wanted 구조: props.pageProps.initialData
    job_detail = data['props']['pageProps']['initialData']
    return job_detail

def format_experience_wanted(job):
    """경력 포맷팅"""
    career = job.get('career', {})
    min_exp = career.get('annual_from')
    max_exp = career.get('annual_to')

    if min_exp == 0 and max_exp == 0:
        return "신입"
    elif min_exp and max_exp:
        return f"{min_exp}~{max_exp}년"
    elif min_exp:
        return f"{min_exp}년 이상"
    return "경력"

def extract_wanted(job_id):
    """Wanted 공고 추출 및 MD 저장"""
    print(f"Extracting Wanted job {job_id}...", file=sys.stderr)

    try:
        job = fetch_wanted_posting(job_id)
        if not job:
            print(f"SKIP: {job_id} - Failed to fetch", file=sys.stderr)
            return None

        # 필드 추출
        job_title = job.get('position', 'Unknown')
        company = job.get('company', {})
        company_name = company.get('company_name', 'Unknown')
        experience = format_experience_wanted(job)
        address = job.get('address', {})
        location = address.get('full_location', '정보 없음')

        # 본문
        intro = job.get('intro', '')
        main_tasks = job.get('main_tasks', '')
        requirements = job.get('requirements', '')
        preferred = job.get('preferred_points', '')
        benefits = job.get('benefits', '')

        # 파일명 생성
        company_slug = slugify(company_name)
        title_slug = slugify(job_title)
        filename = f"{job_id}-{company_slug}-{title_slug}.md"

        # Markdown 생성
        content = f"""---
job_id: {job_id}
source: wanted
url: https://www.wanted.co.kr/wd/{job_id}
---

# {job_title}

## 기본 정보
- 회사: {company_name}
- 경력: {experience}
- 근무지: {location}

## 소개
{intro}

## 주요 업무
{main_tasks}

## 자격 요건
{requirements}

## 우대 사항
{preferred}

## 혜택 및 복지
{benefits}
"""

        # 저장
        output_dir = Path("private/job_postings/unprocessed")
        output_dir.mkdir(exist_ok=True, parents=True)
        output_path = output_dir / filename

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)

        print(f"OK: {job_id} -> {filename}", file=sys.stderr)

        return {
            "id": job_id,
            "company": company_name,
            "title": job_title,
            "file": filename,
            "status": "ok"
        }

    except Exception as e:
        print(f"ERROR: {job_id} - {e}", file=sys.stderr)
        return None

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 wanted_extract.py <job_id1> [job_id2] ...")
        sys.exit(1)

    job_ids = sys.argv[1:]
    results = []

    for job_id in job_ids:
        result = extract_wanted(job_id)
        if result:
            results.append(result)

    # 결과 출력
    print(json.dumps(results, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
