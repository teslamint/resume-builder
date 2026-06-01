# Post-Roadmap Comprehensive Review

> Findings from grill-me review session (2026-06-01) after completing the Phase 0–5 code quality roadmap.

**Scope:** templates/jd/ + templates/build/ — 68 Python files, 18.5k LOC, 932 tests
**Baseline:** pyright 0 errors, all tests pass in 3.93s

---

## Priority 1: Safety Net (test before refactor)

### 1A: Characterization tests for pipeline.py (761 LOC, 0 tests)

- [ ] `classify_file()` — golden-file test: known JD → expected folder + verdict
- [ ] `migrate_status()` — dry_run vs real: assert file moves
- [ ] `process_urls_from_file()` — mock URL fetch, verify ProcessedItem output
- **Done when:** ≥80% branch coverage on `classify_file`; regression caught if folder logic changes

### 1B: Characterization tests for resume_builder.py (1060 LOC, 0 tests)

- [ ] Core build path: known input files → expected output structure
- [ ] `calculate_tenure()` — both separator/include_period variants from 3B unification
- [ ] Data loading functions migrated from headhunter_filler (3B)
- **Done when:** build output matches snapshot for 1 known profile; tenure edge cases covered

### 1C: Characterization tests for refactor targets

- [ ] `ensure_company_info()` — all 5 branch paths (headhunting, existing+thevc, existing+skip, new+extraction, new+stub)
- [ ] `auto.py:_process_urls()` — mock screening/extraction, verify state persistence round-trip
- [ ] `search_helpers.py:load_and_scrape_*` — verify existing test coverage via `test_search_helpers.py` (browser scrape paths may be uncovered)
- **Done when:** each refactor target (items 5, 7, 8) has ≥1 test per branch path before structural changes begin

---

## Priority 2: Quick Wins (Small, independent)

### 2A: `RawJobResult` → `DiscoveredJob` inheritance + field unification

- [ ] `RawJobResult` extends `DiscoveredJob`; add `raw_id`, `platform`, `href` as extra fields
- [ ] Rename `canonical_id` → `job_id` (inherits from base)
- [ ] Update all conversion callsites
- **Sequencing:** do BEFORE item 4A (same file `search_helpers.py`)
- **Done when:** `RawJobResult` inherits `DiscoveredJob`; grep finds zero `canonical_id` refs; 932+ tests pass

### 2B: `http_client_base.py` HTML fetch extension

- [ ] Add `http_text_request(url, *, headers, timeout, max_bytes) -> str`
- [ ] Replace `auto_company._fetch_url_text()`, `search_helpers._fetch_html()`, `check_closure_via_api` inline impl
- [ ] Default `User-Agent` in one place
- **Done when:** grep finds zero `urllib.request.urlopen` outside `http_client_base.py`

### 2C: Enrichment queue consolidation + locking

- [ ] Merge `_append_enrichment_queue` + `_append_saramin_enrichment_queue` → `_append_to_queue(path, company)`
- [ ] Use `queue_utils` file-locking pattern (fcntl.flock)
- **Done when:** grep finds zero `_append_enrichment_queue`/`_append_saramin_enrichment_queue`; queue append uses flock

### 2D: WARN/Error `print()` → `logger.warning` (~40 calls)

- [ ] Convert `print(f"WARN:...` and `print(f"Error:...` patterns
- [ ] Convert `print(..., file=sys.stderr)` diagnostic messages (not progress)
- [ ] Remove scattered `import sys` inside function bodies where only used for stderr print
- **Done when:** `grep -rn 'print.*WARN\|print.*Error\|print.*file=sys.stderr' | grep -v test_` returns ≤5 (audit scripts OK to keep)

### 2E: Rate limit constants centralization

- [ ] Add `rate_limits:` section to `search_config.yaml` (per-site: wanted, remember, thevc, saramin)
- [ ] Each client reads from config; module-level `REQUEST_DELAY` becomes fallback default
- **Done when:** changing a rate limit requires editing `search_config.yaml` only; all `REQUEST_DELAY` constants reference config

---

## Priority 3: Structural Refactoring (requires Priority 1 tests)

### 3A: `auto.py` 990 LOC → 3-module split

**Precondition:** 1C tests for `_process_urls` pass

- [ ] Extract `auto_state.py` — `_state_path`, `_save_state`, `_load_state`, `_find_latest_state`, `_cleanup_state`, `RunSummary`
- [ ] Extract `auto_processor.py` — `_process_urls`, `_handle_prescreen_hit`, `_resolve_jd_and_check_dup`, `_build_url_list`
- [ ] `auto.py` remains: argparse + mode dispatcher (`_handle_*_only` + `run_auto`) — target ≤150 LOC
- **Done when:** `auto.py` ≤150 LOC; `wc -l` for each new module ≤350; all existing tests pass

### 3B: `ensure_company_info` 250 LOC → 3-function decomposition

**Precondition:** 1C tests for all 5 branch paths pass

- [ ] `_update_existing_company_info()` — existing file + completeness check + TheVC inject
- [ ] `_create_new_company_info()` — extraction + stub fallback
- [ ] `_verify_and_warn_homonym(output_path, jd_path)` — deduplicate the 2 copy-pasted homonym blocks
- [ ] `ensure_company_info()` becomes dispatcher: headhunting check → existing? → route — target ≤30 LOC
- **Done when:** `ensure_company_info` ≤30 LOC; homonym verification in exactly 1 function; 1C tests still pass

### 3C: `search_helpers.py` scraper Strategy unification

**Precondition:** 1C search_helpers coverage verified; 2A field rename done first (same file)

- [ ] Common browser scraper base: navigate → wait → scroll → extract (config: selectors, URL pattern)
- [ ] Common HTTP scraper base: fetch → parse (config: JSON paths, pagination)
- [ ] Platform configs: wanted_browser, remember_browser, wanted_http, remember_http
- [ ] Move `from urllib.parse import urljoin` out of loop body
- **Done when:** 4 `load_and_scrape_*` functions → 2 base + 4 configs; no logic duplication between wanted/remember variants

### 3D: `_run_llm` protocol abstraction

- [ ] Define `LLMProvider` protocol: `run(prompt, timeout) -> (provider_name, output)`
- [ ] `CLIProvider` — current subprocess implementation
- [ ] Tests use a `FakeProvider` — no subprocess mock needed
- **Done when:** `auto_screening.py` calls protocol, not subprocess directly; test_auto_screening uses FakeProvider

---

## Priority 4: Large-Scale Cleanup (mechanical, low risk)

### 4A: Dual-import removal for 25 one-shot utilities

**Precondition (CRITICAL):** Caller audit — grep `build.sh`, `*.md` skill files, CI workflows, cron, CLAUDE.md for `python3 templates/.../X.py` direct invocations. Convert any found callers to `python -m` form BEFORE removing fallback imports.

- [ ] Caller audit complete — all direct invocation sites identified and migrated
- [ ] Remove `try/except ImportError` blocks from 25 one-shot utility files
- [ ] Keep dual-import in 12 core + build entry points (preserve direct-script `auto.py` compatibility during caller migration)
- [ ] Add `__main__.py` if needed for `python -m` form
- **Done when:** `grep -c 'except ImportError'` drops from 47 to ≤15; all 25 utilities run via `python -m`

### 4B: Silent exception handlers cleanup (67 remaining)

**Scope:** `except Exception: pass/continue` without any logging — NOT the Phase 5 defensive fallbacks (state loading etc.) which were deliberately kept broad.

- [ ] Add `logger.debug` to all silent `pass`/`continue` handlers
- [ ] Narrow to specific exceptions where the failure mode is known (e.g., `search_helpers:113` → `PlaywrightTimeoutError`)
- [ ] `search_helpers.py` (11 handlers) — priority target
- **Done when:** `grep 'except Exception' ... | grep -v logger` returns 0 for non-audit files; `search_helpers:113` catches timeout specifically

---

## Principles

1. **Test before refactor** — characterization test exists before any structural change to that code
2. **Same-file sequencing** — #2A before #3C (both touch search_helpers.py) to avoid double-churn
3. **Caller audit before removal** — verify no external caller breaks before removing import fallbacks
4. **Incremental delivery** — each item is independently shippable and verifiable
