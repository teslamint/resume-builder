# Repository Guidelines

## Project Structure & Module Organization

- `profile/`: core profile sections (`contact.md`, `summary-*.md`, `skills-*.md`, `education.md`).
- `companies/<company>/`: per-company content with `profile.md`, plus `projects/`, `achievements/`, and sometimes `portfolios/`.
- `templates/`: build tooling and styling (`resume_builder.py`, `generate_notes.py`, `layout.md`, `style.css`, `style-short.css`).
- `overrides/<target>/`: target-specific file overrides mirroring `profile/` and `companies/` structure.
- `build/`: generated artifacts (`resume-*.md`, `resume-*.html`, `resume-*.pdf`, `resume-*-remember.txt`, `resume-*-wanted.txt`).

## Build, Test, and Development Commands

### build.sh Usage
```
./build.sh <public|job|example> [full|short|wanted|base|all] [--target <name>] [--clean]
```

**Common builds:**
- `./build.sh example all`: build demo resume with example data (for testing).
- `./build.sh public all`: build full + short + wanted public resume.
- `./build.sh job all`: build all job resume variants.
- `./build.sh public full`: build full public resume only (MD/HTML/PDF).
- `./build.sh job short`: build 1-page JD-focused resume only.
- `./build.sh public wanted`: build Wanted site plain text format.
- `./build.sh job base`: generate immutable base resume for diff tracking.

**Target-specific builds:**
- `./build.sh job full --target <name>`: build with override files from `overrides/<name>/`, outputs to `build/resume-job-<name>.*`.
- `./build.sh job full --clean`: overwrite notes instead of appending.

**Build pipeline (per format):**
1. `resume_builder.py` → `.md` (Markdown)
2. `resume_builder.py --format pdf` → `-pdf.md` (PDF layout with style includes)
3. `pandoc` → `.html` (with CSS from `templates/themes/default/` or override)
4. `weasyprint` → `.pdf`
5. `pandoc -t plain` → `-remember.txt` (plain text for Remember app)
6. `generate_notes.py` → `resume-job-notes.md` (diff vs base, job variant only)

**Python CLI direct usage:**
- `python3 templates/resume_builder.py --list`: list available company keys.
- `python3 templates/resume_builder.py --variant public > resume-public.md`: generate Markdown only.
- `python3 templates/resume_builder.py --variant job --format wanted`: generate Wanted format.
- `python3 templates/resume_builder.py --variant job --target protopie`: generate with target overrides.
- `python3 templates/resume_builder.py --variant public --example`: generate example resume.
- `python3 templates/generate_notes.py --base build/resume-job-base.md --current build/resume-job.md --target "Company"`: manual diff generation.

Dependencies: `python3`, `pandoc`, `weasyprint` (enforced by `build.sh`).

## Coding Style & Naming Conventions
- Markdown is the source of truth; keep sections consistent with templates.
- Company files use `## Overview`, `## Period`, `## Tech Stack`, `## Responsibilities`, `## Achievements` as applicable.
- Variant tags for content filtering:
  - `<!-- public-only:start -->` / `<!-- public-only:end -->`
  - `<!-- job-only:start -->` / `<!-- job-only:end -->`
- Keep filenames lowercase with hyphens (e.g., `reward-service-api.md`).

## Testing Guidelines

**Resume Build Validation:**
```bash
./build.sh public all && ./build.sh job all
```

**JD Pipeline Unit Tests (no dependencies):**
```bash
python3 templates/test_jd_status.py -v
```

## Commit & Pull Request Guidelines
- Commit messages follow Conventional Commits with scope, e.g. `docs(CO3): add portfolio`, `fix(builder): ...`.
- PRs should include: what changed, which variant(s) impacted, and regenerated outputs if relevant (MD/HTML/PDF diffs).

## Agent-Specific Notes
- Prefer editing source Markdown under `profile/` and `companies/` over generated outputs in the root.
- Keep changes scoped; update variant tags when content differs between `public` and `job` resumes.

## Common Patterns & Gotchas

### Variant Tag Syntax (Critical)
**Correct syntax** (recognized by resume_builder.py):
```html
<!-- public-only:start -->
detailed content for public variant
<!-- public-only:end -->

<!-- job-only:start -->
concise content for job variant
<!-- job-only:end -->
```

**Incorrect syntax** (will NOT be filtered, causes duplicate content):
```html
<!-- variant:public -->  ❌ WRONG
<!-- /variant:public --> ❌ WRONG
```

When fixing variant tags, always convert ALL four tags (opening/closing for both variants).

### Achievement Organization
- Achievements can live in `achievements/*.md` OR inline in `projects/*.md`
- Avoid duplicating achievements between standalone files and project files
- When moving achievements, delete the standalone file after migration

### Content Differentiation by Variant
**Public variant** (portfolio):
- Full ownership: "단독", "전체", "총괄"
- Detailed metrics: commit counts, test file counts, DAU
- Technical depth: ML model names (LSTM, ONNX), architecture patterns

**Job variant** (application):
- IC positioning: remove managerial signals
- Concise bullets without excessive metrics
- Remove over-spec signals: 단독/전체/총괄/리드/커밋/테스트 파일

### Formatting Achievements
Use hierarchical sub-bullets for readability:
```markdown
- **Achievement Title**: Brief description
  - Supporting detail 1
  - Supporting detail 2
```

### Workflow: Modifying Resume Content
1. Edit source files under `companies/` or `profile/`
2. Run `./build.sh <variant> full` to regenerate
3. Verify output with `grep` or visual inspection
4. Commit source files (generated outputs in .gitignore)

### Profile Fields
Company profile.md supports:
- `Period:` - employment period
- `Role:` - job title (can be variant-specific)
- `Employment:` - 정규직/인턴/계약직
- `Position:` - internal position level (public-only recommended)
- `Department:` - department name (public-only)

### Two-File Strategy for JD-Specific Customizations
When customizing resumes for specific job applications:

1. **Generate base once**: `./build.sh job base` creates `build/resume-job-base.md/pdf`
2. **Edit source files** under `profile/` or `companies/` with JD-specific changes
3. **Build with tracking**: `./build.sh job full --target "Company X"` auto-generates diff
4. **Review notes**: `build/resume-job-notes.md` accumulates dated entries with unified diffs

Key files:
- `build/resume-job-base.md/pdf`: Immutable reference (gitignored)
- `build/resume-job.md/pdf`: Current customized version (gitignored)
- `build/resume-job-notes.md`: Change log with diffs per target company

Use `--clean` flag to overwrite notes instead of appending for fresh start.

### Common Bugs Fixed

**Variant Tag Mismatch (Critical)**
- **Symptom**: Duplicate content appearing in both public and job resumes
- **Root cause**: Source files using wrong tag format (`<!-- variant:public -->`) that builder doesn't recognize
- **Fix**: Always use `<!-- public-only:start -->` / `<!-- public-only:end -->` format
- **Affected files**: Check all company project files for incorrect tag syntax

**Diff Line Ending Issues**
- **Symptom**: Malformed diff output in notes file
- **Fix**: Use `splitlines()` without keepends, set explicit `lineterm='\n'` in unified_diff
- **Location**: `templates/generate_notes.py`

**Override Missing for Full-Mode Company Projects**
- **Symptom**: Mixed Korean/English in targeted resume output
- **Root cause**: Only some project files overridden for a full-mode company; non-overridden files pull from original (Korean) source
- **Fix**: When a company is in full mode, override ALL files under `companies/<company>/projects/` — not just key ones

**Summary-Mode Content in Wrong Section**
- **Symptom**: Summary-mode company shows only name/period/role, no description
- **Root cause**: Description placed in `## Summary` section, but `extract_overview()` only reads content under `## Overview`
- **Fix**: Place all summary-mode content (description, key experience) inside `## Overview` using `job-only` variant tags

### Target-Specific Override System

When customizing resumes for specific company targets:

**Structure:**

```text
overrides/
└── <target>/          # e.g., targetco
    ├── config.json    # company list, detail levels, feature flags
    ├── style.css      # optional target-specific CSS (overrides default)
    ├── profile/       # overrides for profile/ files
    │   ├── contact.md
    │   ├── summary-job.md
    │   ├── skills-job.md
    │   ├── education.md
    │   └── languages.md
    └── companies/
        └── <company>/
            ├── profile.md
            └── projects/
                └── <project>.md
```

**config.json schema:**

```json
{
  "job": {
    "companies": ["company1", "CO4", "company5", "CO3", "company2"],
    "company_detail": {
      "CO3": "summary",
      "company2": "summary"
    },
    "include_awards": false,
    "include_certificates": false,
    "include_languages": true
  }
}
```

- `companies`: ordered list (display order in resume)
- `company_detail`: `"summary"` or omit for full (default)
- Config merges with base VARIANT_CONFIG; `company_detail` shallow-merges

**How it works:**

1. `resolve_path()` checks `overrides/{target}/` for matching file path
2. If override exists, it's used instead of base file
3. Override files contain complete content (not patches)
4. Variant tags (`job-only:start/end`) work within overrides
5. Target-specific `style.css` in override dir replaces default theme CSS

**Build command:**

```bash
./build.sh job full --target targetco   # Uses overrides/targetco/ files
./build.sh job full                     # Uses base files only
```

**Build outputs with --target:**

| File | Description |
|------|-------------|
| `build/resume-job-<target>.md` | Markdown output |
| `build/resume-job-<target>.pdf` | PDF output |
| `build/resume-job-<target>-remember.txt` | Plain text (for Remember app) |
| `build/resume-job-notes.md` | Diff notes vs base |

**Creating overrides:**

1. Copy base file to `overrides/<target>/<same-path>`
2. Modify content (add/remove within variant tags)
3. Build with `--target <target>` to verify
4. Test base build still works without override content

**Verification pattern:**

```bash
# Build targeted version
./build.sh job full --target targetco
grep "target-specific phrase" build/resume-job-targetco.md  # Should find

# Build base version
./build.sh job full
grep "target-specific phrase" build/resume-job.md           # Should NOT find
```

**Override Gotchas (Critical):**

1. **Full-mode companies need ALL project files overridden**: Override is file-level. If a company is in full mode (not `"summary"` in `company_detail`), ALL project files under `companies/<company>/projects/` must have override files. Missing overrides will pull in original (possibly Korean) content.

2. **Summary mode only reads `## Overview`**: `extract_overview()` extracts content between `# CompanyName` / `## Overview` and the next `## ` heading. Content in `## Summary` or later sections is ignored for summary-mode companies. Place all summary-mode content (description, key experience) inside `## Overview` using `job-only` tags:
   ```markdown
   ## Overview
   - Period: 2020.09 - 2022.09
   - Employment: Full-time
   <!-- job-only:start -->
   - Role: Backend Developer

   Description text here.

   **Key Experience**
   - Item 1
   - Item 2
   <!-- job-only:end -->
   ```

3. **Company key case sensitivity**: `config.json` company keys must match directory names exactly (e.g., `"CO4"` not `"co4"` if the directory is `companies/CO4/`).

### English Resume Workflow

For creating English-language resumes targeting international companies:

1. Create full override directory: `overrides/<target>/`
2. Override ALL files (profile + all companies in full mode + all their projects)
3. Translate content, do NOT add experiences that don't exist in the original
4. For skills/tech not possessed, emphasize analogous experience instead
5. Build and verify:
   ```bash
   ./build.sh job full --target <target>
   # Check: no Korean remnants
   python3 -c "import re; content=open('build/resume-job-<target>.md').read(); korean=re.findall(r'[\uac00-\ud7af]+', content); print(f'{len(korean)} Korean' if korean else 'All English')"
   # Check: no false claims
   grep -i "keyword-that-should-not-exist" build/resume-job-<target>.md
   ```

### Git Workflow Notes
- Generated outputs in `build/` directory are gitignored
- Override files in `overrides/` directory can be committed or gitignored per preference
- Only source files under `profile/` and `companies/` should be committed
- When verifying changes, check source files directly (not git diff on outputs)

---

## Claude Code Skills

### Job Search Skills

| Skill | Purpose | Output |
|-------|---------|--------|
| `/extract-company-info` | Extract company info from Wanted pages | `company_info/<company>.md` |
| `/extract-job-posting` | Extract JD from recruitment sites | `job_postings/<id>-<company>-<position>.md` |
| `/jd-screening` | Analyze JD fit against criteria | `jd_analysis/screening/<id>-<company>-<position>.md` |
| `/jd-batch` | Batch process URLs or reclassify files | Auto-classify to folders |

### Automated Job Search (jd_search.py / jd_auto.py)

**검색 자동화 스크립트:**
```bash
# 단일 키워드 검색 (테스트)
python3 templates/jd_search.py --query "백엔드 시니어" --dry-run

# 전체 키워드 검색 실행
python3 templates/jd_search.py

# 상태 확인
python3 templates/jd_search.py --status

# 상태 초기화
python3 templates/jd_search.py --reset-state

# 풀 파이프라인 (검색만)
python3 templates/jd_auto.py --search-only
```

**설정 파일:** `job_postings/search_config.yaml`
- 검색 키워드 목록
- 제목 기반 빠른 필터 (title_exclude, title_prefer)
- 실행 설정 (max_urls, scroll_count, request_delay)

**Cron 스케줄 (Clawdbot):**
- `jd-search-morning`: 매일 오전 9시 (KST)
- `jd-search-evening`: 매일 오후 7시 (KST)

**출력:**
- 새 URL 목록: `job_postings/unprocessed/search_YYYYMMDD_HHMM.txt`
- 검색 결과: `job_postings/auto_results/search_YYYYMMDD_HHMM.json`
- 상태 파일: `job_postings/.search_state.json`

### General Skills

| Skill | Purpose |
|-------|---------|
| `/commit` | Smart commit with Conventional Commits |
| `/review` | Code review |
| `/update-agents` | Update this AGENTS.md |

---

## Job Search Workflow

### 1. Company Research
```bash
# Use /extract-company-info or manual research
# Output: company_info/<company>.md
```

#### Company Validation (`templates/company_validator.py`)
```bash
# Human-readable validation (+ risk section auto-insert)
python3 templates/company_validator.py --file company_info/<company>.md --fix

# Machine-readable output for automation
python3 templates/company_validator.py --file company_info/<company>.md --json
```

Notes:
- `--json` prints JSON only (`summary`, `results`, `errors`, `fixed_files`, `report_path`)
- Companies marked as `상장` or `M&A` are treated as non-startups even if file text contains startup keywords (e.g., TheVC, Series)

### 2. JD Extraction
```bash
# Use /extract-job-posting
# Output: job_postings/<id>-<company>-<position>.md
```

### 3. Screening Analysis
```bash
# Use /jd-screening
# Output: jd_analysis/screening/<id>-<company>-<position>.md
# Update: jd_analysis/screening/SUMMARY.md
```

### 4. Interview Prep
```bash
# Create: jd_analysis/interview/<id>-<company>-<position>.md
# Build PDF:
python3 jd_analysis/interview/build-sheet.py <file>.md
python3 jd_analysis/interview/build-sheet.py <file>.md --stage 실무|심화|컬처핏|임원|decision
```

---

## JD Pipeline Commands

### Status Check
```bash
python3 templates/jd_pipeline.py --status
```

### URL Processing
```bash
# Single URL - check duplicates
python3 templates/jd_pipeline.py --url "https://wanted.co.kr/wd/123456"

# Batch URLs from file
python3 templates/jd_pipeline.py --file urls.txt
```

### Auto-Classification
```bash
# Classify markdown files based on screening verdict
python3 templates/jd_pipeline.py --classify job_postings/conditional/hold/

# Re-classify with dry-run + report (recommended before actual move)
python3 templates/jd_pipeline.py --rescreen job_postings/pass/ --dry-run

# Save dry-run report to custom directory
python3 templates/jd_pipeline.py --rescreen job_postings/conditional/hold --dry-run --report-out build/reports --report-format both
```

### Folder Classification Mapping

| Verdict | Target Folder |
|---------|---------------|
| 🟢 지원 추천 | `job_postings/conditional/high/` |
| 🟡 지원 보류 | `job_postings/conditional/hold/` |
| 🔴 지원 비추천 | `job_postings/pass/` |

### Status Management

JD 파일에 frontmatter로 지원 상태를 관리. 상태가 설정된 파일은 재분류로부터 보호됨.

**Frontmatter 스키마:**
```yaml
---
status: rejected  # pending | applied | rejected | interview | offer
status_updated: 2026-01-24
status_reason: 채용 프로세스 부담  # optional
---
```

**보호된 상태:** `applied`, `rejected`, `interview`, `offer` (재분류 스킵)
**비보호 상태:** `pending`, 미설정 (재분류 가능)

```bash
# 상태 설정
python3 templates/jd_pipeline.py --set-status rejected path/to/file.md
python3 templates/jd_pipeline.py --set-status applied path/to/file.md --reason "서류 통과"

# 기존 applied/rejected 폴더 파일에 상태 마이그레이션
python3 templates/jd_pipeline.py --migrate-status --dry-run
python3 templates/jd_pipeline.py --migrate-status
```

---

## Extended Directory Structure

```
resume/
├── profile/              # Profile sections
├── companies/            # Career content
├── templates/            # Build tools & styling
├── scripts/              # Utility scripts (sync, etc.)
├── overrides/            # Target-specific overrides
│   └── <target>/
│       ├── config.json   # Company list & detail levels
│       ├── style.css     # Optional custom CSS
│       ├── profile/      # Profile overrides
│       └── companies/    # Company overrides (mirror structure)
├── build/                # Generated (gitignored)
├── company_info/         # Company database
│   └── <company>.md
├── job_postings/         # JDs with auto-classification
│   ├── jd-screening-rules.md         # User's screening rules (gitignored)
│   ├── jd-screening-rules-template.md # Template for new users
│   ├── examples/
│   │   └── jd-screening-rules-sample.md
│   ├── pass/             # 🔴 Not recommended
│   ├── conditional/
│   │   ├── high/         # 🟢 Recommended
│   │   ├── hold/         # 🟡 On hold
│   │   ├── middle/
│   │   └── low/
│   ├── applied/          # ✅ Applied
│   └── rejected/         # ❌ Rejected
└── jd_analysis/
    ├── screening/        # Screening results
    │   ├── SUMMARY.md
    │   └── <id>-<company>-<position>.md
    └── interview/        # Interview sheets
        ├── HOW-TO-USE.md
        ├── build-sheet.py
        └── <id>-<company>-<position>.md
```

---

## File Naming

| Directory | Pattern | Example |
|-----------|---------|---------|
| `company_info/` | `<company>.md` | `techcorp.md` |
| `job_postings/` | `<id>-<company>-<position>.md` | `123456-techcorp-backend.md` |
| `jd_analysis/screening/` | `<id>-<company>-<position>.md` | `123456-techcorp-backend.md` |
| `jd_analysis/interview/` | `<id>-<company>-<position>.md` | `123456-techcorp-backend.md` |

Private JDs: `private-<company>-<position>.md`

---

## Obsidian Dashboard Sync (sync_dashboard.py)

Bidirectional sync between `job_postings/` and Obsidian dashboard.

**Usage:**
```bash
# Obsidian → job_postings (apply dashboard status changes)
python scripts/sync_dashboard.py --from-obsidian

# job_postings → Obsidian (generate tables for copy-paste)
python scripts/sync_dashboard.py --to-obsidian

# Full bidirectional sync (Obsidian wins on conflict)
python scripts/sync_dashboard.py --sync

# Preview mode
python scripts/sync_dashboard.py --from-obsidian --dry-run
```

**Environment Variables:**
- `OBSIDIAN_DASHBOARD_PATH`: Override default dashboard path (optional)

**Status Mapping (Dashboard → Folder):**

| Dashboard Status | Target Folder |
|------------------|---------------|
| 지원, 서류통과, 면접 | `applied/` |
| 패스 | `pass/` |
| 서류 탈락, 탈락 | `rejected/` |
| 보류, 조건부, 킵 | `conditional/hold/` |

**Notes:**
- `--to-obsidian` prints tables for manual copy-paste (auto-replace not implemented)
- Files in `conditional/high/`, `conditional/hold/` etc. are properly scanned
- Safe file move: skips if destination exists, logs errors on failure
