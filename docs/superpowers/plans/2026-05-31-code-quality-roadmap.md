# Code Quality Roadmap

> Findings from code quality review session (2026-05-31). Prioritized by impact and dependency order.

**Scope:** templates/jd/ + templates/build/ — 111 Python files, 26k LOC, 832 tests

**Prior phases:** Phase 1 (ce_* extractor split) and Phase 2 (search_helpers extraction) are complete — see git history (`refactor(jd):` commits from 2026-04-09 onward). This document covers Phase 0 + Phase 3 onward.

---

## Phase 0: Quick Wins (standalone, no dependency)

- [ ] Remove `sys.path.insert` from 7 test files (pyproject.toml `pythonpath` covers `templates/build`, `templates/jd`, `example/interview`)
  - `test_headhunter_filler.py` (→ templates/build ✓)
  - `test_backfill_wanted_company_info.py` (→ templates/jd ✓)
  - `test_screening_validation.py` (→ templates/jd ✓)
  - `test_pre_screen.py` (ROOT = templates/jd ✓)
  - `test_pre_screen_helpers.py` (ROOT = templates/jd ✓)
  - `test_career_builder.py` (→ templates/build ✓)
  - `test_quick_filter.py` (→ templates/jd ✓)
  - Verified: each insert target resolves to a directory already in pyproject.toml pythonpath
- [ ] Resolve `ce_jd_files.py:normalize_company_name` vs `naming.py:normalize_company_name` — same logic → import from naming; different logic → rename to clarify intent (related to 3E slugify consolidation)

## Phase 3: Structural Refactoring

### Dependency order

```
3A (paths) ──► 3C (run_auto uses central paths)
           ──► 3E (search/queue use central paths)
Phase 0 #2 (normalize_company_name) ──► 3E (slugify consolidation, same naming domain)
3B (DOCX filler) is independent — separate work unit
3D (prompt externalization) is independent
```

### 3A: Path centralization + config/state contract

- [ ] Create `templates/jd/paths.py` with project path constants:
  - `REPO_ROOT`, `PRIVATE_DIR`, `SCREENING_DIR`, `SUMMARY_PATH`, `COMPANY_INFO_DIR`, `JOB_POSTINGS_DIR`, `CONFIG_PATH` (search_config.yaml)
- [ ] Replace 8+ independent `SCREENING_DIR` definitions across audit_*.py, append_reclass_summary.py
- [ ] Replace 4 independent `CONFIG_PATH` definitions (search.py, search_quick.py, quick_filter.py, worker.py)
- [ ] Consolidate `search_helpers._read_search_config` to use shared `CONFIG_PATH`
- [ ] Document config/state file contract: which files are inputs (search_config.yaml, screening rules), which are derived state (run state JSON, SUMMARY.md), and who owns writes

### 3B: headhunter_filler.py decomposition (separate work unit from JD refactoring)

> This is a `templates/build/` concern — do NOT mix with JD pipeline changes in the same commits/PRs.

- [ ] Extract DOCX helpers → `templates/build/docx_helpers.py` (~120 LOC: clear_runs, add_run, insert_paragraph_after, set_plain, delete_paragraph, fill_table_cell, etc.)
- [ ] Reconcile `_calc_tenure_str` with `resume_builder.calculate_tenure` into a single implementation
  - They differ in: period separator handling (`~` vs `-`), "재직중" support, return format on error
  - Must verify both caller sites (headhunter fill + resume build) still produce correct output after unification
- [ ] Extract remaining data loading (`_parse_contact`, `_parse_education`, `_load_company`) → reuse from or merge into `resume_builder.py`
- [ ] Remaining headhunter_filler.py: template analysis + fill logic only

### 3C: run_auto further decomposition

> **Precondition:** Verify `DEFAULT_MIN_COMPLETENESS=70.0` regression — run with `min_completeness` unset and confirm incomplete company info (< 70%) does NOT pass through to screening. Add characterization test if missing.

- [ ] Verify characterization tests cover current default behavior (add if missing)
- [ ] Extract each `--*-only` mode into dedicated function
- [ ] `run_auto` becomes a thin dispatcher: parse mode → call handler
- [ ] Target: run_auto < 80 lines

### 3D: Prompt externalization

- [ ] Move `_build_prompt` template → `private/prompts/screening_system.txt` (or .md)
- [ ] `auto_screening.py` loads and formats at runtime
- [ ] Screening rules remain in existing separate file (already externalized)

### 3E: Search and queue contract cleanup

> Also: verify TheVC round parser boundary cases (nav-tab false positives) as a pre-existing regression gate before modifying search modules.

- [ ] `filter_and_dedup` — clarify ownership: search_helpers vs caller; document dedup semantics (by ID? by company+title?)
  - **Done when:** docstring specifies dedup key + test asserts dedup behavior with duplicate inputs
- [ ] GroupBy experience filter — align with Wanted/Remember filter logic or document why different
  - **Done when:** either unified filter function exists with platform-specific config, OR difference documented in code comment with rationale
- [ ] queue/worker contract — define queue item lifecycle (pending → processing → done/error), make state transitions explicit
  - **Done when:** state transitions are typed (enum or literal union) + test covers each transition + invalid transitions raise
- [ ] Consolidate remaining local `slugify()` wrappers in `check_companies.py`, `remember_batch_extract.py`, `wanted_extract.py` → use `naming.slugify_company` directly
  - **Done when:** grep finds zero local `def slugify` outside `naming.py` + all existing tests still pass

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
