"""SUMMARY.md의 코테 재분류 22행을 정확한 회사명/포지션으로 정정.

전제: 잘못 추가된 22행이 이미 SUMMARY.md에 있음 (slug-format).
방법: ID로 매칭해서 in-place 교체. 백그라운드 동시 append와의 race window는 ~100ms.
"""

from __future__ import annotations

import os
import re
import shutil
from datetime import datetime
from pathlib import Path

SUMMARY = Path("private/jd_analysis/screening/SUMMARY.md")
HIGH = Path("private/job_postings/conditional/high")
SCREEN = Path("private/jd_analysis/screening")

RECLASSIFIED = [
    "198858-hanwha-life-backend.md",
    "268315-sentbe-backend.md",
    "274162-connectwave-danawa-backend.md",
    "281845-42dot-backend-engineer-open-platform.md",
    "288584-포티투닷-senior-backend-engineer-vehicl.md",
    "299401-42dot-sr-backend-engineer-lbs.md",
    "320631-42dot-backend-engineer-pleos.md",
    "325289-noluniv-backend-leisure.md",
    "325291-noluniv-backend-commerce-platform.md",
    "326012-purpleio-crm-backend.md",
    "328130-kakaopay-securities-data-platform.md",
    "334919-noluniv-backend-search.md",
    "336772-wefun-backend.md",
    "337190-씨티케이-백엔드-개발-10년.md",
    "339873-hyundai-autoever-backend-showroom.md",
    "339877-hyundai-autoever-backend-web-platform.md",
    "339880-hyundai-autoever-backend-connected-car-service.md",
    "339882-hyundai-autoever-backend-ccs-platform.md",
    "339898-hyundai-autoever-backend-web-system.md",
    "339900-hyundai-autoever-backend-ccs-deploy.md",
    "339943-hyundai-autoever-backend-enterprise.md",
    "341383-jyp-backend-engineer.md",
]


def _extract(text: str, label_alts: tuple[str, ...]) -> str | None:
    for label in label_alts:
        m = re.search(rf"\|\s*{label}\s*\|\s*([^|\n]+?)\s*\|", text)
        if m:
            return m.group(1).strip()
        m = re.search(rf"\*\*{label}\*\*\s*:\s*([^\n]+)", text)
        if m:
            return m.group(1).strip()
        m = re.search(rf"^{label}\s*:\s*([^\n]+)", text, re.MULTILINE)
        if m:
            return m.group(1).strip()
    return None


def extract_meta(name: str) -> tuple[str, str, str]:
    job_id = name.split("-", 1)[0]
    company = position = None
    for src in (HIGH / name, SCREEN / name):
        if not src.exists():
            continue
        text = src.read_text(encoding="utf-8", errors="replace")
        company = company or _extract(text, ("회사명", "회사", "기업명"))
        position = position or _extract(text, ("포지션", "직무"))
        if company and position:
            break
    fallback_company = name.split("-", 2)[1] if "-" in name else "unknown"
    return job_id, (company or fallback_company), (position or name)


def main() -> None:
    today = datetime.now().strftime("%Y-%m-%d")
    note = f"재분류({today}, 코테 정책 완화): 보류→추천"

    # 정확한 22행 빌드
    correct_by_id: dict[str, str] = {}
    for name in RECLASSIFIED:
        job_id, company, position = extract_meta(name)
        correct_by_id[job_id] = (
            f"| {today} | {job_id} | {company} | {position} | 지원 추천 | `high` <br/>{note} |"
        )

    # 현재 SUMMARY 읽고 잘못된 22행 in-place 교체
    text = SUMMARY.read_text(encoding="utf-8")
    lines = text.split("\n")

    replaced = 0
    new_lines: list[str] = []
    for line in lines:
        m = re.match(r"^\| \d{4}-\d{2}-\d{2} \| (\d+) \|", line)
        if m and "재분류(2026-04-26, 코테 정책 완화)" in line:
            job_id = m.group(1)
            if job_id in correct_by_id:
                new_lines.append(correct_by_id[job_id])
                replaced += 1
                continue
        new_lines.append(line)

    new_text = "\n".join(new_lines)

    # atomic write via rename
    tmp = SUMMARY.with_suffix(".md.tmp")
    tmp.write_text(new_text, encoding="utf-8")
    os.replace(tmp, SUMMARY)

    print(f"교체 완료: {replaced} / {len(correct_by_id)}")


if __name__ == "__main__":
    main()
