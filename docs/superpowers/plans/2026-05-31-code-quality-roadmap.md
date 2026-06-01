# Code Quality Roadmap

> Findings from code quality review session (2026-05-31). Prioritized by impact and dependency order.

**Scope:** templates/jd/ + templates/build/ — 111 Python files, 26k LOC, 832 tests

**Prior phases:** Phase 1 (ce_* extractor split) and Phase 2 (search_helpers extraction) are complete — see git history (`refactor(jd):` commits from 2026-04-09 onward). This document covers Phase 0 + Phase 3 onward.

---

## Phase 0: Quick Wins (standalone, no dependency) ✅

- [x] Remove `sys.path.insert` from 7 test files (pyproject.toml `pythonpath` covers `templates/build`, `templates/jd`, `example/interview`)
  - `test_headhunter_filler.py` (→ templates/build ✓)
  - `test_backfill_wanted_company_info.py` (→ templates/jd ✓)
  - `test_screening_validation.py` (→ templates/jd ✓)
  - `test_pre_screen.py` (ROOT = templates/jd ✓)
  - `test_pre_screen_helpers.py` (ROOT = templates/jd ✓)
  - `test_career_builder.py` (→ templates/build ✓)
  - `test_quick_filter.py` (→ templates/jd ✓)
  - Verified: each insert target resolves to a directory already in pyproject.toml pythonpath
- [x] Resolve `ce_jd_files.py:normalize_company_name` vs `naming.py:normalize_company_name` — different logic → renamed to `normalize_company_name_narrow` to clarify intent

## Phase 3: Structural Refactoring

### Dependency order

```
3A (paths) ──► 3C (run_auto uses central paths)
           ──► 3E (search/queue use central paths)
Phase 0 #2 (normalize_company_name) ──► 3E (slugify consolidation, same naming domain)
3B (DOCX filler) is independent — separate work unit
3D (prompt externalization) is independent
```

### 3A: Path centralization + config/state contract ✅

- [x] Added `SUMMARY_PATH` and `CONFIG_PATH` to existing `constants.py` (no new paths.py — constants.py already had BASE_DIR, PRIVATE_DIR, etc.)
- [x] Replace 8+ independent `SCREENING_DIR` definitions across audit_*.py, freshness_check.py
- [x] Replace 4 independent `CONFIG_PATH` definitions (search.py, search_quick.py, quick_filter.py, worker.py)
- [x] `search_helpers._read_search_config` callers already pass CONFIG_PATH — verified
- [x] Document config/state file contract: which files are inputs (search_config.yaml, screening rules), which are derived state (run state JSON, SUMMARY.md), and who owns writes
  - See `docs/config-state-contract.md`

### 3B: headhunter_filler.py decomposition ✅

> This is a `templates/build/` concern — do NOT mix with JD pipeline changes in the same commits/PRs.

- [x] Extract DOCX helpers → `templates/build/docx_helpers.py` (122 LOC)
- [x] Reconcile `_calc_tenure_str` with `resume_builder.calculate_tenure` → unified with separator/include_period/error_value params
  - Both caller sites verified: resume (separator="-", include_period=True), headhunter (separator="~", include_period=False)
- [x] Extract data loading (`_parse_contact`, `_parse_education`, `_load_company`) → moved into `resume_builder.py`
- [x] Remaining headhunter_filler.py: 1204 LOC, template analysis + fill logic only

### 3C: run_auto further decomposition ✅

> **Precondition:** ✅ `DEFAULT_MIN_COMPLETENESS=70.0` regression fixed (was accidentally set to 0.0 in a4ed43d). Characterization test added.

- [x] Verify characterization tests cover current default behavior (added test_run_auto_blocks_incomplete_company_info_by_default)
- [x] Extract each `--*-only` mode into dedicated function (_handle_company_enrichment_only, _handle_search_only, _handle_screening_only, _handle_full_pipeline)
- [x] `run_auto` becomes a thin dispatcher: parse mode → call handler
- [x] Target: run_auto = 73 lines (< 80 ✅)

### 3D: Prompt externalization ✅

- [x] Move `_build_prompt` template → `templates/jd/prompts/screening_system.txt`
- [x] `auto_screening.py` loads and formats at runtime (with FileNotFoundError on missing template)
- [x] Screening rules remain in existing separate file (already externalized)

### 3E: Search and queue contract cleanup

> Also: verify TheVC round parser boundary cases (nav-tab false positives) as a pre-existing regression gate before modifying search modules.

- [x] `filter_and_dedup` — clarify ownership: search_helpers vs caller; document dedup semantics (by ID? by company+title?)
  - **Done when:** docstring specifies dedup key + test asserts dedup behavior with duplicate inputs
- [x] GroupBy experience filter — align with Wanted/Remember filter logic or document why different
  - **Done when:** either unified filter function exists with platform-specific config, OR difference documented in code comment with rationale
- [x] queue/worker contract — define queue item lifecycle (pending → processing → done/error), make state transitions explicit
  - **Done when:** state transitions are typed (enum or literal union) + test covers each transition + invalid transitions raise
- [x] Consolidate remaining local `slugify()` wrappers in `check_companies.py`, `remember_batch_extract.py`, `wanted_extract.py` → use `naming.slugify_company` directly
  - ✅ grep finds zero local `def slugify` outside `naming.py` + 817 tests pass

## Phase 4: Screening Test Hardening

- [x] Inject `datetime.now()` dependency in `company_validator.py` (parameter or factory)
  - `company_age = now_year - data.founded_year` (line 463)
- [x] Golden-file regression tests for `auto_screening.py`
  - Fixed JD + rules → expected verdict structure
  - Mock LLM subprocess to return known output
- [x] Rule consistency tests: verify all 4 conditions + meta-rule 0.5 against sample corpus
  - Synthetic fixtures: mocked LLM tests verify prompt assembly + verdict parsing for all 4 conditions
  - Golden fixtures (committed): 5 sanitized screening outputs covering salary/lead/scope/volatility reject + evidence hierarchy hold
  - Parser robustness: 35 verdict format variants from real corpus (emoji/bold/table/annotation patterns)
  - Condition-logic coherence: automated verification that 4-condition results match final verdict per 0.5절 rules
  - Full corpus sweep (1091 files): remains in operational audit scripts (audit_05.py, audit_hypotheses.py), not pytest
- [x] Edge case coverage: polyglot rule, headhunter detection, closed-JD skip
  - headhunter detection: all 6 HEADHUNTING_KEYWORDS tested + negative case (deterministic)
  - closed-JD: all _CLOSED_MARKERS covered (deterministic)
  - polyglot: domain_filter.classify_domain returns "skip" for non-primary-stack backend JDs (deterministic)

## Phase 5: Observability (low priority, no rush)

- [x] Add `logger = logging.getLogger(__name__)` to auto.py, pipeline.py, search.py
  - Also added to: notifications.py, company_validator.py, wanted_extract.py, remember_batch_extract.py, rescreen_truncated.py
  - Standardized `_logger` → `logger` in search.py for consistency
- [x] Convert error-path `print()` → `logger.warning/error` (keep progress prints as-is)
  - 12 files, 75 insertions / 51 deletions across error paths
  - Guard-clause warnings (e.g. notifications "channel not configured") also converted
- [x] Add `--verbose` flag → DEBUG level
  - `--verbose` / `-v` in auto.py argparse; `logging.basicConfig()` with WARNING default, DEBUG when verbose
- [x] Narrow `except Exception` in 15+ locations:
  - At minimum: add `logger.warning(f"...: {e}")` before swallowing
  - Where possible: catch specific exceptions (OSError, TimeoutError, json.JSONDecodeError)
  - 22 broad handlers addressed; defensive fallbacks (state loading) kept broad where narrowing proved unsafe
- [x] Consider `pyright --basic` in CI (type annotations already at 70-90% coverage)
  - Evaluated: pyright 1.1.409, `typeCheckingMode = "basic"`, 68 files → 40 errors (below 50-issue threshold)
  - Config added to pyproject.toml (`[tool.pyright]` section) for local use
  - ~~Blocking CI deferred: 40 existing errors need fixing first~~ → All 40 errors fixed (2026-06-01). CI job added (2026-06-01).

---

## Principles (agreed)

1. **One source of truth** — paths, naming functions, data loading defined once
2. **Agent-friendly debugging** — errors always leave a trace (what failed, where, why)
3. **Script collection with proper test infra** — no forced package conversion, but pytest config is authoritative
4. **Screening = core business logic** — highest test priority
5. **Incremental improvement** — no big-bang rewrites; each phase is independently shippable
