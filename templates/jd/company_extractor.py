#!/usr/bin/env python3
"""Playwright-based company info extraction from Wanted + Saramin + TheVC.

Usage:
    python3 templates/jd/company_extractor.py --company "김캐디"
    python3 templates/jd/company_extractor.py --company "김캐디" --platforms wanted,saramin,thevc
    python3 templates/jd/company_extractor.py --company "김캐디" --dry-run
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

try:
    from .ce_jd_files import extract_from_jd_files
    from .ce_merge import build_enriched_markdown, merge_platform_data
    from .ce_saramin import extract_saramin
    from .ce_thevc import extract_thevc
    from .ce_types import ExtractionResult, PlatformData
    from .ce_wanted import extract_wanted
    from .company_validator import COMPANY_INFO_DIR, parse_company_file, validate_company
    from .naming import slugify_company as _slugify_company
except ImportError:
    from ce_jd_files import extract_from_jd_files
    from ce_merge import build_enriched_markdown, merge_platform_data
    from ce_saramin import extract_saramin
    from ce_thevc import extract_thevc
    from ce_types import ExtractionResult, PlatformData
    from ce_wanted import extract_wanted
    from company_validator import COMPANY_INFO_DIR, parse_company_file, validate_company
    from naming import slugify_company as _slugify_company


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
REQUEST_DELAY = 1.5  # seconds between page navigations
ALL_PLATFORMS = ("wanted", "saramin", "thevc")

BROWSER_EXTRACTORS: dict[str, callable] = {
    "wanted": extract_wanted,
    "saramin": extract_saramin,
    "thevc": extract_thevc,
}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def extract_company_info(
    company_name: str,
    *,
    browser_context=None,
    platforms: tuple[str, ...] | list[str] | None = None,
    is_startup: bool = False,
    jd_url: str = "",
    existing_file: Path | None = None,
    dry_run: bool = False,
) -> ExtractionResult:
    """Main entry point for Playwright-based company info extraction."""
    platforms = tuple(platforms or ALL_PLATFORMS)
    slug = _slugify_company(company_name)
    output_path = COMPANY_INFO_DIR / f"{slug}.md"

    platforms_used: list[str] = []
    platforms_failed: list[str] = []
    source_urls: list[str] = []
    data_list: list[PlatformData] = []

    selected = [(name, fn) for name, fn in BROWSER_EXTRACTORS.items() if name in platforms]

    if selected:
        own_playwright = browser_context is None
        pw_instance = None
        browser = None

        if own_playwright:
            from playwright.sync_api import sync_playwright
            pw_instance = sync_playwright().start()
            browser = pw_instance.chromium.launch(headless=True)
            browser_context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent=USER_AGENT,
            )

        try:
            for i, (platform_name, extract_fn) in enumerate(selected):
                try:
                    result = extract_fn(company_name, browser_context)
                    if result:
                        data_list.append(result)
                        platforms_used.append(platform_name)
                        source_urls.append(result.source_url)
                    else:
                        platforms_failed.append(platform_name)
                except Exception as e:
                    print(f"   [{platform_name}] 예외: {e}")
                    platforms_failed.append(platform_name)
                if i < len(selected) - 1:
                    time.sleep(REQUEST_DELAY)
        finally:
            if own_playwright:
                if browser:
                    browser.close()
                if pw_instance:
                    pw_instance.stop()

    # JD file extraction (no browser needed, always attempted)
    try:
        jd_result = extract_from_jd_files(company_name)
        if jd_result:
            data_list.append(jd_result)
            platforms_used.append("jd")
    except Exception as e:
        print(f"   [jd] 예외: {e}")

    # Build markdown
    if data_list:
        merged = merge_platform_data(data_list)
        markdown = build_enriched_markdown(merged, company_name, source_urls)
    else:
        return ExtractionResult(
            company=company_name,
            file_path=output_path,
            completeness=0.0,
            platforms_used=[],
            platforms_failed=platforms_failed,
            source_urls=[],
        )

    if not dry_run:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8")

    completeness = 0.0
    if not dry_run and output_path.exists():
        try:
            parsed = parse_company_file(output_path)
            val_result = validate_company(parsed, output_path)
            completeness = val_result.completeness_score
        except Exception:
            pass

    return ExtractionResult(
        company=company_name,
        file_path=output_path,
        completeness=completeness,
        platforms_used=platforms_used,
        platforms_failed=platforms_failed,
        source_urls=source_urls,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Playwright 기반 회사 정보 추출")
    parser.add_argument("--company", required=True, help="회사명")
    parser.add_argument(
        "--platforms",
        default="wanted,saramin,thevc",
        help="추출 플랫폼 (쉼표 구분, 기본: wanted,saramin,thevc)",
    )
    parser.add_argument("--dry-run", action="store_true", help="파일 저장 안함")
    args = parser.parse_args()

    platforms = tuple(p.strip() for p in args.platforms.split(","))
    print(f"🏢 회사 정보 추출: {args.company}")
    print(f"   플랫폼: {', '.join(platforms)}")

    result = extract_company_info(
        args.company,
        platforms=platforms,
        dry_run=args.dry_run,
    )

    print(f"\n{'=' * 50}")
    print(f"결과: {result.company}")
    print(f"파일: {result.file_path}")
    print(f"완성도: {result.completeness:.0f}%")
    print(f"사용 플랫폼: {', '.join(result.platforms_used) or '없음'}")
    print(f"실패 플랫폼: {', '.join(result.platforms_failed) or '없음'}")
    print(f"출처: {', '.join(result.source_urls) or '없음'}")

    if args.dry_run:
        print("\n(dry-run 모드 — 파일 미저장)")


if __name__ == "__main__":
    main()
