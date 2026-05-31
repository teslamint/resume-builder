# Code Quality Roadmap

> Findings from code quality review session (2026-05-31). Prioritized by impact and dependency order.

**Scope:** templates/jd/ + templates/build/ — 111 Python files, 26k LOC, 832 tests

---

## Phase 0: Quick Wins (standalone, no dependency)

- [ ] Remove `sys.path.insert` from 5 test files (pyproject.toml `pythonpath` already handles this)
  - `test_headhunter_filler.py`, `test_backfill_wanted_company_info.py`, `test_screening_validation.py`, `test_pre_screen.py`, `test_pre_screen_helpers.py`, `test_career_builder.py`, `test_quick_filter.py`
- [ ] Resolve `ce_jd_files.py:normalize_company_name` vs `naming.py:normalize_company_name` — same logic → import from naming; different logic → rename to clarify intent

## Phase 3: Structural Refactoring (extends existing plan)

> Source of truth: `.claude/plans/piped-sprouting-swing.md` (original Phase 3 plan). Items below are additions.

### 3A: Path centralization

- [ ] Create `templates/jd/paths.py` with project path constants:
  - `REPO_ROOT`, `PRIVATE_DIR`, `SCREENING_DIR`, `SUMMARY_PATH`, `COMPANY_INFO_DIR`, `JOB_POSTINGS_DIR`, `CONFIG_PATH` (search_config.yaml)
- [ ] Replace 8+ independent `SCREENING_DIR` definitions across audit_*.py, append_reclass_summary.py
- [ ] Replace 4 independent `CONFIG_PATH` definitions (search.py, search_quick.py, quick_filter.py, worker.py)
- [ ] Consolidate `search_helpers._read_search_config` to use shared `CONFIG_PATH`

### 3B: headhunter_filler.py decomposition

- [ ] Extract DOCX helpers → `templates/build/docx_helpers.py` (~120 LOC: clear_runs, add_run, insert_paragraph_after, set_plain, delete_paragraph, fill_table_cell, etc.)
- [ ] Extract data loading → reuse from `resume_builder.py` (one source of truth for `calculate_tenure`, company/project parsing)
  - Remove duplicate `_calc_tenure_str`, `_parse_contact`, `_parse_education`, `_load_company`
- [ ] Remaining headhunter_filler.py: template analysis + fill logic only

### 3C: run_auto further decomposition

- [ ] Extract each `--*-only` mode into dedicated function
- [ ] `run_auto` becomes a thin dispatcher: parse mode → call handler
- [ ] Target: run_auto < 80 lines

### 3D: Prompt externalization

- [ ] Move `_build_prompt` template → `private/prompts/screening_system.txt` (or .md)
- [ ] `auto_screening.py` loads and formats at runtime
- [ ] Screening rules remain in existing separate file (already externalized)

## Phase 4: Screening Test Hardening

- [ ] Inject `datetime.now()` dependency in `company_validator.py` (parameter or factory)
  - `company_age = now_year - data.founded_year` (line 463)
- [ ] Golden-file regression tests for `auto_screening.py`
  - Fixed JD + rules → expected verdict structure
  - Mock LLM subprocess to return known output
- [ ] Rule consistency tests: verify all 4 conditions + meta-rule 0.5 against sample corpus
- [ ] Edge case coverage: polyglot rule, headhunter detection, closed-JD skip

## Phase 5: Observability (low priority, no rush)

- [ ] Add `logger = logging.getLogger(__name__)` to auto.py, pipeline.py, search.py
- [ ] Convert error-path `print()` → `logger.warning/error` (keep progress prints as-is)
- [ ] Add `--verbose` flag → DEBUG level
- [ ] Narrow `except Exception` in 15+ locations:
  - At minimum: add `logger.warning(f"...: {e}")` before swallowing
  - Where possible: catch specific exceptions (OSError, TimeoutError, json.JSONDecodeError)
- [ ] Consider `pyright --basic` in CI (type annotations already at 70-90% coverage)

---

## Principles (agreed)

1. **One source of truth** — paths, naming functions, data loading defined once
2. **Agent-friendly debugging** — errors always leave a trace (what failed, where, why)
3. **Script collection with proper test infra** — no forced package conversion, but pytest config is authoritative
4. **Screening = core business logic** — highest test priority
5. **Incremental improvement** — no big-bang rewrites; each phase is independently shippable
