#!/usr/bin/env python3
"""One-time re-screening script for truncated screening files (cause 2-3).

Targets 19 files that have verdict-only output due to LLM output format
violations (Insight preamble, summary-only, frontmatter) or Python fallback
templates (_run_llm() failure).

Usage:
    python3 templates/jd/rescreen_truncated.py [--dry-run]
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from auto_screening import run_screening
from constants import COMPANY_INFO_DIR, JOB_POSTINGS_DIR, SCREENING_DIR
from jd_content import load_company_info, extract_metadata_from_jd
from pipeline import classify_file

TARGET_IDS = [
    "227287", "234830", "252452", "291651", "294971", "295390",
    "296173", "296620", "296851", "299660", "302125", "309338",
    "312478", "321594", "346448", "350485", "354314", "356383",
    "360400",
]


def _find_jd_file(job_id: str) -> Path | None:
    for folder in JOB_POSTINGS_DIR.rglob(f"{job_id}-*.md"):
        return folder
    return None


def _find_screening_file(job_id: str) -> Path | None:
    for f in SCREENING_DIR.glob(f"{job_id}-*.md"):
        return f
    return None


def _find_company_file(company: str) -> Path | None:
    normalized = company.lower().replace(" ", "-").replace("_", "-")
    for pattern in [f"{normalized}.md", f"{company}.md"]:
        path = COMPANY_INFO_DIR / pattern
        if path.exists():
            return path
    if COMPANY_INFO_DIR.exists():
        for f in COMPANY_INFO_DIR.glob("*.md"):
            if normalized in f.stem.lower():
                return f
    return None


def main() -> None:
    dry_run = "--dry-run" in sys.argv

    results: list[dict] = []

    for job_id in TARGET_IDS:
        jd_path = _find_jd_file(job_id)
        if not jd_path:
            results.append({"id": job_id, "status": "SKIP", "reason": "JD file not found"})
            continue

        screening_path = _find_screening_file(job_id)
        old_lines = 0
        if screening_path and screening_path.exists():
            old_lines = len(screening_path.read_text(encoding="utf-8").splitlines())
            if not dry_run:
                bak = screening_path.with_suffix(".md.bak")
                shutil.copy2(screening_path, bak)

        jd_content = jd_path.read_text(encoding="utf-8")
        metadata = extract_metadata_from_jd(jd_content)
        company = metadata.get("company", "")
        company_file = _find_company_file(company) if company else None

        print(f"[{job_id}] Re-screening: {jd_path.name} (company_file={company_file})")

        try:
            result = run_screening(
                jd_path=jd_path,
                company_file=company_file,
                llm_timeout=180,
                dry_run=dry_run,
            )
        except Exception as exc:
            results.append({"id": job_id, "status": "ERROR", "reason": str(exc)})
            print(f"  -> ERROR: {exc}")
            continue

        new_lines = len(result.raw_output.splitlines())

        if result.used_fallback:
            results.append({
                "id": job_id,
                "status": "FALLBACK",
                "reason": "LLM failed, fallback template used",
                "old_lines": old_lines,
                "new_lines": new_lines,
                "verdict": result.verdict,
            })
            print(f"  -> FALLBACK: {result.verdict} ({old_lines} -> {new_lines} lines)")
            continue

        if not dry_run:
            classify_result = classify_file(jd_path)
            classify_info = f" -> {classify_result.target_folder}" if classify_result.target_folder else ""
        else:
            classify_info = " (dry-run, skip classify)"

        results.append({
            "id": job_id,
            "status": "OK",
            "old_lines": old_lines,
            "new_lines": new_lines,
            "verdict": result.verdict,
            "provider": result.provider,
            "classify": classify_info.strip(),
        })
        print(f"  -> OK: {result.verdict} via {result.provider} ({old_lines} -> {new_lines} lines){classify_info}")

    print("\n" + "=" * 60)
    print("REPORT")
    print("=" * 60)

    ok = [r for r in results if r["status"] == "OK"]
    skip = [r for r in results if r["status"] == "SKIP"]
    err = [r for r in results if r["status"] in ("ERROR", "FALLBACK")]

    print(f"  OK: {len(ok)}  SKIP: {len(skip)}  ERROR/FALLBACK: {len(err)}")
    print()

    if ok:
        print("Successful re-screenings:")
        for r in ok:
            print(f"  {r['id']}: {r['verdict']} ({r['old_lines']} -> {r['new_lines']} lines) {r.get('classify', '')}")

    if err:
        print("\nFailed:")
        for r in err:
            print(f"  {r['id']}: {r['status']} - {r.get('reason', 'unknown')}")

    if skip:
        print("\nSkipped (JD not found):")
        for r in skip:
            print(f"  {r['id']}: {r['reason']}")


if __name__ == "__main__":
    main()
