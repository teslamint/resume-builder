#!/usr/bin/env python3
"""회사 정보 누락 체크"""
import json
from pathlib import Path

def slugify(company_name):
    """회사명을 파일명 슬러그로 변환"""
    import re
    text = re.sub(r'\(주\)|\(주 \)', '', company_name).strip()
    text = re.sub(r'[^a-zA-Z0-9가-힣]', ' ', text).strip()
    parts = text.lower().split()
    return '-'.join(parts)[:50]

def main():
    # Remember 통과 목록
    with open("private/job_postings/unprocessed/passed.json") as f:
        remember_passed = json.load(f)

    # Wanted 목록
    with open("private/job_postings/unprocessed/wanted_batch.json") as f:
        wanted_jobs = json.load(f)

    # 전체 회사 목록 (중복 제거)
    companies = set()
    for job in remember_passed + wanted_jobs:
        companies.add(job["company"])

    # company_info 디렉토리 확인
    company_info_dir = Path("private/company_info")
    existing_companies = set()

    if company_info_dir.exists():
        for md_file in company_info_dir.glob("*.md"):
            existing_companies.add(md_file.stem)

    # 누락된 회사 확인
    missing_companies = []
    for company in sorted(companies):
        slug = slugify(company)
        if slug not in existing_companies:
            missing_companies.append(company)

    print(f"총 회사 수: {len(companies)}")
    print(f"기존 회사: {len(existing_companies)}")
    print(f"누락 회사: {len(missing_companies)}")
    print()

    if missing_companies:
        print("추출 필요한 회사 목록:")
        for company in missing_companies:
            print(f"  - {company}")
    else:
        print("모든 회사 정보가 존재합니다!")

    # 누락 목록 저장
    with open("private/job_postings/unprocessed/missing_companies.json", "w") as f:
        json.dump(missing_companies, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
