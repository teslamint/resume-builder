#!/usr/bin/env python3
"""
Content Integrity Verifier - 면접 답변의 이력서 근거 검증

Usage:
    python3 templates/build/verify_content.py <interview-md>
    python3 templates/build/verify_content.py <interview-md> --resume <resume-md>
    python3 templates/build/verify_content.py <interview-md> --json
"""

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).parent.parent.parent
DEFAULT_RESUME = BASE_DIR / "private" / "build" / "resume-job-base.md"

COMPANY_ALIASES: Dict[str, List[str]] = {
    "April7": ["에이프릴세븐", "April7", "april7"],
    "DaTalk": ["다톡", "DaTalk", "datalk"],
    "Eundabang": ["은하수다방", "Eundabang", "eundabang"],
    "MARVRUS": ["마블러스", "MARVRUS", "marvrus"],
    "FNS": ["에프앤에스", "FNS", "fns", "패스커", "Fassker"],
    "EJN": ["이제이엔", "EJN", "ejn"],
    "LeeCompany": ["리앤컴퍼니", "Lee&Company", "lee&company"],
}

TECH_KEYWORDS = [
    "JPA", "QueryDSL", "Flyway", "PortOne", "Celery", "Redis", "FastAPI",
    "Spring Boot", "Docker", "ECS", "RDS", "ElastiCache", "Kafka", "RabbitMQ",
    "PostgreSQL", "MySQL", "MongoDB", "DynamoDB", "S3", "CloudFront",
    "Nginx", "Gunicorn", "Uvicorn", "SQLAlchemy", "Alembic", "Pydantic",
    "Kotlin", "Kotest", "JUnit", "pytest", "WebSocket", "SSE", "gRPC",
    "GraphQL", "REST", "OAuth", "JWT", "OIDC", "Terraform", "GitHub Actions",
    "ArgoCD", "Datadog", "Sentry", "Grafana", "Prometheus", "ELK",
    "Next.js", "React", "Vue", "Nuxt", "TypeScript",
    "asyncio", "aiohttp", "httpx", "Celery Beat",
    "Spring Security", "Spring Data", "Spring Cloud",
    "Hibernate", "MyBatis", "JOOQ",
    "CI/CD", "Jenkins", "CircleCI", "Travis",
    "Kubernetes", "K8s", "k8s", "Helm",
    "MSA", "마이크로서비스", "모놀리스",
]

PATTERN_KEYWORDS = [
    "N+1", "fetch join", "DTO 프로젝션", "Saga", "Outbox", "Idempotency",
    "Strangler Fig", "CQRS", "Event Sourcing", "Circuit Breaker",
    "Bulk Insert", "Batch", "커넥션 풀", "connection pool",
    "데드락", "deadlock", "락", "lock", "트랜잭션", "transaction",
    "캐시", "cache", "인덱스", "index", "파티셔닝", "partitioning",
    "샤딩", "sharding", "레플리카", "replica",
    "비동기", "async", "동기", "sync",
    "멀티스레드", "multithread", "코루틴", "coroutine",
    "리팩토링", "refactoring", "마이그레이션", "migration",
]

METRIC_PATTERN = re.compile(r'\d+%\s*(?:이상\s*|p\s*)?(?:단축|감소|개선|향상|절감|증가)')

ALL_KEYWORDS = TECH_KEYWORDS + PATTERN_KEYWORDS

PARENT_COMPANY_MAP = {
    "DaTalk": "April7",
    "Eundabang": "April7",
}



@dataclass
class VerifierConfig:
    company_aliases: Dict[str, List[str]]
    parent_map: Dict[str, str]
    keywords: List[str]
    metric_pattern: re.Pattern

    @property
    def child_map(self) -> Dict[str, List[str]]:
        result: Dict[str, List[str]] = {}
        for child, parent in self.parent_map.items():
            result.setdefault(parent, []).append(child)
        return result

    @property
    def alias_map(self) -> Dict[str, str]:
        result = {}
        for key, aliases in self.company_aliases.items():
            for alias in aliases:
                result[alias] = key
                result[alias.lower()] = key
        return result


DEFAULT_CONFIG = VerifierConfig(
    company_aliases=COMPANY_ALIASES,
    parent_map=PARENT_COMPANY_MAP,
    keywords=ALL_KEYWORDS,
    metric_pattern=METRIC_PATTERN,
)


@dataclass
class Claim:
    company_key: str
    keyword: str
    source_line: str
    line_number: int


@dataclass
class VerificationResult:
    claim: Claim
    status: str  # "verified", "uncertain", "ungrounded"
    found_in_company: Optional[str] = None
    evidence_line: Optional[int] = None


def _is_ascii(s: str) -> bool:
    return all(ord(c) < 128 for c in s)


def _alias_match(alias: str, text: str) -> Optional[int]:
    if _is_ascii(alias):
        m = re.search(
            r'(?<![a-zA-Z0-9])' + re.escape(alias) + r'(?![a-zA-Z0-9])',
            text, re.IGNORECASE,
        )
    else:
        m = re.search(re.escape(alias), text)
    return m.start() if m else None


def parse_resume_sections(resume_path: Path, config: VerifierConfig = None) -> Dict[str, str]:
    config = config or DEFAULT_CONFIG
    content = resume_path.read_text(encoding="utf-8")
    sections: Dict[str, str] = {}
    sorted_aliases = sorted(config.alias_map.items(), key=lambda x: len(x[0]), reverse=True)
    parts = re.split(r'^# ', content, flags=re.MULTILINE)
    for part in parts[1:]:
        first_line = part.split("\n", 1)[0].strip()
        matched_key = None
        for alias, key in sorted_aliases:
            if _alias_match(alias, first_line) is not None:
                matched_key = key
                break
        if matched_key:
            section_text = f"# {part}"
            sections[matched_key] = section_text
            for alias in config.company_aliases.get(matched_key, []):
                sections[alias] = section_text

    return sections


def extract_claims(interview_path: Path, config: VerifierConfig = None) -> List[Claim]:
    config = config or DEFAULT_CONFIG
    content = interview_path.read_text(encoding="utf-8")
    lines = content.split("\n")
    alias_map = config.alias_map
    claims: List[Claim] = []
    seen: set = set()

    for i, line in enumerate(lines, 1):
        if not line.startswith("> "):
            continue

        text = line[2:]
        mentioned_companies: Dict[str, int] = {}

        for alias, key in alias_map.items():
            pos = _alias_match(alias, text)
            if pos is not None:
                if key not in mentioned_companies or pos < mentioned_companies[key]:
                    mentioned_companies[key] = pos

        if not mentioned_companies:
            continue

        company_list = sorted(mentioned_companies.items(), key=lambda x: x[1])

        text_lower = text.lower()
        for keyword in config.keywords:
            kw_pos = text_lower.find(keyword.lower())
            if kw_pos == -1:
                continue

            closest_company = min(company_list, key=lambda x: abs(x[1] - kw_pos))
            claim_id = (closest_company[0], keyword.lower())
            if claim_id not in seen:
                seen.add(claim_id)
                claims.append(Claim(
                    company_key=closest_company[0],
                    keyword=keyword,
                    source_line=text.strip(),
                    line_number=i,
                ))

        for match in config.metric_pattern.finditer(text):
            metric = match.group()
            closest_company = min(company_list, key=lambda x: abs(x[1] - match.start()))
            claim_id = (closest_company[0], metric)
            if claim_id not in seen:
                seen.add(claim_id)
                claims.append(Claim(
                    company_key=closest_company[0],
                    keyword=metric,
                    source_line=text.strip(),
                    line_number=i,
                ))

    return claims


def verify_claims(claims: List[Claim], sections: Dict[str, str],
                   config: VerifierConfig = None) -> List[VerificationResult]:
    config = config or DEFAULT_CONFIG
    results: List[VerificationResult] = []
    child_map = config.child_map

    for claim in claims:
        company_section = sections.get(claim.company_key, "")
        parent_key = config.parent_map.get(claim.company_key)
        parent_section = sections.get(parent_key, "") if parent_key else ""
        child_keys = child_map.get(claim.company_key, [])
        child_sections = "\n".join(sections.get(ck, "") for ck in child_keys)
        combined_section = company_section + "\n" + parent_section + "\n" + child_sections
        keyword_lower = claim.keyword.lower()

        if combined_section.strip() and keyword_lower in combined_section.lower():
            search_section = None
            found_key = None
            if keyword_lower in company_section.lower():
                search_section = company_section
                found_key = claim.company_key
            elif parent_section and keyword_lower in parent_section.lower():
                search_section = parent_section
                found_key = parent_key
            else:
                for ck in child_keys:
                    cs = sections.get(ck, "")
                    if keyword_lower in cs.lower():
                        search_section = cs
                        found_key = ck
                        break
            evidence_line = None
            if search_section:
                for j, sl in enumerate(search_section.split("\n"), 1):
                    if keyword_lower in sl.lower():
                        evidence_line = j
                        break
            results.append(VerificationResult(
                claim=claim,
                status="verified",
                found_in_company=found_key or claim.company_key,
                evidence_line=evidence_line,
            ))
            continue

        skip_keys = {claim.company_key} | set(config.company_aliases.get(claim.company_key, []))
        found_elsewhere = None
        found_line = None
        for key, section_text in sections.items():
            if key in skip_keys or key not in config.company_aliases:
                continue
            if keyword_lower in section_text.lower():
                section_lines = section_text.split("\n")
                for j, sl in enumerate(section_lines, 1):
                    if keyword_lower in sl.lower():
                        found_line = j
                        break
                found_elsewhere = key
                break

        if found_elsewhere:
            results.append(VerificationResult(
                claim=claim,
                status="uncertain",
                found_in_company=found_elsewhere,
                evidence_line=found_line,
            ))
        else:
            results.append(VerificationResult(
                claim=claim,
                status="ungrounded",
            ))

    return results


def format_text_report(results: List[VerificationResult], interview_path: Path) -> str:
    lines = [
        f"Content Integrity Report: {interview_path.name}",
        "=" * 60,
        "",
    ]

    verified = [r for r in results if r.status == "verified"]
    uncertain = [r for r in results if r.status == "uncertain"]
    ungrounded = [r for r in results if r.status == "ungrounded"]

    for r in results:
        if r.status == "verified":
            icon = "\u2705"
            detail = f"(resume L{r.evidence_line})" if r.evidence_line else ""
        elif r.status == "uncertain":
            icon = "\u26a0\ufe0f"
            detail = f"(found in {r.found_in_company}, not {r.claim.company_key})"
        else:
            icon = "\u274c"
            detail = "(not found in resume)"

        lines.append(
            f"  {icon} [{r.claim.company_key}] \"{r.claim.keyword}\" {detail}"
        )
        lines.append(f"     L{r.claim.line_number}: {r.claim.source_line[:100]}")
        lines.append("")

    lines.append("-" * 60)
    lines.append(
        f"Summary: {len(verified)} verified, {len(uncertain)} uncertain, "
        f"{len(ungrounded)} ungrounded"
    )

    if ungrounded:
        lines.append("")
        lines.append("UNGROUNDED CLAIMS:")
        for r in ungrounded:
            lines.append(f"  - [{r.claim.company_key}] \"{r.claim.keyword}\" (L{r.claim.line_number})")

    return "\n".join(lines)


def format_json_report(results: List[VerificationResult], interview_path: Path) -> str:
    verified = [r for r in results if r.status == "verified"]
    uncertain = [r for r in results if r.status == "uncertain"]
    ungrounded = [r for r in results if r.status == "ungrounded"]

    payload = {
        "interview_file": str(interview_path),
        "summary": {
            "total_claims": len(results),
            "verified": len(verified),
            "uncertain": len(uncertain),
            "ungrounded": len(ungrounded),
        },
        "claims": [
            {
                "company": r.claim.company_key,
                "keyword": r.claim.keyword,
                "status": r.status,
                "source_line": r.claim.line_number,
                "found_in_company": r.found_in_company,
                "evidence_line": r.evidence_line,
            }
            for r in results
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description="면접 답변 이력서 근거 검증")
    parser.add_argument("interview", help="인터뷰 시트 마크다운 파일")
    parser.add_argument("--resume", default=str(DEFAULT_RESUME), help="이력서 파일 경로")
    parser.add_argument("--json", action="store_true", help="JSON 출력")

    args = parser.parse_args()

    interview_path = Path(args.interview)
    if not interview_path.exists():
        print(f"Error: {interview_path} not found", file=sys.stderr)
        sys.exit(1)

    resume_path = Path(args.resume)
    if not resume_path.exists():
        print(f"Error: {resume_path} not found", file=sys.stderr)
        sys.exit(1)

    sections = parse_resume_sections(resume_path)
    if not sections:
        print("Warning: no company sections found in resume", file=sys.stderr)

    claims = extract_claims(interview_path)
    if not claims:
        if args.json:
            print(format_json_report([], interview_path))
        else:
            print("No company-specific claims found in interview sheet.")
        sys.exit(0)

    results = verify_claims(claims, sections)

    if args.json:
        print(format_json_report(results, interview_path))
    else:
        print(format_text_report(results, interview_path))

    ungrounded = [r for r in results if r.status == "ungrounded"]
    sys.exit(1 if ungrounded else 0)


if __name__ == "__main__":
    main()
