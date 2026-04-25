# ce_* Platform Extractors + Generic Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract 4 platform-specific modules from company_extractor.py (798 → ~170 LOC) and replace 3× duplicated try/except/sleep with a generic extractor loop.

**Architecture:** Each platform extractor becomes a standalone module (`ce_wanted.py`, `ce_saramin.py`, `ce_thevc.py`, `ce_jd_files.py`) with uniform interface `(company_name, context) → Optional[PlatformData]`. Orchestrator loops over an `EXTRACTORS` dict. `ce_jd_files` is separate (no browser dependency).

**Tech Stack:** Python 3.12+, pytest, uv

---

### File Map

| Action | File | LOC | Responsibility |
|--------|------|-----|---------------|
| Create | `templates/jd/ce_jd_files.py` | ~90 | Offline JD file extraction + normalize_company_name |
| Create | `templates/jd/ce_wanted.py` | ~190 | Wanted platform extraction (lines 146-328) |
| Create | `templates/jd/ce_saramin.py` | ~135 | Saramin platform extraction (lines 334-462) |
| Create | `templates/jd/ce_thevc.py` | ~160 | TheVC platform extraction (lines 468-624) |
| Create | `templates/tests/test_ce_jd_files.py` | ~60 | normalize_company_name unit tests |
| Modify | `templates/jd/company_extractor.py` | 798→~170 | Delete functions, add imports, generic loop |
| Modify | `templates/tests/characterization/test_normalize_variants.py:30` | 1 line | Import path update |

### Current company_extractor.py layout (after Step 1)

```
Lines 1-40:    Imports + constants (USER_AGENT, REQUEST_DELAY, ALL_PLATFORMS, BASE_DIR, JOB_POSTINGS_DIR)
Lines 44-140:  JD files section  → ce_jd_files.py
Lines 142-328: Wanted section    → ce_wanted.py
Lines 330-462: Saramin section   → ce_saramin.py
Lines 464-624: TheVC section     → ce_thevc.py
Lines 626-758: extract_company_info (KEEP — refactor to generic loop)
Lines 760-798: main() CLI (KEEP)
```

---

### Task 1: Baseline

**Files:** (none modified)

- [ ] **Step 1: Verify 411 tests pass**

```bash
uv run python -m pytest templates/tests/ -q
```

Expected: 411 passed

---

### Task 2: Create `ce_jd_files.py` + tests

**Files:**
- Create: `templates/jd/ce_jd_files.py`
- Create: `templates/tests/test_ce_jd_files.py`

This module has no browser dependency — it reads local JD markdown files to extract investment data. Contains `normalize_company_name` (intentionally different from `naming.normalize_company_name` per retrospective §Q1).

- [ ] **Step 1: Write test_ce_jd_files.py (red)**

```python
"""Tests for ce_jd_files — offline JD file extraction and company name normalization."""
import tempfile
from pathlib import Path

from ce_types import PlatformData


class TestNormalizeCompanyName:
    """Tests for normalize_company_name (intentionally different from naming.normalize_company_name).

    This function is narrow: only strips (주)/(유)/(사) and ALL spaces.
    Does NOT remove English suffixes like Inc/Corp.
    """

    def test_strips_ju(self):
        from ce_jd_files import normalize_company_name

        assert normalize_company_name("(주)카카오") == "카카오"

    def test_strips_yu(self):
        from ce_jd_files import normalize_company_name

        assert normalize_company_name("(유)네이버") == "네이버"

    def test_strips_sa(self):
        from ce_jd_files import normalize_company_name

        assert normalize_company_name("(사)비영리단체") == "비영리단체"

    def test_strips_all_spaces(self):
        from ce_jd_files import normalize_company_name

        assert normalize_company_name("삼성 전자") == "삼성전자"

    def test_keeps_english_suffix(self):
        """Unlike naming.normalize_company_name, this does NOT remove Inc/Corp."""
        from ce_jd_files import normalize_company_name

        result = normalize_company_name("LINE Plus Corp.")
        assert "Corp" in result

    def test_empty_string(self):
        from ce_jd_files import normalize_company_name

        assert normalize_company_name("") == ""


class TestExtractFromJdFiles:
    def test_returns_none_when_no_jd_files(self):
        from ce_jd_files import extract_from_jd_files

        # Use a company name unlikely to have JD files
        result = extract_from_jd_files("NONEXISTENT_TEST_COMPANY_12345")
        assert result is None

    def test_returns_platform_data_type(self):
        """If result is not None, it should be PlatformData with platform='jd'."""
        from ce_jd_files import extract_from_jd_files

        result = extract_from_jd_files("NONEXISTENT_TEST_COMPANY_12345")
        # Can't guarantee a positive match without real JD files
        # Just verify the function doesn't crash
        assert result is None or isinstance(result, PlatformData)
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run python -m pytest templates/tests/test_ce_jd_files.py -v 2>&1 | head -5
```

Expected: FAIL — ModuleNotFoundError: No module named 'ce_jd_files'

- [ ] **Step 3: Create ce_jd_files.py**

Read `templates/jd/company_extractor.py` lines 44-140. Create `templates/jd/ce_jd_files.py` by copying these functions with these changes:
- `_normalize_company_name` → `normalize_company_name`
- `_extract_from_jd_files` → `extract_from_jd_files`
- Import `PlatformData` from `ce_types` (absolute import, matching ce_merge.py convention)
- Import `JOB_POSTINGS_DIR` from `constants` (NOT from company_extractor — canonical source)
- Add module docstring

Module header:
```python
"""Offline JD file extraction — no browser needed.

Extracts investment/revenue data from existing JD markdown files.
normalize_company_name is intentionally different from naming.normalize_company_name
(narrow regex: only (주)/(유)/(사), strips ALL spaces — see test_normalize_variants.py).
"""
from __future__ import annotations

import re
from pathlib import Path

from ce_types import PlatformData
from constants import JOB_POSTINGS_DIR
```

Replace internal references: `_normalize_company_name(` → `normalize_company_name(`

- [ ] **Step 4: Run ce_jd_files tests — verify they pass**

```bash
uv run python -m pytest templates/tests/test_ce_jd_files.py -v
```

Expected: all PASS

- [ ] **Step 5: Run full suite — no regressions**

```bash
uv run python -m pytest templates/tests/ -q
```

Expected: 411 + 8 = 419 passed

- [ ] **Step 6: Commit**

```bash
git add templates/jd/ce_jd_files.py templates/tests/test_ce_jd_files.py
git commit -m "$(cat <<'EOF'
refactor(jd): extract JD file extraction to ce_jd_files.py

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Create `ce_wanted.py`

**Files:**
- Create: `templates/jd/ce_wanted.py`

Mechanical extraction of lines 142-328 from company_extractor.py. No new tests (browser-dependent functions; existing 419 tests are safety net).

- [ ] **Step 1: Read company_extractor.py lines 142-328**

Functions to extract:
- `_search_wanted_company_id(company_name, context)` → `search_company_id`
- `_parse_next_data_company(html)` → `parse_next_data_company`
- `_extract_wanted_from_text(body_text, data)` → `extract_wanted_from_text`
- `_find_query_data(queries, prefix)` → `find_query_data`
- `_extract_wanted(company_name, context)` → `extract_wanted`

- [ ] **Step 2: Create ce_wanted.py**

Module header:
```python
"""Wanted platform company info extraction via Playwright."""
from __future__ import annotations

import json
import re
import time
from urllib.parse import quote

from ce_types import PlatformData
```

Copy all 5 functions, dropping underscore prefix. The entry point is `extract_wanted(company_name, context) → PlatformData | None`.

Internal calls update:
- `_search_wanted_company_id(` → `search_company_id(`
- `_parse_next_data_company(` → `parse_next_data_company(`
- `_extract_wanted_from_text(` → `extract_wanted_from_text(`
- `_find_query_data(` → `find_query_data(`

- [ ] **Step 3: Verify import**

```bash
PYTHONPATH=templates/jd uv run python -c "from ce_wanted import extract_wanted; print('OK')"
```

Expected: OK

- [ ] **Step 4: Commit**

```bash
git add templates/jd/ce_wanted.py
git commit -m "$(cat <<'EOF'
refactor(jd): extract Wanted platform extractor to ce_wanted.py

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Create `ce_saramin.py`

**Files:**
- Create: `templates/jd/ce_saramin.py`

Mechanical extraction of lines 330-462 from company_extractor.py.

- [ ] **Step 1: Read company_extractor.py lines 330-462**

Functions:
- `_search_saramin_csn(company_name, context)` → `search_csn`
- `_parse_saramin_benefits(body_text)` → `parse_benefits`
- `_extract_saramin(company_name, context)` → `extract_saramin`

- [ ] **Step 2: Create ce_saramin.py**

Module header:
```python
"""Saramin platform company info extraction via Playwright."""
from __future__ import annotations

import re
import time

from ce_types import PlatformData
```

Copy all 3 functions, dropping underscore prefix. Entry point: `extract_saramin(company_name, context) → PlatformData | None`.

Internal calls update:
- `_search_saramin_csn(` → `search_csn(`
- `_parse_saramin_benefits(` → `parse_benefits(`

- [ ] **Step 3: Verify import**

```bash
PYTHONPATH=templates/jd uv run python -c "from ce_saramin import extract_saramin; print('OK')"
```

- [ ] **Step 4: Commit**

```bash
git add templates/jd/ce_saramin.py
git commit -m "$(cat <<'EOF'
refactor(jd): extract Saramin platform extractor to ce_saramin.py

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Create `ce_thevc.py`

**Files:**
- Create: `templates/jd/ce_thevc.py`

Mechanical extraction of lines 464-624 from company_extractor.py. This module has an extra dependency: COMPANY_INFO_DIR (for English name lookup) and slugify_company (from naming).

- [ ] **Step 1: Read company_extractor.py lines 464-624**

Functions:
- `_search_thevc_slug_single(keyword, context)` → `search_slug_single`
- `_get_english_name_from_company_info(company_name)` → `get_english_name_from_company_info`
- `_search_thevc_slug(company_name, context)` → `search_slug`
- `_extract_thevc(company_name, context)` → `extract_thevc`

- [ ] **Step 2: Create ce_thevc.py**

Module header:
```python
"""TheVC platform company info extraction via Playwright."""
from __future__ import annotations

import re
import time
from urllib.parse import quote

from ce_types import PlatformData
from constants import COMPANY_INFO_DIR
from naming import slugify_company
```

Note: `get_english_name_from_company_info` uses `COMPANY_INFO_DIR` and `slugify_company`. Import from `constants.py` (canonical source) not from `company_validator`.

Copy all 4 functions. Internal calls:
- `_search_thevc_slug_single(` → `search_slug_single(`
- `_get_english_name_from_company_info(` → `get_english_name_from_company_info(`
- `_search_thevc_slug(` → `search_slug(`
- `_slugify_company(` → `slugify_company(`

- [ ] **Step 3: Verify import**

```bash
PYTHONPATH=templates/jd uv run python -c "from ce_thevc import extract_thevc; print('OK')"
```

- [ ] **Step 4: Commit**

```bash
git add templates/jd/ce_thevc.py
git commit -m "$(cat <<'EOF'
refactor(jd): extract TheVC platform extractor to ce_thevc.py

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Rewire company_extractor.py — generic extractor loop

**Files:**
- Modify: `templates/jd/company_extractor.py`

This is the core refactoring: delete all extracted functions, add imports from ce_* modules, replace 3× try/except/sleep with generic loop.

- [ ] **Step 1: Add ce_* imports**

Add to the try/except import block:
```python
try:
    from .ce_jd_files import extract_from_jd_files
    from .ce_merge import build_enriched_markdown, merge_platform_data
    from .ce_saramin import extract_saramin
    from .ce_thevc import extract_thevc
    from .ce_types import ExtractionResult, PlatformData
    from .ce_wanted import extract_wanted
    from .company_validator import COMPANY_INFO_DIR, parse_company_file, validate_company
    from .naming import slugify_company as _slugify_company
except ImportError:
    from ce_jd_files import extract_from_jd_files
    from ce_merge import build_enriched_markdown, merge_platform_data
    from ce_saramin import extract_saramin
    from ce_thevc import extract_thevc
    from ce_types import ExtractionResult, PlatformData
    from ce_wanted import extract_wanted
    from company_validator import COMPANY_INFO_DIR, parse_company_file, validate_company
    from naming import slugify_company as _slugify_company
```

- [ ] **Step 2: Add BROWSER_EXTRACTORS dict after constants**

```python
BROWSER_EXTRACTORS: dict[str, callable] = {
    "wanted": extract_wanted,
    "saramin": extract_saramin,
    "thevc": extract_thevc,
}
```

- [ ] **Step 3: Delete all extracted functions**

Delete these sections entirely:
- Lines 44-140: JD files section (moved to ce_jd_files.py)
- Lines 142-328: Wanted section (moved to ce_wanted.py)
- Lines 330-462: Saramin section (moved to ce_saramin.py)
- Lines 464-624: TheVC section (moved to ce_thevc.py)

Also delete now-unused imports — after extraction, orchestrator no longer uses these:
- `import json` (was only in Wanted extraction)
- `import re` (ALL regex calls were in extracted functions)
- `from urllib.parse import quote` (was only in platform URL construction)
- `from typing import Optional` (orchestrator uses PEP 604 `X | None` syntax)

Keep only: `import argparse`, `import time`, `from pathlib import Path`.

- [ ] **Step 4: Replace 3× try/except/sleep with generic loop**

Replace lines 663-705 (the three if-blocks) with:

```python
    try:
        for platform_name, extract_fn in BROWSER_EXTRACTORS.items():
            if platform_name not in platforms:
                continue
            try:
                result = extract_fn(company_name, browser_context)
                if result:
                    data_list.append(result)
                    platforms_used.append(platform_name)
                    source_urls.append(result.source_url)
                else:
                    platforms_failed.append(platform_name)
            except Exception as e:
                print(f"   [{platform_name}] 예외: {e}")
                platforms_failed.append(platform_name)
            time.sleep(REQUEST_DELAY)
    finally:
        if own_playwright:
            if browser:
                browser.close()
            if pw_instance:
                pw_instance.stop()
```

Note: original code skipped `time.sleep` after thevc (last platform). The generic loop adds it — minor behavior change (one extra 1.5s sleep), acceptable.

- [ ] **Step 5: Update JD file extraction call**

Replace `_extract_from_jd_files(company_name)` with `extract_from_jd_files(company_name)` (already imported from ce_jd_files).

- [ ] **Step 6: Remove BASE_DIR and JOB_POSTINGS_DIR**

Both are unused after extraction:
- `JOB_POSTINGS_DIR` (line 40) — only used by `_extract_from_jd_files` (now in ce_jd_files.py)
- `BASE_DIR` (line 39) — only used to define `JOB_POSTINGS_DIR`

Delete both lines.

- [ ] **Step 7: Run full test suite**

```bash
uv run python -m pytest templates/tests/ -q
```

Expected: 419 passed

- [ ] **Step 8: Verify CLI**

```bash
uv run python templates/jd/company_extractor.py --help
```

- [ ] **Step 9: Verify no circular imports**

```bash
PYTHONPATH=templates/jd uv run python -c "
from company_extractor import extract_company_info
from ce_wanted import extract_wanted
from ce_saramin import extract_saramin
from ce_thevc import extract_thevc
from ce_jd_files import extract_from_jd_files
print('All imports OK')
"
```

- [ ] **Step 10: Check LOC**

```bash
wc -l templates/jd/company_extractor.py
```

Expected: ~170 (down from 798)

- [ ] **Step 11: Commit**

```bash
git add templates/jd/company_extractor.py
git commit -m "$(cat <<'EOF'
refactor(jd): replace 3x try/except with generic extractor loop, delete extracted functions

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Update test_normalize_variants.py import

**Files:**
- Modify: `templates/tests/characterization/test_normalize_variants.py:30`

- [ ] **Step 1: Update import**

```python
# Before (line 30):
from company_extractor import _normalize_company_name as ce_normalize

# After:
from ce_jd_files import normalize_company_name as ce_normalize
```

Also update the class docstring (line 153) if it references `company_extractor._normalize_company_name`.

- [ ] **Step 2: Run characterization tests**

```bash
uv run python -m pytest templates/tests/characterization/test_normalize_variants.py -v
```

Expected: all PASS (behavior unchanged)

- [ ] **Step 3: Run full suite**

```bash
uv run python -m pytest templates/tests/ -q
```

Expected: 419 passed

- [ ] **Step 4: Commit**

```bash
git add templates/tests/characterization/test_normalize_variants.py
git commit -m "$(cat <<'EOF'
test(jd): update normalize import path to ce_jd_files

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: Final verification

**Files:** (none modified)

- [ ] **Step 1: Full test suite**

```bash
uv run python -m pytest templates/tests/ -v --tb=short 2>&1 | tail -5
```

Expected: 419 passed

- [ ] **Step 2: Dependency graph**

```bash
PYTHONPATH=templates/jd uv run python -c "
from ce_types import PlatformData
from ce_merge import merge_platform_data
from ce_jd_files import extract_from_jd_files, normalize_company_name
from ce_wanted import extract_wanted
from ce_saramin import extract_saramin
from ce_thevc import extract_thevc
from company_extractor import extract_company_info, BROWSER_EXTRACTORS
print('All OK')
print(f'BROWSER_EXTRACTORS keys: {list(BROWSER_EXTRACTORS.keys())}')
"
```

Expected:
```
All OK
BROWSER_EXTRACTORS keys: ['wanted', 'saramin', 'thevc']
```

- [ ] **Step 3: LOC summary**

```bash
wc -l templates/jd/ce_types.py templates/jd/ce_merge.py templates/jd/ce_jd_files.py templates/jd/ce_wanted.py templates/jd/ce_saramin.py templates/jd/ce_thevc.py templates/jd/company_extractor.py
```

Expected:
```
  46 ce_types.py
 291 ce_merge.py
  ~90 ce_jd_files.py
 ~190 ce_wanted.py
 ~135 ce_saramin.py
 ~160 ce_thevc.py
 ~170 company_extractor.py
~1082 total
```

Max file: ce_merge.py (291 LOC) — down from company_extractor.py (1,111 LOC before Step 1).
