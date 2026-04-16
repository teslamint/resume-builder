# Claude Code Project Guide

Resume builder & job search automation system. Markdown source → PDF/HTML/TXT output.

> **Full documentation**: [Getting Started](docs/getting-started.md) · [Customization](docs/customization.md) · [AI Workflow](docs/ai-workflow.md)

## Skills Quick Reference

| Skill | Purpose | Output |
|-------|---------|--------|
| `/extract-company-info` | Company info from Wanted/Remember/Saramin/TheVC | `private/company_info/<company>.md` |
| `/extract-recruitment-info` | Combined company + JD extraction | `private/company_info/` + `private/job_postings/` |
| `/extract-job-posting` | JD extraction from recruitment sites | `private/job_postings/<id>-<company>-<position>.md` |
| `/jd-screening` | JD fit analysis against screening rules | `private/jd_analysis/screening/<id>-<company>-<position>.md` |
| `/jd-batch` | Batch process URLs or reclassify files | Auto-classify to folders |
| `/resume-build` | Build resume with variant/target options | `private/build/` |

## Auto Pipeline CLI

```bash
python3 templates/jd/auto.py                          # full pipeline
python3 templates/jd/auto.py --from-urls <file>        # skip search
python3 templates/jd/auto.py --screening-only --from-urls <file>  # screen existing JDs only
python3 templates/jd/auto.py --company-enrichment-only  # reprocess TheVC queue
python3 templates/jd/auto.py --min-completeness 60      # re-collect if existing company info < 60%
python3 templates/jd/auto.py --thevc-mode auto|skip|require  # TheVC login failure handling
python3 templates/jd/auto.py --resume                        # resume from last incomplete run
```

- `--min-completeness N`: skip re-collection when existing `company_info` completeness ≥ N% (0–100)
- Headhunting companies (써치/서치펌/헤드헌팅/리크루팅/인력파견) are auto-detected and excluded from info collection
- `find_existing_jd()` searches all `conditional/` subdirs: `high/`, `hold/`, `middle/`, `low/`

## Critical Gotchas

### 1. Variant Tag Syntax
```html
<!-- public-only:start --> / <!-- public-only:end -->   ✅ CORRECT
<!-- job-only:start -->    / <!-- job-only:end -->       ✅ CORRECT
<!-- variant:public -->    / <!-- /variant:public -->    ❌ WRONG (not filtered, causes duplicates)
```

### 2. Summary Mode Only Reads `## Overview`
`extract_overview()` reads content between `## Overview` and next `## `. Content in `## Summary` or later sections is **ignored**. Place all summary-mode content inside `## Overview` with `job-only` tags.

### 3. Full-Mode Override Requires ALL Project Files
Override is file-level. If a company is in full mode, ALL files under `companies/<company>/projects/` must have overrides. Missing → original (Korean) content leaks through.

### 4. Company Key Case Sensitivity
`config.json` keys must match directory names exactly: `"CompanyB"` not `"companyb"`.

### 5. variant_config.json is Gitignored
Must be created manually: `cp variant_config.example.json private/variant_config.json`

## Resume Content Integrity

Override content must not add technologies, roles, or achievements absent from base `companies/` or `profile/` files.

**Inflation patterns to reject:**
- **Role**: adding 매니저/리드/총괄 when actual role is IC
- **Verb**: 재설계 when actual work was 분리; 전환 when actual was 설계
- **Scope**: Cluster when actual infra was managed services (RDS, ElastiCache); Kubernetes when actual was ECS
- **Architecture**: MSA 전환 when actual was partial service extraction

```bash
# Verify after override edits:
grep -i "kubernetes\|k8s" private/build/resume-job-<target>.md
grep "재설계\|총괄\|리드\|매니저" private/build/resume-job-<target>.md
diff private/overrides/<target>/companies/<company>/profile.md private/companies/<company>/profile.md
```

### Generated Content Integrity (interview sheets, mock interviews, etc.)

When writing company-specific technical experience in AI-generated content:
- State ONLY what `private/build/resume-job-base.md` explicitly says as fact
- Do NOT infer specific technical experiences from general statements (e.g., "used Spring Boot" ≠ "solved JPA N+1 with fetch join")
- When experience is absent, write: "직접 경험은 없지만 ~로 접근하겠다"
- Derived documents (`resume-based-qa.md` etc.) must also be verified against the resume source

**Inference patterns to reject:**
- ❌ "Used Spring Boot → therefore experienced JPA N+1"
- ❌ "Commerce service → therefore designed product-category relationships"
- ❌ "Used JPA → therefore applied fetch join and DTO projection"
- ⭕ "Spring Boot 3/Kotlin 기반 커머스 API 설계·개발" (resume verbatim)

```bash
# Verify generated content against resume:
python3 templates/build/verify_content.py private/jd_analysis/interview/<file>.md
```

## Build Verification

```bash
./build.sh job full --target <target>   # targeted
./build.sh job full                     # base
./build.sh public all                   # public variant
python3 templates/tests/test_jd_status.py -v  # unit tests
```

## JD Screening

JD screening analyses should follow the user's custom screening rules and output format exactly. Use Korean for verdict labels (e.g., 지원 비추천). Do not truncate or abbreviate the structured output.
