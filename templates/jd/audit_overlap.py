#!/usr/bin/env python3
"""
JD Screening Mode Overlap Audit (Plan Step 0.5)

Scans all screening/*.md files, assigns an (M1, M2, M3) bitmask per file based
on keyword patterns, and emits:
  - overlap_map_<date>.csv
  - stratum aggregation to stdout

No verdict logic — pure metadata scan. Used to plan stratified sampling in the
Step 1 audit. See /Users/teslamint/.claude/plans/hashed-cuddling-pearl.md.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_JD_DIR = Path(__file__).resolve().parent
if str(_JD_DIR) not in sys.path:
    sys.path.insert(0, str(_JD_DIR))
from path_utils import extract_job_id_from_filename  # noqa: E402

SCREENING_DIR = REPO_ROOT / "private" / "jd_analysis" / "screening"
PASS_DIR = REPO_ROOT / "private" / "job_postings" / "pass"

M1_PATTERNS = [
    re.compile(r"AI/ML Engineer.*❌"),
    re.compile(r"도메인 불일치"),
    re.compile(r"Cloud.*❌"),
    re.compile(r"Infra.*❌"),
    re.compile(r"Platform.*❌"),
    re.compile(r"DevOps.*❌"),
    re.compile(r"포지션 소개"),
    re.compile(r"포지션명"),
]
M2_PATTERNS = [
    re.compile(r"M&A"),
    re.compile(r"인수합병"),
]
M3_PATTERNS = [
    re.compile(r"overqualified", re.IGNORECASE),
    re.compile(r"경력 상한"),
]
M3_NEGATION_WINDOW = 40
M3_NEGATION_PHRASES = ("해당 없음", "없습니다", "없음)", "아님", "무관")

STRATUM_LABELS = {
    "000": "없음 (플래그 없는 pass)",
    "100": "M1-only (도메인 오판)",
    "010": "M2-only (M&A)",
    "001": "M3-only (경력 상한)",
    "110": "M1+M2",
    "101": "M1+M3",
    "011": "M2+M3",
    "111": "M1+M2+M3 (triple)",
}


def _pct(numerator: int, denominator: int) -> float:
    """Safe percentage — returns 0.0 when the denominator is zero."""
    return numerator / denominator * 100 if denominator else 0.0


def _has_any(text: str, patterns) -> bool:
    return any(p.search(text) for p in patterns)


def _has_m3(text: str) -> bool:
    """M3 detection with negation filter.

    A match like 'overqualified 해당 없음' inside M3_NEGATION_WINDOW chars
    is treated as a non-match (false positive suppression).
    """
    for p in M3_PATTERNS:
        for m in p.finditer(text):
            start, end = m.start(), m.end()
            window = text[max(0, start - M3_NEGATION_WINDOW) : min(len(text), end + M3_NEGATION_WINDOW)]
            if any(phrase in window for phrase in M3_NEGATION_PHRASES):
                continue
            return True
    return False


def detect_modes(text: str) -> tuple[bool, bool, bool]:
    return _has_any(text, M1_PATTERNS), _has_any(text, M2_PATTERNS), _has_m3(text)


def extract_id(filename: str) -> str:
    return extract_job_id_from_filename(filename) or ""


def main() -> int:
    parser = argparse.ArgumentParser(description="JD Screening Mode Overlap Audit")
    parser.add_argument("--output", default=None, help="Output CSV path")
    parser.add_argument("--date-tag", default=None, help="Date tag (default: today)")
    args = parser.parse_args()

    date_tag = args.date_tag or date.today().isoformat()
    output_path = (
        Path(args.output)
        if args.output
        else REPO_ROOT / "private" / "jd_analysis" / f"overlap_map_{date_tag}.csv"
    )

    if not SCREENING_DIR.exists():
        print(f"Error: {SCREENING_DIR} not found", file=sys.stderr)
        return 1

    pass_files = {f.name for f in PASS_DIR.iterdir() if f.suffix == ".md"} if PASS_DIR.exists() else set()

    rows = []
    for md_file in sorted(SCREENING_DIR.glob("*.md")):
        if md_file.name == "SUMMARY.md":
            continue
        text = md_file.read_text(encoding="utf-8")
        m1, m2, m3 = detect_modes(text)
        in_pass = md_file.name in pass_files
        mask_bin = f"{(int(m1) << 2) | (int(m2) << 1) | int(m3):03b}"
        rows.append(
            {
                "id": extract_id(md_file.name),
                "filename": md_file.name,
                "in_pass": "1" if in_pass else "0",
                "M1": "1" if m1 else "0",
                "M2": "1" if m2 else "0",
                "M3": "1" if m3 else "0",
                "mask": mask_bin,
            }
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "filename", "in_pass", "M1", "M2", "M3", "mask"])
        writer.writeheader()
        writer.writerows(rows)

    pass_rows = [r for r in rows if r["in_pass"] == "1"]
    counter = Counter(r["mask"] for r in pass_rows)

    total_all = len(rows)
    total_pass = len(pass_rows)
    print(f"총 screening 파일: {total_all}")
    print(f"pass/ 대응: {total_pass}")
    print()
    print(f"{'스트라텀':<36} {'건수':>6} {'pass 비율':>11}")
    print("-" * 56)
    for mask_str in ["000", "100", "010", "001", "110", "101", "011", "111"]:
        cnt = counter.get(mask_str, 0)
        print(f"{STRATUM_LABELS[mask_str]:<36} {cnt:>6} {_pct(cnt, total_pass):>10.1f}%")

    m1_count = sum(1 for r in pass_rows if r["M1"] == "1")
    m2_count = sum(1 for r in pass_rows if r["M2"] == "1")
    m3_count = sum(1 for r in pass_rows if r["M3"] == "1")
    overlap_any = sum(1 for r in pass_rows if r["mask"] != "000")

    print()
    print(f"pass/ M1 (도메인):       {m1_count:>4} ({_pct(m1_count, total_pass):.1f}%)")
    print(f"pass/ M2 (M&A):          {m2_count:>4} ({_pct(m2_count, total_pass):.1f}%)")
    print(f"pass/ M3 (경력 상한):    {m3_count:>4} ({_pct(m3_count, total_pass):.1f}%)")
    print(f"pass/ 플래그 있는 건:    {overlap_any:>4} ({_pct(overlap_any, total_pass):.1f}%)")
    print()
    print(f"CSV 출력: {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
