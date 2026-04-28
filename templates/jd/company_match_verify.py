"""Lightweight cross-check between company_info file and the JD it was matched to.

Catches homonym extraction errors like 와이폴라리스 vs 에스와이폴라리스 by comparing
key business tokens between the company_info markdown and the JD's company-introduction
section.

Operator-facing: returns (ok, confidence, mismatch_terms). Caller decides whether to
block, warn, or continue. The auto pipeline emits a stderr warning only.

Calibration (2026-04-26): thresholds set against two known cases —
- FAIL: 에스와이폴라리스.md vs groupby-355 (진짜 와이폴라리스, 도메인 0% overlap)
- PASS: 캐처스.md vs groupby-235 (회사명 + C2M + 커머스 overlap)
"""

from __future__ import annotations

import re
from pathlib import Path

_HEADING_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
_SECTION_RE = re.compile(r"^##\s+(.+)$", re.MULTILINE)
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9]+|[가-힣]{2,}")

_STOP_WORDS: frozenset[str] = frozenset({
    "회사", "기업", "조직", "팀", "사업", "사업부", "부서",
    "정보", "내용", "항목", "출처", "기준", "확인", "현재", "최근", "주요",
    "개발", "운영", "관리", "구축", "유지보수", "지원", "제공", "수행",
    "솔루션", "플랫폼", "서비스", "시스템", "프로젝트", "프로그램", "어플리케이션",
    "기술", "기능", "방식", "환경", "역할", "업무", "포지션", "직무",
    "스택", "클라우드", "인프라", "데이터베이스", "네트워크", "프론트엔드", "백엔드",
    "경험", "경력", "능력", "지식", "전공", "전문", "필수", "우대", "자격", "요건",
    "고객", "고객사", "사용자", "이용자",
    "한국", "글로벌", "해외", "국내", "서울", "강남", "서초",
    "company", "service", "platform", "solution", "system", "team", "project",
    "tech", "stack", "cloud", "data", "info", "user", "global", "korea",
    "ltd", "inc", "corp", "co", "kr", "com",
    "있는", "있음", "없음", "다양한", "관련", "기반", "통한", "위한",
    "년도", "이상", "이하", "수준", "정도",
})

_PLATFORM_DOMAINS: frozenset[str] = frozenset({
    "wanted", "saramin", "jobkorea", "thevc", "groupby",
    "rememberapp", "remember", "linkedin", "github",
    "naver", "google", "kakao", "daum",
})

_SECONDARY_LABELS: frozenset[str] = frozenset({"co", "com", "net", "org", "gov", "edu", "ac", "or", "ne"})


def _read(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def _extract_section(content: str, names: list[str]) -> str:
    """Return concatenated text of `## <name>` sections matching any of `names`."""
    if not content:
        return ""

    boundaries: list[tuple[int, int, str]] = []
    matches = list(_SECTION_RE.finditer(content))
    for i, m in enumerate(matches):
        title = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        boundaries.append((start, end, title))

    parts: list[str] = []
    for start, end, title in boundaries:
        if any(n in title for n in names):
            parts.append(content[start:end])
    return "\n".join(parts)


def _extract_heading_company(content: str) -> str:
    m = _HEADING_RE.search(content)
    if not m:
        return ""
    raw = m.group(1).strip()
    raw = re.sub(r"\([^)]*\)", "", raw).strip()
    return raw.lower()


def _extract_jd_company(content: str) -> str:
    m = re.search(r"\|\s*회사명\s*\|\s*([^|]+)\|", content)
    if not m:
        return ""
    raw = m.group(1).strip()
    raw = re.sub(r"\([^)]*\)", "", raw).strip()
    return raw.lower()


def _extract_domains(text: str) -> set[str]:
    """Pull out company-specific domain stems (e.g., 'ypolaris' from 'www.ypolaris.com').

    Extracts the registrable SLD to avoid false positives from generic subdomains
    like 'careers' in 'careers.alpha.com'. Handles ccTLD+SLD patterns (co.kr, ac.kr).
    Excludes recruiting platforms and generic services so that two unrelated
    companies extracted from the same source (e.g., both via Wanted) don't
    match on the platform domain alone.
    """
    domains: set[str] = set()
    for m in re.finditer(r"(?:https?://)?([a-z0-9][a-z0-9.-]*\.[a-z]{2,})", text.lower()):
        parts = m.group(1).split(".")
        if len(parts) < 2:
            continue
        idx = len(parts) - 2
        if parts[idx] in _SECONDARY_LABELS and idx > 0:
            idx -= 1
        stem = parts[idx]
        if stem == "www" or stem in _PLATFORM_DOMAINS or len(stem) < 3:
            continue
        domains.add(stem)
    return domains


def _tokenize(text: str) -> set[str]:
    if not text:
        return set()
    text_lower = text.lower()
    raw = _TOKEN_RE.findall(text_lower)
    return {t for t in raw if t not in _STOP_WORDS and len(t) >= 2}


def _name_match_kind(name_a: str, name_b: str) -> str:
    """Classify name relationship into one of: 'exact', 'substring', 'none'.

    'substring' alone is NOT a strong signal — '와이폴라리스' ⊂ '에스와이폴라리스'
    despite being unrelated companies. Callers must combine substring with another
    signal (token overlap or domain match) before treating it as a match.
    """
    if not name_a or not name_b:
        return "none"
    if name_a == name_b:
        return "exact"
    if name_a in name_b or name_b in name_a:
        return "substring"
    return "none"


def verify_company_match(
    company_info_path: str | Path,
    jd_path: str | Path,
    threshold: float = 0.10,
) -> tuple[bool, float, list[str]]:
    """Compare company_info content vs JD company-introduction tokens.

    Signal hierarchy (any one strong signal → ok=True):
      1. Exact heading-name match (heading "캐처스" vs JD "캐처스")
      2. Company-specific domain overlap (e.g., 'ypolaris' in both, after
         excluding recruiting platforms like wanted/groupby)
      3. Token Jaccard overlap ≥ threshold
      4. Substring name match + token overlap ≥ threshold/2 (weak combo)

    Args:
        company_info_path: Path to a `private/company_info/<slug>.md` file.
        jd_path: Path to a JD markdown file.
        threshold: Minimum Jaccard overlap of business tokens (default 0.10
            from calibration: 캐처스 PASS at 0.125, 와이폴라리스 FAIL at 0.011).

    Returns:
        (ok, confidence, mismatch_terms) where:
          - ok: True if any strong signal aligns.
          - confidence: Jaccard score in [0, 1].
          - mismatch_terms: tokens unique to company_info (top 10), useful for
            operator review when ok is False.
    """
    info_text = _read(company_info_path)
    jd_text = _read(jd_path)

    info_company = _extract_heading_company(info_text)
    jd_company = _extract_jd_company(jd_text)

    info_intro = _extract_section(info_text, ["회사 소개", "회사소개", "사업 영역", "사업영역", "회사 개요", "회사개요"])
    jd_intro = _extract_section(jd_text, ["회사 개요", "회사개요", "회사 소개", "회사소개", "주요 업무", "주요업무"])

    info_tokens = _tokenize(info_intro) | _tokenize(info_company)
    jd_tokens = _tokenize(jd_intro) | _tokenize(jd_company)

    info_domains = _extract_domains(info_text)
    jd_domains = _extract_domains(jd_text)
    domain_overlap = info_domains & jd_domains

    name_kind = _name_match_kind(info_company, jd_company)
    has_strong_signal = name_kind == "exact" or bool(domain_overlap)

    if not has_strong_signal and (not info_tokens or not jd_tokens):
        return (False, 0.0, [])

    intersection = info_tokens & jd_tokens
    union = info_tokens | jd_tokens
    jaccard = len(intersection) / len(union) if union else 0.0

    ok = (
        has_strong_signal
        or jaccard >= threshold
        or (name_kind == "substring" and jaccard >= threshold / 2)
    )

    mismatches = sorted(info_tokens - jd_tokens, key=lambda t: -len(t))[:10]
    return (ok, round(jaccard, 3), mismatches)
