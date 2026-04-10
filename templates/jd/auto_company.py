#!/usr/bin/env python3
"""Company info generation utilities for JD auto pipeline."""

from __future__ import annotations

import logging
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    from .company_extractor import extract_company_info
    from .company_validator import COMPANY_INFO_DIR, parse_company_file, validate_company
    from .jd_content import extract_metadata_from_jd
    from .naming import slugify_company
except ImportError:
    from company_extractor import extract_company_info
    from company_validator import COMPANY_INFO_DIR, parse_company_file, validate_company
    from jd_content import extract_metadata_from_jd
    from naming import slugify_company

_log = logging.getLogger(__name__)


THEVC_MODES = {"auto", "skip", "require"}
ENRICHMENT_QUEUE_PATH = Path(__file__).parent.parent.parent / "private" / "job_postings" / "unprocessed" / "company_enrichment_thevc.txt"

HEADHUNTING_KEYWORDS = ["써치", "서치펌", "헤드헌팅", "리크루팅", "인력파견", "헤드헌터"]


def is_headhunting_company(company_name: str) -> bool:
    """헤드헌팅/서치펌 여부 감지. 해당 시 정보 수집 제외 대상."""
    return any(kw in company_name for kw in HEADHUNTING_KEYWORDS)


@dataclass
class CompanyInfoResult:
    company: str
    file_path: Path
    used_existing: bool
    completeness: float
    thevc_attempted: bool
    thevc_status: str
    investment_data_source: str


def _extract_company_name_from_jd(jd_path: Path) -> Optional[str]:
    content = jd_path.read_text(encoding="utf-8")
    meta = extract_metadata_from_jd(content)
    company = (meta.get("company") or "").strip()

    if company:
        return company

    # fallback: "# title - company"
    first_line = content.splitlines()[0] if content.splitlines() else ""
    if " - " in first_line:
        candidate = first_line.split(" - ")[-1].strip().strip("# ")
        if candidate:
            return candidate

    # fallback: filename-based
    parts = jd_path.stem.split("-")
    if len(parts) >= 2:
        return parts[1]
    return None


def _find_existing_company_file(company: str) -> Optional[Path]:
    slug = slugify_company(company)
    exact = COMPANY_INFO_DIR / f"{slug}.md"
    if exact.exists():
        return exact

    company_lower = company.lower()
    for file in COMPANY_INFO_DIR.glob("*.md"):
        if file.name.startswith("_"):
            continue
        stem = file.stem.lower()
        if slug in stem or company_lower in stem:
            return file
    return None


def _looks_startup(jd_text: str) -> bool:
    startup_tokens = [
        "시리즈",
        "series",
        "startup",
        "스타트업",
        "투자",
        "pre-a",
        "seed",
        "벤처",
        "thevc",
    ]
    text_lower = jd_text.lower()
    return any(token in text_lower for token in startup_tokens)


def _fetch_url_text(url: str, timeout: int = 15) -> str:
    if not url.startswith(("https://", "http://")):
        raise ValueError(f"Unsupported URL scheme: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read(2 * 1024 * 1024).decode("utf-8", errors="ignore")


def _strip_html(html: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.IGNORECASE)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_thevc_investment(company: str) -> tuple[str, Optional[dict]]:
    """Return (status, investment_data)."""
    query = urllib.parse.quote(company)
    search_url = f"https://thevc.kr/integrated-search/overview?keyword={query}"

    try:
        html = _fetch_url_text(search_url)
    except (urllib.error.URLError, TimeoutError, OSError):
        return "network_error", None
    except Exception:
        return "parse_error", None

    text = _strip_html(html)

    login_signals = ["로그인", "Sign in", "회원가입", "계정", "Google로 시작"]
    if any(signal.lower() in text.lower() for signal in login_signals):
        # Best-effort signal: many public pages still show login CTA,
        # so we require no investment tokens to classify as not_logged_in.
        inv_tokens = ["Series", "Seed", "누적", "투자", "억원", "Pre-A"]
        if not any(tok.lower() in text.lower() for tok in inv_tokens):
            return "not_logged_in", None

    round_match = re.search(r"(Seed|Pre-A|Series\s*[A-Z]|IPO|M&A)", text, re.IGNORECASE)
    investment_match = re.search(r"([\d,]+(?:\.\d+)?)\s*억", text)

    if not round_match and not investment_match:
        return "access_limited", None

    return (
        "success",
        {
            "round": round_match.group(1) if round_match else "정보 없음",
            "total": f"{investment_match.group(1)}억원" if investment_match else "정보 없음",
            "source": search_url,
        },
    )


def _build_company_info_markdown(company: str, jd_url: str, startup: bool, thevc_note: str, investment: Optional[dict]) -> str:
    investment_section = ""
    if startup:
        round_value = investment.get("round", "정보 없음") if investment else "정보 없음"
        total_value = investment.get("total", "정보 없음") if investment else "정보 없음"
        inv_source = investment.get("source", "https://thevc.kr") if investment else "https://thevc.kr"

        investment_section = f"""
## 투자 정보

| 항목 | 내용 |
|------|------|
| 현재 라운드 | {round_value} |
| 누적 투자금 | {total_value} |

> {thevc_note}
"""
        if inv_source:
            investment_section += f"\n출처: [{inv_source}]({inv_source})\n"

    return f"""# {company}

## 기업 정보

| 항목 | 내용 |
|------|------|
| 회사명 | {company} |
| 업종 | 정보 없음 |
| 설립 | 정보 없음 |
| 직원수 | 정보 없음 |

## 연봉 정보

| 항목 | 금액 | 출처 |
|------|------|------|
| 평균 연봉 | 정보 없음 | 정보 없음 |

## 인원 통계

| 항목 | 수치 |
|------|------|
| 현재 인원 | 정보 없음 |
| 1년간 입사자 | 정보 없음 |
| 1년간 퇴사자 | 정보 없음 |
{investment_section}
---

*자동 생성일: TBD*
*JD 출처: [{jd_url}]({jd_url})*
"""


def _build_thevc_section(investment: dict) -> str:
    """Build TheVC investment section markdown."""
    round_value = investment.get("round", "정보 없음")
    total_value = investment.get("total", "정보 없음")
    inv_source = investment.get("source", "https://thevc.kr")

    section = f"""## 투자 정보

| 항목 | 내용 |
|------|------|
| 현재 라운드 | {round_value} |
| 누적 투자금 | {total_value} |

> TheVC에서 투자정보를 추출했습니다.
"""
    if inv_source:
        section += f"\n출처: [{inv_source}]({inv_source})\n"
    return section


def _inject_thevc_into_file(file_path: Path, investment: dict) -> None:
    """Inject or replace TheVC investment section in an existing company info file."""
    content = file_path.read_text(encoding="utf-8")
    thevc_section = _build_thevc_section(investment)

    if "## 투자 정보" in content:
        content = re.sub(
            r"## 투자 정보.*?(?=\n## |\n---|\Z)",
            thevc_section,
            content,
            flags=re.DOTALL,
        )
    elif "\n---\n" in content:
        content = content.replace("\n---\n", f"\n{thevc_section}\n---\n", 1)
    else:
        content += f"\n{thevc_section}"

    file_path.write_text(content, encoding="utf-8")


def _append_enrichment_queue(company: str) -> None:
    ENRICHMENT_QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing = set()
    if ENRICHMENT_QUEUE_PATH.exists():
        existing = {line.strip() for line in ENRICHMENT_QUEUE_PATH.read_text(encoding="utf-8").splitlines() if line.strip()}
    if company not in existing:
        with open(ENRICHMENT_QUEUE_PATH, "a", encoding="utf-8") as f:
            f.write(company + "\n")


def ensure_company_info(
    jd_path: Path,
    jd_url: str,
    company_name: Optional[str] = None,
    thevc_mode: str = "auto",
    dry_run: bool = False,
    min_completeness: float = 0.0,
) -> CompanyInfoResult:
    if thevc_mode not in THEVC_MODES:
        raise ValueError(f"유효하지 않은 thevc_mode: {thevc_mode}")

    company = (company_name or _extract_company_name_from_jd(jd_path) or "unknown-company").strip()

    if is_headhunting_company(company):
        from datetime import date
        slug = slugify_company(company)
        file_path = COMPANY_INFO_DIR / f"{slug}.md"
        if not file_path.exists():
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(
                f"# {company}\n\n⚠️ 헤드헌팅/서치펌 — 정보 수집 제외 대상.\n\n---\n\n*확인일: {date.today().isoformat()}*\n",
                encoding="utf-8",
            )
        return CompanyInfoResult(
            company=company,
            file_path=file_path,
            used_existing=True,
            completeness=0.0,
            thevc_attempted=False,
            thevc_status="skipped",
            investment_data_source="headhunting_excluded",
        )

    existing = _find_existing_company_file(company)
    if existing:
        completeness = -1.0
        try:
            data = parse_company_file(existing)
            result = validate_company(data, existing)
            completeness = result.completeness_score
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(
                "completeness 파싱 실패 (%s): %s — re-collection 진행", existing, exc
            )

        if completeness >= 0 and completeness >= min_completeness:
            return CompanyInfoResult(
                company=company,
                file_path=existing,
                used_existing=True,
                completeness=completeness,
                thevc_attempted=False,
                thevc_status="skipped",
                investment_data_source="existing",
            )

    jd_text = jd_path.read_text(encoding="utf-8")
    startup = _looks_startup(jd_text)

    thevc_attempted = False
    thevc_status = "skipped"
    investment_data = None
    investment_source = "none"
    thevc_note = "TheVC 투자정보를 사용하지 않았습니다."

    if startup and thevc_mode != "skip":
        thevc_attempted = True
        thevc_status, investment_data = _extract_thevc_investment(company)
        if thevc_status == "success" and investment_data:
            investment_source = "thevc"
            thevc_note = "TheVC에서 투자정보를 추출했습니다."
        elif thevc_status == "not_logged_in":
            thevc_note = "TheVC 로그인 필요로 투자정보를 수집하지 못했습니다."
            _append_enrichment_queue(company)
        elif thevc_status == "access_limited":
            thevc_note = "TheVC 접근 제한으로 투자정보를 수집하지 못했습니다."
            _append_enrichment_queue(company)
        else:
            thevc_note = "TheVC 투자정보 추출에 실패했습니다."

        if thevc_mode == "require" and thevc_status != "success":
            raise RuntimeError(f"TheVC 투자정보 수집 실패({thevc_status}) - require 모드")

    slug = slugify_company(company)
    output_path = COMPANY_INFO_DIR / f"{slug}.md"

    # Phase 2: Wanted + Saramin extraction (skip on dry_run)
    extraction = None
    has_extraction = False

    if not dry_run:
        try:
            extraction = extract_company_info(
                company_name=company,
                platforms=["wanted", "saramin"],
            )
            has_extraction = len(extraction.platforms_used) > 0
            if has_extraction:
                output_path = extraction.file_path
                _log.info("회사 정보 추출 완료: %s (platforms=%s)", company, extraction.platforms_used)
        except Exception as exc:
            _log.warning("회사 정보 추출 실패 (%s): %s — 스텁 fallback", company, exc)
            extraction = None
            has_extraction = False

    # Phase 3: Build final file
    if has_extraction and extraction:
        if investment_data:
            _inject_thevc_into_file(output_path, investment_data)
    else:
        markdown = _build_company_info_markdown(company, jd_url, startup, thevc_note, investment_data)
        if not dry_run:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(markdown, encoding="utf-8")

    completeness = 0.0
    if not dry_run and output_path.exists():
        try:
            data = parse_company_file(output_path)
            result = validate_company(data, output_path)
            completeness = result.completeness_score
        except Exception:
            completeness = 0.0

    return CompanyInfoResult(
        company=company,
        file_path=output_path,
        used_existing=False,
        completeness=completeness,
        thevc_attempted=thevc_attempted,
        thevc_status=thevc_status,
        investment_data_source=investment_source if investment_source != "none" else
            ("extraction" if has_extraction else "none"),
    )
