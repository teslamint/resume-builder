# AI Agent Project Guide

Resume builder & job search automation system. Markdown source → PDF/HTML/TXT output.

> **Full documentation**: [Getting Started](docs/getting-started.md) · [Customization](docs/customization.md) · [AI Workflow](docs/ai-workflow.md)

## Project Overview

Source files in `private/profile/` and `private/companies/` → build system (`templates/build/`) → output in `private/build/` (gitignored).
Job search pipeline in `templates/jd/` with company info (`private/company_info/`), JD files (`private/job_postings/`), and analysis (`private/jd_analysis/`).

## Critical Rules

- **Markdown is source of truth** — edit `private/profile/` and `private/companies/`, never `private/build/` outputs
- **Conventional Commits** with scope: `docs(company): add portfolio`, `fix(builder): handle edge case`
- **Variant tags** filter content per resume type (`public` vs `job`)
- **Do not embellish resume content** — only claim technologies/patterns evidenced in the codebase

## Critical Gotchas

### 1. Variant Tag Syntax
```html
<!-- public-only:start --> / <!-- public-only:end -->   ✅ CORRECT
<!-- job-only:start -->    / <!-- job-only:end -->       ✅ CORRECT
<!-- variant:public -->    / <!-- /variant:public -->    ❌ WRONG (not filtered, causes duplicates)
```
When fixing variant tags, convert ALL four tags (opening/closing for both variants).

### 2. Summary Mode Only Reads `## Overview`
`extract_overview()` reads content between `## Overview` and next `## `. Content in `## Summary` or later sections is **ignored**. Place summary-mode content inside `## Overview` with `job-only` tags.

### 3. Full-Mode Override Requires ALL Project Files
Override is file-level. Full-mode companies need ALL `private/companies/<company>/projects/` files overridden. Missing → original (possibly Korean) content leaks.

### 4. Company Key Case Sensitivity
`config.json` keys must match directory names exactly: `"CompanyB"` not `"companyb"`.

### 5. variant_config.json is Gitignored
Must create manually: `cp variant_config.example.json private/variant_config.json`

## Resume Content Integrity

Override content must not add technologies, roles, or achievements absent from base `private/companies/` or `private/profile/` files.

**Inflation patterns to reject:**
- **Role**: adding 매니저/리드/총괄 when actual role is IC
- **Verb**: 재설계 when actual work was 분리; 전환 when actual was 설계
- **Scope**: Cluster when infra was managed services; Kubernetes when actual was ECS
- **Architecture**: MSA 전환 when actual was partial service extraction

### Generated Content Integrity

AI-generated content (interview sheets, mock interviews) must not infer specific technical experiences from general resume statements. "Used Spring Boot" ≠ "solved JPA N+1". State only what the resume explicitly documents. Verify with: `python3 templates/build/verify_content.py private/jd_analysis/interview/<file>.md`

## Build & Test Commands

```bash
# Resume builds
./build.sh <public|job|example> [full|short|wanted|base|all] [--target <name>] [--clean]

# Quick validation
./build.sh public all && ./build.sh job all

# Unit tests
python3 templates/tests/test_jd_status.py -v
```

## Key Directory Structure

```
private/                → all personal data (gitignored)
  profile/              → core sections (contact, summary, skills, education)
  companies/<co>/       → per-company: profile.md, projects/, achievements/
  overrides/<target>/   → target-specific overrides (mirror profile/ & companies/)
  build/                → generated outputs
  company_info/         → company database
  job_postings/         → JDs with auto-classification (pass/, conditional/, applied/, rejected/)
  jd_analysis/          → screening results + interview sheets
templates/build/        → resume builder, notes generator
templates/jd/           → job search pipeline (search, auto, pipeline, validator)
```

## File Naming

| Directory | Pattern | Example |
|-----------|---------|---------|
| `private/company_info/` | `<company>.md` | `techcorp.md` |
| `private/job_postings/` | `<id>-<company>-<position>.md` | `123456-techcorp-backend.md` |
| `private/jd_analysis/screening/` | `<id>-<company>-<position>.md` | `123456-techcorp-backend.md` |
