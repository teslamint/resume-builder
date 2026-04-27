"""high/ 풀 마감 JD 일괄 이동.

closure_check_high.json 결과 기반:
- CLOSED_DEFINITE (due_time=null): 즉시 closed/ 이동
- CLOSED_LIKELY (60일+ 과거): 즉시 closed/ 이동
- AGED (30~60일 과거): 보류 (수동 확인)
- ACTIVE/RECENT_PAST: 유지
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path

HIGH = Path("private/job_postings/conditional/high")
CLOSED = Path("private/job_postings/closed")
SCREEN = Path("private/jd_analysis/screening")
SUMMARY = Path("private/jd_analysis/screening/SUMMARY.md")

DECISIONS = json.loads(Path("/tmp/closure_check_high.json").read_text())

CLOSED_CATEGORIES = ("CLOSED_DEFINITE", "CLOSED_LIKELY")


def extract_meta(jd_path: Path) -> tuple[str, str, str]:
    text = jd_path.read_text(encoding="utf-8", errors="replace")
    company_m = re.search(r"\|\s*회사명\s*\|\s*([^|\n]+)\|", text)
    position_m = re.search(r"\|\s*포지션\s*\|\s*([^|\n]+)\|", text)
    job_id = jd_path.stem.split("-", 1)[0]
    company = (company_m.group(1).strip() if company_m else jd_path.stem.split("-", 2)[1])
    position = (position_m.group(1).strip() if position_m else jd_path.stem)
    return job_id, company, position


def main() -> None:
    today = datetime.now().strftime("%Y-%m-%d")
    CLOSED.mkdir(parents=True, exist_ok=True)

    moved = []
    skipped = []
    summary_rows = []

    for d in DECISIONS:
        if d.get("category") not in CLOSED_CATEGORIES:
            continue
        src = HIGH / d["file"]
        if not src.exists():
            skipped.append((d["file"], "원본 없음"))
            continue
        dst = CLOSED / d["file"]
        if dst.exists():
            skipped.append((d["file"], "closed/에 이미 있음"))
            continue
        shutil.move(str(src), str(dst))
        job_id, company, position = extract_meta(dst)
        category = d["category"]
        due = d.get("due") or "(null)"
        reason = "due_time=null" if category == "CLOSED_DEFINITE" else f"due 60일+ 과거 ({due})"
        summary_rows.append(
            f"| {today} | {job_id} | {company} | {position} | 지원 비추천 | `closed` "
            f"<br/>재분류({today}, 마감 자동 검출 [{reason}]): high→closed |\n"
        )
        moved.append((d["file"], category, due))

    if summary_rows:
        with open(SUMMARY, "a", encoding="utf-8") as f:
            f.writelines(summary_rows)

    print(f"=== 이동 완료: {len(moved)}건 ===")
    for f, c, d in moved:
        print(f"  [{c}] {f} (due: {d})")
    if skipped:
        print(f"\n=== 스킵: {len(skipped)}건 ===")
        for f, reason in skipped:
            print(f"  - {f}: {reason}")
    print(f"\n📝 SUMMARY.md에 {len(summary_rows)}건 재분류 추가")


if __name__ == "__main__":
    main()
