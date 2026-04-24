#!/usr/bin/env python3
"""
R2 Hypothesis Audit — H1/H2/H3 (Plan Step 1 adjunct)

Tests three adjacent failure hypotheses identified during Rubric audit:
  H1 — Among pass/ 🔴 cuts, share of cases whose company_info has critical
       fields (salary / revenue / headcount / investment round) empty.
  H2 — Among salary-based 🔴 cuts, share using approximated (T2) or absent
       (T3) evidence vs actual measurements (T1).
  H3 — Folder-location mismatch vs screening verdict vs SUMMARY.md verdict
       (three-way, tie-break: folder > SUMMARY > screening).

Critical: for H3 verdict extraction, use the LAST '최종 판정' line
(ref. 311992 has 3 verdict blocks from multiple re-screens).

Output: three CSVs + stdout aggregation.
"""

from __future__ import annotations

import csv
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCREENING_DIR = REPO_ROOT / "private" / "jd_analysis" / "screening"
COMPANY_INFO_DIR = REPO_ROOT / "private" / "company_info"
SUMMARY_MD = SCREENING_DIR / "SUMMARY.md"
JOB_POSTING_DIRS = {
    "pass": REPO_ROOT / "private" / "job_postings" / "pass",
    "high": REPO_ROOT / "private" / "job_postings" / "conditional" / "high",
    "hold": REPO_ROOT / "private" / "job_postings" / "conditional" / "hold",
    "applied": REPO_ROOT / "private" / "job_postings" / "applied",
}

# ---------- helpers ----------

VACANT_RE = re.compile(r"정보\s*없음|비공개|TBD|정보없음")


def load_file_locations() -> dict[str, str]:
    """Map filename → folder label."""
    loc = {}
    for label, path in JOB_POSTING_DIRS.items():
        if not path.exists():
            continue
        for f in path.iterdir():
            if f.suffix == ".md":
                loc[f.name] = label
    return loc


def extract_id(filename: str) -> str:
    m = re.match(r"^(\d{4,6})-", filename)
    return m.group(1) if m else ""


def derive_company_slug(screening_fn: str) -> str:
    """Attempt to derive company_info key from screening filename."""
    # strip id prefix and .md
    stem = re.sub(r"^\d+-", "", screening_fn[:-3])
    # first hyphen-separated token is typically the company
    first = stem.split("-")[0]
    return first


# ---------- verdict extraction (H3 core, handles 311992 edge case) ----------

VERDICT_RE = re.compile(r"최종\s*판정\s*[:：]?\s*([^\n]+)")
VERDICT_MAP = {
    "🔴": "pass",
    "🟡": "hold",
    "🟢": "high",
    "✅": "applied",
    "지원 비추천": "pass",
    "지원 보류": "hold",
    "지원 추천": "high",
    "지원추천": "high",
    "이미 지원": "applied",
}


def extract_last_verdict(text: str) -> tuple[str, str]:
    """Returns (verdict_label, raw_match) using LAST 최종 판정 occurrence."""
    matches = list(VERDICT_RE.finditer(text))
    if not matches:
        return ("unknown", "")
    last_raw = matches[-1].group(1).strip()
    for emoji, label in VERDICT_MAP.items():
        if emoji in last_raw:
            return (label, last_raw)
    return ("unknown", last_raw)


# ---------- H1: company_info vacancy ----------

CRITICAL_FIELD_ANCHORS = {
    "salary": ("평균 연봉", "연봉 정보"),
    "headcount": ("현재 인원", "직원수"),
    "revenue": ("매출액", "매출 추이", "매출"),
    "round": ("현재 라운드", "투자 정보"),
}


def measure_company_info_gaps(company_info_path: Path) -> dict:
    """Return field-level vacancy measurement for a company_info file."""
    if not company_info_path.exists():
        return {"exists": False, "vacant_fields": [], "total_checked": 0}
    text = company_info_path.read_text(encoding="utf-8")
    result = {"exists": True, "vacant_fields": [], "total_checked": 0}
    for field, anchors in CRITICAL_FIELD_ANCHORS.items():
        result["total_checked"] += 1
        field_block = ""
        for anchor in anchors:
            idx = text.find(anchor)
            if idx >= 0:
                field_block = text[idx : idx + 300]
                break
        if not field_block:
            result["vacant_fields"].append(field)
            continue
        # Count vacancy markers in the block
        vacant_markers = VACANT_RE.findall(field_block)
        if len(vacant_markers) >= 2 or (not re.search(r"[0-9]+\s*[만억%명]", field_block)):
            result["vacant_fields"].append(field)
    return result


# ---------- H2: salary evidence tier ----------

T1_PATTERNS = [
    re.compile(r"연봉상위\s*[\d~~%]+"),
    re.compile(r"상위\s*\d+%"),
    re.compile(r"평균\s*연봉.*[\d,]+만원"),
    re.compile(r"전사\s*평균.*[\d,]+만원"),
    re.compile(r"TheVC.*매출"),
    re.compile(r"Wanted.*뱃지"),
]
T2_PATTERNS = [
    re.compile(r"×\s*1\.[3-7]"),
    re.compile(r"\*\s*1\.[3-7]"),
    re.compile(r"시니어\s*추정"),
    re.compile(r"시니어\s*연봉\s*추정"),
    re.compile(r"보수적\s*추정"),
    re.compile(r"추정\s*연봉"),
]
T3_PATTERNS = [
    re.compile(r"협의"),
    re.compile(r"추정\s*불가"),
    re.compile(r"데이터\s*부재"),
    re.compile(r"정보\s*없음.*연봉"),
    re.compile(r"연봉.*정보\s*없음"),
    re.compile(r"연봉\s*미기재"),
    re.compile(r"연봉\s*비공개"),
]
SALARY_CUT_PATTERNS = [
    re.compile(r"연봉\s*(?:리스크|구조|수준|하한).*❌"),
    re.compile(r"시니어\s*추정.*❌"),
    re.compile(r"하한.*미달"),
    re.compile(r"연봉\s*❌"),
    re.compile(r"연봉\s*구조적\s*하향"),
]


def classify_salary_tier(text: str) -> dict:
    """Check if this screening has a salary-based cut; classify evidence tier."""
    has_salary_cut = any(p.search(text) for p in SALARY_CUT_PATTERNS)
    t1 = any(p.search(text) for p in T1_PATTERNS)
    t2 = any(p.search(text) for p in T2_PATTERNS)
    t3 = any(p.search(text) for p in T3_PATTERNS)
    if has_salary_cut:
        # priority: T1 if present else T2 else T3 else unknown
        if t1 and not t2:
            tier = "T1"
        elif t2:
            tier = "T2"  # approximated
        elif t3:
            tier = "T3"  # absent
        else:
            tier = "unknown"
    else:
        tier = "no_salary_cut"
    return {"has_salary_cut": has_salary_cut, "tier": tier, "t1": t1, "t2": t2, "t3": t3}


# ---------- SUMMARY parser ----------

SUMMARY_VERDICT_RE = re.compile(
    r"^\|\s*\d{4}-\d{2}-\d{2}\s*\|\s*(\d{4,6})\s*\|[^|]*\|[^|]*\|\s*([^|]+?)\s*\|",
    re.MULTILINE,
)


def parse_summary_verdicts() -> dict[str, str]:
    if not SUMMARY_MD.exists():
        return {}
    text = SUMMARY_MD.read_text(encoding="utf-8")
    out = {}
    for m in SUMMARY_VERDICT_RE.finditer(text):
        id_, verdict_raw = m.group(1), m.group(2).strip()
        label = "unknown"
        for emoji, lbl in VERDICT_MAP.items():
            if emoji in verdict_raw:
                label = lbl
                break
        out[id_] = label
    return out


# ---------- main ----------

def main() -> int:
    date_tag = date.today().isoformat()

    file_locations = load_file_locations()
    summary_verdicts = parse_summary_verdicts()

    # Precompute company_info vacancies per slug (cache)
    ci_cache: dict[str, dict] = {}

    h1_rows = []
    h2_rows = []
    h3_rows = []

    for md in sorted(SCREENING_DIR.glob("*.md")):
        if md.name == "SUMMARY.md":
            continue
        text = md.read_text(encoding="utf-8")
        id_ = extract_id(md.name)

        # last verdict (H3 + shared)
        verdict_label, verdict_raw = extract_last_verdict(text)

        # folder location
        folder = file_locations.get(md.name, "missing")

        # summary verdict
        summary_v = summary_verdicts.get(id_, "unknown")

        # ---------- H3 ----------
        # Tie-break order: folder > summary > screening
        # Ground truth = folder
        mismatch_folder_vs_screening = (folder != verdict_label and folder != "missing" and verdict_label != "unknown")
        mismatch_folder_vs_summary = (folder != summary_v and folder != "missing" and summary_v != "unknown")
        mismatch_screening_vs_summary = (verdict_label != summary_v and verdict_label != "unknown" and summary_v != "unknown")

        h3_rows.append({
            "id": id_,
            "filename": md.name,
            "folder": folder,
            "screening_last_verdict": verdict_label,
            "screening_raw": verdict_raw[:80],
            "summary_verdict": summary_v,
            "folder_vs_screening_mismatch": "1" if mismatch_folder_vs_screening else "0",
            "folder_vs_summary_mismatch": "1" if mismatch_folder_vs_summary else "0",
            "screening_vs_summary_mismatch": "1" if mismatch_screening_vs_summary else "0",
        })

        # ---------- H1 & H2 scope: pass/ 🔴 cuts only ----------
        if folder != "pass":
            continue
        if verdict_label != "pass":
            # verdict says not 🔴 but in pass/ - still interesting for H3 but skip H1/H2
            continue

        # H1: look up company_info file
        slug = derive_company_slug(md.name)
        ci_path = COMPANY_INFO_DIR / f"{slug}.md"
        if slug not in ci_cache:
            ci_cache[slug] = measure_company_info_gaps(ci_path)
        ci = ci_cache[slug]
        vacancy_ratio = len(ci["vacant_fields"]) / ci["total_checked"] if ci["total_checked"] else 0
        all_empty = (len(ci["vacant_fields"]) == ci["total_checked"]) if ci["exists"] else True

        h1_rows.append({
            "id": id_,
            "filename": md.name,
            "company_slug": slug,
            "ci_exists": "1" if ci["exists"] else "0",
            "vacant_fields": "|".join(ci["vacant_fields"]),
            "vacant_count": len(ci["vacant_fields"]),
            "total_fields": ci["total_checked"] or 4,
            "vacancy_ratio": f"{vacancy_ratio:.2f}",
            "all_empty_or_missing": "1" if all_empty else "0",
        })

        # H2: salary evidence tier
        h2 = classify_salary_tier(text)
        h2_rows.append({
            "id": id_,
            "filename": md.name,
            "has_salary_cut": "1" if h2["has_salary_cut"] else "0",
            "tier": h2["tier"],
            "t1_hit": "1" if h2["t1"] else "0",
            "t2_hit": "1" if h2["t2"] else "0",
            "t3_hit": "1" if h2["t3"] else "0",
        })

    # Write CSVs
    out_dir = REPO_ROOT / "private" / "jd_analysis"
    paths = {
        "h1": out_dir / f"r2_h1_company_info_gaps_{date_tag}.csv",
        "h2": out_dir / f"r2_h2_salary_evidence_{date_tag}.csv",
        "h3": out_dir / f"r2_h3_verdict_consistency_{date_tag}.csv",
    }

    with paths["h1"].open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(h1_rows[0].keys()))
        writer.writeheader()
        writer.writerows(h1_rows)
    with paths["h2"].open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(h2_rows[0].keys()))
        writer.writeheader()
        writer.writerows(h2_rows)
    with paths["h3"].open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(h3_rows[0].keys()))
        writer.writeheader()
        writer.writerows(h3_rows)

    # ========== H1 summary ==========
    total_pass_red = len(h1_rows)
    ci_missing = sum(1 for r in h1_rows if r["ci_exists"] == "0")
    all_empty = sum(1 for r in h1_rows if r["all_empty_or_missing"] == "1")
    partial_gaps = sum(1 for r in h1_rows if r["vacant_count"] != "0" and r["all_empty_or_missing"] == "0")

    print("=" * 70)
    print("H1: pass/ 🔴 cuts — company_info 핵심 필드 공백률")
    print("=" * 70)
    print(f"총 pass/ 🔴 건수:              {total_pass_red}")
    print(f"company_info 파일 없음:        {ci_missing} ({ci_missing/total_pass_red*100:.1f}%)")
    print(f"4개 필드 모두 공백/없음:       {all_empty} ({all_empty/total_pass_red*100:.1f}%)")
    print(f"일부 필드 공백:                {partial_gaps} ({partial_gaps/total_pass_red*100:.1f}%)")

    # ========== H2 summary ==========
    salary_cuts = [r for r in h2_rows if r["has_salary_cut"] == "1"]
    total_salary = len(salary_cuts)
    tier_counts = Counter(r["tier"] for r in salary_cuts)

    print()
    print("=" * 70)
    print("H2: salary cuts — evidence tier 분포")
    print("=" * 70)
    print(f"총 pass/ 🔴 중 salary cut 건:  {total_salary}")
    for tier in ("T1", "T2", "T3", "unknown"):
        cnt = tier_counts.get(tier, 0)
        pct = cnt / total_salary * 100 if total_salary else 0.0
        print(f"  {tier}: {cnt:>4}  ({pct:.1f}%)")
    t23 = tier_counts.get("T2", 0) + tier_counts.get("T3", 0)
    t23_pct = t23 / total_salary * 100 if total_salary else 0.0
    print(f"T2+T3 합계:                     {t23} ({t23_pct:.1f}%)")

    # ========== H3 summary ==========
    total_all = len(h3_rows)
    fvs = sum(1 for r in h3_rows if r["folder_vs_screening_mismatch"] == "1")
    fvS = sum(1 for r in h3_rows if r["folder_vs_summary_mismatch"] == "1")
    sVS = sum(1 for r in h3_rows if r["screening_vs_summary_mismatch"] == "1")
    missing_folder = sum(1 for r in h3_rows if r["folder"] == "missing")

    print()
    print("=" * 70)
    print("H3: verdict-folder 3-way consistency")
    print("=" * 70)
    print(f"총 screening 파일:             {total_all}")
    print(f"folder 매칭 실패(missing):    {missing_folder}")
    print(f"folder ≠ screening verdict:    {fvs}")
    print(f"folder ≠ SUMMARY verdict:      {fvS}")
    print(f"screening ≠ SUMMARY verdict:   {sVS}")

    print()
    print("CSV 출력:")
    for k, p in paths.items():
        print(f"  {k}: {p}")

    # ========== thresholds ==========
    print()
    print("=" * 70)
    print("Escalation threshold (사전 설정)")
    print("=" * 70)
    h1_escalate = all_empty / total_pass_red > 0.10 if total_pass_red else False
    h2_escalate = t23_pct > 20.0
    h3_escalate = fvs > 5

    print(f"H1 all_empty > 10%:     {all_empty/total_pass_red*100:.1f}%  →  {'🚨 ESCALATE' if h1_escalate else '✅ 유지'}")
    print(f"H2 T2+T3 > 20%:         {t23_pct:.1f}%  →  {'🚨 ESCALATE' if h2_escalate else '✅ 유지'}")
    print(f"H3 folder/screening mismatch > 5: {fvs}  →  {'🚨 ESCALATE' if h3_escalate else '✅ 유지'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
