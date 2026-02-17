#!/usr/bin/env python3
"""Non-interactive JD extractors for JD auto pipeline."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    from .utils import JOB_POSTINGS_DIR, extract_job_id, get_platform_from_url
    from .wanted_extract import fetch_wanted_posting, format_experience_wanted, slugify as wanted_slugify
    from .remember_batch_extract import fetch_posting as fetch_remember_posting
    from .remember_batch_extract import format_experience as format_remember_experience
    from .remember_batch_extract import format_salary as format_remember_salary
    from .remember_batch_extract import format_address as format_remember_address
    from .remember_batch_extract import slugify as remember_slugify
except ImportError:
    from utils import JOB_POSTINGS_DIR, extract_job_id, get_platform_from_url
    from wanted_extract import fetch_wanted_posting, format_experience_wanted, slugify as wanted_slugify
    from remember_batch_extract import fetch_posting as fetch_remember_posting
    from remember_batch_extract import format_experience as format_remember_experience
    from remember_batch_extract import format_salary as format_remember_salary
    from remember_batch_extract import format_address as format_remember_address
    from remember_batch_extract import slugify as remember_slugify


@dataclass
class ExtractedJD:
    job_id: str
    platform: str
    url: str
    company: str
    title: str
    output_path: Path


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _write_markdown(file_path: Path, content: str) -> Path:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content.rstrip() + "\n", encoding="utf-8")
    return file_path


def _format_jd_markdown(
    *,
    title: str,
    company: str,
    experience: str,
    location: str,
    url: str,
    description: str,
    requirements: str,
    preferred: str,
    benefits: str,
    source: str,
) -> str:
    return f"""# {title}

## 기본 정보

| 항목 | 내용 |
|------|------|
| 회사명 | {company} |
| 포지션 | {title} |
| 경력 | {experience or '정보 없음'} |
| 근무지 | {location or '정보 없음'} |
| 출처 | [{source}]({url}) |

## 주요 업무

{description or '정보 없음'}

## 자격 요건

{requirements or '정보 없음'}

## 우대사항

{preferred or '정보 없음'}

## 혜택 및 복지

{benefits or '정보 없음'}
"""


def extract_wanted(url: str, output_dir: Optional[Path] = None) -> ExtractedJD:
    job_id = extract_job_id(url)
    if not job_id:
        raise ValueError(f"Wanted URL에서 job_id를 추출할 수 없습니다: {url}")

    job = fetch_wanted_posting(job_id)
    if not job:
        raise RuntimeError(f"Wanted 공고 조회 실패: {url}")

    title = _normalize_text(job.get("position", "")) or f"wanted-{job_id}"
    company_info = job.get("company", {}) or {}
    company = _normalize_text(company_info.get("company_name", "")) or "unknown-company"
    experience = format_experience_wanted(job)

    address = job.get("address", {}) or {}
    location = _normalize_text(address.get("full_location", ""))

    intro = job.get("intro", "")
    tasks = job.get("main_tasks", "")
    requirements = job.get("requirements", "")
    preferred = job.get("preferred_points", "")
    benefits = job.get("benefits", "")
    description = "\n\n".join([p for p in [intro, tasks] if p])

    company_slug = wanted_slugify(company)
    title_slug = wanted_slugify(title)

    output_root = output_dir or (JOB_POSTINGS_DIR / "unprocessed")
    output_path = output_root / f"{job_id}-{company_slug}-{title_slug}.md"

    markdown = _format_jd_markdown(
        title=title,
        company=company,
        experience=experience,
        location=location,
        url=url,
        description=description,
        requirements=requirements,
        preferred=preferred,
        benefits=benefits,
        source="Wanted",
    )

    _write_markdown(output_path, markdown)

    return ExtractedJD(
        job_id=job_id,
        platform="wanted",
        url=url,
        company=company,
        title=title,
        output_path=output_path,
    )


def extract_remember(url: str, output_dir: Optional[Path] = None) -> ExtractedJD:
    job_id = extract_job_id(url)
    if not job_id:
        raise ValueError(f"Remember URL에서 job_id를 추출할 수 없습니다: {url}")

    posting = fetch_remember_posting(job_id)
    if not posting:
        raise RuntimeError(f"Remember 공고 조회 실패: {url}")

    org = posting.get("organization", {}) or {}
    company = _normalize_text((org.get("name", "") or "").replace("(주)", "").replace("(주 )", ""))
    company = company or "unknown-company"

    title = _normalize_text(posting.get("title", "")) or f"remember-{job_id}"
    experience = format_remember_experience(posting)
    location = format_remember_address(posting)

    description = posting.get("jobDescription", "") or posting.get("introduction", "")
    requirements = posting.get("qualifications", "")
    preferred = posting.get("preferredQualifications", "")
    benefits = posting.get("additionalInformation", "")
    salary = format_remember_salary(posting)

    if salary and benefits:
        benefits = f"연봉: {salary}\n\n{benefits}"
    elif salary:
        benefits = f"연봉: {salary}"

    company_slug = remember_slugify(company)
    title_slug = remember_slugify(title)[:30]

    output_root = output_dir or (JOB_POSTINGS_DIR / "unprocessed")
    output_path = output_root / f"{job_id}-{company_slug}-{title_slug}.md"

    markdown = _format_jd_markdown(
        title=title,
        company=company,
        experience=experience,
        location=location,
        url=url,
        description=description,
        requirements=requirements,
        preferred=preferred,
        benefits=benefits,
        source="Remember",
    )

    _write_markdown(output_path, markdown)

    return ExtractedJD(
        job_id=job_id,
        platform="remember",
        url=url,
        company=company,
        title=title,
        output_path=output_path,
    )


def extract_jd_from_url(url: str, output_dir: Optional[Path] = None) -> ExtractedJD:
    platform = get_platform_from_url(url)
    if platform == "wanted":
        return extract_wanted(url, output_dir=output_dir)
    if platform == "remember":
        return extract_remember(url, output_dir=output_dir)
    raise ValueError(f"지원하지 않는 플랫폼입니다: {url}")
