# Repository Guidelines

## Project Structure & Module Organization

- `profile/`: core profile sections (`contact.md`, `summary-*.md`, `skills-*.md`, `education.md`).
- `companies/<company>/`: per-company content with `profile.md`, plus `projects/`, `achievements/`, and sometimes `portfolios/`.
- `templates/`: build tooling and styling (`resume_builder.py`, `generate_notes.py`, `layout.md`, `style.css`, `style-short.css`).
- `overrides/<target>/`: target-specific file overrides mirroring `profile/` and `companies/` structure.
- `build/`: generated artifacts (`resume-*.md`, `resume-*.html`, `resume-*.pdf`, `resume-*-remember.txt`, `resume-*-wanted.txt`).

## Build, Test, and Development Commands
- `./build.sh example all`: build demo resume with example data (for testing).
- `./build.sh public all`: build full + short + wanted public resume.
- `./build.sh job all`: build all job resume variants.
- `./build.sh public full`: build full public resume only (MD/HTML/PDF).
- `./build.sh job short`: build 1-page JD-focused resume only.
- `./build.sh public wanted`: build Wanted site plain text format.
- `./build.sh job base`: generate immutable base resume for diff tracking.
- `./build.sh job full --target "Company"`: build with automatic diff notes vs base.
- `./build.sh job full --clean`: overwrite notes instead of appending.
- `python3 templates/resume_builder.py --list`: list available company keys.
- `python3 templates/resume_builder.py --variant public > resume-public.md`: generate Markdown only.
- `python3 templates/resume_builder.py --variant job --format wanted`: generate Wanted format.
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

### Target-Specific Override System

When customizing resumes for specific company targets:

**Structure:**

```text
overrides/
└── <target>/          # e.g., targetco
    ├── profile/       # overrides for profile/ files
    │   └── summary-job.md
    └── companies/
        └── <company>/
            └── projects/
                └── <project>.md
```

**How it works:**

1. `resolve_path()` checks `overrides/{target}/` for matching file
2. If override exists, it's used instead of base file
3. Override files contain complete content (not patches)
4. Variant tags (`job-only:start/end`) work within overrides

**Build command:**

```bash
./build.sh job full --target targetco   # Uses overrides/targetco/ files
./build.sh job full                     # Uses base files only
```

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
# Classify files based on screening verdict
python3 templates/jd_pipeline.py --classify job_postings/unprocessed/

# Re-classify with dry-run preview
python3 templates/jd_pipeline.py --rescreen job_postings/pass/ --dry-run
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
├── templates/            # Build tools
├── overrides/            # Target overrides
├── build/                # Generated (gitignored)
├── company_info/         # Company database
│   └── <company>.md
├── job_postings/         # JDs with auto-classification
│   ├── jd-screening-rules.md
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
