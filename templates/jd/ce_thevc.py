"""TheVC platform company info extraction via Playwright.

Extracts investment data (round, total, investors, founded year) from TheVC SPA.
Uses multi-strategy slug search: Korean name → English name → short name.

Hidden dependency: get_english_name_from_company_info reads company_info/<slug>.md
and parses the H1 title expecting format '# 회사명 (EnglishName)'. The regex
r'^#\\s+.+?\\(([A-Za-z][\\w\\s&.-]*)\\)' extracts the parenthetical English name.
If the file doesn't exist or H1 doesn't match, returns None.
"""
from __future__ import annotations

import re
import time
from urllib.parse import quote

try:
    from .ce_types import PlatformData
    from .constants import COMPANY_INFO_DIR
    from .naming import slugify_company
except ImportError:
    from ce_types import PlatformData
    from constants import COMPANY_INFO_DIR
    from naming import slugify_company

REQUEST_DELAY = 1.5


def search_slug_single(keyword: str, context) -> str | None:
    """Search TheVC for company slug with a single keyword."""
    search_url = f"https://thevc.kr/integrated-search/overview?keyword={quote(keyword)}"
    page = context.new_page()
    try:
        page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(3000)

        links = page.query_selector_all("a[href]")
        for link in links:
            href = link.get_attribute("href") or ""
            if (
                href.startswith("/")
                and not href.startswith("/integrated-search")
                and not href.startswith("/login")
                and not href.startswith("/search")
                and not href.startswith("/api")
                and not href.startswith("/static")
                and "/" not in href[1:]
            ):
                return href.lstrip("/")
        return None
    finally:
        page.close()


def get_english_name_from_company_info(company_name: str) -> str | None:
    """Extract English name from existing company_info file H1 title.

    Reads company_info/<slugified_name>.md and looks for an H1 line matching
    '# 회사명 (EnglishName)'. Returns the parenthetical English name or None.

    File format contract:
    - Path: COMPANY_INFO_DIR / f"{slugify_company(company_name)}.md"
    - H1 regex: r'^#\\s+.+?\\(([A-Za-z][\\w\\s&.-]*)\\)' (MULTILINE)
    - If file missing or H1 doesn't contain parenthetical English name → None
    """
    slug = slugify_company(company_name)
    info_path = COMPANY_INFO_DIR / f"{slug}.md"
    if not info_path.exists():
        return None
    try:
        content = info_path.read_text(encoding="utf-8")
        m = re.search(r"^#\s+.+?\(([A-Za-z][\w\s&.-]*)\)", content, re.MULTILINE)
        if m:
            return m.group(1).strip()
    except Exception:
        pass
    return None


def search_slug(company_name: str, context) -> str | None:
    """Search TheVC for company slug with retry: original → English name → short name."""
    slug = search_slug_single(company_name, context)
    if slug:
        return slug

    en_name = get_english_name_from_company_info(company_name)
    if en_name:
        print(f"   [thevc] 한글명 실패, 영문명 재시도: {en_name}")
        time.sleep(REQUEST_DELAY)
        slug = search_slug_single(en_name, context)
        if slug:
            return slug

    words = company_name.split()
    if len(words) > 2:
        short_name = " ".join(words[:2])
        print(f"   [thevc] 짧은 이름 재시도: {short_name}")
        time.sleep(REQUEST_DELAY)
        slug = search_slug_single(short_name, context)
        if slug:
            return slug

    return None


def extract_thevc(company_name: str, context) -> PlatformData | None:
    """Extract investment info from TheVC SPA via Playwright."""
    slug = search_slug(company_name, context)
    if not slug:
        print(f"   [thevc] 회사 검색 실패: {company_name}")
        return None

    time.sleep(REQUEST_DELAY)

    company_url = f"https://thevc.kr/{slug}"
    page = context.new_page()
    try:
        page.goto(company_url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(3000)

        body_text = page.inner_text("body")
        login_signals = ["로그인이 필요합니다", "Sign in to continue", "로그인 후 확인"]
        if any(sig in body_text for sig in login_signals):
            print(f"   [thevc] 로그인 wall 감지 — 가용 데이터만 추출")

        data = PlatformData(
            platform="thevc", source_url=company_url, company_name=company_name
        )

        inv_tabs = page.query_selector_all('a, button, [role="tab"]')
        for tab in inv_tabs:
            tab_text = (tab.inner_text() or "").strip()
            if "투자" in tab_text:
                try:
                    tab.click()
                    page.wait_for_timeout(2000)
                except Exception:
                    pass
                break

        body_text = page.inner_text("body")

        round_match = re.search(
            r"(Seed|Pre-A|Pre-B|Series\s*[A-Z]\+?|IPO|M&A)",
            body_text,
            re.IGNORECASE,
        )
        if round_match:
            data.investment_round = round_match.group(1).strip()

        total_match = re.search(r"(?:누적|총\s*투자[금액]?)\s*([\d,]+(?:\.\d+)?)\s*억", body_text)
        if total_match:
            data.investment_total = f"{total_match.group(1)}억원"
        else:
            inv_match = re.search(r"([\d,]+(?:\.\d+)?)\s*억\s*원?", body_text)
            if inv_match:
                data.investment_total = f"{inv_match.group(1)}억원"

        investor_patterns = [
            r"투자자[:\s]*(.*)",
            r"참여\s*(?:투자자|기관)[:\s]*(.*)",
        ]
        for pat in investor_patterns:
            m = re.search(pat, body_text)
            if m:
                raw = m.group(1).strip()
                data.investors = [inv.strip() for inv in re.split(r"[,、·]", raw) if inv.strip()]
                break

        founded_match = re.search(r"설립[:\s]*(\d{4})", body_text)
        if founded_match:
            data.founded_year = int(founded_match.group(1))

        if data.investment_round or data.investment_total:
            print(f"   [thevc] 추출 완료: round={data.investment_round}, total={data.investment_total}")
        else:
            print(f"   [thevc] 투자정보 추출 실패 (접근 제한 가능)")

        return data

    finally:
        page.close()
