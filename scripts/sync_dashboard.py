#!/usr/bin/env python3
"""
Bidirectional sync between job_postings/ and Obsidian dashboard.

Usage:
    python sync_dashboard.py --to-obsidian    # Generate dashboard from job_postings
    python sync_dashboard.py --from-obsidian  # Update job_postings from dashboard changes
    python sync_dashboard.py --sync           # Full bidirectional sync (obsidian wins on conflict)
"""

import argparse
import difflib
import logging
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml

# Logging setup
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Paths
RESUME_ROOT = Path(__file__).parent.parent
JOB_POSTINGS = RESUME_ROOT / "job_postings"
SYNC_CONFIG_PATH = Path(__file__).parent / "sync_config.yaml"


def load_sync_config() -> dict:
    if not SYNC_CONFIG_PATH.exists():
        return {}
    with open(SYNC_CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _resolve_dashboard_path() -> Optional[Path]:
    env = os.environ.get("OBSIDIAN_DASHBOARD_PATH")
    if env:
        return Path(env)
    config = load_sync_config()
    path = config.get("dashboard_path")
    if path:
        return Path(path).expanduser()
    return None


OBSIDIAN_DASHBOARD = _resolve_dashboard_path()

# Status -> Directory mapping
STATUS_DIRS = {
    "applied": "applied",
    "지원": "applied",
    "서류통과": "applied",
    "서류 통과": "applied",
    "면접": "applied",
    "recommend": "conditional",
    "hold": "conditional", 
    "보류": "conditional",
    "조건부": "conditional",
    "조건부(상)": "conditional",
    "조건부(하)": "conditional",
    "우선": "conditional",
    "킵": "conditional",
    "pass": "pass",
    "패스": "pass",
    "rejected": "rejected",
    "서류 탈락": "rejected",
    "서류탈락": "rejected",
    "탈락": "rejected",
}

# Reverse mapping for display
DIR_TO_STATUS = {
    "applied": "지원",
    "conditional": "검토중",
    "pass": "패스",
    "rejected": "서류 탈락",
}


def parse_frontmatter(content: str, file_path: Optional[Path] = None) -> tuple[dict, str]:
    """Parse YAML frontmatter from markdown."""
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            try:
                fm = yaml.safe_load(parts[1]) or {}
                return fm, parts[2].strip()
            except yaml.YAMLError as e:
                location = f" in {file_path}" if file_path else ""
                logger.warning(f"YAML parsing error{location}: {e}")
    return {}, content


def update_frontmatter(content: str, updates: dict) -> str:
    """Update YAML frontmatter in markdown."""
    fm, body = parse_frontmatter(content)
    fm.update(updates)
    new_fm = yaml.dump(fm, allow_unicode=True, default_flow_style=False).strip()
    return f"---\n{new_fm}\n---\n{body}"


def extract_job_id_from_filename(filename: str) -> Optional[str]:
    """Extract job ID from filename like '290750-linaone-backend-engineer.md'."""
    match = re.match(r'^(\d+)-', filename)
    if match:
        return match.group(1)
    # Handle filenames like 'kdl-backend-engineer.md' (no ID)
    return None


def extract_url_from_content(content: str) -> Optional[str]:
    """Extract URL from markdown content."""
    # Check frontmatter first
    fm, _ = parse_frontmatter(content)
    if "url" in fm:
        return fm["url"]
    
    # Check table format
    url_patterns = [
        r'\|\s*(?:원본 URL|URL)\s*\|\s*(https?://[^\s|]+)',
        r'(https://(?:www\.)?wanted\.co\.kr/wd/\d+)',
        r'(https://career\.rememberapp\.co\.kr/job/posting/\d+)',
        r'(https://[^\s)]+)',
    ]
    for pattern in url_patterns:
        match = re.search(pattern, content)
        if match:
            return match.group(1).strip()
    return None


def extract_company_from_content(content: str) -> Optional[str]:
    """Extract company name from markdown content."""
    fm, body = parse_frontmatter(content)
    if "company" in fm:
        return fm["company"]
    
    # Check table format
    match = re.search(r'\|\s*회사명\s*\|\s*([^|]+)', body)
    if match:
        return match.group(1).strip()

    # Bold list: - **회사명**: ... or - **회사**: ...
    match = re.search(r'-\s*\*\*회사(?:명)?\*\*:\s*(.+)', body)
    if match:
        return match.group(1).strip()

    # Plain text: 회사명: ...
    match = re.search(r'^회사명:\s*(.+)', body, re.MULTILINE)
    if match:
        return match.group(1).strip()

    # Check title format like "# 회사명 - 포지션"
    match = re.search(r'^#\s*(?:\([^)]+\))?\s*([^-]+)', body, re.MULTILINE)
    if match:
        return match.group(1).strip()
    
    return None


def extract_position_from_content(content: str) -> Optional[str]:
    """Extract position from markdown content."""
    fm, body = parse_frontmatter(content)
    if "position" in fm:
        return fm["position"]
    
    # Check table format
    match = re.search(r'\|\s*포지션\s*\|\s*([^|]+)', body)
    if match:
        return match.group(1).strip()

    # Bold list: - **포지션**: ...
    match = re.search(r'-\s*\*\*포지션\*\*:\s*(.+)', body)
    if match:
        return match.group(1).strip()

    # Plain text: 포지션: ...
    match = re.search(r'^포지션:\s*(.+)', body, re.MULTILINE)
    if match:
        return match.group(1).strip()

    return None


def scan_job_postings() -> dict:
    """Scan all job posting files and return structured data."""
    jobs = {}

    # Include conditional subdirectories (high, hold, middle, low)
    scan_dirs = [
        "applied",
        "conditional",
        "conditional/high",
        "conditional/hold",
        "conditional/middle",
        "conditional/low",
        "pass",
        "rejected",
    ]

    for status_dir in scan_dirs:
        dir_path = JOB_POSTINGS / status_dir
        if not dir_path.exists():
            continue

        for file in dir_path.glob("*.md"):
            content = file.read_text(encoding="utf-8")
            fm, body = parse_frontmatter(content, file)
            
            job_id = extract_job_id_from_filename(file.name)
            url = extract_url_from_content(content)
            company = extract_company_from_content(content)
            position = extract_position_from_content(content)
            
            # Use filename as unique key if no job_id
            key = job_id or file.stem
            
            jobs[key] = {
                "file": file,
                "filename": file.name,
                "status_dir": status_dir,
                "status": fm.get("status", DIR_TO_STATUS.get(status_dir, status_dir)),
                "status_updated": fm.get("status_updated"),
                "url": url,
                "company": company,
                "position": position,
                "reason": fm.get("reason", ""),
            }
    
    return jobs


def parse_dashboard_table(content: str) -> list[dict]:
    """Parse job entries from Obsidian dashboard tables."""
    entries = []
    
    for line in content.split('\n'):
        # Skip non-table lines
        if not line.strip().startswith('|'):
            continue
        
        # Split by | and clean up
        cells = [c.strip() for c in line.split('|')]
        # Remove first and last empty strings from split (but keep middle empty cells!)
        if cells and cells[0] == '':
            cells = cells[1:]
        if cells and cells[-1] == '':
            cells = cells[:-1]
        
        # Need at least 5 columns: ID/플랫폼, 회사, 포지션, 최종 판단, 핵심 사유
        if len(cells) < 4:
            continue
        
        # Skip header rows
        if cells[0].startswith('**') and 'ID' in cells[0]:
            continue
        if cells[0].startswith('---') or cells[0] == '-':
            continue
        
        id_cell = cells[0]
        company_cell = cells[1] if len(cells) > 1 else ""
        position_cell = cells[2] if len(cells) > 2 else ""
        status_cell = cells[3] if len(cells) > 3 else ""
        reason_cell = cells[4] if len(cells) > 4 else ""
        
        # Extract job ID and URL from id_cell
        # Format: [ID](url) / 플랫폼  or  ID / 플랫폼
        job_id = None
        url = None
        
        id_match = re.search(r'\[(\d+)\]\(([^)]+)\)', id_cell)
        if id_match:
            job_id = id_match.group(1)
            url = id_match.group(2)
        else:
            # Try plain ID
            id_match = re.match(r'^(\d+)', id_cell.strip())
            if id_match:
                job_id = id_match.group(1)
        
        # Clean up company (remove markdown links, bold)
        company = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', company_cell)
        company = company.replace('**', '').strip()
        
        # Clean up status
        status = status_cell.replace('**', '').strip()
        # Get LAST status if there's an arrow (e.g., "지원 -> 서류 탈락" → "서류 탈락")
        status_clean = status.split('->')[-1].strip() if '->' in status else status
        
        # Skip entries with empty or invalid status
        if not status_clean or status_clean == '-':
            continue
        
        if job_id or company:
            entries.append({
                "job_id": job_id,
                "url": url,
                "company": company,
                "position": position_cell.strip(),
                "status": status_clean,
                "full_status": status,
                "reason": reason_cell.strip(),
            })
    
    return entries


def get_target_dir(status: str) -> str:
    """Get target directory for a given status."""
    status_lower = status.lower().strip()
    
    # Check exact match first
    if status_lower in STATUS_DIRS:
        return STATUS_DIRS[status_lower]
    
    # Check if status contains keywords
    if "지원" in status or "applied" in status_lower:
        return "applied"
    if "통과" in status or "면접" in status:
        return "applied"
    if "탈락" in status or "rejected" in status_lower:
        return "rejected"
    if "패스" in status or "pass" in status_lower:
        return "pass"
    
    # Default to conditional
    return "conditional"


def generate_dashboard_tables(jobs: dict) -> tuple[str, str]:
    """Generate markdown tables for dashboard from job data."""
    applied = []
    reviewing = []
    
    for key, job in sorted(jobs.items(), key=lambda x: str(x[1].get("status_updated") or ""), reverse=True):
        url = job.get("url") or ""
        job_id = extract_job_id_from_filename(job["filename"]) or ""
        company = job.get("company") or "Unknown"
        position = job.get("position") or "Unknown"
        status = job.get("status") or ""
        reason = job.get("reason") or ""
        
        # Determine platform from URL
        if url and "wanted.co.kr" in url:
            platform = "원티드"
        elif url and "rememberapp" in url:
            platform = "리멤버"
        elif url and "offercent" in url:
            platform = "오퍼센트"
        elif url and ("greetinghr" in url or "greeting" in url):
            platform = "그리팅"
        else:
            platform = "-"
        
        if job_id and url:
            id_cell = f"[{job_id}]({url}) / {platform}"
        elif url:
            id_cell = f"[공고]({url}) / {platform}"
        else:
            id_cell = f"- / {platform}"
        
        row = f"| {id_cell} | {company} | {position} | {status} | {reason} |"
        
        if job["status_dir"] == "applied":
            applied.append(row)
        else:
            reviewing.append(row)
    
    applied_table = "| **ID** / 플랫폼 | **회사** | **포지션** | **최종 판단** | **핵심 사유 요약** |\n"
    applied_table += "| --- | --- | --- | --- | --- |\n"
    applied_table += "\n".join(applied) if applied else "| - | - | - | - | - |"
    
    reviewing_table = "| **ID** / 플랫폼 | **회사** | **포지션** | **최종 판단** | **핵심 사유 요약** |\n"
    reviewing_table += "| --- | --- | --- | --- | --- |\n"
    reviewing_table += "\n".join(reviewing) if reviewing else "| - | - | - | - | - |"
    
    return applied_table, reviewing_table


def replace_section_content(
    content: str,
    start_header: str,
    end_header: str,
    new_body: str,
) -> str:
    """Replace content between two markdown headers, preserving both headers."""
    pattern = re.compile(
        re.escape(start_header) + r"\n" + r"(.*?)" + r"\n?" + re.escape(end_header),
        re.DOTALL,
    )
    replacement = start_header + "\n" + new_body + "\n" + end_header
    result, count = pattern.subn(replacement, content)
    if count == 0:
        logger.warning(f"Section not found: {start_header!r} ... {end_header!r}")
    return result


def update_unknown_cells(raw_line: str, new_entry: dict) -> str:
    """Replace Unknown cells in an existing table row with actual values from new_entry.

    Only updates company (cells[2]) and position (cells[3]) if they are "Unknown".
    Other cells (status, reason, links) are preserved as-is.
    """
    cells = raw_line.split('|')
    # Table row after split: ['', ' ID/플랫폼 ', ' 회사 ', ' 포지션 ', ' 상태 ', ' 사유 ', '']
    if len(cells) < 6:
        return raw_line

    company = cells[2].strip()
    position = cells[3].strip()
    updated = False

    new_company = new_entry.get("company")
    new_position = new_entry.get("position")

    if company == "Unknown" and new_company and new_company != "Unknown":
        cells[2] = f" {new_company} "
        updated = True
    if position == "Unknown" and new_position and new_position != "Unknown":
        cells[3] = f" {new_position} "
        updated = True

    return '|'.join(cells) if updated else raw_line


def merge_table_rows(existing_content: str, new_table: str) -> tuple[str, int, int, int]:
    """Merge new table rows into existing section content.

    Returns (merged_table, kept_count, added_count, updated_count).
    Existing rows are preserved (manual edits kept). Only new IDs are appended.
    Unknown company/position cells in existing rows are selectively updated.
    """
    existing_entries = parse_dashboard_table(existing_content)
    new_entries = parse_dashboard_table(new_table)

    existing_ids = {e["job_id"] for e in existing_entries if e.get("job_id")}
    existing_raw_lines = set()
    for line in existing_content.split("\n"):
        if line.strip().startswith("|") and not line.strip().startswith("| **") and not line.strip().startswith("| ---"):
            existing_raw_lines.add(line.strip())

    new_rows_to_add = []
    for entry in new_entries:
        job_id = entry.get("job_id")
        if job_id and job_id in existing_ids:
            continue
        matching_line = None
        for line in new_table.split("\n"):
            if job_id and f"[{job_id}]" in line:
                matching_line = line
                break
            elif not job_id and entry.get("company") and entry["company"] in line:
                matching_line = line
                break
        if matching_line and matching_line.strip() not in existing_raw_lines:
            new_rows_to_add.append(matching_line)

    new_entries_by_id = {}
    for entry in new_entries:
        jid = entry.get("job_id")
        if jid:
            new_entries_by_id[jid] = entry

    existing_lines = existing_content.rstrip("\n").split("\n")
    table_header_lines = []
    table_body_lines = []
    for line in existing_lines:
        stripped = line.strip()
        if stripped.startswith("| **") or stripped.startswith("| ---"):
            table_header_lines.append(line)
        elif stripped.startswith("|"):
            table_body_lines.append(line)

    updated_body_lines = []
    updated_count = 0
    for line in table_body_lines:
        id_match = re.search(r'\[(\d+)\]', line)
        if id_match:
            jid = id_match.group(1)
            if jid in new_entries_by_id:
                new_line = update_unknown_cells(line, new_entries_by_id[jid])
                if new_line != line:
                    updated_count += 1
                updated_body_lines.append(new_line)
                continue
        updated_body_lines.append(line)

    new_table_lines = new_table.strip().split("\n")
    header_lines = [l for l in new_table_lines if l.strip().startswith("| **") or l.strip().startswith("| ---")]

    kept_count = len(updated_body_lines)
    added_count = len(new_rows_to_add)

    merged = "\n".join(header_lines + updated_body_lines + new_rows_to_add)
    return merged, kept_count, added_count, updated_count


def to_obsidian(dry_run: bool = False, force: bool = False, dashboard_path: Optional[Path] = None):
    """Generate Obsidian dashboard from job_postings."""
    print("📤 Syncing: resume → Obsidian")
    
    jobs = scan_job_postings()
    print(f"   Found {len(jobs)} job postings")
    
    applied_table, reviewing_table = generate_dashboard_tables(jobs)
    
    # Read current dashboard
    if not dashboard_path.exists():
        print(f"   ❌ Dashboard not found: {dashboard_path}")
        return
    
    content = dashboard_path.read_text(encoding="utf-8")

    start_applied = "## 📊 지원 현황 요약"
    start_review = "## 검토 현황 요약"
    end_review = "## 🧠 판단 기준"

    if start_applied not in content or start_review not in content or end_review not in content:
        print("   ❌ Dashboard section headers not found. Expected:")
        print(f"      {start_applied}")
        print(f"      {start_review}")
        print(f"      {end_review}")
        return

    applied_section_start = content.index(start_applied)
    applied_section_end = content.index(start_review)
    existing_applied_content = content[applied_section_start + len(start_applied):applied_section_end].strip()

    review_section_start = content.index(start_review)
    review_section_end = content.index(end_review)
    existing_review_content = content[review_section_start + len(start_review):review_section_end].strip()

    if force:
        final_applied = applied_table
        final_review = reviewing_table
        applied_kept, applied_added, applied_updated = 0, len(parse_dashboard_table(applied_table)), 0
        review_kept, review_added, review_updated = 0, len(parse_dashboard_table(reviewing_table)), 0
        print("   ⚡ Force mode: overwriting all rows")
    else:
        final_applied, applied_kept, applied_added, applied_updated = merge_table_rows(existing_applied_content, applied_table)
        final_review, review_kept, review_added, review_updated = merge_table_rows(existing_review_content, reviewing_table)

    new_content = replace_section_content(content, start_applied, start_review, final_applied + "\n")
    new_content = replace_section_content(new_content, start_review, end_review, final_review + "\n")

    if new_content == content:
        print("   ✅ No changes needed")
        return

    if dry_run:
        diff = difflib.unified_diff(
            content.splitlines(keepends=False),
            new_content.splitlines(keepends=False),
            fromfile="dashboard (current)",
            tofile="dashboard (updated)",
            lineterm="",
        )
        diff_text = "\n".join(diff)
        if diff_text:
            print(f"\n{'='*60}")
            print(diff_text)
            print(f"{'='*60}")
        print(f"\n   📊 지원 현황: 기존 유지 {applied_kept}건 / 갱신 {applied_updated}건 / 추가 {applied_added}건")
        print(f"   📋 검토 현황: 기존 유지 {review_kept}건 / 갱신 {review_updated}건 / 추가 {review_added}건")
        print("   (dry-run mode, no changes applied)")
        return

    backup_path = dashboard_path.with_suffix(dashboard_path.suffix + ".bak")
    shutil.copy2(dashboard_path, backup_path)
    logger.info(f"Backup created: {backup_path}")

    dashboard_path.write_text(new_content, encoding="utf-8")

    total_applied = applied_kept + applied_added
    total_review = review_kept + review_added
    print(f"   📊 지원 현황: 기존 유지 {applied_kept}건 / 갱신 {applied_updated}건 / 추가 {applied_added}건 / 총 {total_applied}건")
    print(f"   📋 검토 현황: 기존 유지 {review_kept}건 / 갱신 {review_updated}건 / 추가 {review_added}건 / 총 {total_review}건")
    print(f"   💾 Backup: {backup_path}")
    print("   ✅ Dashboard updated")


def from_obsidian(dry_run: bool = False, dashboard_path: Optional[Path] = None):
    """Update job_postings from Obsidian dashboard changes."""
    print("📥 Syncing: Obsidian → resume")
    
    if not dashboard_path.exists():
        print(f"   ❌ Dashboard not found: {dashboard_path}")
        return
    
    content = dashboard_path.read_text(encoding="utf-8")
    entries = parse_dashboard_table(content)
    print(f"   Found {len(entries)} entries in dashboard")
    
    jobs = scan_job_postings()
    
    # Deduplicate entries by job_id, keeping the last occurrence
    seen_ids = {}
    for entry in entries:
        job_id = entry.get("job_id")
        if job_id:
            seen_ids[job_id] = entry
    entries = list(seen_ids.values())
    print(f"   After dedup: {len(entries)} unique entries")
    
    changes = []
    for entry in entries:
        job_id = entry.get("job_id")
        if not job_id or job_id not in jobs:
            continue
        
        job = jobs[job_id]
        dashboard_status = entry.get("status", "")
        target_dir = get_target_dir(dashboard_status)
        
        if target_dir != job["status_dir"]:
            changes.append({
                "job_id": job_id,
                "company": entry.get("company"),
                "from_dir": job["status_dir"],
                "to_dir": target_dir,
                "status": dashboard_status,
                "file": job["file"],
            })
    
    if not changes:
        print("   ✅ No changes detected")
        return
    
    print(f"\n📝 Changes to apply:")
    for c in changes:
        print(f"   {c['job_id']} ({c['company']}): {c['from_dir']} → {c['to_dir']} (status: {c['status']})")
    
    if dry_run:
        print("\n   (dry-run mode, no changes applied)")
        return
    
    for c in changes:
        src = c["file"]
        # For conditional status, default to conditional/hold/
        to_dir = c["to_dir"]
        if to_dir == "conditional":
            to_dir = "conditional/hold"
        dst_dir = JOB_POSTINGS / to_dir
        dst = dst_dir / src.name

        # Safety check: prevent overwrite
        if dst.exists() and dst != src:
            logger.warning(f"Destination exists, skipping: {dst}")
            print(f"   ⚠️  Skipped (exists): {src.name} → {dst}")
            continue

        try:
            # Update frontmatter
            content = src.read_text(encoding="utf-8")
            content = update_frontmatter(content, {
                "status": c["status"],
                "status_updated": datetime.now().strftime("%Y-%m-%d"),
            })

            # Move file safely
            dst_dir.mkdir(parents=True, exist_ok=True)
            dst.write_text(content, encoding="utf-8")

            # Only delete source after successful write
            if src != dst:
                src.unlink()
            print(f"   ✅ Moved: {src.name} → {to_dir}/")
        except Exception as e:
            logger.error(f"Failed to move {src.name}: {e}")
            print(f"   ❌ Failed: {src.name} ({e})")
            # Cleanup partial write if needed
            if dst.exists() and not src.exists():
                logger.warning(f"Partial write detected, attempting recovery")
            continue


def main():
    parser = argparse.ArgumentParser(description="Sync job dashboard between resume and Obsidian")
    parser.add_argument("--to-obsidian", action="store_true", help="Generate dashboard from job_postings")
    parser.add_argument("--from-obsidian", action="store_true", help="Update job_postings from dashboard")
    parser.add_argument("--sync", action="store_true", help="Full bidirectional sync")
    parser.add_argument("--dry-run", "-n", action="store_true", help="Show what would be done")
    parser.add_argument("--force", action="store_true", help="Overwrite dashboard tables instead of merging")
    parser.add_argument("--dashboard", "-d", type=Path, default=None, help="Path to dashboard file")

    args = parser.parse_args()
    dashboard_path = args.dashboard or OBSIDIAN_DASHBOARD
    if dashboard_path is None:
        print("❌ Dashboard path not configured.")
        print("   Set OBSIDIAN_DASHBOARD_PATH env var, or create scripts/sync_config.yaml,")
        print("   or use --dashboard <path>")
        return

    if args.sync:
        from_obsidian(dry_run=args.dry_run, dashboard_path=dashboard_path)
        print()
        to_obsidian(dry_run=args.dry_run, force=args.force, dashboard_path=dashboard_path)
    elif args.to_obsidian:
        to_obsidian(dry_run=args.dry_run, force=args.force, dashboard_path=dashboard_path)
    elif args.from_obsidian:
        from_obsidian(dry_run=args.dry_run, dashboard_path=dashboard_path)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
