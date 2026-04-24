#!/usr/bin/env python3
"""
JD Screening Freshness Check (Plan Step 0.6)

Lists screening files older than N days. Used to flag stale screening results
that may have diverged from the current JD page (JD drift). Read-only scan.

Output: CSV with columns (filename, mtime, days_old, in_pass) — no verdict logic.
See /Users/teslamint/.claude/plans/hashed-cuddling-pearl.md Step 3-③.
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCREENING_DIR = REPO_ROOT / "private" / "jd_analysis" / "screening"
PASS_DIR = REPO_ROOT / "private" / "job_postings" / "pass"


def main() -> int:
    parser = argparse.ArgumentParser(description="List stale screening files (mtime-based)")
    parser.add_argument("--days", type=int, default=30, help="Minimum age in days (default: 30)")
    parser.add_argument("--output", default=None, help="Output CSV path")
    parser.add_argument("--date-tag", default=None, help="Date tag (default: today)")
    args = parser.parse_args()

    date_tag = args.date_tag or date.today().isoformat()
    output_path = (
        Path(args.output)
        if args.output
        else REPO_ROOT / "private" / "jd_analysis" / f"stale_screening_{date_tag}.csv"
    )

    if not SCREENING_DIR.exists():
        print(f"Error: {SCREENING_DIR} not found", file=sys.stderr)
        return 1

    pass_files = {f.name for f in PASS_DIR.iterdir() if f.suffix == ".md"} if PASS_DIR.exists() else set()

    now_ts = datetime.now().timestamp()
    threshold_sec = args.days * 86400

    rows = []
    for md_file in sorted(SCREENING_DIR.glob("*.md")):
        if md_file.name == "SUMMARY.md":
            continue
        mtime = md_file.stat().st_mtime
        age_sec = now_ts - mtime
        if age_sec < threshold_sec:
            continue
        days_old = int(age_sec / 86400)
        rows.append(
            {
                "filename": md_file.name,
                "mtime": datetime.fromtimestamp(mtime).isoformat(timespec="seconds"),
                "days_old": days_old,
                "in_pass": "1" if md_file.name in pass_files else "0",
            }
        )

    rows.sort(key=lambda r: r["days_old"], reverse=True)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["filename", "mtime", "days_old", "in_pass"])
        writer.writeheader()
        writer.writerows(rows)

    total = len(rows)
    in_pass = sum(1 for r in rows if r["in_pass"] == "1")
    print(f"threshold:   {args.days}일+")
    print(f"총 stale:    {total}")
    print(f"pass/ 내:    {in_pass}")
    if rows:
        oldest = rows[0]
        print(f"최장 stale:  {oldest['filename']} ({oldest['days_old']}일)")
    print(f"CSV:         {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
