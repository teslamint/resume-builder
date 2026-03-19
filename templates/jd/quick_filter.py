#!/usr/bin/env python3
"""타이틀 기반 빠른 필터링"""
import json
import sys
import re
from pathlib import Path

def load_config():
    """필터 조건 반환"""
    return {
        "quick_filters": {
            "title_include": [
                "백엔드", "Backend", "Back-end", "Back End",
                "개발자", "Developer", "엔지니어", "Engineer",
                "서버", "Server", "Software"
            ],
            "title_exclude": [
                "인턴", "주니어", "Junior", "신입", "리더", "CTO", "VP", "Head of",
                "프론트엔드", "Frontend", "풀스택", "Infra", "인프라",
                "데브옵스", "DevOps", "SRE", "QA", "팀장", "리드", "Lead",
                "프리랜서", "기술영업", "세일즈"
            ]
        }
    }

def apply_quick_filter(batch_result, config):
    """
    빠른 필터 적용
    Returns: (pass_filter: bool, reason: str)
    """
    title = batch_result["title"]
    leader = batch_result.get("leader", False)

    quick = config["quick_filters"]
    include_keywords = quick["title_include"]
    exclude_keywords = quick["title_exclude"]

    # 1. Leader 포지션 체크
    if leader:
        return False, "리더 포지션"

    # 2. Exclude 키워드 체크
    for keyword in exclude_keywords:
        if re.search(keyword, title, re.IGNORECASE):
            return False, f"제외 키워드: {keyword}"

    # 3. Include 키워드 체크
    has_include = False
    for keyword in include_keywords:
        if re.search(keyword, title, re.IGNORECASE):
            has_include = True
            break

    if not has_include:
        return False, "필수 키워드 없음"

    return True, "통과"

def main():
    batch_file = Path("private/job_postings/unprocessed/batch_results.json")
    if not batch_file.exists():
        print("batch_results.json not found")
        sys.exit(1)

    with open(batch_file) as f:
        results = json.load(f)

    config = load_config()

    passed = []
    filtered = []

    for item in results:
        ok, reason = apply_quick_filter(item, config)
        if ok:
            passed.append(item)
        else:
            filtered.append({**item, "filter_reason": reason})

    print(f"총 {len(results)}건 처리")
    print(f"  - 통과: {len(passed)}건")
    print(f"  - 필터: {len(filtered)}건")
    print()

    # 필터된 파일 이동
    if filtered:
        print(f"필터된 {len(filtered)}건을 pass/로 이동:")
        pass_dir = Path("private/job_postings/pass")
        pass_dir.mkdir(exist_ok=True)
        unprocessed_dir = Path("private/job_postings/unprocessed")

        for item in filtered:
            src = unprocessed_dir / item["file"]
            dst = pass_dir / item["file"]
            if src.exists():
                src.rename(dst)
                print(f"  - {item['file']} ({item['filter_reason']})")

    print()
    print(f"스크리닝 대상: {len(passed)}건")
    for item in passed:
        print(f"  - {item['id']}: {item['company']} - {item['title']}")

    # 통과한 파일 목록 저장
    passed_file = Path("private/job_postings/unprocessed/passed.json")
    with open(passed_file, "w") as f:
        json.dump(passed, f, ensure_ascii=False, indent=2)

    print()
    print(f"통과 목록 저장: {passed_file}")

if __name__ == "__main__":
    main()
