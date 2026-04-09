#!/usr/bin/env python3
"""Tests for verify_content.py — resume claim verification.

All tests use fictional company data via TEST_CONFIG to decouple
from real resume data in the production module.
"""

import re
from pathlib import Path

import pytest

from verify_content import (
    Claim,
    VerifierConfig,
    VerificationResult,
    extract_claims,
    parse_resume_sections,
    verify_claims,
)

TEST_ALIASES = {
    "AlphaCorp": ["알파코프", "AlphaCorp", "alphacorp"],
    "BetaLabs": ["베타랩", "BetaLabs", "betalabs"],
    "GammaTech": ["감마텍", "GammaTech", "gammatech"],
    "DeltaIO": ["델타아이오", "DeltaIO", "deltaio"],
}

TEST_PARENT_MAP = {
    "BetaLabs": "AlphaCorp",
    "GammaTech": "AlphaCorp",
}

TEST_KEYWORDS = [
    "Redis", "JPA", "N+1", "fetch join", "커넥션 풀",
    "WebSocket", "GraphQL", "Docker", "Kafka",
]

TEST_METRIC = re.compile(r'\d+%\s*(?:이상\s*|p\s*)?(?:단축|감소|개선|향상|절감|증가)')

TEST_CONFIG = VerifierConfig(
    company_aliases=TEST_ALIASES,
    parent_map=TEST_PARENT_MAP,
    keywords=TEST_KEYWORDS,
    metric_pattern=TEST_METRIC,
)


def _write(tmp_path: Path, name: str, text: str) -> Path:
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


# --- parse_resume_sections ---

def test_parse_sections_basic(tmp_path):
    resume = _write(tmp_path, "resume.md", (
        "# AlphaCorp (알파코프)\n\n"
        "커넥션 풀 안정화 작업을 수행\n\n"
        "# BetaLabs (베타랩)\n\n"
        "N+1 문제 해결\n"
    ))
    sections = parse_resume_sections(resume, config=TEST_CONFIG)
    assert "AlphaCorp" in sections
    assert "BetaLabs" in sections
    assert "커넥션 풀" in sections["AlphaCorp"]
    assert "N+1" in sections["BetaLabs"]


def test_parse_sections_korean_alias(tmp_path):
    resume = _write(tmp_path, "resume.md", (
        "# 주식회사 베타랩\n\n"
        "JPA 최적화\n"
    ))
    sections = parse_resume_sections(resume, config=TEST_CONFIG)
    assert "BetaLabs" in sections


def test_parse_sections_word_boundary(tmp_path):
    resume = _write(tmp_path, "resume.md", (
        "# rejection handling\n\n"
        "error handling module\n"
    ))
    sections = parse_resume_sections(resume, config=TEST_CONFIG)
    assert len(sections) == 0


# --- extract_claims ---

def test_extract_claims_basic(tmp_path):
    interview = _write(tmp_path, "interview.md", (
        "> BetaLabs에서 N+1 발생 시 fetch join으로 해결\n"
    ))
    claims = extract_claims(interview, config=TEST_CONFIG)
    keywords = {c.keyword for c in claims}
    company_keys = {c.company_key for c in claims}
    assert "N+1" in keywords
    assert "BetaLabs" in company_keys


def test_extract_claims_no_company(tmp_path):
    interview = _write(tmp_path, "interview.md", (
        "> Redis를 사용해서 캐시를 구현했습니다\n"
    ))
    claims = extract_claims(interview, config=TEST_CONFIG)
    assert len(claims) == 0


def test_extract_claims_multi_company_same_line(tmp_path):
    interview = _write(tmp_path, "interview.md", (
        "> AlphaCorp에서 Redis 캐시를 도입하여 성능을 개선하였고, BetaLabs에서 JPA 최적화\n"
    ))
    claims = extract_claims(interview, config=TEST_CONFIG)
    redis_claims = [c for c in claims if c.keyword == "Redis"]
    jpa_claims = [c for c in claims if c.keyword == "JPA"]
    assert len(redis_claims) > 0
    assert redis_claims[0].company_key == "AlphaCorp"
    assert len(jpa_claims) > 0
    assert jpa_claims[0].company_key == "BetaLabs"


def test_extract_claims_metric_pattern(tmp_path):
    interview = _write(tmp_path, "interview.md", (
        "> AlphaCorp에서 30% 감소 달성\n"
        "> BetaLabs에서 50% 이상 개선 확인\n"
    ))
    claims = extract_claims(interview, config=TEST_CONFIG)
    metric_keywords = {c.keyword for c in claims if "%" in c.keyword}
    assert "30% 감소" in metric_keywords
    assert "50% 이상 개선" in metric_keywords


def test_extract_claims_case_insensitive(tmp_path):
    interview = _write(tmp_path, "interview.md", (
        "> AlphaCorp에서 redis를 사용했습니다\n"
    ))
    claims = extract_claims(interview, config=TEST_CONFIG)
    redis_claims = [c for c in claims if c.keyword.lower() == "redis"]
    assert len(redis_claims) > 0


def test_extract_claims_empty_file(tmp_path):
    interview = _write(tmp_path, "interview.md", "")
    claims = extract_claims(interview, config=TEST_CONFIG)
    assert len(claims) == 0


# --- verify_claims ---

def test_verify_verified():
    claim = Claim(company_key="BetaLabs", keyword="N+1", source_line="test", line_number=1)
    sections = {"BetaLabs": "# BetaLabs\n\nN+1 문제를 해결함\n"}
    results = verify_claims([claim], sections, config=TEST_CONFIG)
    assert len(results) == 1
    assert results[0].status == "verified"
    assert results[0].found_in_company == "BetaLabs"


def test_verify_uncertain():
    claim = Claim(company_key="DeltaIO", keyword="N+1", source_line="test", line_number=1)
    sections = {"AlphaCorp": "# AlphaCorp\n\nN+1 쿼리 수정\n"}
    for alias in TEST_ALIASES["AlphaCorp"]:
        sections[alias] = sections["AlphaCorp"]
    results = verify_claims([claim], sections, config=TEST_CONFIG)
    assert len(results) == 1
    assert results[0].status == "uncertain"
    assert results[0].found_in_company == "AlphaCorp"


def test_verify_ungrounded():
    claim = Claim(company_key="BetaLabs", keyword="GraphQL", source_line="test", line_number=1)
    sections = {"AlphaCorp": "# AlphaCorp\n\nRedis 캐시\n"}
    for alias in TEST_ALIASES["AlphaCorp"]:
        sections[alias] = sections["AlphaCorp"]
    results = verify_claims([claim], sections, config=TEST_CONFIG)
    assert len(results) == 1
    assert results[0].status == "ungrounded"


def test_verify_parent_fallback(tmp_path):
    resume = _write(tmp_path, "resume.md", (
        "# AlphaCorp (알파코프)\n\n"
        "Redis 캐시 도입으로 성능 개선\n"
    ))
    interview = _write(tmp_path, "interview.md", (
        "> BetaLabs에서 Redis 캐시를 적용했습니다\n"
    ))
    sections = parse_resume_sections(resume, config=TEST_CONFIG)
    claims = extract_claims(interview, config=TEST_CONFIG)
    redis_claims = [c for c in claims if c.keyword == "Redis"]
    assert len(redis_claims) > 0
    results = verify_claims(redis_claims, sections, config=TEST_CONFIG)
    assert all(r.status == "verified" for r in results)


def test_verify_child_fallback(tmp_path):
    resume = _write(tmp_path, "resume.md", (
        "# BetaLabs (베타랩)\n\n"
        "WebSocket 기반 실시간 채팅 구현\n"
    ))
    interview = _write(tmp_path, "interview.md", (
        "> AlphaCorp에서 WebSocket을 활용했습니다\n"
    ))
    sections = parse_resume_sections(resume, config=TEST_CONFIG)
    claims = extract_claims(interview, config=TEST_CONFIG)
    ws_claims = [c for c in claims if c.keyword == "WebSocket"]
    assert len(ws_claims) > 0
    results = verify_claims(ws_claims, sections, config=TEST_CONFIG)
    assert all(r.status == "verified" for r in results)


def test_verify_case_insensitive(tmp_path):
    resume = _write(tmp_path, "resume.md", (
        "# BetaLabs (베타랩)\n\n"
        "redis 캐시 적용\n"
    ))
    interview = _write(tmp_path, "interview.md", (
        "> BetaLabs에서 Redis를 사용했습니다\n"
    ))
    sections = parse_resume_sections(resume, config=TEST_CONFIG)
    claims = extract_claims(interview, config=TEST_CONFIG)
    redis_claims = [c for c in claims if c.keyword.lower() == "redis"]
    assert len(redis_claims) > 0
    results = verify_claims(redis_claims, sections, config=TEST_CONFIG)
    assert all(r.status == "verified" for r in results)


# --- Integration ---

def test_integration_fabricated_claim(tmp_path):
    resume = _write(tmp_path, "resume.md", (
        "# BetaLabs (베타랩)\n\n"
        "JPA N+1 문제 해결\n"
    ))
    interview = _write(tmp_path, "interview.md", (
        "> BetaLabs에서 fetch join을 적용했습니다\n"
    ))
    sections = parse_resume_sections(resume, config=TEST_CONFIG)
    claims = extract_claims(interview, config=TEST_CONFIG)
    fetch_claims = [c for c in claims if c.keyword == "fetch join"]
    assert len(fetch_claims) > 0
    results = verify_claims(fetch_claims, sections, config=TEST_CONFIG)
    assert all(r.status == "ungrounded" for r in results)


def test_integration_valid_claim(tmp_path):
    resume = _write(tmp_path, "resume.md", (
        "# AlphaCorp (알파코프)\n\n"
        "커넥션 풀 안정화를 통해 서비스 안정성 확보\n"
    ))
    interview = _write(tmp_path, "interview.md", (
        "> AlphaCorp에서 커넥션 풀 안정화 작업을 진행했습니다\n"
    ))
    sections = parse_resume_sections(resume, config=TEST_CONFIG)
    claims = extract_claims(interview, config=TEST_CONFIG)
    pool_claims = [c for c in claims if c.keyword == "커넥션 풀"]
    assert len(pool_claims) > 0
    results = verify_claims(pool_claims, sections, config=TEST_CONFIG)
    assert all(r.status == "verified" for r in results)


def test_integration_empty_resume(tmp_path):
    resume = _write(tmp_path, "resume.md", "")
    sections = parse_resume_sections(resume, config=TEST_CONFIG)
    assert len(sections) == 0
