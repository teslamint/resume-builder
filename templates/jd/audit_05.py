#!/usr/bin/env python3
"""
audit_05.py — JD screening 사후 감사 자동화

Purpose
-------
2026-04-17 룰 0.5절(증거 계층 원칙) 도입 이후, 일관성 결함을 수동 감사로 18건
검증 → 7건(39%) 잘못 컷 발견. 나머지 비추천 ~155건은 미감사 상태. 분석일
메타데이터 부재로 시점 분리 불가 → 173건 모두 잠재 대상.

수동 검토는 비현실적이므로 의심도 점수로 우선 검토 후보를 식별하고, 라운드별
인간/advisor 검증으로 수렴한다.

해결 결함 (3가지)
----------------
1. P1 — Polyglot 룰 위반 (룰 0장)
   "Node.js/Python/스택 불일치"를 단독 컷 사유로 사용
2. P2 — 0.5절(증거 계층 원칙) 일관성 결함
   2차 증거(##소개)·정성적 우려를 1차 증거 ❌로 라우팅
3. P3 — TheVC 라운드 라벨 추론 (룰 5.5절)
   미검증 M&A 추론을 ④ ❌로 사용

Usage
-----
    # 골든 검증 (정정 처리된 파일도 포함)
    python templates/jd/audit_05.py --include-processed --output /tmp/audit_05_validation.csv

    # 전수 감사 (현재 비추천만)
    python templates/jd/audit_05.py --output private/jd_analysis/audit_05_2026-04-25.csv

    # 라플라스(285243) anchor 검증 — score >= 60일 경우 비0 종료
    python templates/jd/audit_05.py --include-processed --check-anchor 285243

    # advisor 라운드 검토용 풀 컨텍스트 JSON
    python templates/jd/audit_05.py --json --output /tmp/audit_05.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
_JD_DIR = Path(__file__).resolve().parent
if str(_JD_DIR) not in sys.path:
    sys.path.insert(0, str(_JD_DIR))

from path_utils import extract_job_id_from_filename, find_existing_jd  # noqa: E402
from verdict import normalize_verdict  # noqa: E402
from constants import PROTECTED_STATUSES  # noqa: E402
from audit_hypotheses import (  # noqa: E402
    extract_last_verdict,
    parse_summary_verdicts,
    load_file_locations,
)

SCREENING_DIR = REPO_ROOT / "private" / "jd_analysis" / "screening"
COMPANY_INFO_DIR = REPO_ROOT / "private" / "company_info"


# ----------------------------------------------------------------------
# Correction-block stripping
# ----------------------------------------------------------------------

# 정정된 파일은 헤더 직후에 다음 형태의 인용 블록이 있다:
#   > **2026-04-25 자기 수정 (...)**: ...
#   > - 1차 증거: ...
# 이 블록 전체와 헤더의 `(YYYY-MM-DD 정정)` 마커를 제거해야 원본 컷 사유만
# 분석에 사용된다. 그렇지 않으면 정정 후 재분석된 텍스트가 P1/P2/P3 매칭을
# 오염시킨다.
_CORRECTION_BLOCK_RE = re.compile(
    r"^>\s*\*\*\d{4}-\d{2}-\d{2}\s*자기\s*수정.*?(?=^[^>\s]|^\s*$\n^[^>]|\Z)",
    re.MULTILINE | re.DOTALL,
)
_CORRECTION_QUOTE_LINE_RE = re.compile(r"^>.*$\n?", re.MULTILINE)
_CORRECTION_HEADER_RE = re.compile(r"\(\s*\d{4}-\d{2}-\d{2}\s*정정\s*\)")


def strip_correction_blocks(text: str) -> str:
    """Remove self-correction quote blocks and `(YYYY-MM-DD 정정)` markers.

    Strategy: find the first '> **YYYY-MM-DD 자기 수정' line and strip every
    consecutive blockquote line from that point until a non-blockquote line.
    Then remove the header's `(YYYY-MM-DD 정정)` marker.
    """
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if re.match(r"^>\s*\*\*\d{4}-\d{2}-\d{2}\s*자기\s*수정", line):
            # consume this and following blockquote lines (incl. blank lines
            # between blockquote runs)
            i += 1
            while i < len(lines):
                nxt = lines[i]
                if nxt.startswith(">") or nxt.strip() == "":
                    i += 1
                    continue
                break
            continue
        out.append(line)
        i += 1
    cleaned = "".join(out)
    cleaned = _CORRECTION_HEADER_RE.sub("", cleaned)
    return cleaned


# ----------------------------------------------------------------------
# JD primary evidence extraction
# ----------------------------------------------------------------------

_PRIMARY_SECTION_RE = re.compile(
    r"^(##\s*(?:주요\s*업무|자격\s*요건|우대\s*사항)[^\n]*\n.+?)(?=^##\s|\Z)",
    re.MULTILINE | re.DOTALL,
)


def extract_jd_primary_evidence(jd_path: Optional[Path]) -> str:
    """Concatenate '주요 업무', '자격 요건', '우대 사항' sections from JD file."""
    if jd_path is None or not jd_path.exists():
        return ""
    text = jd_path.read_text(encoding="utf-8")
    sections = [m.group(1) for m in _PRIMARY_SECTION_RE.finditer(text)]
    return "\n".join(sections)


# ----------------------------------------------------------------------
# Cut-reason extraction
# ----------------------------------------------------------------------

_OPINION_SECTION_RE = re.compile(
    r"^##\s*(?:종합\s*의견|한\s*줄\s*요약|결론|판정\s*근거)[^\n]*\n(.+?)(?=^##\s|\Z)",
    re.MULTILINE | re.DOTALL,
)
_TABLE_REJECT_ROW_RE = re.compile(
    r"^\|[^\n|]*\|\s*❌\s*\|([^\n|]+)\|", re.MULTILINE
)
_LINE_REJECT_RE = re.compile(r"❌[^\n]+", re.MULTILINE)


def extract_cut_reason(screening_text: str) -> str:
    """Concatenate cut-reason candidates from screening file.

    Sources (priority order, all concatenated):
      1. ## 종합 의견 / 한 줄 요약 / 결론 sections
      2. Judgment table rows where verdict cell is ❌
      3. Any line containing ❌ (catch-all)
    """
    parts: list[str] = []

    for m in _OPINION_SECTION_RE.finditer(screening_text):
        parts.append(m.group(1))

    for m in _TABLE_REJECT_ROW_RE.finditer(screening_text):
        parts.append(m.group(1).strip())

    parts.extend(_LINE_REJECT_RE.findall(screening_text))

    return "\n".join(parts)


# ----------------------------------------------------------------------
# Pattern dictionaries
# ----------------------------------------------------------------------

# P1 — Polyglot 룰 위반 (룰 0장)
P1_PATTERNS = [
    (re.compile(r"Node\.?js[^\n]*?(?:불일치|미스매치|아님|미일치)"), "Node.js 불일치"),
    (re.compile(r"Python[^\n]*?(?:불일치|미스매치|아님|미일치)"), "Python 불일치"),
    (re.compile(r"Java\s*(?:[/&]\s*Spring)?[^\n]*?(?:아님|불일치|미스매치)"), "Java/Spring 불일치"),
    (re.compile(r"TypeScript[^\n]*?불일치"), "TypeScript 불일치"),
    (re.compile(r"C#[^\n]*?(?:전면\s*)?불일치"), "C# 불일치"),
    (re.compile(r"스택\s*불일치"), "스택 불일치"),
    (re.compile(r"주력\s*스택\s*(?:불일치|미스매치|아님)"), "주력 스택 불일치"),
    # "Node.js/Python 필수" 표현 (모플 케이스 직접 매치)
    (re.compile(r"(?:Node\.?js|Python|TypeScript)[^\n]{0,12}필수[^\n]*?(?:불일치|미스매치|스택)"),
     "필수 스택 불일치"),
]

# P3 — TheVC 라운드/M&A 추론 (룰 5.5절)
P3_PATTERNS = [
    (re.compile(r"M&A\s*(?:진행|리스크)"), "M&A 추론"),
    (re.compile(r"인수합병[^\n]*?(?:리스크|진행|불확실)"), "인수합병 추론"),
    (re.compile(r"피인수[^\n]*?(?:리스크|불확실)"), "피인수 추론"),
]

# 1차 증거 매치 키워드 — 룰 2/3/4/5에서 ❌ 라우팅을 정당화하는 표현.
# 컷 사유에 이 키워드 또는 정량 패턴이 등장하면 P2 점수를 무효화한다.
PRIMARY_EVIDENCE_KEYWORDS = [
    # 룰 2 — 성장/리드 (1차 증거: 자격요건/우대)
    "주도적", "오너십", "회색 영역", "리드 경험 우대",
    # 룰 3 — 조직 운영 (1차: 직함/주요업무)
    "팀 전체 운영", "인사 최종", "Engineering Manager", "VP", "CTO",
    "리드 전가", "팀 리딩",
    # 룰 4 — 업무 범위 (1차: 주요업무)
    "신규 구축", "신규 시스템", "신규 플랫폼",
    "대규모 트래픽", "수백만 사용자", "스케일 업", "scale-up",
    "X배 성장", "성장하면 보상",
    # 룰 5 — 조직 변동성/연봉 (1차: 자격요건/회사정보)
    "포괄임금", "스톡옵션 전면", "시드~시리즈", "Series A", "Series B",
    "시드", "Pre-A",
    # 컴팩트한 정량 ❌ 마커 — 시니어 대비 낮음 등은 1차 증거 매치
    "시니어 대비 낮", "14년차 대비",
]

# 약어성 키워드는 word boundary로 매치해야 substring 오매치를 방지할 수 있다.
# 예: "VP"가 "VPP/DR/V2G" 안에서 매치되어 1차 증거 hit로 잘못 분류되는 것을 차단.
_BOUNDED_KEYWORDS = {"VP", "CTO", "Series A", "Series B", "Pre-A"}


def has_primary_evidence_match(text: str) -> tuple[bool, list[str]]:
    """Detect 1차 증거 키워드 매치. 짧은 약어는 word boundary로 매치."""
    hits: list[str] = []
    for kw in PRIMARY_EVIDENCE_KEYWORDS:
        if kw in _BOUNDED_KEYWORDS:
            if re.search(rf"(?<![A-Za-z0-9]){re.escape(kw)}(?![A-Za-z0-9])", text):
                hits.append(kw)
        else:
            if kw in text:
                hits.append(kw)
    return (bool(hits), hits)


# 정성적 우려 패턴 — P2 트리거. 컷 사유가 이런 표현 단독으로 ❌ 라우팅하면
# 0.5절 위반 가능성이 높다.
_QUALITATIVE_CONCERN_PATTERNS = [
    (re.compile(r"성장\s*중심"), "성장 중심"),
    (re.compile(r"스케일링"), "스케일링"),
    (re.compile(r"성장\s*단계"), "성장 단계"),
    (re.compile(r"초기\s*스타트업"), "초기 스타트업"),
    (re.compile(r"안정성\s*리스크"), "안정성 리스크"),
    (re.compile(r"보상\s*여력\s*의문"), "보상 여력 의문"),
    (re.compile(r"growth-?focused", re.IGNORECASE), "growth-focused"),
    (re.compile(r"성장\s*스타트업"), "성장 스타트업"),
    (re.compile(r"급성장\s*스타트업"), "급성장 스타트업"),
    (re.compile(r"성장\s*드라이브"), "성장 드라이브"),
    (re.compile(r"책임\s*분산\s*불명확"), "책임 분산 불명확"),
    (re.compile(r"빠른\s*개발[·\s]*배포"), "빠른 개발·배포"),
    (re.compile(r"빠르게\s*개발하고\s*배포"), "빠르게 개발하고 배포"),
    (re.compile(r"프로덕트\s*성장"), "프로덕트 성장"),
    (re.compile(r"Growth\s*Feature", re.IGNORECASE), "Growth Feature"),
]

# 데이터 부재 단독 ❌ 패턴 — 디렉셔널(172078) 케이스
_DATA_VACANT_PATTERNS = [
    (re.compile(r"비공개"), "비공개"),
    (re.compile(r"정보\s*(?:부재|없음|미공개|전무)"), "정보 부재"),
    (re.compile(r"데이터\s*(?:부재|없음|전무)"), "데이터 부재"),
    (re.compile(r"미기재"), "미기재"),
    (re.compile(r"공개\s*정보\s*(?:극히\s*)?제한적"), "공개 정보 제한적"),
    (re.compile(r"검증\s*불가"), "검증 불가"),
    (re.compile(r"매출\s*(?:정보\s*)?(?:전무|없음)"), "매출 전무"),
]


# ----------------------------------------------------------------------
# Auto-exclusion rules
# ----------------------------------------------------------------------

# 자동 제외 룰은 두 가지 신호만 사용:
#   (1) JD 본문 + screening 본문 — 가상자산/병역특례 (도메인성)
#   (2) position_title (filename slug) — 직함 기반
# JD 본문에 "AI/ML 우대" 같은 표현이 있으면 non_backend 매치를 안 한다.
_GLOBAL_EXCLUDE_PATTERNS = {
    "crypto": re.compile(
        r"가상자산|암호화폐|크립토(?:[^\w]|$)|crypto(?:[^\w]|$)|블록체인|Web3", re.IGNORECASE
    ),
    "military": re.compile(r"병역특례|산업기능요원|보충역"),
}

# position_title (filename slug) 기반 직무 제외. filename은 hyphenated slug
# 형태(e.g. "ai-agent-be-engineer")이므로 토큰 형태 매치.
_POSITION_EXCLUDE_PATTERNS = {
    "non_backend": re.compile(
        r"(?:^|-)(?:ai-?ml-?engineer|ai-?engineer|ml-?engineer|data-?engineer|"
        r"cloud-?engineer|devops-?engineer|platform-?engineer|frontend|"
        r"front-?end|fe-?engineer|ios|android|mobile|"
        r"windows-?driver|kernel-?(?:driver|developer|engineer)|"
        r"driver-?(?:engineer|developer)|embedded-?(?:engineer|developer)|"
        r"firmware-?(?:engineer|developer)|"
        r"deep-?learning-?(?:engineer|algorithm-?eng)|algorithm-?engineer|"
        r"computer-?vision-?engineer|ml-?research-?engineer|"
        r"sap-?(?:mm|fi|pp|hr|sd)|"
        r"applied-?ai-?(?:technical-?)?engineer|ai-?technical-?engineer|"
        r"customer-?engineer|production-?engineer|process-?engineer|"
        r"manufacturing-?engineer|"
        r"react-?(?:개발자|developer)|vue-?(?:개발자|developer)|"
        r"frontend-?developer|front-?end-?developer|"
        r"모바일-?앱-?개발자|모바일-?개발자|앱-?개발자|"
        r"product-?engineer-?marketing|marketing-?engineer|"
        r"growth-?engineer|growth-?marketing|"
        r"ai-?엔지니어|llm-?엔지니어|ai-?개발자|llm-?개발자|"
        r"ai-?agent|llm-?agent|agent-?engineer|agent-?developer)(?:-|$)",
        re.IGNORECASE,
    ),
    "contract_role": re.compile(
        r"(?:^|-)(?:계약직|contract(?:or)?)(?:-|$)", re.IGNORECASE
    ),
    "manager_role": re.compile(
        r"(?:^|-)(?:engineering-?manager|head-?of-?engineering|"
        r"vp-?of-?engineering|cto|tech-?lead|개발총괄)(?:-|$)",
        re.IGNORECASE,
    ),
}

# 컷 사유 자체에 "백엔드와 전혀 다른 직무" 명시가 있으면 misclassification으로
# 자동 제외. 모빌린트(346968) Windows 커널 드라이버 / 두산로보틱스(298311) 로봇
# 모션 제어 등 직무 자체가 백엔드가 아닌 케이스 — screening filename에
# "backend" 토큰이 있어 position 매치 실패하므로 컷 사유 자체에서 검출.
_MISCLASSIFICATION_RE = re.compile(
    r"백엔드와\s*전혀\s*다른|"
    r"임베디드(?:[/\s]*시스템)?(?:[/\s]*커널)?\s*개발|"
    r"디바이스\s*드라이버|"
    r"커널\s*(?:모드\s*)?드라이버|"
    r"드라이버\s*레벨|"
    r"백엔드(?:\s*엔지니어(?:링)?(?:\s*직군)?)?\s*(?:가|이)?\s*아[님닌]|"
    r"백엔드\s*엔지니어링\s*직군\s*아[님닌]|"
    r"백엔드\s*개발과\s*무관|"
    r"로봇\s*모션\s*제어|"
    r"로봇\s*제어\s*알고리즘|"
    r"\bROS\b.*\bRTOS\b|"
    r"\bRTOS\b.*\bROS\b|"
    r"하드웨어[/\s]*소프트웨어\s*연동|"
    r"\bSAP\s*(?:MM|FI|PP|HR|SD|S/?4HANA)\b|"
    r"\bABAP\b|"
    r"ERP\s*모듈|"
    r"\bADAS\b|\bBSP\b|콕핏(?:\s*엣지)?|"
    r"임베디드[\s/]*자동차|임베디드\s*시스템|"
    r"제조업\s*생산기술|공정혁신\s*엔지니어|"
    r"기계공학\s*(?:및)?\s*유사전공|"
    r"산업공학\s*전공|전기공학\s*전공|"
    r"4M\s*개선|제조원가\s*절감|"
    r"Flutter\s*기반\s*모바일|모바일\s*앱\s*개발|"
    r"iOS\s*및\s*Android|Android\s*및\s*iOS|"
    r"마케팅\s*자동화|그로스\s*엔지니어링|"
    r"Product\s*Engineer\s*\(Marketing\)|"
    r"프론트엔드\s*전담|React/TypeScript\s*프론트엔드|"
    r"생성형\s*AI/LLM\s*엔지니어|LLM\s*엔지니어|"
    r"AI/LLM\s*전문\s*포지션|AI\s*Agent\s*전문|"
    r"멀티\s*에이전트\s*아키텍처"
)

# "경력 X~Y년" 매치 — lo<=4 AND hi<=10 (모두 만족 시 자동 제외).
# 단순 floor (`경력 N년 이상`)는 한국 채용공고 대다수에 등장하므로 제외 사유로
# 부적합. ceiling (`경력 상한 N년`)은 드물게 매치되므로 유지.
_EXP_RANGE_RE = re.compile(r"경력\s*(\d{1,2})\s*[~\-]\s*(\d{1,2})\s*년")
# "3-5년차" 같은 표현 (filename slug, JD 헤더에 흔함)
_EXP_YEARCHA_RE = re.compile(r"(\d{1,2})\s*[~\-]\s*(\d{1,2})\s*년차")
_EXP_CEILING_RE = re.compile(r"경력\s*(?:상한|최대)\s*(\d{1,2})\s*년")


def detect_auto_exclusions(
    screening_text: str, jd_text: str, position_title: str
) -> list[str]:
    """Apply auto-exclusion rules. Returns list of triggered rule names."""
    excluded: list[str] = []

    blob = f"{jd_text}\n{screening_text}"
    for label, pat in _GLOBAL_EXCLUDE_PATTERNS.items():
        if pat.search(blob):
            excluded.append(label)

    for label, pat in _POSITION_EXCLUDE_PATTERNS.items():
        if pat.search(position_title):
            excluded.append(label)

    # 컷 사유 자체가 misclassification을 인정하는 표현 (모빌린트 패턴)
    if _MISCLASSIFICATION_RE.search(screening_text):
        excluded.append("misclassification")

    # 경력 범위: hi ≤ 10 단독으로 14년차 ceiling 미달 (헤리트 6-9년차 패턴).
    # lo 조건은 "5-12년" 같은 14년차 인근 ceiling을 잡지 못하므로 제거.
    blob_short = f"{position_title}\n{jd_text}\n{screening_text}"
    for m in _EXP_RANGE_RE.finditer(blob_short):
        lo, hi = int(m.group(1)), int(m.group(2))
        if hi <= 10:
            excluded.append(f"exp_range_{lo}_{hi}")
            break

    # "3-5년차" 같은 표현 — filename + JD 헤더에 자주 등장
    for m in _EXP_YEARCHA_RE.finditer(blob_short):
        lo, hi = int(m.group(1)), int(m.group(2))
        if hi <= 10:
            excluded.append(f"exp_yearcha_{lo}_{hi}")
            break

    for m in _EXP_CEILING_RE.finditer(blob_short):
        ceiling = int(m.group(1))
        if ceiling <= 10:
            excluded.append(f"exp_ceiling_{ceiling}")
            break

    return excluded


# ----------------------------------------------------------------------
# Suspicion scoring
# ----------------------------------------------------------------------

@dataclass
class SuspicionResult:
    job_id: str
    company: str
    position: str
    folder: str
    score: int = 0
    patterns: list[str] = field(default_factory=list)
    auto_excluded: list[str] = field(default_factory=list)
    cut_reason_excerpt: str = ""
    primary_evidence_excerpt: str = ""
    jd_path: str = ""
    screening_path: str = ""

    @property
    def is_excluded(self) -> bool:
        return bool(self.auto_excluded)


def score_suspicion(
    cut_reason: str, jd_primary: str, qualitative_only_in_cut: bool = False
) -> tuple[int, list[str]]:
    """Compute suspicion score and matched patterns.

    Score additions:
      P1  +30 — Polyglot rule violation
      P2  +25 — 0.5절 일관성 결함 (정성적 우려 단독 + 1차 증거 부재)
      P3  +20 — TheVC M&A 추론
      Q1  +20 — 단일 ❌ + 직접 1차 증거 매치 부재
      Q2  +15 — 4조건 모두 △ 패턴
      D1  +25 — 데이터 부재 단독 ❌ (디렉셔널 패턴, P2 변형)
    """
    score = 0
    patterns: list[str] = []

    # P1 — Polyglot
    for pat, label in P1_PATTERNS:
        if pat.search(cut_reason):
            score += 30
            patterns.append(f"P1:{label}")
            break  # 한 번만 적용

    # P2 — 0.5절 일관성 결함
    # 트리거: 컷 사유에 정성적 우려 표현 등장 + 컷 사유에 1차 증거 키워드 부재
    # JD primary 매치 검사는 의도적으로 제외 — JD 자격요건에 1차 증거가 있어도
    # 컷 사유가 정성적 우려 단독이면 P2가 발동되어야 한다 (디렉셔널/레브잇 케이스).
    qualitative_hits = [
        label for pat, label in _QUALITATIVE_CONCERN_PATTERNS if pat.search(cut_reason)
    ]
    cut_has_primary, cut_primary_hits = has_primary_evidence_match(cut_reason)

    if qualitative_hits and not cut_has_primary:
        score += 30
        patterns.append("P2:" + "|".join(qualitative_hits[:2]))

    # D1 — 데이터 부재 단독 ❌ (디렉셔널 패턴)
    data_vacant_hits = [
        label for pat, label in _DATA_VACANT_PATTERNS if pat.search(cut_reason)
    ]
    if data_vacant_hits and not cut_has_primary:
        # 정성적 우려와 중첩되면 +5만 (P2가 이미 +30)
        if "P2:" in " ".join(patterns):
            score += 5
            patterns.append("D1:" + "|".join(data_vacant_hits[:2]) + "(보강)")
        else:
            score += 30
            patterns.append("D1:" + "|".join(data_vacant_hits[:2]))

    # P3 — TheVC 추론
    for pat, label in P3_PATTERNS:
        if pat.search(cut_reason):
            score += 20
            patterns.append(f"P3:{label}")
            break

    # Q1 — 단일 ❌ + 직접 매치 부재
    cut_reject_count = cut_reason.count("❌")
    if cut_reject_count == 1 and not cut_has_primary:
        score += 20
        patterns.append("Q1:single_reject_no_primary")

    # Q2 — 4조건 모두 △ 패턴
    triangle_count = len(re.findall(r"△", cut_reason))
    if triangle_count >= 3:
        score += 15
        patterns.append(f"Q2:triangle_{triangle_count}")

    return (score, patterns)


# ----------------------------------------------------------------------
# Per-file processing
# ----------------------------------------------------------------------

def parse_filename_metadata(filename: str) -> tuple[str, str, str]:
    """Extract (job_id, company_slug, position_slug) from filename."""
    job_id = extract_job_id_from_filename(filename) or ""
    stem = Path(filename).stem
    parts = stem.split("-")
    # path_utils variants:
    #   "123456-company-position.md"
    #   "groupby-8807-company-position.md"
    #   "private-company-position.md"
    if parts and parts[0].isdigit():
        rest = parts[1:]
    elif len(parts) > 1 and parts[0] == "groupby" and parts[1].isdigit():
        rest = parts[2:]
    elif len(parts) > 1 and parts[1].isdigit():
        rest = parts[2:]
    else:
        rest = parts[1:] if len(parts) > 1 else []
    if not rest:
        return (job_id, "", "")
    # 휴리스틱: 첫 1~2 토큰을 company, 나머지를 position으로
    company = rest[0]
    position = "-".join(rest[1:]) if len(rest) > 1 else ""
    return (job_id, company, position)


def process_screening_file(
    screening_path: Path,
    file_locations: dict[str, str],
    include_processed: bool,
) -> Optional[SuspicionResult]:
    """Process a single screening file. Returns None if filtered out."""
    raw_text = screening_path.read_text(encoding="utf-8")

    # 정정 블록 stripping — 원본 컷 사유만 분석
    text = strip_correction_blocks(raw_text)

    # 현재 verdict 확인
    verdict_label, _ = extract_last_verdict(text)
    folder = file_locations.get(screening_path.name, "missing")

    # protected status (applied/rejected/interview/offer)는 status-pipeline 소관 —
    # screening verdict가 "지원 비추천"으로 남아있더라도 audit 대상이 아님.
    if folder in PROTECTED_STATUSES:
        return None

    # 비추천 (pass) 또는 정정 처리된 파일만 대상
    is_currently_pass = (verdict_label == "pass") or (folder == "pass")
    is_correction_processed = bool(_CORRECTION_HEADER_RE.search(raw_text))

    if not is_currently_pass:
        if not (include_processed and is_correction_processed):
            return None

    job_id, company, position = parse_filename_metadata(screening_path.name)

    # JD 파일 lookup
    jd_path = find_existing_jd(job_id) if job_id else None
    jd_primary = extract_jd_primary_evidence(jd_path)

    # JD 누락 처리
    if jd_path is None:
        return SuspicionResult(
            job_id=job_id,
            company=company,
            position=position,
            folder=folder,
            score=0,
            auto_excluded=["jd_missing"],
            cut_reason_excerpt="",
            primary_evidence_excerpt="",
            jd_path="",
            screening_path=str(screening_path.relative_to(REPO_ROOT)),
        )

    cut_reason = extract_cut_reason(text)

    # 자동 제외 룰
    jd_text = jd_path.read_text(encoding="utf-8") if jd_path else ""
    auto_excluded = detect_auto_exclusions(text, jd_text, position)

    # 점수 계산
    score, patterns = score_suspicion(cut_reason, jd_primary)

    # 자동 제외 시 -50 (보통 음수가 되어 임계값 미만)
    if auto_excluded:
        score = max(0, score - 50)

    return SuspicionResult(
        job_id=job_id,
        company=company,
        position=position,
        folder=folder,
        score=score,
        patterns=patterns,
        auto_excluded=auto_excluded,
        cut_reason_excerpt=cut_reason[:300].replace("\n", " ⏎ "),
        primary_evidence_excerpt=jd_primary[:300].replace("\n", " ⏎ "),
        jd_path=str(jd_path.relative_to(REPO_ROOT)) if jd_path else "",
        screening_path=str(screening_path.relative_to(REPO_ROOT)),
    )


# ----------------------------------------------------------------------
# CSV / JSON output
# ----------------------------------------------------------------------

CSV_FIELDNAMES = [
    "job_id",
    "company",
    "position",
    "folder",
    "suspicion_score",
    "suspicion_patterns",
    "auto_excluded",
    "auto_exclude_reasons",
    "cut_reason_excerpt",
    "primary_evidence_excerpt",
    "jd_path",
    "screening_path",
]


def result_to_csv_row(r: SuspicionResult) -> dict[str, str]:
    return {
        "job_id": r.job_id,
        "company": r.company,
        "position": r.position,
        "folder": r.folder,
        "suspicion_score": str(r.score),
        "suspicion_patterns": ";".join(r.patterns),
        "auto_excluded": "1" if r.is_excluded else "0",
        "auto_exclude_reasons": ";".join(r.auto_excluded),
        "cut_reason_excerpt": r.cut_reason_excerpt,
        "primary_evidence_excerpt": r.primary_evidence_excerpt,
        "jd_path": r.jd_path,
        "screening_path": r.screening_path,
    }


def result_to_json(r: SuspicionResult, full_jd: bool = False) -> dict:
    out = {
        "job_id": r.job_id,
        "company": r.company,
        "position": r.position,
        "folder": r.folder,
        "suspicion_score": r.score,
        "patterns": r.patterns,
        "auto_excluded": r.auto_excluded,
        "cut_reason": r.cut_reason_excerpt,
        "primary_evidence": r.primary_evidence_excerpt,
        "jd_path": r.jd_path,
        "screening_path": r.screening_path,
    }
    if full_jd and r.jd_path:
        full = (REPO_ROOT / r.jd_path).read_text(encoding="utf-8")
        out["jd_full"] = full
    return out


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="JD screening 사후 감사 (룰 0.5절/Polyglot/TheVC)")
    parser.add_argument("--output", default=None, help="CSV output path")
    parser.add_argument("--json", action="store_true", help="Also write JSON with full context")
    parser.add_argument(
        "--include-processed",
        action="store_true",
        help="정정 처리된 파일도 포함 (골든 검증용)",
    )
    parser.add_argument(
        "--check-anchor",
        type=str,
        default=None,
        help="anchor job_id (e.g. 285243). score >= 60일 경우 비0 종료",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=30,
        help="CSV에 포함할 최소 의심도 점수 (기본 30)",
    )
    parser.add_argument(
        "--anchor-cutoff",
        type=int,
        default=60,
        help="anchor 검증 임계값 (기본 60)",
    )
    args = parser.parse_args()

    if not SCREENING_DIR.exists():
        print(f"Error: {SCREENING_DIR} not found", file=sys.stderr)
        return 1

    file_locations = load_file_locations()

    results: list[SuspicionResult] = []
    for md_file in sorted(SCREENING_DIR.glob("*.md")):
        if md_file.name == "SUMMARY.md":
            continue
        r = process_screening_file(md_file, file_locations, args.include_processed)
        if r is not None:
            results.append(r)

    # 점수 내림차순 정렬
    results.sort(key=lambda x: (-x.score, x.job_id))

    # 출력 경로
    out_path = (
        Path(args.output)
        if args.output
        else REPO_ROOT / "private" / "jd_analysis" / "audit_05.csv"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 임계값 필터링 (CSV에는 threshold 이상만)
    filtered = [r for r in results if r.score >= args.threshold or r.is_excluded]

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        for r in filtered:
            writer.writerow(result_to_csv_row(r))

    if args.json:
        json_path = out_path.with_suffix(".json")
        with json_path.open("w", encoding="utf-8") as f:
            json.dump(
                [result_to_json(r, full_jd=True) for r in filtered if not r.is_excluded],
                f,
                ensure_ascii=False,
                indent=2,
            )

    # ---------- summary ----------
    total = len(results)
    excluded = sum(1 for r in results if r.is_excluded)
    high = sum(1 for r in results if r.score >= 70)
    mid = sum(1 for r in results if 60 <= r.score < 70)
    low_review = sum(1 for r in results if 30 <= r.score < 60)
    no_signal = sum(1 for r in results if r.score < 30 and not r.is_excluded)

    print("=" * 70)
    print(f"audit_05 — JD 비추천 사후 감사 ({total}건)")
    print("=" * 70)
    print(f"자동 제외:                    {excluded:>4} ({100*excluded/total:.1f}%)" if total else "자동 제외:                       0")
    print(f"의심도 ≥70 (거의 확실):       {high:>4}")
    print(f"의심도 60-69 (우선 처리):     {mid:>4}")
    print(f"의심도 30-59 (라운드 검토):   {low_review:>4}")
    print(f"의심도 <30 (무신호):           {no_signal:>4}")
    print()
    print(f"CSV 출력: {out_path}")
    if args.json:
        print(f"JSON 출력: {json_path}")

    # 패턴 분포
    pattern_counts: dict[str, int] = {}
    for r in results:
        if r.is_excluded:
            continue
        for p in r.patterns:
            key = p.split(":")[0]
            pattern_counts[key] = pattern_counts.get(key, 0) + 1
    if pattern_counts:
        print()
        print("패턴 분포 (자동 제외 제외):")
        for k in sorted(pattern_counts.keys()):
            print(f"  {k}: {pattern_counts[k]}")

    # ---------- anchor check ----------
    anchor_failed = False
    if args.check_anchor:
        anchor = next((r for r in results if r.job_id == args.check_anchor), None)
        print()
        print("=" * 70)
        print(f"Anchor check — job_id={args.check_anchor}")
        print("=" * 70)
        if anchor is None:
            print(f"⚠️  anchor job_id={args.check_anchor} not found in results")
            anchor_failed = True
        else:
            print(f"score={anchor.score}, patterns={anchor.patterns}, excluded={anchor.auto_excluded}")
            if anchor.score >= args.anchor_cutoff:
                print(f"❌ FAIL: anchor score {anchor.score} >= {args.anchor_cutoff}")
                anchor_failed = True
            else:
                print(f"✅ OK: anchor score {anchor.score} < {args.anchor_cutoff}")

    return 1 if anchor_failed else 0


if __name__ == "__main__":
    sys.exit(main())
