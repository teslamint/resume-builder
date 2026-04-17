#!/usr/bin/env python3
"""LLM-driven JD screening for JD auto pipeline."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    from .company_validator import parse_company_file, validate_company
    from .constants import JOB_POSTINGS_DIR, SCREENING_DIR
    from .jd_content import extract_metadata_from_jd, load_screening_rules, update_summary
    from .path_utils import extract_job_id_from_filename
    from .verdict import parse_verdict_from_screening
except ImportError:
    from company_validator import parse_company_file, validate_company
    from constants import JOB_POSTINGS_DIR, SCREENING_DIR
    from jd_content import extract_metadata_from_jd, load_screening_rules, update_summary
    from path_utils import extract_job_id_from_filename
    from verdict import parse_verdict_from_screening


@dataclass
class ScreeningResult:
    verdict: str
    screening_path: Path
    provider: str
    used_fallback: bool
    raw_output: str


def _load_text(path: Optional[Path]) -> str:
    if not path or not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _build_prompt(jd_content: str, rules: str, company_content: str, company_risk_summary: str) -> str:
    return f"""아래 기준으로 JD 스크리닝을 수행하세요.

요구사항:
1) 반드시 최종 판정을 `지원 추천` 또는 `지원 보류` 또는 `지원 비추천` 중 하나로 명시
2) 결과는 Markdown으로 작성
3) 아래 섹션 순서 사용:
   - ## 기본 정보
   - ## 스크리닝 결과
   - ## 최종 판정
   - ## 핵심 근거
4) 최종 판정 섹션에 `### 최종 판정: <판정>` 형식을 포함

[스크리닝 규칙]
{rules}

[기업 리스크 요약]
{company_risk_summary}

[기업 정보]
{company_content}

[JD 원문]
{jd_content}
"""


def _build_company_risk_summary(company_file: Optional[Path]) -> str:
    if not company_file or not company_file.exists():
        return "기업 정보 파일 없음"

    try:
        data = parse_company_file(company_file)
        result = validate_company(data, company_file)
        risks = [r for r in result.risk_flags if r.severity in ("critical", "high")]

        if not risks:
            return f"완성도: {result.completeness_score:.0f}%, 고위험 플래그 없음"

        lines = [f"완성도: {result.completeness_score:.0f}%"]
        for risk in risks:
            lines.append(f"- {risk.severity.upper()} {risk.code}: {risk.message}")
        return "\n".join(lines)
    except Exception as exc:
        return f"기업 정보 검증 실패: {exc}"


def _find_executable(name: str, extra_paths: list[Path] | None = None) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    for p in (extra_paths or []):
        if p.exists() and os.access(p, os.X_OK):
            return str(p)
    return None


def _resolve_commands() -> list[tuple[str, list[str]]]:
    claude_cmd = os.getenv("CLAUDE_SCREENING_CMD")
    codex_cmd = os.getenv("CODEX_SCREENING_CMD")

    if not claude_cmd:
        claude_bin = _find_executable("claude", [
            Path.home() / ".local" / "bin" / "claude",
            Path("/opt/homebrew/bin/claude"),
        ])
        claude_cmd = f"{claude_bin} --print" if claude_bin else None

    if not codex_cmd:
        codex_bin = _find_executable("codex", [
            Path("/opt/homebrew/bin/codex"),
        ])
        codex_cmd = f"{codex_bin} exec" if codex_bin else None

    providers = []
    if claude_cmd:
        providers.append(("claude", shlex.split(claude_cmd)))
    if codex_cmd:
        providers.append(("codex", shlex.split(codex_cmd)))
    return providers


def _run_llm(prompt: str, timeout: int) -> tuple[str, str]:
    env = os.environ.copy()
    env.pop("CLAUDECODE", None)

    last_error = ""
    for provider, cmd in _resolve_commands():
        try:
            proc = subprocess.run(
                cmd,
                input=prompt,
                text=True,
                capture_output=True,
                timeout=timeout,
                env=env,
            )
        except FileNotFoundError:
            last_error = f"{provider} command not found"
            continue
        except Exception as exc:
            last_error = f"{provider} execution error: {exc}"
            continue

        if proc.returncode != 0:
            last_error = f"{provider} exit={proc.returncode}: {proc.stderr.strip()}"
            continue

        output = proc.stdout.strip()
        if not output:
            last_error = f"{provider} returned empty output"
            continue

        return provider, output

    raise RuntimeError(last_error or "No LLM provider succeeded")


def _screening_filename(jd_path: Path) -> str:
    job_id = extract_job_id_from_filename(jd_path.name) or jd_path.stem.split("-")[0]
    if jd_path.stem.startswith(f"{job_id}-"):
        return f"{jd_path.stem}.md"
    return f"{job_id}-{jd_path.stem.split('-', 1)[1]}.md" if "-" in jd_path.stem else f"{job_id}.md"


def _normalize_output(markdown: str, verdict: str) -> str:
    if "### 최종 판정:" in markdown:
        return markdown
    return markdown.rstrip() + f"\n\n## 최종 판정\n\n### 최종 판정: {verdict}\n"


def run_screening(
    jd_path: Path,
    company_file: Optional[Path],
    llm_timeout: int = 120,
    dry_run: bool = False,
) -> ScreeningResult:
    jd_content = jd_path.read_text(encoding="utf-8")
    rules = load_screening_rules()
    company_content = _load_text(company_file)
    risk_summary = _build_company_risk_summary(company_file)

    prompt = _build_prompt(jd_content, rules, company_content, risk_summary)

    provider = "fallback"
    used_fallback = False
    raw_output = ""

    try:
        provider, raw_output = _run_llm(prompt, timeout=llm_timeout)
        verdict = parse_verdict_from_screening(raw_output) or "지원 보류"
        normalized_output = _normalize_output(raw_output, verdict)
    except Exception as exc:
        used_fallback = True
        verdict = "지원 보류"
        raw_output = f"LLM 스크리닝 실패: {exc}"
        normalized_output = f"""# JD 스크리닝 (자동 fallback)

## 기본 정보

- 파일: {jd_path.name}

## 최종 판정

### 최종 판정: 지원 보류

## 핵심 근거

- LLM 스크리닝 실행 실패로 자동 보류 처리
- 사유: {exc}
"""

    screening_path = SCREENING_DIR / _screening_filename(jd_path)

    if not dry_run:
        screening_path.parent.mkdir(parents=True, exist_ok=True)
        screening_path.write_text(normalized_output.rstrip() + "\n", encoding="utf-8")

        metadata = extract_metadata_from_jd(jd_content)
        job_id = extract_job_id_from_filename(jd_path.name) or jd_path.stem
        if metadata.get("company"):
            company = metadata["company"]
        elif "-" in jd_path.stem:
            company = jd_path.stem.split("-", 2)[1]
        else:
            company = "unknown"
        position = metadata.get("position") or jd_path.stem
        update_summary(job_id=job_id, company=company, position=position, verdict=verdict, folder="pending")

    return ScreeningResult(
        verdict=verdict,
        screening_path=screening_path,
        provider=provider,
        used_fallback=used_fallback,
        raw_output=raw_output,
    )
