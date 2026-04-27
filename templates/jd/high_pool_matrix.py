"""high/ 풀 의사결정 매트릭스.

각 JD에서 회사·포지션·경력·근무지·연봉을 추출하고,
screening 결과·company_info에서 추가 신호를 수집해
우선순위 점수와 함께 표로 출력.
"""

from __future__ import annotations

import re
from pathlib import Path

HIGH = Path("private/job_postings/conditional/high")
SCREEN = Path("private/jd_analysis/screening")
COMPANY_INFO = Path("private/company_info")

# 통근 리스크 지역 분류 (룰 문서 기준)
COMMUTE_OK = ("서울", "강남", "역삼", "판교", "양재", "선릉", "삼성", "광화문", "여의도", "마포", "을지로", "종로", "용산")
COMMUTE_RISK = ("분당", "수내", "정자", "동탄", "화성", "평택", "오송", "청주", "남양주", "광주", "이천", "여주", "하남")


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


def commute_tier(location: str | None) -> str:
    if not location:
        return "?"
    for kw in COMMUTE_RISK:
        if kw in location:
            return "RISK"
    for kw in COMMUTE_OK:
        if kw in location:
            return "OK"
    return "?"


def find_company_info(company: str | None) -> Path | None:
    if not company:
        return None
    norm = company.lower().replace(" ", "-").replace("(", "").replace(")", "")
    # 검색 — 정확 일치 + 부분
    for c in COMPANY_INFO.glob("*.md"):
        stem_low = c.stem.lower()
        if norm in stem_low or stem_low in norm:
            return c
        # 한글 부분 일치
        bare = re.sub(r"[a-z\-_0-9]", "", company.lower())
        if bare and bare in c.stem.lower():
            return c
    return None


def get_company_signals(company_file: Path) -> dict:
    if not company_file or not company_file.exists():
        return {}
    text = company_file.read_text(encoding="utf-8", errors="replace")
    sig = {}
    sig["avg_salary"] = _extract(text, ("평균 연봉",))
    sig["employees"] = _extract(text, ("현재 인원", "직원수"))
    sig["revenue"] = _extract(text, ("매출",))
    sig["industry"] = _extract(text, ("업종",))
    return sig


def categorize_company(company: str | None, signals: dict) -> str:
    """대기업/중견/스타트업 분류."""
    if not company:
        return "?"
    employees_str = signals.get("employees", "") or ""
    employees_num = re.search(r"(\d[\d,]*)", employees_str.replace(",", ""))
    n_employees = int(employees_num.group(1)) if employees_num else 0

    # 명시적 대기업/계열
    big_keywords = ["삼성", "현대", "LG", "SK", "한화", "롯데", "신세계", "포스코", "GS", "KT", "두산",
                    "카카오", "네이버", "쿠팡", "배달의민족", "우아한", "토스", "당근", "라인",
                    "코웨이", "기아", "넥슨", "엔씨", "넷마블", "크래프톤"]
    if any(b in company for b in big_keywords):
        return "대기업·계열"
    if n_employees >= 1000:
        return "대기업·계열"
    if 300 <= n_employees < 1000:
        return "중견"
    if n_employees > 0:
        return "스타트업"
    return "?"


def get_screening_verdict_note(name: str) -> tuple[str, str]:
    """스크리닝 파일에서 verdict 키워드와 한 줄 요약."""
    sp = SCREEN / name
    if not sp.exists():
        return "?", ""
    text = sp.read_text(encoding="utf-8", errors="replace")
    # 코테 정책 완화로 자동 승급 유무
    is_codingtest_recovery = "코테 정책 완화" in text or "코딩테스트 정책 완화" in text
    # 한 줄 요약 추출
    m = re.search(r"##\s*한 줄 요약\s*\n\s*>?\s*(.+?)(?:\n|$)", text)
    summary = m.group(1).strip() if m else ""
    if not summary:
        # 첫 결론 문장 fallback
        m2 = re.search(r"##\s*핵심 근거.*?\n\s*-?\s*\*\*(.+?)\*\*", text, re.DOTALL)
        summary = m2.group(1).strip() if m2 else ""
    tag = "코테회복" if is_codingtest_recovery else ""
    return tag, summary[:80]


def main() -> None:
    rows = []
    for jd in sorted(HIGH.glob("*.md")):
        text = jd.read_text(encoding="utf-8", errors="replace")
        company = _extract(text, ("회사명", "회사", "기업명")) or jd.stem.split("-", 2)[1]
        position = _extract(text, ("포지션", "직무")) or jd.stem
        career = _extract(text, ("경력 요건", "경력"))
        location = _extract(text, ("근무지",))
        ci = find_company_info(company)
        signals = get_company_signals(ci) if ci else {}
        co_type = categorize_company(company, signals)
        commute = commute_tier(location)
        tag, note = get_screening_verdict_note(jd.name)

        # 우선순위 점수 (간단 규칙)
        score = 0
        if co_type == "대기업·계열": score += 30
        elif co_type == "중견": score += 20
        elif co_type == "스타트업": score += 10
        if commute == "OK": score += 10
        elif commute == "RISK": score -= 20
        if signals.get("avg_salary") and "만원" in signals["avg_salary"]:
            sal_num = re.search(r"(\d[\d,]*)", signals["avg_salary"].replace(",", ""))
            if sal_num and int(sal_num.group(1)) >= 7000:
                score += 15
            elif sal_num and int(sal_num.group(1)) < 5000:
                score -= 10
        if not tag:
            score += 5  # 직접 추천 (코테회복 아님)

        rows.append({
            "id": jd.stem.split("-", 1)[0],
            "company": company,
            "position": position[:45],
            "career": career or "?",
            "location": (location or "?")[:30],
            "co_type": co_type,
            "commute": commute,
            "avg_salary": (signals.get("avg_salary") or "?")[:15],
            "tag": tag,
            "note": note,
            "score": score,
        })

    rows.sort(key=lambda r: -r["score"])

    print(f"# high/ 풀 우선순위 매트릭스 ({len(rows)}건)\n")
    print(f"{'#':>3}  {'점':>3}  {'ID':6}  {'회사':24}  {'유형':10}  {'근무지':22}  {'통근':5}  {'평균연봉':13}  {'태그':8}  포지션")
    print("-" * 220)
    for i, r in enumerate(rows, 1):
        print(f"{i:>3}  {r['score']:>3}  {r['id']:6}  {r['company'][:24]:24}  {r['co_type']:10}  {r['location'][:22]:22}  {r['commute']:5}  {r['avg_salary']:13}  {r['tag']:8}  {r['position']}")


if __name__ == "__main__":
    main()
