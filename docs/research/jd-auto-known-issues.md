# JD Auto Pipeline — Known Issues Backlog

Surfaced during the 2026-04-27/28 incident triage of `templates/jd/auto.py`. Each item is reproducible, has a clear root cause, and a suggested fix that was deliberately deferred to keep the patch surface minimal during the headhunting-gate fix.

## 1. `_find_latest_state` selects the wrong run when both timestamp and tag-based state files coexist

- **Status**: **Resolved 2026-04-28** (branch `jd-screening-experience-match`)
- **Location**: `templates/jd/auto.py:98-115` (`_find_latest_state`)
- **Symptom**: `python3 templates/jd/auto.py --resume` retried items from a stale `jd-batch-...` run instead of the most recent timestamp-prefixed run, even though the timestamp run was newer in wall-clock time.
- **Root cause**: `sorted(state_files, reverse=True)` sorts by filename lexically. Because `j > 2` in ASCII, every file named `.auto_state_jd-batch-*.json` is ordered before `.auto_state_2026MMDD_HHMMSS.json` regardless of mtime. The first file with any non-`done` item is returned.
- **Fix**: Replaced `sorted(state_files, reverse=True)` with `sorted(state_files, key=lambda p: p.stat().st_mtime, reverse=True)`. Regression test added: `templates/tests/test_auto_state.py::TestFindLatestStateMtime`.

## 2. `find_existing_jd` excludes `unprocessed/` from its search path

- **Status**: **Resolved 2026-04-28** (branch `jd-screening-experience-match`)
- **Location**: `templates/jd/path_utils.py:97-121` (`find_existing_jd`), `templates/jd/auto.py:176-180` (`_resolve_jd_path_for_screening`)
- **Symptom**: `--screening-only --from-urls <urls>` raises `screening-only 모드에서 기존 JD를 찾지 못했습니다` even when the JD file is on disk under `private/job_postings/unprocessed/`.
- **Root cause**: `search_dirs` did not include `unprocessed/`. Newly extracted JDs that have not yet been classified are invisible to `_resolve_jd_path_for_screening`.
- **Fix**: Added `find_jd_anywhere(job_id)` in `path_utils.py` — same search pattern as `find_existing_jd` plus `unprocessed/` appended last. `_resolve_jd_path_for_screening` in `auto.py` now calls `find_jd_anywhere` instead of `find_existing_jd`. The dedup check at `auto.py:484` still uses `find_existing_jd` (unchanged) so unprocessed JDs are not treated as duplicates. Regression tests added: `templates/tests/test_jd_auto.py::TestScreeningOnlyFindsUnprocessed`.

## 3. Result JSON `jd_path` is a snapshot of extraction time, not the final on-disk location

- **Status**: **Resolved 2026-04-28** (branch `jd-screening-experience-match`)
- **Location**: `templates/jd/auto.py` (classification block, lines 627-640)
- **Symptom**: `auto_<run_id>.json` records `jd_path` as `private/job_postings/unprocessed/...` even when the classification step has subsequently moved the file to `pass/`, `conditional/hold/`, etc.
- **Root cause**: The result row was populated immediately after extraction and not refreshed after the classifier moved the file.
- **Fix**: After `_classify` returns a non-empty `classified` folder, `find_existing_jd(job_id)` is called to resolve the new path, and both `row.jd_path` and `state_items[job_id]["jd_path"]` are updated before `_save_state`. Regression test added: `templates/tests/test_jd_auto.py::TestAutoJdPathAfterClassify`.

## 4. `ce_saramin` Playwright session is rejected by Saramin's anti-bot redirect

- **Status**: **Resolved 2026-04-28** — main pipeline decoupled from Saramin failures via enrichment queue (Path H). 4차 Patchright + headed mode bypass confirmed: AB180 extracted successfully (1,104명, 복지 7개 항목).
- **Location**: `templates/jd/ce_saramin.py:20` and `:66` (the two `page.goto(... wait_until="domcontentloaded", timeout=20000)` calls).
- **Symptom**: every Saramin extraction attempt times out after 20s. Confirmed across multiple sessions on 2026-04-27 22:15 (4 companies: 유모스원, AB180, 에임인텔리전스, and another), 2026-04-28 00:47 (348459 유모스원 probe), and was also the latent cause of the 티맥스소프트 18:01 stub fallback (where both Wanted *and* Saramin failed, producing 0%/`none`).
- **Root cause** (verified): a direct `curl https://www.saramin.co.kr/zf_user/search/company?searchword=test` returns `HTTP/1.1 307 Temporary Redirect` with no `Location` header and a 96-byte body containing only `<meta http-equiv="refresh" content="0;url=https://www.saramin.co.kr/error/HTTP_BAD_REQUEST.php">`. Saramin treats non-browser-shaped requests as bad and bounces them via meta-refresh. Playwright running with default headless settings appears to fall into the same bucket and never reaches `domcontentloaded` on the target page.
- **Reproduction**:
  ```bash
  curl -sS --max-time 30 "https://www.saramin.co.kr/zf_user/search/company?searchword=test"
  # Body is the meta-refresh to /error/HTTP_BAD_REQUEST.php
  ```
  Or run `python3 templates/jd/auto.py --from-urls <single-wanted-url> 2>&1 | grep saramin` and observe the `Page.goto: Timeout 20000ms exceeded` from `ce_saramin`.
- **Applied partial fix**: `--disable-blink-features=AutomationControlled` added to `company_extractor.py` Chromium launch args. No effect on Saramin's gate.
- **Fix history**:
  - 1차 2026-04-28: `--disable-blink-features=AutomationControlled` — no effect
  - 2차 2026-04-28: `playwright-stealth` v2.0.3 — no effect
  - 3차 2026-04-28: Cookie warm-up probe — **가설 기각**. `page.goto("https://www.saramin.co.kr/")` itself times out (main page blocked, not just the search endpoint). Cookie acquisition is impossible; the gate operates before any session is established.
  - 4차 2026-04-28: Patchright drop-in via dedicated backfill script (`enrich_saramin_company_info.py`) — **성공**. AB180 추출 확인 (csn 획득, 직원수·복지 파싱 정상).
- **Current mitigation (Path H)**:
  - `auto_company.py` routes Saramin failures to `private/job_postings/unprocessed/company_enrichment_saramin.txt` queue.
  - Main pipeline proceeds with Wanted-only data when Saramin fails; no longer blocked.
  - Static User-Agent override removed from `company_extractor.py` (Chrome 131 string vs bundled Chromium version mismatch was itself a bot signal).
- **Backfill path (Path B)**:
  - `templates/jd/enrich_saramin_company_info.py` — dedicated script, reads from saramin queue, uses Patchright + `--headed` option.
  - Setup (one-time): `uv sync && uv run patchright install chromium`
  - Run: `uv run python3 templates/jd/enrich_saramin_company_info.py --headed --limit 3`
  - Kill criterion: if 0/3 companies succeed with Patchright + headed, status → `Mitigated (Saramin permanently best-effort)`.
- **Tmaxsoft caveat**: 티맥스소프트's stub at `private/company_info/티맥스소프트.md` shows every field as `정보 없음`, indicating *both* Wanted and Saramin extraction failed — not just Saramin. Fixing Saramin alone will not unblock those JDs; their resolution likely needs a Wanted company-name normalization or a manual company info entry. This is a separate lane from issue #4.
