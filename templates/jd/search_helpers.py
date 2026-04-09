"""Shared search helpers — page load + DOM scraping for Wanted and Remember.

Extracts raw job listing data from search result pages. Does NOT own:
- Dedup (caller checks seen_ids, is_duplicate, queued_ids)
- Filtering (caller applies quick_filter_title, filter_experience, company rejection)
- State management (caller updates SearchState or queue)
- Stats counting (caller decides when to increment total_found)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import quote

try:
    from .jd_content import parse_remember_experience
except ImportError:
    from jd_content import parse_remember_experience


@dataclass
class RawJobResult:
    """A single job listing extracted from a search page."""
    raw_id: str              # Platform-native ID (e.g., "12345")
    canonical_id: str        # Normalized ID (e.g., "remember-12345" or "12345")
    title: str
    company: str
    experience: str
    url: str                 # Full URL to the posting
    href: str                # Original href from the DOM element
    platform: str            # "wanted" or "remember"

    def duplicate_keys(self) -> list[str]:
        """All IDs to check for dedup. Remember uses dual-key (canonical + raw)."""
        if self.platform == "remember":
            return [self.canonical_id, self.raw_id]
        return [self.canonical_id]


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


def load_and_scrape_wanted(page, search_url: str, config: SearchPageConfig) -> ScrapeOutcome:
    """Navigate to Wanted search page, scroll, extract job rows.

    Caller builds search_url. Helper handles navigation, wait, scroll, DOM extraction.
    Returns ScrapeOutcome with raw results (no filtering or dedup applied).
    """
    import time

    outcome = ScrapeOutcome()

    try:
        page.goto(search_url, wait_until="domcontentloaded", timeout=30000)

        has_results = page.locator('a[href*="/wd/"]')
        no_results = page.locator('text=검색 결과가 없습니다').or_(
            page.locator('[class*="EmptyContent"]')
        ).or_(page.locator('text=일치하는 결과가 없'))

        try:
            has_results.first.or_(no_results.first).wait_for(
                state="attached", timeout=config.timeout_ms
            )
        except Exception:
            outcome.timed_out = True
            return outcome

        if no_results.count() > 0 or has_results.count() == 0:
            outcome.no_results = True
            return outcome

        time.sleep(config.post_load_delay)

        for _ in range(config.scroll_count):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(config.scroll_sleep)

        job_links = page.query_selector_all('a[href*="/wd/"]')
        seen_in_page: set[str] = set()

        for link in job_links:
            href = link.get_attribute("href")
            if not href or "/wd/" not in href:
                continue

            match = re.search(r"/wd/(\d+)", href)
            if not match:
                continue

            job_id = match.group(1)
            if job_id in seen_in_page:
                continue
            seen_in_page.add(job_id)

            outcome.candidate_count += 1

            text = link.inner_text()
            lines = [l.strip() for l in text.split("\n") if l.strip()]
            if len(lines) < 2:
                continue

            title = lines[0]
            company = lines[1] if len(lines) > 1 else "Unknown"
            experience = lines[2] if len(lines) > 2 else ""

            from urllib.parse import urljoin
            full_url = urljoin(config.base_url, href)

            outcome.results.append(RawJobResult(
                raw_id=job_id,
                canonical_id=job_id,
                title=title,
                company=company,
                experience=experience,
                url=full_url,
                href=href,
                platform="wanted",
            ))

    except Exception as e:
        outcome.error = e

    return outcome


def load_and_scrape_remember(page, search_url: str, config: SearchPageConfig) -> ScrapeOutcome:
    """Navigate to Remember search page, scroll, extract job rows.

    Caller builds search_url (Remember needs JSON+quote construction).
    Helper handles jdViewSource=inweb_list filter internally (DOM-level).
    """
    import time

    outcome = ScrapeOutcome()

    try:
        page.goto(search_url, wait_until="domcontentloaded", timeout=30000)

        has_results = page.locator('a[href*="/job/posting/"]')
        no_results = page.locator('text=총 0개 공고')

        try:
            has_results.first.or_(no_results.first).wait_for(
                state="attached", timeout=config.timeout_ms
            )
        except Exception:
            outcome.timed_out = True
            return outcome

        if no_results.count() > 0 or has_results.count() == 0:
            outcome.no_results = True
            return outcome

        time.sleep(config.post_load_delay)

        for _ in range(config.scroll_count):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(config.scroll_sleep)

        job_links = page.query_selector_all('a[href*="/job/posting/"]')
        seen_in_page: set[str] = set()

        for link in job_links:
            href = link.get_attribute("href")
            if not href or "/job/posting/" not in href:
                continue

            if "jdViewSource=inweb_list" not in href:
                continue

            match = re.search(r"/job/posting/(\d+)", href)
            if not match:
                continue

            raw_id = match.group(1)
            if raw_id in seen_in_page:
                continue
            seen_in_page.add(raw_id)

            outcome.candidate_count += 1

            text = link.inner_text()
            lines = [l.strip() for l in text.split("\n") if l.strip()]
            if len(lines) < 2:
                continue

            company = lines[0]
            title = lines[1]
            experience = parse_remember_experience(lines[2:])

            canonical_id = f"remember-{raw_id}"
            full_url = f"{config.base_url}/job/posting/{raw_id}"

            outcome.results.append(RawJobResult(
                raw_id=raw_id,
                canonical_id=canonical_id,
                title=title,
                company=company,
                experience=experience,
                url=full_url,
                href=href,
                platform="remember",
            ))

    except Exception as e:
        outcome.error = e

    return outcome
