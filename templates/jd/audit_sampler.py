#!/usr/bin/env python3
"""
JD Audit Manifest Sampler (Plan Step 0.6)

Reads the overlap map CSV from audit_overlap.py and generates a reproducible
stratified sample for Step 1 audit. Uses a fixed seed so reruns are identical.

No verdict logic — pure random sampling from pass/ rows. See plan file at
/Users/teslamint/.claude/plans/hashed-cuddling-pearl.md.

Default stratum sizes (tuned to codex's CI-based recommendation):
  - M1-only (~121): 30 rows          (±15% CI target)
  - M2-only (~40):  20 rows          (small population, ±20% floor)
  - M3-only (~134): 30 rows          (±15% CI target)
  - overlap-any (~191): 40 rows      (pair/triple combined; high value)
  - rubric (non-pass or plain): 5 from 000 stratum (sanity check)
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OVERLAP_TEMPLATE = REPO_ROOT / "private" / "jd_analysis" / "overlap_map_{date}.csv"

DEFAULT_SIZES = {
    "M1-only": 30,
    "M2-only": 20,
    "M3-only": 30,
    "overlap-any": 40,
    "rubric-000": 5,
}


def classify_row(row: dict) -> str:
    if row["in_pass"] != "1":
        return "not-pass"
    mask = row["mask"]
    if mask == "000":
        return "rubric-000"
    if mask == "100":
        return "M1-only"
    if mask == "010":
        return "M2-only"
    if mask == "001":
        return "M3-only"
    return "overlap-any"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate stratified audit sample manifest")
    parser.add_argument("--overlap-csv", default=None, help="Input CSV from audit_overlap.py")
    parser.add_argument("--output", default=None, help="Output manifest CSV path")
    parser.add_argument("--date-tag", default=None, help="Date tag (default: today)")
    parser.add_argument("--seed", type=int, default=20260417, help="Random seed (default: 20260417)")
    for stratum, default in DEFAULT_SIZES.items():
        parser.add_argument(f"--n-{stratum}", type=int, default=default, help=f"Sample size for {stratum}")
    args = parser.parse_args()

    date_tag = args.date_tag or date.today().isoformat()
    overlap_csv = Path(args.overlap_csv) if args.overlap_csv else Path(
        str(DEFAULT_OVERLAP_TEMPLATE).format(date=date_tag)
    )
    output_path = (
        Path(args.output)
        if args.output
        else REPO_ROOT / "private" / "jd_analysis" / f"audit_manifest_{date_tag}.csv"
    )

    if not overlap_csv.exists():
        print(f"Error: overlap CSV not found at {overlap_csv}", file=sys.stderr)
        print("Run templates/jd/audit_overlap.py first.", file=sys.stderr)
        return 1

    with overlap_csv.open(encoding="utf-8") as f:
        all_rows = list(csv.DictReader(f))

    buckets: dict[str, list[dict]] = {k: [] for k in DEFAULT_SIZES}
    for row in all_rows:
        stratum = classify_row(row)
        if stratum in buckets:
            buckets[stratum].append(row)

    rng = random.Random(args.seed)
    sample_rows = []
    for stratum, pool in buckets.items():
        requested = getattr(args, f"n_{stratum.replace('-', '_')}")
        n = min(requested, len(pool))
        picked = rng.sample(pool, n) if n > 0 else []
        for pr in picked:
            sample_rows.append(
                {
                    "stratum": stratum,
                    "id": pr["id"],
                    "filename": pr["filename"],
                    "mask": pr["mask"],
                    "M1": pr["M1"],
                    "M2": pr["M2"],
                    "M3": pr["M3"],
                    "audit_status": "pending",
                    "reverdict": "",
                    "flipped": "",
                    "H1_completeness_mismatch": "",
                    "H2_salary_evidence_layer": "",
                    "H3_verdict_folder_mismatch": "",
                    "notes": "",
                }
            )

    fieldnames = [
        "stratum",
        "id",
        "filename",
        "mask",
        "M1",
        "M2",
        "M3",
        "audit_status",
        "reverdict",
        "flipped",
        "H1_completeness_mismatch",
        "H2_salary_evidence_layer",
        "H3_verdict_folder_mismatch",
        "notes",
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(sample_rows)

    print(f"seed: {args.seed}")
    print(f"overlap CSV: {overlap_csv}")
    print(f"manifest:    {output_path}")
    print()
    print(f"{'스트라텀':<20} {'요청':>6} {'가용':>6} {'선정':>6}")
    print("-" * 44)
    grand_total = 0
    for stratum, pool in buckets.items():
        requested = getattr(args, f"n_{stratum.replace('-', '_')}")
        picked = min(requested, len(pool))
        print(f"{stratum:<20} {requested:>6} {len(pool):>6} {picked:>6}")
        grand_total += picked
    print("-" * 44)
    print(f"{'합계':<20} {'':>6} {'':>6} {grand_total:>6}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
