"""high/ 46건의 due_time을 Wanted/Remember API로 검증하고 마감 분류.

분류 기준:
- due_time = None → CLOSED_DEFINITE (closed/ 자동 이동)
- due_time 과거 60일+ → CLOSED_LIKELY (closed/ 이동 권장)
- due_time 과거 30~60일 → AGED (수동 확인)
- due_time 과거 0~30일 또는 미래 → ACTIVE
"""

from __future__ import annotations

import json
import re
import shutil
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HIGH = Path("private/job_postings/conditional/high")
CLOSED = Path("private/job_postings/closed")
SUMMARY = Path("private/jd_analysis/screening/SUMMARY.md")

NOW = datetime.now()


def fetch_wanted_due(job_id: str) -> tuple[str | None, str]:
    """Wanted job_id로 due_time 가져옴. (due_time, error)"""
    url = f'https://www.wanted.co.kr/wd/{job_id}'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode('utf-8')
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>([\s\S]*?)</script>', html)
        if not m:
            return None, "no __NEXT_DATA__"
        data = json.loads(m.group(1))
        job = data.get('props', {}).get('pageProps', {}).get('initialData', {})
        return job.get('due_time'), ""
    except Exception as e:
        return None, str(e)


def parse_due(due_str: str | None) -> datetime | None:
    if not due_str:
        return None
    try:
        return datetime.fromisoformat(due_str.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def classify(due_str: str | None) -> str:
    if due_str is None:
        return "CLOSED_DEFINITE"  # null due_time
    due = parse_due(due_str)
    if due is None:
        return "UNKNOWN"
    delta_days = (NOW - due).days
    if delta_days > 60:
        return "CLOSED_LIKELY"
    if delta_days > 30:
        return "AGED"
    if delta_days >= 0:
        return "RECENT_PAST"
    return "ACTIVE"


def main() -> None:
    results = []
    for jd in sorted(HIGH.glob("*.md")):
        text = jd.read_text(encoding="utf-8", errors="replace")
        # URL 추출
        m = re.search(r"https?://www\.wanted\.co\.kr/wd/(\d+)", text)
        if not m:
            results.append({"file": jd.name, "platform": "non-wanted", "category": "SKIP", "due": "N/A"})
            continue
        job_id = m.group(1)
        due_str, err = fetch_wanted_due(job_id)
        category = classify(due_str)
        results.append({
            "file": jd.name,
            "job_id": job_id,
            "due": due_str or "(null)",
            "category": category,
            "error": err,
        })

    # 카테고리별 분포
    print(f"\n총 {len(results)}건 검사 완료\n")
    from collections import Counter
    cat_count = Counter(r["category"] for r in results)
    for cat, n in cat_count.most_common():
        print(f"  {cat:20s} {n}건")

    print("\n=== CLOSED_DEFINITE (due_time=null, 즉시 closed/ 이동 후보) ===")
    for r in results:
        if r["category"] == "CLOSED_DEFINITE":
            print(f"  - {r['file']}")

    print("\n=== CLOSED_LIKELY (60일+ 과거) ===")
    for r in results:
        if r["category"] == "CLOSED_LIKELY":
            print(f"  - {r['file']}  (due: {r['due']})")

    print("\n=== AGED (30~60일 과거, 수동 확인) ===")
    for r in results:
        if r["category"] == "AGED":
            print(f"  - {r['file']}  (due: {r['due']})")

    print("\n=== RECENT_PAST or ACTIVE (정상 풀 후보) ===")
    for r in results:
        if r["category"] in ("RECENT_PAST", "ACTIVE"):
            print(f"  - {r['file']}  (due: {r['due']})")

    # JSON 출력
    Path("/tmp/closure_check_high.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
