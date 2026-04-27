"""기존 high/hold/pass 풀에서 직전 채용 이력 매칭 검사 + 자동 분류.

룰: 같은 회사에 직전 6개월 내 지원·탈락 이력 → 자동 ❌ rejected/

사용:
  python3 templates/jd/backfill_prior_applications.py --dry-run
  python3 templates/jd/backfill_prior_applications.py
"""

from __future__ import annotations

import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

try:
    from naming import slugify_company
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from naming import slugify_company

JOB_POSTINGS = Path("private/job_postings")
SUMMARY = Path("private/jd_analysis/screening/SUMMARY.md")
PRIOR_FOLDERS = ("applied", "rejected", "submitted")
TARGET_FOLDERS = ("conditional/high", "conditional/hold", "pass")
PRIOR_DAYS = 180


def extract_company_slug(jd_path: Path) -> str | None:
    try:
        text = jd_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for pat in (
        r"\|\s*회사명?\s*\|\s*([^|\n]+?)\s*\|",
        r"\*\*회사\*\*\s*:\s*([^\n]+)",
        r"^회사명?\s*:\s*([^\n]+)",
    ):
        m = re.search(pat, text, re.MULTILINE)
        if m:
            raw = m.group(1).split("/")[0].split("(")[0].strip()
            slug = slugify_company(raw, max_len=30, fallback="")
            if slug:
                return slug
    parts = jd_path.stem.split("-", 2)
    if len(parts) > 1:
        return slugify_company(parts[1], max_len=30, fallback="")
    return None


def collect_priors(cutoff_ts: float) -> list[tuple[str, Path, float]]:
    priors = []
    for folder in PRIOR_FOLDERS:
        d = JOB_POSTINGS / folder
        if not d.exists():
            continue
        for jd in d.glob("*.md"):
            mt = jd.stat().st_mtime
            if mt < cutoff_ts:
                continue
            slug = extract_company_slug(jd)
            if slug and len(slug) >= 2:
                priors.append((slug, jd, mt))
    return priors


def find_match(target_slug: str, priors: list) -> tuple[Path, float] | None:
    for slug, path, mt in priors:
        if target_slug == slug:
            return path, mt
        if len(target_slug) >= 4 and len(slug) >= 4:
            if target_slug in slug or slug in target_slug:
                return path, mt
    return None


def main(dry_run: bool) -> None:
    cutoff = datetime.now().timestamp() - PRIOR_DAYS * 86400
    priors = collect_priors(cutoff)
    print(f"직전 6개월 이력 (applied/rejected/submitted): {len(priors)}건")
    print()

    today = datetime.now().strftime("%Y-%m-%d")
    matches = []

    for folder in TARGET_FOLDERS:
        d = JOB_POSTINGS / folder
        if not d.exists():
            continue
        for jd in d.glob("*.md"):
            target_slug = extract_company_slug(jd)
            if not target_slug:
                continue
            match = find_match(target_slug, priors)
            if match:
                prior_path, prior_mt = match
                # 본인 자신은 건너뜀
                if prior_path.name == jd.name:
                    continue
                matches.append({
                    "jd": jd,
                    "from": folder,
                    "company_slug": target_slug,
                    "prior": prior_path,
                    "prior_date": datetime.fromtimestamp(prior_mt).strftime("%Y-%m-%d"),
                })

    print(f"=== 직전 이력 매칭: {len(matches)}건 ===\n")
    for m in matches:
        print(f"  📁 {m['from']}/{m['jd'].name}")
        print(f"      회사 슬러그: {m['company_slug']}")
        print(f"      직전 매칭: {m['prior'].name} ({m['prior_date']}, {m['prior'].parent.name})")
        print()

    if dry_run:
        print("(--dry-run: 이동 안 함)")
        return

    summary_rows = []
    rejected_dir = JOB_POSTINGS / "rejected"
    rejected_dir.mkdir(parents=True, exist_ok=True)

    for m in matches:
        src = m["jd"]
        dst = rejected_dir / src.name
        if dst.exists():
            print(f"  ⚠️ rejected/에 이미 존재: {src.name}")
            continue
        shutil.move(str(src), str(dst))
        text = dst.read_text(encoding="utf-8", errors="replace")
        company_m = re.search(r"\|\s*회사명?\s*\|\s*([^|\n]+)\|", text)
        position_m = re.search(r"\|\s*포지션\s*\|\s*([^|\n]+)\|", text)
        job_id = src.stem.split("-", 1)[0]
        if job_id == "remember":
            job_id = src.stem.split("-", 2)[1]
        company = company_m.group(1).strip() if company_m else m["company_slug"]
        position = position_m.group(1).strip() if position_m else src.stem
        summary_rows.append(
            f"| {today} | {job_id} | {company} | {position} | 지원 비추천 | `rejected` "
            f"<br/>재분류({today}, 직전 6개월 동일 회사 [{m['prior'].name} {m['prior_date']}] 이력): "
            f"{m['from']}→rejected |\n"
        )
        print(f"  ✅ {src.name} → rejected/")

    if summary_rows:
        with open(SUMMARY, "a", encoding="utf-8") as f:
            f.writelines(summary_rows)
        print(f"\nSUMMARY.md에 {len(summary_rows)}건 추가")


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    main(dry_run=dry)
