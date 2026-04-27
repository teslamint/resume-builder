"""
hold 풀 원인 분석 — '안정성 부족' 단독 컷 vs 다중 이슈 분리.

목적: 룰 완화(A) 전 캘리브레이션(B) 가능성을 정량화한다.

분류 기준:
- AUTO_FALLBACK: LLM 호출 실패로 자동 보류 처리됨 (룰 무관)
- STABILITY_ONLY: '회사 안정성' ❌ 단독 또는 '회사 안정성 + 연봉(추정 불가)' 조합
- MULTI_ISSUE: ❌가 2개 이상 (회사 안정성 외 다른 컷도 있음)
- ROLE_CUT: 리드 전가 / 도메인 / 성장 중심 등 역할·도메인 컷이 주요
- COMPENSATION_CUT: 연봉 ❌가 단독 컷 사유
- UNCLASSIFIED: 위 카테고리에 안 잡히는 케이스 (수동 검토 대상)

출력: hold/ 폴더 313건의 원인 히스토그램 + STABILITY_ONLY 후보 리스트
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path


HOLD_DIR = Path("private/job_postings/conditional/hold")
SCREENING_DIR = Path("private/jd_analysis/screening")

FALLBACK_MARKERS = (
    "자동 fallback",
    "LLM 스크리닝 실행 실패",
    "usage limit",
    "codex exit",
    "exit=1",
)

# 표준 기준 라벨 (정규화 키워드)
CRITERION_PATTERNS = {
    "stability": ["회사 안정성", "회사·재무", "조직 안정성", "재무 안정성"],
    "compensation": ["연봉 구조", "연봉", "보상 구조", "보상"],
    "lead_role": ["리드 전가", "역할 책임", "리드 요소", "포지션 역할"],
    "operations": ["운영", "정합성", "안정성·운영", "운영 중심"],
    "growth": ["성장 중심", "성장 KPI", "스케일"],
    "process": ["채용 프로세스", "사전 과제", "코딩테스트"],
    "domain": ["도메인", "백엔드/서버", "포지션 도메인"],
    "experience": ["경력 범위", "경력 상한", "경력 요건"],
}

VERDICT_NEG = ("❌", "X", ":negative:")
VERDICT_POS = ("⭕", "O", ":positive:")
VERDICT_NEU = ("△", "🟡", "보류")


def is_fallback(content: str) -> bool:
    return any(marker in content for marker in FALLBACK_MARKERS)


def parse_screening_table(content: str) -> dict[str, str]:
    """스크리닝 결과 테이블에서 기준별 판정(⭕/❌/△)을 추출.

    예:
    | 회사 안정성 | ❌ | ... |
    | 연봉 구조   | ❌ | ... |
    -> {"stability": "❌", "compensation": "❌", ...}
    """
    result: dict[str, str] = {}
    # ## 스크리닝 결과 ~ 다음 ## 까지만 잘라서 본다
    m = re.search(
        r"##\s*스크리닝\s*결과\s*\n(.*?)(?=\n##\s)", content, re.DOTALL
    )
    if not m:
        return result
    table = m.group(1)

    # 표 라인: | 기준명 | 판정 | 근거 |
    for line in table.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        criterion_name, verdict = cells[0], cells[1]
        # 헤더 / 구분선 스킵
        if criterion_name in ("기준", "") or set(criterion_name) <= {"-", " ", ":"}:
            continue
        # 매핑
        for key, patterns in CRITERION_PATTERNS.items():
            if any(p in criterion_name for p in patterns):
                result[key] = verdict
                break

    return result


def classify_hold(criteria: dict[str, str]) -> tuple[str, list[str]]:
    """기준별 판정에서 컷 카테고리 결정.

    Returns: (category, list_of_negative_criteria)
    """
    negs = [k for k, v in criteria.items() if any(n in v for n in VERDICT_NEG)]
    neus = [k for k, v in criteria.items() if any(n in v for n in VERDICT_NEU)]

    # 표 파싱 자체가 실패한 경우
    if not criteria:
        return "UNPARSED", []

    # 판정 표는 있는데 ❌ 없음 (보류는 △/프로세스에서)
    if not negs:
        # 운영 ❌ 또는 △도 없는데 hold면 → 보류 메타 (정보 부족 등)
        if "process" in neus or "operations" in neus:
            return "PROCESS_OR_OPS_NEUTRAL", neus
        return "INFO_INSUFFICIENT", neus

    # ❌가 1개일 때
    if len(negs) == 1:
        only = negs[0]
        if only == "stability":
            return "STABILITY_ONLY", negs
        if only == "compensation":
            return "COMPENSATION_ONLY", negs
        if only in ("lead_role", "domain", "growth"):
            return "ROLE_OR_DOMAIN_ONLY", negs
        return f"OTHER_SINGLE_{only.upper()}", negs

    # ❌ 2개 — 안정성 + 연봉 조합은 사실상 "정보 없는 스타트업" 패턴
    if len(negs) == 2 and set(negs) == {"stability", "compensation"}:
        return "STABILITY_PLUS_COMP", negs

    # 안정성 + 다른 비-연봉
    if "stability" in negs:
        return f"STABILITY_PLUS_OTHER", negs

    # 안정성은 OK인데 다른 ❌가 다수
    return "MULTI_NON_STABILITY", negs


def main() -> None:
    hold_files = sorted(HOLD_DIR.glob("*.md"))
    print(f"총 hold 파일: {len(hold_files)}\n")

    categories: Counter[str] = Counter()
    stability_only_files: list[tuple[str, dict[str, str]]] = []
    stability_plus_comp_files: list[tuple[str, dict[str, str]]] = []
    fallback_files: list[str] = []
    unparsed_files: list[str] = []

    no_screening = 0
    for jd_path in hold_files:
        screening_path = SCREENING_DIR / jd_path.name
        if not screening_path.exists():
            no_screening += 1
            categories["NO_SCREENING_FILE"] += 1
            continue

        content = screening_path.read_text(encoding="utf-8", errors="replace")
        if is_fallback(content):
            categories["AUTO_FALLBACK"] += 1
            fallback_files.append(jd_path.name)
            continue

        crit = parse_screening_table(content)
        category, negs = classify_hold(crit)
        categories[category] += 1

        if category == "UNPARSED":
            unparsed_files.append(jd_path.name)
        elif category == "STABILITY_ONLY":
            stability_only_files.append((jd_path.name, crit))
        elif category == "STABILITY_PLUS_COMP":
            stability_plus_comp_files.append((jd_path.name, crit))

    # === 출력 ===
    print("=" * 60)
    print("hold 풀 원인 분류 히스토그램")
    print("=" * 60)
    for cat, n in categories.most_common():
        pct = n * 100.0 / len(hold_files)
        print(f"  {cat:30s} {n:4d}  ({pct:5.1f}%)")

    print()
    print("=" * 60)
    print(f"STABILITY_ONLY 후보: {len(stability_only_files)}건")
    print("(= 안정성 정보만 부재하면 통과 가능성 있는 케이스)")
    print("=" * 60)
    for name, crit in stability_only_files[:50]:
        crit_summary = " ".join(f"{k}={v}" for k, v in crit.items() if v.strip())
        print(f"  - {name}")
        print(f"      {crit_summary}")

    print()
    print("=" * 60)
    print(f"STABILITY_PLUS_COMP 후보: {len(stability_plus_comp_files)}건")
    print("(= 안정성+연봉 둘 다 부재 = 정보 없는 스타트업 패턴)")
    print("(연봉 ❌가 '추정 불가'면 후보, '7,560 미만 확실'이면 진짜 컷)")
    print("=" * 60)
    for name, _ in stability_plus_comp_files[:30]:
        print(f"  - {name}")

    print()
    print("=" * 60)
    print(f"표 파싱 실패: {len(unparsed_files)}건 (수동 확인 필요)")
    print("=" * 60)
    for name in unparsed_files[:10]:
        print(f"  - {name}")


if __name__ == "__main__":
    main()
