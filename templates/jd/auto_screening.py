#!/usr/bin/env python3
"""LLM-driven JD screening for JD auto pipeline."""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import tempfile
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


BASE_DIR = Path(__file__).parent.parent.parent
PROFILE_DIR = BASE_DIR / "private" / "profile"
COMPANIES_DIR = BASE_DIR / "private" / "companies"
MAX_CANDIDATE_CONTEXT_CHARS = 60000
MAX_CANDIDATE_FILE_CHARS = 4000
PROFILE_CONTEXT_FILES = (
    "summary-job.md",
    "skills-job.md",
    "core-competencies.md",
)
MAX_FALLBACK_REASON_CHARS = 240


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


def _source_label(path: Path) -> str:
    try:
        return str(path.relative_to(BASE_DIR))
    except ValueError:
        return str(path)


def _read_context_file(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if len(text) > MAX_CANDIDATE_FILE_CHARS:
        text = text[:MAX_CANDIDATE_FILE_CHARS].rstrip() + "\n...(truncated)"
    return f"[source: {_source_label(path)}]\n{text}"


def _load_candidate_context() -> str:
    paths: list[Path] = []

    for filename in PROFILE_CONTEXT_FILES:
        path = PROFILE_DIR / filename
        if path.exists():
            paths.append(path)

    if COMPANIES_DIR.exists():
        paths.extend(sorted(COMPANIES_DIR.glob("*/profile.md")))
        paths.extend(sorted(COMPANIES_DIR.glob("*/projects/*.md")))

    blocks: list[str] = []
    total_chars = 0
    for path in paths:
        if not path.exists() or path.name == "CLAUDE.md":
            continue
        block = _read_context_file(path)
        next_total = total_chars + len(block) + 2
        if next_total > MAX_CANDIDATE_CONTEXT_CHARS:
            remaining = MAX_CANDIDATE_CONTEXT_CHARS - total_chars
            if remaining > 200:
                blocks.append(block[:remaining].rstrip() + "\n...(context truncated)")
            break
        blocks.append(block)
        total_chars = next_total

    return "\n\n---\n\n".join(blocks) if blocks else "후보자 이력 파일 없음"


def _build_prompt(
    jd_content: str,
    rules: str,
    company_content: str,
    company_risk_summary: str,
    candidate_context: str,
) -> str:
    return f"""아래 기준으로 JD 스크리닝을 수행하세요.

요구사항:
1) 반드시 최종 판정을 `지원 추천` 또는 `지원 보류` 또는 `지원 비추천` 중 하나로 명시
2) 결과는 Markdown으로 stdout에 직접 출력 (파일 저장 아님 — 권한 요청·승인 대기 응답 금지)
3) 출력 첫 줄은 반드시 `## 기본 정보`로 시작. 프리앰블, Insight, 주석, 코드블록, 구분선으로 시작하지 않음
4) 아래 섹션 순서 사용:
   - ## 기본 정보
   - ## 스크리닝 결과
   - ## 이력/경험 매칭
   - ## 최종 판정
   - ## 핵심 근거
5) 최종 판정 섹션에 `### 최종 판정: <판정>` 형식을 포함
6) `## 이력/경험 매칭`에서는 JD 필수요건/우대사항/역할 기대치를 후보자 이력 근거와 대조
7) 후보자 이력에 명시된 근거가 없으면 추정하지 말고 `근거 없음` 또는 `근거 약함`으로 표기
8) 이력 매칭 근거는 가능한 한 `[source: ...]` 경로를 함께 언급
9) 저장용 분석 문서처럼 작성하고, 사용자에게 말을 거는 문장이나 후속 제안 문장을 쓰지 않음
10) `원하시면`, `해드리겠습니다`, `다음 단계로`, `~할 수 있습니다` 같은 대화형 문구 금지
11) 판정은 단호하게 유지하되 회사나 포지션을 평가절하하지 말고, 후보자의 기준과 맞는지 중심으로 설명
12) 내부 기준 용어를 결과 문서에 그대로 쓰지 않음. 금지어는 표, 제목, 본문 어디에도 쓰지 않음: `리드 전가 리스크`, `금융 리스크`, `즉시 컷`, `하드 컷`, `구조적 리스크`, `미스매치`, `불충족`, `충족 실패`, `갭`, `부재`, `전무`, `산출`, `하한`
13) 금지어가 [스크리닝 규칙]에 등장하더라도 결과 문서에는 재사용하지 않음
14) 금지어 대신 자연어로 풀어 씀. 예: `리드 전가 리스크` → `입사 직후부터 방향 조율과 기술 의사결정 부담이 커질 가능성`, `즉시 컷` → `다른 장점이 있어도 우선순위를 낮게 보는 조건`, `불충족`/`충족 실패` → `기준에 맞지 않음`, `갭` → `차이가 있음`, `부재`/`전무` → `확인되지 않음`, `산출` → `계산`, `하한` → `최소 기준`
15) 표의 `비고`와 `근거` 칸은 판정 용어보다 읽히는 문장으로 작성. 예: `②③④ 충족 실패` 대신 `책임자·업무 범위·조직 상황을 안심하고 보기 어렵다`
16) `## 핵심 근거`는 3~5개의 짧은 문단 또는 불릿으로 압축하고, 각 항목을 "왜 이 기준과 맞지 않는지"로 설명
17) 감사 로그처럼 딱딱한 표현을 피하고, `검증 불가`, `정량 근거 없음`, `판단 불가` 같은 표현은 필요한 경우에도 한 문서에 2회 이하로 제한
18) 출력 전에 자체 검수: 금지어가 표/제목/본문 어디든 남아 있으면 반드시 자연어 표현으로 바꾼 뒤 최종 출력

[스크리닝 규칙]
{rules}

[후보자 이력/경험 근거]
{candidate_context}

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


def _is_codex_exec_command(cmd: list[str]) -> bool:
    if not cmd:
        return False
    executable = Path(cmd[0]).name
    return executable == "codex" and len(cmd) > 1 and cmd[1] == "exec"


def _should_capture_codex_last_message(cmd: list[str]) -> bool:
    return _is_codex_exec_command(cmd) and "--output-last-message" not in cmd and "-o" not in cmd


def _classify_provider_error(provider: str, detail: str) -> str:
    text = detail.replace("\r", "\n").strip()
    lowered = text.lower()

    if "not logged in" in lowered and "please run /login" in lowered:
        return f"{provider}: not logged in"

    if provider == "codex":
        if "readonly database" in lowered or (
            "operation not permitted" in lowered and ".codex" in lowered
        ):
            return f"{provider}: blocked by Codex App sandbox/home state"
        if "operation not permitted" in lowered and "app-server" in lowered:
            return f"{provider}: blocked by Codex App sandbox"

    if (
        "failed to lookup address information" in lowered
        or "could not resolve host" in lowered
        or "network is unreachable" in lowered
    ):
        return f"{provider}: network unavailable"

    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if not first_line:
        return f"{provider}: execution failed"
    if len(first_line) > MAX_FALLBACK_REASON_CHARS:
        first_line = first_line[:MAX_FALLBACK_REASON_CHARS].rstrip() + "..."
    return f"{provider}: {first_line}"


def _format_failed_process(provider: str, returncode: int, stdout: str, stderr: str) -> str:
    detail = "\n".join(part for part in (stderr.strip(), stdout.strip()) if part)
    classified = _classify_provider_error(provider, detail)
    if classified.startswith(f"{provider}:"):
        return classified
    return f"{provider}: exit={returncode}"


def _run_provider_command(
    provider: str,
    cmd: list[str],
    prompt: str,
    timeout: int,
    env: dict[str, str],
) -> tuple[int, str, str]:
    output_path: Path | None = None
    run_cmd = list(cmd)

    if _should_capture_codex_last_message(run_cmd):
        fd, path = tempfile.mkstemp(prefix="jd-screening-codex-", suffix=".md")
        os.close(fd)
        output_path = Path(path)
        run_cmd.extend(["--output-last-message", str(output_path)])

    try:
        proc = subprocess.run(
            run_cmd,
            input=prompt,
            text=True,
            capture_output=True,
            timeout=timeout,
            env=env,
        )
        stdout = proc.stdout
        if proc.returncode == 0 and output_path and output_path.exists():
            captured = output_path.read_text(encoding="utf-8").strip()
            if captured:
                stdout = captured
        return proc.returncode, stdout, proc.stderr
    finally:
        if output_path:
            try:
                output_path.unlink()
            except FileNotFoundError:
                pass


def _run_llm(prompt: str, timeout: int) -> tuple[str, str]:
    env = os.environ.copy()
    env.pop("CLAUDECODE", None)

    errors: list[str] = []
    for provider, cmd in _resolve_commands():
        try:
            returncode, stdout, stderr = _run_provider_command(provider, cmd, prompt, timeout, env)
        except FileNotFoundError:
            errors.append(f"{provider}: command not found")
            continue
        except subprocess.TimeoutExpired:
            errors.append(f"{provider}: timed out after {timeout}s")
            continue
        except Exception as exc:
            errors.append(f"{provider}: execution error: {exc}")
            continue

        if returncode != 0:
            errors.append(_format_failed_process(provider, returncode, stdout, stderr))
            continue

        output = stdout.strip()
        if not output:
            errors.append(f"{provider}: returned empty output")
            continue

        return provider, output

    raise RuntimeError("; ".join(errors) or "No LLM provider succeeded")


def _screening_filename(jd_path: Path) -> str:
    job_id = extract_job_id_from_filename(jd_path.name) or jd_path.stem.split("-")[0]
    if jd_path.stem.startswith(f"{job_id}-"):
        return f"{jd_path.stem}.md"
    return f"{job_id}-{jd_path.stem.split('-', 1)[1]}.md" if "-" in jd_path.stem else f"{job_id}.md"


_REQUIRED_SECTIONS = (
    "## 기본 정보",
    "## 스크리닝 결과",
    "## 이력/경험 매칭",
    "## 최종 판정",
    "## 핵심 근거",
)

_CONVERSATIONAL_PATTERNS = (
    "승인 대기 중",
    "권한을 요청합니다",
    "저장 권한이 필요",
    "실행 권한이 필요",
    "Plan 파일을 작성",
    "진행 방식을 확인하겠습니다",
    "어디에 저장할까",
    "저장할 위치를 알려",
    "진행해도 될까",
    "스크리닝을 진행하겠습니다",
    "분석을 진행하겠습니다",
    "도와드리겠습니다",
)

_MIN_CONTENT_LINES = 5

_FILLER_PREFIXES = ("|---", "|-", "| ---", "| -")


def _is_substantive_line(line: str) -> bool:
    """Return True if line is non-empty, non-heading, non-filler."""
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.startswith("#"):
        return False
    for prefix in _FILLER_PREFIXES:
        if stripped.startswith(prefix) and set(stripped.replace("|", "").strip()) <= {"-", " "}:
            return False
    return True


def _validate_screening_structure(markdown: str) -> tuple[bool, str]:
    lines = markdown.splitlines()
    heading_lines = {l.strip() for l in lines if l.strip().startswith("#")}
    missing = [s for s in _REQUIRED_SECTIONS if s not in heading_lines]
    if missing:
        return False, f"필수 섹션 누락: {', '.join(missing)}"

    content_lines = [l for l in lines if _is_substantive_line(l)]
    if len(content_lines) < _MIN_CONTENT_LINES:
        return False, f"섹션 내용 부족 (헤더/구분선 제외 {len(content_lines)}줄 < {_MIN_CONTENT_LINES})"

    for pat in _CONVERSATIONAL_PATTERNS:
        if pat in markdown:
            return False, f"대화형 패턴 탐지: '{pat}'"

    return True, ""


def _normalize_output(markdown: str, verdict: str) -> str:
    if "### 최종 판정:" in markdown:
        return markdown
    return markdown.rstrip() + f"\n\n## 최종 판정\n\n### 최종 판정: {verdict}\n"


def _table_cell(value: Optional[str], default: str = "확인 필요") -> str:
    text = (value or default).strip() or default
    return text.replace("|", "\\|").replace("\n", " ")


def _summarize_llm_error(exc: Exception) -> str:
    message = str(exc).replace("\r", "\n").strip()
    if not message:
        return "LLM 실행 오류"

    exit_match = re.search(r"\b([A-Za-z_-]+ exit=\d+)\b", message)
    if exit_match:
        return exit_match.group(1)

    first_line = next((line.strip() for line in message.splitlines() if line.strip()), "")
    if len(first_line) > MAX_FALLBACK_REASON_CHARS:
        return first_line[:MAX_FALLBACK_REASON_CHARS].rstrip() + "..."
    return first_line or "LLM 실행 오류"


def _build_fallback_output(jd_path: Path, jd_content: str, reason: str) -> str:
    metadata = extract_metadata_from_jd(jd_content)
    company = metadata.get("company")
    position = metadata.get("position") or jd_path.stem
    source_url = metadata.get("url")

    return f"""## 기본 정보

| 항목 | 내용 |
|------|------|
| 파일 | {_table_cell(jd_path.name)} |
| 회사명 | {_table_cell(company)} |
| 포지션 | {_table_cell(position)} |
| 출처 | {_table_cell(source_url)} |
| 생성 방식 | 자동 fallback |

## 스크리닝 결과

LLM 스크리닝 실행이 완료되지 않아 자동 판정은 보류로 기록한다. 채용 적합성은 수동 재스크리닝 전까지 확정하지 않는다.

## 이력/경험 매칭

| 항목 | 판단 |
|------|------|
| 후보자 이력 대조 | LLM 분석 실패로 이력 근거 대조가 수행되지 않았다. |
| JD 필수요건 대조 | 수동 재스크리닝 필요. |

## 최종 판정

### 최종 판정: 지원 보류

## 핵심 근거

- 자동 분석 경로에서 LLM 응답을 얻지 못했다.
- 실패 사유: {reason}
- 이 문서는 원시 실행 로그를 저장하지 않고 수동 재스크리닝을 위한 보류 상태만 기록한다.
"""


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
    candidate_context = _load_candidate_context()

    prompt = _build_prompt(jd_content, rules, company_content, risk_summary, candidate_context)

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
        reason = _summarize_llm_error(exc)
        raw_output = f"LLM 스크리닝 실패: {reason}"
        normalized_output = _build_fallback_output(jd_path, jd_content, reason)

    valid, reason = _validate_screening_structure(normalized_output)
    if not valid:
        if used_fallback:
            raise RuntimeError(f"fallback 구조 검증 실패: {reason}")

        retry_prefix = (
            "이전 응답이 필수 섹션을 누락했습니다. "
            "반드시 ## 기본 정보 / ## 스크리닝 결과 / ## 이력/경험 매칭 / "
            "## 최종 판정 / ## 핵심 근거 순서로 출력하세요.\n\n"
        )
        try:
            provider, raw_output = _run_llm(retry_prefix + prompt, timeout=llm_timeout)
            verdict = parse_verdict_from_screening(raw_output) or "지원 보류"
            normalized_output = _normalize_output(raw_output, verdict)
        except Exception:
            raise RuntimeError(f"구조 검증 실패 + 재시도 LLM 오류: {reason}")
        valid, reason = _validate_screening_structure(normalized_output)
        if not valid:
            raise RuntimeError(f"구조 검증 실패 (재시도 후): {reason}")

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
