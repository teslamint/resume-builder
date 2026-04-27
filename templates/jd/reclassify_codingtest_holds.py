"""코딩테스트 정책 완화(2026-04-26)로 22건 hold → high 일괄 재분류.

각 파일에 대해:
1. 스크리닝 결과 파일의 최종 판정을 '지원 보류' → '지원 추천' 으로 갱신
2. 본문 상단에 정책 변경 정정 노트 추가
3. JD 파일을 conditional/hold/ → conditional/high/ 로 이동
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import List

HOLD = Path("private/job_postings/conditional/hold")
HIGH = Path("private/job_postings/conditional/high")
SCREEN = Path("private/jd_analysis/screening")

FALLBACK = ("자동 fallback", "LLM 스크리닝 실행 실패", "usage limit", "codex exit", "exit=1")
PROC_KEYS = ("채용 프로세스", "채용프로세스", "사전 과제", "사전과제", "코딩테스트", "라이브 코딩", "라이브코딩")

CORRECTION_NOTE = (
    "> **2026-04-26 코딩테스트 정책 완화로 자동 승급 (🟡 → 🟢)**: "
    "스크리닝 룰 2장·6장 수정에 따라 코딩테스트/사전 과제는 더 이상 자동 한 단계 하향 사유에서 제외. "
    "본 건은 다른 모든 substantive 기준 ⭕로, 코테 자동 하향만이 보류 사유였음.\n\n"
)


def find_clean_codingtest_holds() -> List[str]:
    clean = []
    for jd in sorted(HOLD.glob("*.md")):
        sp = SCREEN / jd.name
        if not sp.exists():
            continue
        content = sp.read_text(encoding="utf-8", errors="replace")
        if any(m in content for m in FALLBACK):
            continue
        proc_hit = re.search(
            r"(채용 ?프로세스|사전 ?과제|코딩테스트|라이브 ?코딩).{0,80}?(🟡|보류|△|하향)",
            content,
        )
        if not proc_hit:
            continue
        table_lines = [l for l in content.splitlines() if l.startswith("|")]
        substantive = [l for l in table_lines if not any(k in l for k in PROC_KEYS)]
        if not any("❌" in l for l in substantive):
            clean.append(jd.name)
    return clean


def update_screening_file(name: str) -> tuple[bool, str]:
    sp = SCREEN / name
    content = sp.read_text(encoding="utf-8")
    original = content

    # 1) Verdict line — match any line containing 🟡 + verdict keyword and replace
    # heading verdict: ### 최종 판정: 🟡 ...
    # quote verdict: > 판정: 🟡 ... or > 최종 판정: 🟡 ...
    # bold verdict:  **최종 판정**: 🟡 ...
    matched = False
    line_patterns = [
        (
            r"^(###\s*최종\s*판정\s*:\s*)🟡[^\n]*",
            r"\g<1>🟢 지원 추천 (2026-04-26 코테 정책 완화로 자동 승급)",
        ),
        (
            r"^(>\s*(?:최종\s*)?판정\s*:\s*)🟡[^\n]*",
            r"\g<1>🟢 지원 추천 (2026-04-26 코테 정책 완화로 자동 승급)",
        ),
        (
            r"^(\*\*최종\s*판정\*\*\s*:\s*)🟡[^\n]*",
            r"\g<1>🟢 지원 추천 (2026-04-26 코테 정책 완화로 자동 승급)",
        ),
        (
            r"^(#{1,6}\s*최종\s*판정\s*\n)",
            r"\g<1>",  # no-op for plain section header — fall through
        ),
    ]
    for pat, repl in line_patterns:
        new_content, count = re.subn(pat, repl, content, count=0, flags=re.MULTILINE)
        if count > 0 and new_content != content:
            content = new_content
            matched = True

    if not matched:
        return False, "verdict 라인 패턴 미발견"

    # 2) Correction note at top (after first H1 if present)
    if CORRECTION_NOTE.strip().split('\n')[0] not in content:
        h1 = re.search(r"^#\s+.+\n", content, re.MULTILINE)
        if h1:
            insert_at = h1.end()
            content = content[:insert_at] + "\n" + CORRECTION_NOTE + content[insert_at:]
        else:
            content = CORRECTION_NOTE + content

    if content == original:
        return False, "no-op"

    sp.write_text(content, encoding="utf-8")
    return True, "ok"


def move_jd(name: str) -> tuple[bool, str]:
    src = HOLD / name
    dst = HIGH / name
    if not src.exists():
        return False, "JD 원본 없음"
    if dst.exists():
        return False, "high/에 동명 파일 이미 존재"
    HIGH.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    return True, "moved"


def main() -> None:
    targets = find_clean_codingtest_holds()
    print(f"대상: {len(targets)}건\n")

    updated = []
    skipped = []
    for name in targets:
        ok_screen, msg_screen = update_screening_file(name)
        if not ok_screen:
            skipped.append((name, f"스크리닝 갱신 실패: {msg_screen}"))
            continue
        ok_move, msg_move = move_jd(name)
        if not ok_move:
            skipped.append((name, f"JD 이동 실패: {msg_move}"))
            continue
        updated.append(name)
        print(f"  ✅ {name}")

    print()
    print(f"성공: {len(updated)}건 / 실패·스킵: {len(skipped)}건")
    if skipped:
        print("\n스킵된 항목:")
        for name, reason in skipped:
            print(f"  - {name} : {reason}")


if __name__ == "__main__":
    main()
