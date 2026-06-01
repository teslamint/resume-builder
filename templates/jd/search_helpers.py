"""Shared search helpers — page load + DOM scraping for Wanted and Remember,
API-based listing for GroupBy/Wanted/Remember, and title filtering.

Extracts raw job listing data from search result pages or API responses. Does NOT own:
- Dedup (caller checks seen_ids, is_duplicate, queued_ids)
- Experience filtering (caller applies filter_experience, company rejection)
- State management (caller updates SearchState or queue)
- Stats counting (caller decides when to increment total_found)
"""
from __future__ import annotations

import html
import importlib
import logging
import re
from contextlib import suppress
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Callable, Optional
from urllib.parse import quote, urljoin

try:
    from .experience_filter import filter_experience
    from .http_client_base import http_text_request
    from .jd_content import is_rejected_company, parse_remember_experience
    from .models import DiscoveredJob
    from .path_utils import is_duplicate
    from .remember_client import RememberAPIError, search_jobs as remember_search_jobs, format_experience as remember_format_exp
    from .wanted_client import WantedAPIError, search_jobs as wanted_search_jobs, format_experience as wanted_format_exp
except ImportError:
    from experience_filter import filter_experience
    from http_client_base import http_text_request
    from jd_content import is_rejected_company, parse_remember_experience
    from models import DiscoveredJob
    from path_utils import is_duplicate
    from remember_client import RememberAPIError, search_jobs as remember_search_jobs, format_experience as remember_format_exp
    from wanted_client import WantedAPIError, search_jobs as wanted_search_jobs, format_experience as wanted_format_exp

logger = logging.getLogger(__name__)
KNOWN_PARSE_EXCEPTIONS = (AttributeError, KeyError, TypeError, ValueError)


@lru_cache(maxsize=1)
def _load_playwright_error() -> type[BaseException] | None:
    with suppress(ImportError, AttributeError):
        return importlib.import_module("templates.jd.browser_utils").PlaywrightError
    with suppress(ImportError, AttributeError):
        return importlib.import_module("browser_utils").PlaywrightError
    return None


@lru_cache(maxsize=1)
def _load_playwright_timeout_error() -> type[BaseException] | None:
    with suppress(ImportError, AttributeError):
        return importlib.import_module(
            "templates.jd.browser_utils"
        ).PlaywrightTimeoutError
    with suppress(ImportError, AttributeError):
        return importlib.import_module("browser_utils").PlaywrightTimeoutError
    return None


def _is_timeout_exception(error: Exception) -> bool:
    playwright_timeout_error = _load_playwright_timeout_error()
    if playwright_timeout_error is not None and isinstance(error, playwright_timeout_error):
        return True
    if isinstance(error, TimeoutError):
        return True
    return str(error).strip().lower() == "timeout"


def _is_row_parse_exception(error: Exception) -> bool:
    if isinstance(error, KNOWN_PARSE_EXCEPTIONS):
        return True
    playwright_error = _load_playwright_error()
    return playwright_error is not None and isinstance(error, playwright_error)


def _fetch_html(url: str, timeout_seconds: int = 15) -> str:
    return http_text_request(url, timeout=timeout_seconds)


def _split_html_lines(raw: str) -> list[str]:
    cleaned = re.sub(r"(?i)<br\s*/?>", "\n", raw)
    cleaned = re.sub(r"<[^>]+>", "", cleaned)
    cleaned = html.unescape(cleaned)
    return [line.strip() for line in cleaned.splitlines() if line.strip()]


@dataclass
class RawJobResult(DiscoveredJob):
    """A single job listing extracted from a search page."""
    raw_id: str              # Platform-native ID (e.g., "12345")
    href: str                # Original href from the DOM element
    platform: str            # "wanted" or "remember"

    def duplicate_keys(self) -> list[str]:
        """All IDs to check for dedup. Remember uses dual-key (job_id + raw_id)."""
        if self.platform == "remember":
            return [self.job_id, self.raw_id]
        return [self.job_id]


@dataclass
class SearchPageConfig:
    """Configuration for page load + scrape behavior."""
    base_url: str
    timeout_ms: int = 15000
    post_load_delay: float = 3.5
    scroll_count: int = 3
    scroll_sleep: float = 1.0


@dataclass
class ScrapeOutcome:
    """Result of a single page scrape operation."""
    results: list[RawJobResult] = field(default_factory=list)
    candidate_count: int = 0  # After href/id validation + in-page dedup + jdViewSource, BEFORE text parsing
    timed_out: bool = False
    no_results: bool = False
    error: Exception | None = None


BrowserResultBuilder = Callable[[SearchPageConfig, str, str, list[str]], RawJobResult | None]
HttpResultBuilder = Callable[[SearchPageConfig, str, str, list[str]], RawJobResult | None]


@dataclass(frozen=True)
class BrowserScraperConfig:
    results_selector: str
    no_results_selectors: tuple[str, ...]
    url_pattern: re.Pattern[str]
    required_href_fragment: str | None
    build_result: BrowserResultBuilder


@dataclass(frozen=True)
class HttpScraperConfig:
    no_results_markers: tuple[str, ...]
    link_pattern: re.Pattern[str]
    required_href_fragment: str | None
    build_result: HttpResultBuilder
    empty_error: str


def _combine_locators(page, selectors: tuple[str, ...]):
    locator = page.locator(selectors[0])
    for selector in selectors[1:]:
        locator = locator.or_(page.locator(selector))
    return locator


def _scroll_to_page_end(page, config: SearchPageConfig) -> None:
    import time

    time.sleep(config.post_load_delay)
    for _ in range(config.scroll_count):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(config.scroll_sleep)


def _build_wanted_result(
    *,
    raw_id: str,
    title: str,
    company: str,
    experience: str,
    href: str,
    url: str,
) -> RawJobResult:
    return RawJobResult(
        raw_id=raw_id,
        job_id=raw_id,
        title=title,
        company=company,
        experience=experience,
        url=url,
        href=href,
        platform="wanted",
    )


def _build_remember_result(
    *,
    raw_id: str,
    title: str,
    company: str,
    experience: str,
    href: str,
    url: str,
) -> RawJobResult:
    return RawJobResult(
        raw_id=raw_id,
        job_id=f"remember-{raw_id}",
        title=title,
        company=company,
        experience=experience,
        url=url,
        href=href,
        platform="remember",
    )


def _build_wanted_browser_result(
    config: SearchPageConfig, href: str, raw_id: str, lines: list[str]
) -> RawJobResult | None:
    if len(lines) < 2:
        return None

    return _build_wanted_result(
        raw_id=raw_id,
        title=lines[0],
        company=lines[1],
        experience=lines[2] if len(lines) > 2 else "",
        href=href,
        url=urljoin(config.base_url, href),
    )


def _build_remember_browser_result(
    config: SearchPageConfig, href: str, raw_id: str, lines: list[str]
) -> RawJobResult | None:
    if len(lines) < 2:
        return None

    return _build_remember_result(
        raw_id=raw_id,
        company=lines[0],
        title=lines[1],
        experience=parse_remember_experience(lines[2:]),
        href=href,
        url=f"{config.base_url}/job/posting/{raw_id}",
    )


def _build_wanted_http_result(
    config: SearchPageConfig, href: str, raw_id: str, lines: list[str]
) -> RawJobResult | None:
    if len(lines) < 2:
        return None

    return _build_wanted_result(
        raw_id=raw_id,
        title=lines[0],
        company=lines[1],
        experience=lines[2] if len(lines) > 2 else "",
        href=href,
        url=f"{config.base_url}/wd/{raw_id}" if href.startswith("/wd/") else href,
    )


def _build_remember_http_result(
    config: SearchPageConfig, href: str, raw_id: str, lines: list[str]
) -> RawJobResult | None:
    if len(lines) < 2:
        return None

    return _build_remember_result(
        raw_id=raw_id,
        company=lines[0],
        title=lines[1],
        experience=parse_remember_experience(lines[2:]),
        href=href,
        url=f"{config.base_url}/job/posting/{raw_id}" if href.startswith("/job/posting/") else href,
    )


wanted_browser = BrowserScraperConfig(
    results_selector='a[href*="/wd/"]',
    no_results_selectors=(
        "text=검색 결과가 없습니다",
        '[class*="EmptyContent"]',
        "text=일치하는 결과가 없",
    ),
    url_pattern=re.compile(r"/wd/(\d+)"),
    required_href_fragment=None,
    build_result=_build_wanted_browser_result,
)

remember_browser = BrowserScraperConfig(
    results_selector='a[href*="/job/posting/"]',
    no_results_selectors=("text=총 0개 공고",),
    url_pattern=re.compile(r"/job/posting/(\d+)"),
    required_href_fragment="jdViewSource=inweb_list",
    build_result=_build_remember_browser_result,
)

wanted_http = HttpScraperConfig(
    no_results_markers=("검색 결과가 없습니다", "일치하는 결과가 없습니다"),
    link_pattern=re.compile(
        r'<a[^>]*href=["\']([^"\']*?/wd/(\d+)[^"\']*)["\'][^>]*>(.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    ),
    required_href_fragment=None,
    build_result=_build_wanted_http_result,
    empty_error="Wanted HTTP 검색에서 공고 링크를 추출하지 못했습니다.",
)

remember_http = HttpScraperConfig(
    no_results_markers=("총 0개 공고",),
    link_pattern=re.compile(
        r'<a[^>]*href=["\']([^"\']*?/job/posting/(\d+)[^"\']*)["\'][^>]*>(.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    ),
    required_href_fragment="jdViewSource=inweb_list",
    build_result=_build_remember_http_result,
    empty_error="Remember HTTP 검색에서 공고 링크를 추출하지 못했습니다.",
)


def _load_and_scrape_browser(page, search_url: str, config: SearchPageConfig, scraper: BrowserScraperConfig) -> ScrapeOutcome:
    """Navigate to a search page, scroll, and extract raw job rows."""
    outcome = ScrapeOutcome()

    try:
        page.goto(search_url, wait_until="domcontentloaded", timeout=30000)

        has_results = page.locator(scraper.results_selector)
        no_results = _combine_locators(page, scraper.no_results_selectors)

        try:
            has_results.first.or_(no_results.first).wait_for(
                state="attached", timeout=config.timeout_ms
            )
        except Exception as e:
            if _is_timeout_exception(e):
                logger.debug("Timed out waiting for search results at %s: %s", search_url, e)
                outcome.timed_out = True
                return outcome
            raise

        if no_results.count() > 0 or has_results.count() == 0:
            outcome.no_results = True
            return outcome

        _scroll_to_page_end(page, config)

        job_links = page.query_selector_all(scraper.results_selector)
        seen_in_page: set[str] = set()

        for link in job_links:
            try:
                href = link.get_attribute("href")
                if not href:
                    continue
                if scraper.required_href_fragment and scraper.required_href_fragment not in href:
                    continue

                match = scraper.url_pattern.search(href)
                if not match:
                    continue

                raw_id = match.group(1)
                if raw_id in seen_in_page:
                    continue
                seen_in_page.add(raw_id)

                outcome.candidate_count += 1

                text = link.inner_text()
                lines = [line.strip() for line in text.split("\n") if line.strip()]
                result = scraper.build_result(config, href, raw_id, lines)
                if result is None:
                    continue
                outcome.results.append(result)
            except Exception as e:
                if _is_row_parse_exception(e):
                    logger.debug("Failed to parse search result row at %s: %s", search_url, e)
                    continue
                raise

    except Exception as e:
        outcome.error = e

    return outcome


def load_and_scrape_wanted(page, search_url: str, config: SearchPageConfig) -> ScrapeOutcome:
    """Navigate to Wanted search page, scroll, extract job rows.

    Caller builds search_url. Helper handles navigation, wait, scroll, DOM extraction.
    Returns ScrapeOutcome with raw results (no filtering or dedup applied).
    """
    return _load_and_scrape_browser(page, search_url, config, wanted_browser)


def load_and_scrape_remember(page, search_url: str, config: SearchPageConfig) -> ScrapeOutcome:
    """Navigate to Remember search page, scroll, extract job rows.

    Caller builds search_url (Remember needs JSON+quote construction).
    Helper handles jdViewSource=inweb_list filter internally (DOM-level).
    """
    return _load_and_scrape_browser(page, search_url, config, remember_browser)


def _load_and_scrape_http(search_url: str, config: SearchPageConfig, scraper: HttpScraperConfig) -> ScrapeOutcome:
    """Fetch a search page over HTTP and parse raw job rows from the HTML."""
    outcome = ScrapeOutcome()

    try:
        html_text = _fetch_html(search_url, timeout_seconds=max(15, int(config.timeout_ms / 1000)))
    except Exception as e:
        outcome.error = e
        return outcome

    if any(marker in html_text for marker in scraper.no_results_markers):
        outcome.no_results = True
        return outcome

    seen_in_page: set[str] = set()
    for match in scraper.link_pattern.finditer(html_text):
        href, raw_id, inner_html = match.groups()
        if raw_id in seen_in_page:
            continue
        if scraper.required_href_fragment and scraper.required_href_fragment not in href:
            continue

        lines = _split_html_lines(inner_html)
        if len(lines) < 2:
            continue

        seen_in_page.add(raw_id)
        outcome.candidate_count += 1

        result = scraper.build_result(config, href, raw_id, lines)
        if result is None:
            continue
        outcome.results.append(result)

    if outcome.results:
        return outcome

    outcome.error = ValueError(scraper.empty_error)
    return outcome


def load_and_scrape_wanted_http(search_url: str, config: SearchPageConfig) -> ScrapeOutcome:
    """Fallback Wanted search path without Playwright (raw HTML parse)."""
    return _load_and_scrape_http(search_url, config, wanted_http)


def load_and_scrape_remember_http(search_url: str, config: SearchPageConfig) -> ScrapeOutcome:
    """Fallback Remember search path without Playwright (raw HTML parse)."""
    return _load_and_scrape_http(search_url, config, remember_http)


# ---------------------------------------------------------------------------
# GroupBy helpers — API-based, no Playwright needed
# GroupBy provides structured (min, max) integers via API, so callers pass
# those directly to filter_experience. Wanted/Remember expose Korean text and
# rely on parse_experience_range() inside the common filter path.
# ---------------------------------------------------------------------------

def format_groupby_experience(item: dict) -> str:
    """Convert GroupBy API item to display-only Korean experience string."""
    career_type = item.get("careerType", "")
    exp_range = item.get("experienceRange") or {}
    exp_min = exp_range.get("min")
    exp_max = exp_range.get("max")

    if career_type == "무관" or career_type == "인턴":
        return f"경력 {career_type}"

    if exp_min is not None and exp_max is not None and exp_max > 0:
        return f"경력 {exp_min}-{exp_max}년"

    if exp_min is not None and exp_min > 0:
        return f"경력 {exp_min}년 이상"

    return f"경력 {career_type}" if career_type else ""


def groupby_experience_values(item: dict) -> tuple[int | None, int | None]:
    """Extract structured (min_years, max_years) from GroupBy API item.

    Returns (None, None) for 무관/인턴 or missing data.
    """
    career_type = item.get("careerType", "")
    if career_type in ("무관", "인턴"):
        return None, None

    exp_range = item.get("experienceRange") or {}
    exp_min = exp_range.get("min")
    exp_max = exp_range.get("max")

    if exp_max == 0:
        exp_max = None
    if exp_min == 0 and exp_max is None:
        return None, None

    return exp_min, exp_max


def convert_groupby_to_raw_results(
    items: list[dict], base_url: str = "https://groupby.kr"
) -> ScrapeOutcome:
    """Convert GroupBy API items to ScrapeOutcome with RawJobResult list."""
    outcome = ScrapeOutcome()

    for item in items:
        try:
            item_id = item.get("id")
            if item_id is None:
                continue

            startup = item.get("startup") or {}
            job_id = f"groupby-{item_id}"

            outcome.candidate_count += 1
            outcome.results.append(RawJobResult(
                raw_id=str(item_id),
                job_id=job_id,
                title=(item.get("name") or "").strip(),
                company=(startup.get("name") or "").strip(),
                experience=format_groupby_experience(item),
                url=f"{base_url}/positions/{item_id}",
                href=f"/positions/{item_id}",
                platform="groupby",
            ))
        except KNOWN_PARSE_EXCEPTIONS as e:
            logger.debug("Failed to convert GroupBy item %s: %s", item.get("id"), e)
            continue

    return outcome


# ---------------------------------------------------------------------------
# Wanted API helpers
# ---------------------------------------------------------------------------

def search_wanted_api(query: str, max_items: int = 60, base_url: str = "https://www.wanted.co.kr") -> ScrapeOutcome:
    """Search Wanted via REST API, returning ScrapeOutcome with RawJobResult list."""
    outcome = ScrapeOutcome()

    try:
        items = wanted_search_jobs(query, max_items=max_items)
    except WantedAPIError as e:
        outcome.error = e
        return outcome

    if not items:
        outcome.no_results = True
        return outcome

    return convert_wanted_to_raw_results(items, base_url=base_url)


def convert_wanted_to_raw_results(
    items: list[dict], base_url: str = "https://www.wanted.co.kr"
) -> ScrapeOutcome:
    """Convert Wanted API items to ScrapeOutcome with RawJobResult list."""
    outcome = ScrapeOutcome()

    for item in items:
        try:
            item_id = item.get("id")
            if item_id is None:
                continue

            company_info = item.get("company") or {}
            job_id = str(item_id)

            outcome.candidate_count += 1
            outcome.results.append(RawJobResult(
                raw_id=job_id,
                job_id=job_id,
                title=(item.get("position") or "").strip(),
                company=(company_info.get("name") or "").strip(),
                experience=wanted_format_exp(item),
                url=f"{base_url}/wd/{job_id}",
                href=f"/wd/{job_id}",
                platform="wanted",
            ))
        except KNOWN_PARSE_EXCEPTIONS as e:
            logger.debug("Failed to convert Wanted item %s: %s", item.get("id"), e)
            continue

    return outcome


# ---------------------------------------------------------------------------
# Remember API helpers
# ---------------------------------------------------------------------------

def search_remember_api(query: str, max_items: int = 60, base_url: str = "https://career.rememberapp.co.kr") -> ScrapeOutcome:
    """Search Remember via REST API, returning ScrapeOutcome with RawJobResult list."""
    outcome = ScrapeOutcome()

    try:
        items, total_count = remember_search_jobs([query], max_items=max_items)
    except RememberAPIError as e:
        outcome.error = e
        return outcome

    if not items:
        outcome.no_results = True
        return outcome

    return convert_remember_to_raw_results(items, base_url=base_url)


def convert_remember_to_raw_results(
    items: list[dict], base_url: str = "https://career.rememberapp.co.kr"
) -> ScrapeOutcome:
    """Convert Remember API items to ScrapeOutcome with RawJobResult list."""
    outcome = ScrapeOutcome()

    for item in items:
        try:
            item_id = item.get("id")
            if item_id is None:
                continue

            organization = item.get("organization") or {}
            raw_id = str(item_id)
            job_id = f"remember-{raw_id}"

            outcome.candidate_count += 1
            outcome.results.append(RawJobResult(
                raw_id=raw_id,
                job_id=job_id,
                title=(item.get("title") or "").strip(),
                company=(organization.get("name") or "").strip(),
                experience=remember_format_exp(item),
                url=f"{base_url}/job/posting/{raw_id}",
                href=f"/job/posting/{raw_id}",
                platform="remember",
            ))
        except KNOWN_PARSE_EXCEPTIONS as e:
            logger.debug("Failed to convert Remember item %s: %s", item.get("id"), e)
            continue

    return outcome


# ---------------------------------------------------------------------------
# Config reader
# ---------------------------------------------------------------------------

def _read_search_config(path) -> Optional[dict]:
    """Read and parse a YAML search config file. Returns None if missing."""
    from pathlib import Path
    p = Path(path)
    if not p.exists():
        return None
    import yaml
    with p.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# ---------------------------------------------------------------------------
# Title filtering
# ---------------------------------------------------------------------------

def quick_filter_title(title: str, config: dict) -> Optional[str]:
    """Quick filter based on title keywords.

    Returns: ``'pass'`` (skip), ``'prefer'`` (prioritize), or ``None`` (neutral).
    """
    filters = config.get("quick_filters", {})
    title_lower = title.lower()

    for keyword in filters.get("title_exclude", []):
        if keyword.lower() in title_lower:
            return "pass"

    include_keywords = filters.get("title_include", [])
    if include_keywords:
        if not any(kw.lower() in title_lower for kw in include_keywords):
            return "pass"

    for keyword in filters.get("title_prefer", []):
        if keyword.lower() in title_lower:
            return "prefer"

    return None


# ---------------------------------------------------------------------------
# Unified filter + dedup
# ---------------------------------------------------------------------------

@dataclass
class FilterResult:
    """Result of filter_and_dedup: accepted items + aggregate counters."""
    accepted: list[RawJobResult] = field(default_factory=list)
    total_found: int = 0
    filtered_out: int = 0
    duplicates: int = 0


def filter_and_dedup(
    results: list[RawJobResult],
    *,
    config: dict,
    seen_ids: set[str],
    rejected_companies: set,
    config_excludes: list,
) -> FilterResult:
    """Apply title/company/experience filters and dedup against *seen_ids* + filesystem.

    Mutates *seen_ids* in-place (adds accepted and fs-dup job IDs).
    Uses ``RawJobResult.duplicate_keys()`` for platform-aware dedup:
    job_id for most platforms, and [job_id, raw_id] for Remember.
    Filesystem dedup is checked through ``is_duplicate()`` for each dedup key.
    """
    out = FilterResult()

    for raw in results:
        out.total_found += 1

        if quick_filter_title(raw.title, config) == "pass":
            out.filtered_out += 1
            continue

        if is_rejected_company(raw.company, rejected_companies, config_excludes):
            out.filtered_out += 1
            continue

        if filter_experience(raw.experience, config):
            out.filtered_out += 1
            continue

        dup_keys = raw.duplicate_keys()
        if any(k in seen_ids for k in dup_keys):
            out.duplicates += 1
            continue

        fs_dup = False
        for k in dup_keys:
            found, _ = is_duplicate(k)
            if found:
                fs_dup = True
                break
        if fs_dup:
            out.duplicates += 1
            seen_ids.add(raw.job_id)
            continue

        out.accepted.append(raw)
        seen_ids.add(raw.job_id)

    return out
