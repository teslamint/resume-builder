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
    from .company_match_verify import verify_company_match
    from .company_validator import COMPANY_INFO_DIR, parse_company_file, validate_company
    from .jd_content import extract_metadata_from_jd
    from .naming import slugify_company
except ImportError:
    from company_extractor import extract_company_info
    from company_match_verify import verify_company_match
    from company_validator import COMPANY_INFO_DIR, parse_company_file, validate_company
    from jd_content import extract_metadata_from_jd
    from naming import slugify_company

_log = logging.getLogger(__name__)


THEVC_MODES = {"auto", "skip", "require"}
ENRICHMENT_QUEUE_PATH = Path(__file__).parent.parent.parent / "private" / "job_postings" / "unprocessed" / "company_enrichment_thevc.txt"
SARAMIN_ENRICHMENT_QUEUE_PATH = Path(__file__).parent.parent.parent / "private" / "job_postings" / "unprocessed" / "company_enrichment_saramin.txt"

HEADHUNTING_KEYWORDS = ["써치", "서치펌", "헤드헌팅", "리크루팅", "인력파견", "헤드헌터"]
THEVC_SOURCE_TOKENS = ("thevc.kr", "TheVC")
FALSE_STARTUP_TOKENS = (
    "ipo",
    "m&a",
    "상장기업",
    "코스피 상장",
    "코스닥 상장",
    "대기업",
    "글로벌 기업",
    "한국법인",
    "계열",
    "일반기업",
    "해당 없음",
    "해당없음",
)
REAL_STARTUP_ROUND_TOKENS = ("seed", "pre-a", "pre-b", "series", "시리즈", "브릿지", "예비 유니콘")
STARTUP_SIGNAL_TOKENS = ("스타트업", "벤처", "투자 유치", "인원 급성장", "설립3년이하")


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


_HEADING_LINE_RE = re.compile(r"^#\s+(.+)$")
_HEADING_PAREN_RE = re.compile(r"\([^)]*\)")


def _read_first_heading(path: Path) -> str:
    """Read first '# ' heading from a markdown file. Lowercase, paren-stripped."""
    try:
        with path.open(encoding="utf-8") as f:
            for line in f:
                m = _HEADING_LINE_RE.match(line.rstrip("\n"))
                if m:
                    return _HEADING_PAREN_RE.sub("", m.group(1)).strip().lower()
    except OSError:
        return ""
    return ""


def _completeness_score(path: Path) -> float:
    """Best-effort completeness score; 0.0 on parse failure."""
    try:
        data = parse_company_file(path)
        return validate_company(data, path).completeness_score
    except Exception:
        return 0.0


def _resolve_company_alias(company: str) -> Optional[Path]:
    """Find the best existing company_info file across hangul/english slug aliases.

    Tries direct slug, raw-name filename, and heading-reverse-lookup candidates,
    then returns the one with the highest completeness score (mtime tiebreaker).
    Returns None if no candidate file exists.

    Heading-vs-filename mismatch is NOT filtered here — the homonym verifier
    in ensure_company_info handles that signal separately.
    """
    if not company:
        return None

    candidates: list[Path] = []
    seen: set[Path] = set()

    def _add(p: Path) -> None:
        if p.exists() and p not in seen:
            candidates.append(p)
            seen.add(p)

    _add(COMPANY_INFO_DIR / f"{slugify_company(company)}.md")
    _add(COMPANY_INFO_DIR / f"{Path(company).name}.md")

    # Reverse-lookup by # heading. Cheap enough as fallback (one-line read per file).
    company_norm = _HEADING_PAREN_RE.sub("", company).strip().lower()
    if company_norm:
        for file in COMPANY_INFO_DIR.glob("*.md"):
            if file.name.startswith("_") or file in seen:
                continue
            head = _read_first_heading(file)
            if head and head == company_norm:
                _add(file)

    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    def _exact_match(p: Path) -> int:
        head = _read_first_heading(p)
        return 1 if head and head == company_norm else 0

    scored = [
        (_exact_match(c), _completeness_score(c), c.stat().st_mtime, c)
        for c in candidates
    ]
    scored.sort(key=lambda t: (-t[0], -t[1], -t[2]))
    return scored[0][3]


def _find_existing_company_file(company: str) -> Optional[Path]:
    return _resolve_company_alias(company)


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


def _has_thevc_source(text: str) -> bool:
    return any(token.lower() in text.lower() for token in THEVC_SOURCE_TOKENS)


def _existing_needs_thevc_enrichment(path: Path, completeness: float) -> bool:
    if completeness < 0:
        return False
    try:
        content = path.read_text(encoding="utf-8")
        data = parse_company_file(path)
    except Exception:
        return False
    if _has_thevc_source(content):
        return False

    lowered = content.lower()
    if any(token in lowered for token in FALSE_STARTUP_TOKENS):
        return False
    if "| 스타트업 여부 | yes |" in lowered or "| 스타트업 여부 | 예 |" in lowered:
        return True
    round_value = (data.investment_round or "").lower()
    if any(token in round_value for token in REAL_STARTUP_ROUND_TOKENS):
        return True
    if data.investment_total:
        return True
    return data.is_startup and any(token in lowered for token in STARTUP_SIGNAL_TOKENS)


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
            "investors": [],
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
| 스타트업 여부 | {'Yes' if startup else 'No'} |
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
    """Inject TheVC investment data into existing company info file.

    If the file already has a ## 투자 정보 section (e.g. from JD-based extraction),
    enriches it with TheVC data (round/total) while preserving existing fields
    like investors that TheVC may not have.
    """
    content = file_path.read_text(encoding="utf-8")

    round_value = investment.get("round", "")
    total_value = investment.get("total", "")
    investors = investment.get("investors") or []
    inv_source = investment.get("source", "https://thevc.kr")

    if "## 투자 정보" in content:
        # Enrich existing section: update round/total if TheVC has them
        if round_value and round_value != "정보 없음":
            content = re.sub(
                r"\| 현재 라운드 \| .+? \|",
                f"| 현재 라운드 | {round_value} |",
                content,
            )
        if total_value and total_value != "정보 없음":
            content = re.sub(
                r"\| 누적 투자금 \| .+? \|",
                f"| 누적 투자금 | {total_value} |",
                content,
            )
        if investors:
            investor_row = f"| 주요 투자자 | {', '.join(investors[:5])} |"
            if re.search(r"\| 주요 투자자 \| .+? \|", content):
                content = re.sub(r"\| 주요 투자자 \| .+? \|", investor_row, content)
            else:
                content = re.sub(
                    r"(\| 누적 투자금 \| [^\n]+\|)",
                    f"\\1\n{investor_row}",
                    content,
                    count=1,
                )
        # Add TheVC source note if not already present
        if not _has_thevc_source(content) and inv_source:
            content = content.replace(
                "\n---\n",
                f"\n> TheVC에서 투자정보를 보강했습니다. 출처: [{inv_source}]({inv_source})\n\n---\n",
                1,
            )
    else:
        # No existing investment section — add full TheVC section
        thevc_section = _build_thevc_section(investment)
        if "\n---\n" in content:
            content = content.replace("\n---\n", f"\n{thevc_section}\n---\n", 1)
        else:
            content += f"\n{thevc_section}"

    file_path.write_text(content, encoding="utf-8")


def _inject_thevc_note_into_file(file_path: Path, thevc_note: str) -> None:
    """Add TheVC status note to file when TheVC failed but company is startup."""
    content = file_path.read_text(encoding="utf-8")
    if "TheVC" in content:
        return
    if "## 투자 정보" in content:
        content = re.sub(
            r"(## 투자 정보.*?)(?=\n## |\n---|\Z)",
            lambda m: m.group(1).rstrip() + f"\n\n> {thevc_note}\n",
            content,
            count=1,
            flags=re.DOTALL,
        )
        file_path.write_text(content, encoding="utf-8")
    else:
        note_section = f"\n## 투자 정보\n\n| 항목 | 내용 |\n|------|------|\n| 현재 라운드 | 정보 없음 |\n| 누적 투자금 | 정보 없음 |\n\n> {thevc_note}\n"
        if "\n---\n" in content:
            content = content.replace("\n---\n", f"{note_section}\n---\n", 1)
        else:
            content += note_section
        file_path.write_text(content, encoding="utf-8")


def _append_thevc_source_note(file_path: Path, source_url: str, note: str) -> None:
    content = file_path.read_text(encoding="utf-8")
    if _has_thevc_source(content):
        return

    note_line = f"> {note} 출처: [{source_url}]({source_url})\n"
    if "\n---\n" in content:
        content = content.replace("\n---\n", f"\n{note_line}\n---\n", 1)
    else:
        content += f"\n{note_line}"
    file_path.write_text(content, encoding="utf-8")


def _append_enrichment_queue(company: str) -> None:
    ENRICHMENT_QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing = set()
    if ENRICHMENT_QUEUE_PATH.exists():
        existing = {line.strip() for line in ENRICHMENT_QUEUE_PATH.read_text(encoding="utf-8").splitlines() if line.strip()}
    if company not in existing:
        with open(ENRICHMENT_QUEUE_PATH, "a", encoding="utf-8") as f:
            f.write(company + "\n")


def _append_saramin_enrichment_queue(company: str) -> None:
    SARAMIN_ENRICHMENT_QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing = set()
    if SARAMIN_ENRICHMENT_QUEUE_PATH.exists():
        existing = {line.strip() for line in SARAMIN_ENRICHMENT_QUEUE_PATH.read_text(encoding="utf-8").splitlines() if line.strip()}
    if company not in existing:
        with open(SARAMIN_ENRICHMENT_QUEUE_PATH, "a", encoding="utf-8") as f:
            f.write(company + "\n")


def _thevc_failure_note(status: str) -> str:
    if status == "not_logged_in":
        return "TheVC 로그인 필요로 투자정보를 수집하지 못했습니다."
    if status == "access_limited":
        return "TheVC 접근 제한으로 투자정보를 수집하지 못했습니다."
    return "TheVC 투자정보 추출에 실패했습니다."


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
    jd_text = jd_path.read_text(encoding="utf-8")
    if existing:
        completeness = -1.0
        data = None
        try:
            data = parse_company_file(existing)
            result = validate_company(data, existing)
            completeness = result.completeness_score
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(
                "completeness 파싱 실패 (%s): %s — re-collection 진행", existing, exc
            )

        startup_signal = (data.is_startup if data else False) or _looks_startup(jd_text)
        missing_investment_data = (
            data is not None
            and (data.investment_round is None or data.investment_total is None)
        )
        startup_needs_thevc = startup_signal and missing_investment_data

        if completeness >= 0 and completeness >= min_completeness:
            if startup_needs_thevc and thevc_mode != "skip":
                thevc_status, investment_data = _extract_thevc_investment(company)
                if thevc_status == "success" and investment_data:
                    _inject_thevc_into_file(existing, investment_data)
                    completeness = _completeness_score(existing)
                    return CompanyInfoResult(
                        company=company,
                        file_path=existing,
                        used_existing=True,
                        completeness=completeness,
                        thevc_attempted=True,
                        thevc_status=thevc_status,
                        investment_data_source="thevc",
                    )

                if thevc_mode == "require":
                    raise RuntimeError(f"TheVC 투자정보 수집 실패({thevc_status}) - require 모드")

                thevc_note = _thevc_failure_note(thevc_status)
                _inject_thevc_note_into_file(existing, thevc_note)
                _append_enrichment_queue(company)
                completeness = _completeness_score(existing)
                return CompanyInfoResult(
                    company=company,
                    file_path=existing,
                    used_existing=True,
                    completeness=completeness,
                    thevc_attempted=True,
                    thevc_status=thevc_status,
                    investment_data_source="existing",
                )

            try:
                ok, conf, mismatches = verify_company_match(existing, jd_path)
                if not ok and mismatches:
                    import sys
                    print(
                        f"WARN: company_info({existing.name}) vs JD({jd_path.name}) "
                        f"동음이의 매칭 가능성 (confidence={conf}). "
                        f"company_info에만 있는 토큰: {mismatches[:5]} — 운영자 검토 권장",
                        file=sys.stderr,
                    )
            except Exception as exc:
                _log.warning("company_match_verify 실패 (%s): %s", existing.name, exc)
            return CompanyInfoResult(
                company=company,
                file_path=existing,
                used_existing=True,
                completeness=completeness,
                thevc_attempted=False,
                thevc_status="skipped",
                investment_data_source="existing",
            )

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
        else:
            thevc_note = _thevc_failure_note(thevc_status)
            _append_enrichment_queue(company)

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
            if "saramin" in extraction.platforms_failed:
                _append_saramin_enrichment_queue(company)
        except Exception as exc:
            _log.warning("회사 정보 추출 실패 (%s): %s — 스텁 fallback", company, exc)
            extraction = None
            has_extraction = False

    # Phase 3: Build final file
    if has_extraction and extraction:
        if investment_data:
            _inject_thevc_into_file(output_path, investment_data)
        elif startup:
            _inject_thevc_note_into_file(output_path, thevc_note)
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

        try:
            ok, conf, mismatches = verify_company_match(output_path, jd_path)
            if not ok and mismatches:
                import sys
                print(
                    f"WARN: company_info({output_path.name}) vs JD({jd_path.name}) "
                    f"동음이의 매칭 가능성 (confidence={conf}). "
                    f"company_info에만 있는 토큰: {mismatches[:5]} — 운영자 검토 권장",
                    file=sys.stderr,
                )
        except Exception as exc:
            _log.warning("company_match_verify 실패 (%s): %s", output_path.name, exc)

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
