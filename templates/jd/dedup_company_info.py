#!/usr/bin/env python3
"""Classify cosmetic-duplicate company_info groups and emit safe action artifacts.

Reads ``private/job_postings/unprocessed/cosmetic_duplicates_followup.txt`` and,
for each group of duplicate files, computes (a) per-file completeness, (b) token
Jaccard between the kept and deleted file headings + intro sections, and (c) the
list of external markdown files referencing each candidate-for-deletion.

Outputs (in ``private/build/``):

  - ``dedup_company_info_report.md`` — markdown summary + per-group classification
  - ``dedup_actions.sh`` — operator-runnable script: external-ref rewrites (Python
    one-liner so BSD/GNU sed differences don't matter) followed by ``git rm`` and
    ``git commit`` calls in 10-group batches
  - ``dedup_merge_diffs/<company>.diff`` — unified diff for groups needing manual
    merge (operator applies deleted-file uniques to kept file by hand)

The script never deletes files or commits — operator reviews and runs the emitted
bash. Categories (greedy single-round for groups with 3+ files):

  - ``auto_safe``     : keep ≥0.50, max deleted ≤0.15, token jaccard ≥0.30, no ext refs
  - ``ref_rewrite``   : auto_safe condition + ≥1 external reference
  - ``manual_merge``  : both keep and ≥1 deleted file ≥0.30 (real merge needed)
  - ``manual_review`` : keep ≥0.50, max deleted in (0.15, 0.30] (operator decides)
  - ``manual_homonym``: token jaccard <0.30 (likely different company)
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    from .company_match_verify import _extract_heading_company, _extract_section, _tokenize
    from .company_validator import COMPANY_INFO_DIR, parse_company_file, validate_company
except ImportError:
    from company_match_verify import _extract_heading_company, _extract_section, _tokenize
    from company_validator import COMPANY_INFO_DIR, parse_company_file, validate_company

BASE_DIR = Path(__file__).resolve().parent.parent.parent
QUEUE_PATH = BASE_DIR / "private" / "job_postings" / "unprocessed" / "cosmetic_duplicates_followup.txt"
BUILD_DIR = BASE_DIR / "private" / "build"
REPORT_PATH = BUILD_DIR / "dedup_company_info_report.md"
ACTIONS_PATH = BUILD_DIR / "dedup_actions.sh"
MERGE_DIFF_DIR = BUILD_DIR / "dedup_merge_diffs"

REF_GREP_DIRS = [
    BASE_DIR / "private" / "jd_analysis",
    BASE_DIR / "private" / "job_postings",
    BASE_DIR / "private" / "build",
    BASE_DIR / "private" / "company_info",
]

INTRO_SECTION_NAMES = [
    "회사 소개", "회사소개",
    "사업 영역", "사업영역",
    "회사 개요", "회사개요",
    "기업 정보", "기업정보",
]

JACCARD_HOMONYM_THRESHOLD = 0.10  # below this AND heading mismatch → likely homonym
KEEP_HIGH_THRESHOLD = 50.0        # completeness_score is 0–100 (fields_present / total * 100)
DELETE_LOW_THRESHOLD = 15.0
DELETE_MID_THRESHOLD = 30.0
COMMIT_BATCH_SIZE = 10

GROUP_HEADER_RE = re.compile(r"^##\s+(.+?)\s+\((\d+)\s+files?\)\s*$")
FILE_LINE_RE = re.compile(r"^\s*-\s*(\S+\.md)\s*\((\d+)\s*bytes?\)\s*$")


# ────────────────────────────── data ──────────────────────────────

@dataclass
class Group:
    company: str
    files: list[Path]
    sizes: list[int]


@dataclass
class Classification:
    group: Group
    kind: str
    keep: Path
    deletes: list[Path]
    keep_score: float
    delete_scores: list[float]
    min_jaccard: float
    headings_match: bool
    external_refs: dict[str, list[Path]] = field(default_factory=dict)

    def to_json(self) -> dict:
        return {
            "company": self.group.company,
            "kind": self.kind,
            "keep": self.keep.name,
            "keep_score": round(self.keep_score, 2),
            "deletes": [d.name for d in self.deletes],
            "delete_scores": [round(s, 2) for s in self.delete_scores],
            "min_jaccard": round(self.min_jaccard, 3),
            "headings_match": self.headings_match,
            "external_refs": {
                name: [str(p.relative_to(BASE_DIR)) for p in paths]
                for name, paths in self.external_refs.items()
            },
        }


# ────────────────────────────── parsing ──────────────────────────────

def parse_queue(path: Path) -> list[Group]:
    groups: list[Group] = []
    current: Optional[Group] = None

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        if not line:
            continue
        m = GROUP_HEADER_RE.match(line)
        if m:
            if current and current.files:
                groups.append(current)
            current = Group(company=m.group(1).strip(), files=[], sizes=[])
            continue
        if line.startswith("#"):
            continue
        m = FILE_LINE_RE.match(line)
        if m and current is not None:
            current.files.append(COMPANY_INFO_DIR / m.group(1))
            current.sizes.append(int(m.group(2)))

    if current and current.files:
        groups.append(current)
    return groups


# ────────────────────────────── scoring ──────────────────────────────

def completeness_score(path: Path) -> float:
    try:
        data = parse_company_file(path)
        return validate_company(data, path).completeness_score
    except Exception:
        return 0.0


def file_tokens(path: Path) -> set[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return set()
    intro = _extract_section(text, INTRO_SECTION_NAMES)
    head = _extract_heading_company(text)
    return _tokenize(intro) | _tokenize(head)


def token_jaccard(a: Path, b: Path) -> float:
    ta, tb = file_tokens(a), file_tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def heading_match(a: Path, b: Path) -> bool:
    """True if both files' # headings (paren-stripped, lowercased) align.

    Cosmetic-duplicate files almost always have identical or substring-related
    headings even when their slugs differ ("kurly.md" → "# 컬리 (Kurly)" → "컬리"
    matches "컬리.md" → "# 컬리"). This is the primary same-company signal,
    with token Jaccard as a secondary check for stub files that lack a heading.
    """
    try:
        head_a = _extract_heading_company(a.read_text(encoding="utf-8"))
        head_b = _extract_heading_company(b.read_text(encoding="utf-8"))
    except OSError:
        return False
    if not head_a or not head_b:
        return False
    return head_a == head_b or head_a in head_b or head_b in head_a


# ────────────────────────────── external refs ──────────────────────────────

def find_external_refs(filename: str, exclude: set[Path]) -> list[Path]:
    """Return markdown files in REF_GREP_DIRS that mention `filename`.

    Excludes paths in `exclude` (e.g., the file itself and other group members)
    so a group's internal cross-references don't count as external use.
    """
    existing = [str(d) for d in REF_GREP_DIRS if d.exists()]
    if not existing:
        return []

    try:
        result = subprocess.run(
            ["grep", "-rl", "--include=*.md", filename, *existing],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return []

    refs: list[Path] = []
    for raw in result.stdout.splitlines():
        if not raw.strip():
            continue
        p = Path(raw).resolve()
        if p in exclude:
            continue
        refs.append(p)
    return refs


# ────────────────────────────── classification ──────────────────────────────

def classify_group(group: Group) -> Classification:
    paths = group.files
    scores = [completeness_score(p) for p in paths]
    keep_idx = max(range(len(paths)), key=lambda i: (scores[i], paths[i].stat().st_mtime if paths[i].exists() else 0))
    keep = paths[keep_idx]
    deletes = [p for i, p in enumerate(paths) if i != keep_idx]
    delete_scores = [scores[i] for i in range(len(paths)) if i != keep_idx]

    jaccards = [token_jaccard(keep, d) for d in deletes]
    min_jaccard = min(jaccards) if jaccards else 1.0
    all_headings_match = all(heading_match(keep, d) for d in deletes)

    exclude = set(p.resolve() for p in paths if p.exists())
    external_refs = {d.name: find_external_refs(d.name, exclude) for d in deletes}
    has_refs = any(refs for refs in external_refs.values())

    keep_score = scores[keep_idx]
    max_delete_score = max(delete_scores) if delete_scores else 0.0

    # Homonym only when BOTH signals fail: heading mismatch AND low token overlap.
    # A matching # heading (e.g., both files start "# 컬리") is strong evidence
    # the slugs are aliases for the same company even if one file is a stub.
    if not all_headings_match and min_jaccard < JACCARD_HOMONYM_THRESHOLD:
        kind = "manual_homonym"
    elif keep_score >= KEEP_HIGH_THRESHOLD and max_delete_score <= DELETE_LOW_THRESHOLD and min_jaccard >= 0.30:
        kind = "ref_rewrite" if has_refs else "auto_safe"
    elif keep_score >= DELETE_MID_THRESHOLD and max_delete_score >= DELETE_MID_THRESHOLD:
        kind = "manual_merge"
    elif keep_score >= KEEP_HIGH_THRESHOLD and DELETE_LOW_THRESHOLD < max_delete_score < DELETE_MID_THRESHOLD:
        kind = "manual_review"
    else:
        kind = "manual_review"

    return Classification(
        group=group,
        kind=kind,
        keep=keep,
        deletes=deletes,
        keep_score=keep_score,
        delete_scores=delete_scores,
        min_jaccard=min_jaccard,
        headings_match=all_headings_match,
        external_refs=external_refs,
    )


# ────────────────────────────── emit: report ──────────────────────────────

def emit_report(classifications: list[Classification], path: Path) -> None:
    by_kind: dict[str, list[Classification]] = {}
    for c in classifications:
        by_kind.setdefault(c.kind, []).append(c)

    lines: list[str] = []
    lines.append("# Cosmetic duplicate cleanup classification")
    lines.append("")
    lines.append(f"Total groups: {len(classifications)}")
    lines.append("")
    lines.append("| Category | Count | Description |")
    lines.append("|----------|-------|-------------|")
    descriptions = {
        "auto_safe":      "keep ≥50%, deleted ≤15%, no ext refs — script removes",
        "ref_rewrite":    "auto_safe condition + ≥1 external ref — script rewrites refs then removes",
        "manual_merge":   "both keep and ≥1 deleted file ≥30% — operator merges using emitted diff",
        "manual_review":  "keep ≥50%, deleted ∈ (15%, 30%] — operator decides delete vs merge",
        "manual_homonym": "headings differ AND token jaccard <0.10 — likely different company",
    }
    for kind in ["auto_safe", "ref_rewrite", "manual_merge", "manual_review", "manual_homonym"]:
        lines.append(f"| {kind} | {len(by_kind.get(kind, []))} | {descriptions[kind]} |")
    lines.append("")

    for kind in ["auto_safe", "ref_rewrite", "manual_merge", "manual_review", "manual_homonym"]:
        bucket = by_kind.get(kind, [])
        if not bucket:
            continue
        lines.append(f"## {kind} ({len(bucket)})")
        lines.append("")
        lines.append("| Company | Keep (score) | Delete (score) | Jaccard | Heading match | Ext refs |")
        lines.append("|---------|--------------|----------------|---------|---------------|----------|")
        for c in sorted(bucket, key=lambda x: x.group.company):
            deleted_summary = ", ".join(
                f"{d.name} ({s:.0f}%)" for d, s in zip(c.deletes, c.delete_scores)
            )
            ref_count = sum(len(r) for r in c.external_refs.values())
            lines.append(
                f"| {c.group.company} | {c.keep.name} ({c.keep_score:.0f}%) | "
                f"{deleted_summary} | {c.min_jaccard:.2f} | "
                f"{'yes' if c.headings_match else 'no'} | {ref_count} |"
            )
        lines.append("")

    lines.append("## Operator workflow")
    lines.append("")
    lines.append("1. Review this report.")
    lines.append("2. Inspect `dedup_actions.sh` (auto_safe + ref_rewrite). Run when satisfied.")
    lines.append("3. Apply diffs in `dedup_merge_diffs/` for `manual_merge` groups.")
    lines.append("4. Decide each `manual_review` group case-by-case.")
    lines.append("5. Move `manual_homonym` cases to the homonym follow-up queue.")
    lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


# ────────────────────────────── emit: actions ──────────────────────────────

_ACTIONS_HEADER = """\
#!/usr/bin/env bash
# Generated by templates/jd/dedup_company_info.py
# Review every block before running. Each batch is a self-contained git commit.
set -euo pipefail
cd "$(dirname "$0")/../.."
"""

_REWRITE_PYTHON = textwrap.dedent("""\
    python3 - <<'PYEOF'
    import pathlib, re

    rewrites = {rewrites!r}
    scan_dirs = [pathlib.Path(d) for d in {scan_dirs!r}]
    for d in scan_dirs:
        if not d.exists():
            continue
        for p in d.rglob("*.md"):
            try:
                s = p.read_text(encoding="utf-8")
            except OSError:
                continue
            new_s = s
            for old, new in rewrites.items():
                # (?<!\\w) / (?!\\w): unicode word boundary; safer than \\b for hangul.
                new_s = re.sub(rf"(?<!\\w){{re.escape(old)}}(?!\\w)", new, new_s)
            if new_s != s:
                p.write_text(new_s, encoding="utf-8")
                print(f"rewrote refs in {{p}}")
    PYEOF
""")


def emit_actions(classifications: list[Classification], path: Path) -> None:
    auto = [c for c in classifications if c.kind in ("auto_safe", "ref_rewrite")]
    if not auto:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_ACTIONS_HEADER + '\necho "no auto-safe groups to process"\n', encoding="utf-8")
        return

    lines = [_ACTIONS_HEADER]

    rewrite_classes = [c for c in classifications if c.kind == "ref_rewrite"]
    if rewrite_classes:
        rewrites: dict[str, str] = {}
        for c in rewrite_classes:
            for d in c.deletes:
                rewrites[d.name] = c.keep.name
        scan_dirs = [str(d.relative_to(BASE_DIR)) for d in REF_GREP_DIRS]
        lines.append("# ── Step A: rewrite external references ──────────────────────────")
        lines.append(_REWRITE_PYTHON.format(rewrites=rewrites, scan_dirs=scan_dirs))
        lines.append("")
        git_add_dirs = [str(d.relative_to(BASE_DIR)) for d in REF_GREP_DIRS if d.exists()]
        if git_add_dirs:
            scan_args = " ".join(f"'{d}'" for d in git_add_dirs)
            lines.append(f"git add -u -- {scan_args}")
        lines.append('if ! git diff --quiet --cached; then')
        lines.append('    git commit -m "chore(company_info): rewrite refs from cosmetic-duplicate slugs"')
        lines.append('else')
        lines.append('    echo "no ref rewrites needed"')
        lines.append('fi')
        lines.append("")

    lines.append("# ── Step B: remove duplicate files in 10-group batches ────────────")
    for batch_idx, start in enumerate(range(0, len(auto), COMMIT_BATCH_SIZE), start=1):
        batch = auto[start:start + COMMIT_BATCH_SIZE]
        lines.append(f"# batch {batch_idx} ({len(batch)} groups)")
        for c in batch:
            for d in c.deletes:
                rel = d.relative_to(BASE_DIR)
                lines.append(f"git rm '{rel}'")
        subject = f"chore(company_info): dedup cosmetic duplicates batch {batch_idx} ({len(batch)} groups)"
        body = "Removed stub variants in favor of richer counterparts. See dedup_company_info_report.md."
        lines.append(f"git commit -m {json.dumps(subject)} -m {json.dumps(body)}")
        lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    path.chmod(0o755)


# ────────────────────────────── emit: merge diffs ──────────────────────────────

def emit_merge_diffs(classifications: list[Classification], out_dir: Path) -> None:
    import difflib

    out_dir.mkdir(parents=True, exist_ok=True)
    for c in classifications:
        if c.kind != "manual_merge":
            continue
        keep_text = c.keep.read_text(encoding="utf-8").splitlines(keepends=True)
        for d in c.deletes:
            d_text = d.read_text(encoding="utf-8").splitlines(keepends=True)
            diff = list(difflib.unified_diff(
                keep_text, d_text,
                fromfile=str(c.keep.relative_to(BASE_DIR)),
                tofile=str(d.relative_to(BASE_DIR)),
            ))
            slug = re.sub(r"[^A-Za-z0-9가-힣_-]+", "-", c.group.company).strip("-") or "group"
            target = out_dir / f"{slug}__{d.stem}.diff"
            target.write_text("".join(diff), encoding="utf-8")


# ────────────────────────────── cli ──────────────────────────────

def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    p.add_argument("--queue", type=Path, default=QUEUE_PATH, help="Path to cosmetic_duplicates_followup.txt")
    p.add_argument("--classify", action="store_true", help="Write report (default)")
    p.add_argument("--emit-actions", action="store_true", help="Also write shell script + merge diffs")
    p.add_argument("--dry-run", action="store_true", help="Print JSON to stdout, write nothing")
    args = p.parse_args(argv)

    if not args.queue.exists():
        print(f"queue not found: {args.queue}", file=sys.stderr)
        return 2

    groups = parse_queue(args.queue)
    if not groups:
        print(f"no groups parsed from {args.queue}", file=sys.stderr)
        return 1

    print(f"parsed {len(groups)} groups from {args.queue.name}", file=sys.stderr)
    classifications = [classify_group(g) for g in groups]

    if args.dry_run:
        json.dump(
            {
                "total": len(classifications),
                "by_kind": {
                    k: sum(1 for c in classifications if c.kind == k)
                    for k in ["auto_safe", "ref_rewrite", "manual_merge", "manual_review", "manual_homonym"]
                },
                "groups": [c.to_json() for c in classifications],
            },
            sys.stdout,
            ensure_ascii=False,
            indent=2,
        )
        print()
        return 0

    emit_report(classifications, REPORT_PATH)
    print(f"wrote {REPORT_PATH.relative_to(BASE_DIR)}", file=sys.stderr)

    if args.emit_actions:
        emit_actions(classifications, ACTIONS_PATH)
        print(f"wrote {ACTIONS_PATH.relative_to(BASE_DIR)}", file=sys.stderr)
        emit_merge_diffs(classifications, MERGE_DIFF_DIR)
        print(f"wrote diffs under {MERGE_DIFF_DIR.relative_to(BASE_DIR)}/", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
