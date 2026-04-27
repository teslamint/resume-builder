"""기존 JD 전체에서 채용 마감 키워드 검출 + closed/ 폴더로 이동.

룰 0장 신규 항목(2026-04-27): 마감 키워드는 verdict 무관 하드 컷.
"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

CLOSED_MARKERS = (
    "채용 마감",
    "채용이 마감",
    "마감되었습니다",
    "이 공고는 마감",
    "지원 기간이 종료",
    "상시채용 종료",
    "Position closed",
    "이 포지션은 마감",
)

JD_DIRS = [
    Path("private/job_postings/conditional/hold"),
    Path("private/job_postings/conditional/high"),
    Path("private/job_postings/pass"),
    Path("private/job_postings/applied"),
    Path("private/job_postings/unprocessed"),
]

CLOSED_DIR = Path("private/job_postings/closed")
SUMMARY = Path("private/jd_analysis/screening/SUMMARY.md")


def is_closed(text: str) -> str | None:
    for marker in CLOSED_MARKERS:
        if marker in text:
            return marker
    return None


def main(dry_run: bool = False) -> None:
    CLOSED_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")

    found = []
    for d in JD_DIRS:
        if not d.exists():
            continue
        for jd in d.glob("*.md"):
            text = jd.read_text(encoding="utf-8", errors="replace")
            marker = is_closed(text)
            if marker:
                found.append((jd, d.name, marker))

    print(f"마감 검출: {len(found)}건")
    print()

    summary_rows = []
    for jd, src_folder, marker in found:
        # 파일명에서 ID + 회사 + 포지션 추출 (best effort)
        parts = jd.stem.split("-", 2)
        job_id = parts[0]
        company = parts[1] if len(parts) > 1 else "unknown"
        position = parts[2] if len(parts) > 2 else jd.stem

        if dry_run:
            print(f"  [DRY] {jd.name}  ({src_folder} → closed)  marker='{marker}'")
            continue

        # applied/는 보호 — 마감되어도 이동하지 않음 (이미 지원한 케이스)
        if "applied" in str(jd):
            print(f"  ⏭️  applied/ 보호: {jd.name}")
            continue

        dst = CLOSED_DIR / jd.name
        if dst.exists():
            print(f"  ⚠️  중복 (이미 closed/에 있음): {jd.name}")
            continue
        shutil.move(str(jd), str(dst))
        summary_rows.append(
            f"| {today} | {job_id} | {company} | {position} | 지원 비추천 | `closed` "
            f"<br/>재분류({today}, 채용 마감 자동 검출 [{marker}]): {src_folder}→closed |\n"
        )
        print(f"  ✅ {jd.name}  ({src_folder} → closed)")

    if summary_rows and not dry_run:
        with open(SUMMARY, "a", encoding="utf-8") as f:
            f.writelines(summary_rows)
        print(f"\nSUMMARY.md에 {len(summary_rows)}건 재분류 추가")


if __name__ == "__main__":
    import sys
    dry = "--dry-run" in sys.argv
    main(dry_run=dry)
