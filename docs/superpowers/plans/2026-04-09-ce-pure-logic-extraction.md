# ce_types + ce_merge Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract 280 LOC of pure computation (merge priority logic + markdown generation) from the 1,111-LOC `company_extractor.py` into testable modules, preventing circular imports with a leaf types module.

**Architecture:** `ce_types.py` (leaf, stdlib-only dataclasses) -> `ce_merge.py` (pure logic, imports ce_types) -> `company_extractor.py` (orchestrator, imports both). TDD: tests written before moving code to verify behavior is preserved.

**Tech Stack:** Python 3.12+, pytest, uv

---

### File Map

| Action | File | Responsibility | LOC |
|--------|------|---------------|-----|
| Create | `templates/jd/ce_types.py` | PlatformData + ExtractionResult dataclasses (leaf) | ~30 |
| Create | `templates/jd/ce_merge.py` | merge_platform_data + build_enriched_markdown (pure) | ~180 |
| Modify | `templates/jd/company_extractor.py` | Remove moved code, add imports | 1111 -> ~830 |
| Create | `templates/tests/test_ce_merge.py` | Merge priority unit tests | ~120 |
| Create | `templates/tests/test_ce_merge_roundtrip.py` | Markdown gen <-> validator parse roundtrip | ~80 |

---

### Task 1: Baseline — verify all tests pass

**Files:** (none modified)

- [ ] **Step 1: Run existing test suite**

```bash
uv run python -m pytest templates/tests/ -v
```

Expected: all tests PASS. Record count for comparison later.

- [ ] **Step 2: Commit baseline (empty)**

```bash
git commit --allow-empty -m "chore: baseline before ce_types/ce_merge extraction"
```

---

### Task 2: Create `ce_types.py`

**Files:**
- Create: `templates/jd/ce_types.py`

- [ ] **Step 1: Write ce_types.py**

```python
"""Shared data types for company extractor modules.

Leaf module — stdlib only, no local imports.
Prevents circular imports when company_extractor.py and ce_*.py need the same types.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PlatformData:
    """Data extracted from a single platform."""

    platform: str  # "wanted" | "saramin" | "thevc" | "jd"
    source_url: str
    company_name: str
    company_name_en: str | None = None
    industry: str | None = None
    founded_year: int | None = None
    employee_count: int | None = None
    employee_joined_1y: int | None = None
    employee_left_1y: int | None = None
    avg_salary: int | None = None  # 만원
    salary_percentile: str | None = None
    revenue: list[dict] | None = None  # [{year, amount_억}]
    investment_round: str | None = None
    investment_total: str | None = None  # "N억원"
    investors: list[str] = field(default_factory=list)
    benefits: list[str] = field(default_factory=list)
    description: str | None = None
    tags: list[str] = field(default_factory=list)
    raw_extra: dict = field(default_factory=dict)


@dataclass
class ExtractionResult:
    """Result of a company info extraction run."""

    company: str
    file_path: Path
    completeness: float
    platforms_used: list[str]
    platforms_failed: list[str]
    source_urls: list[str]
```

- [ ] **Step 2: Verify import works**

```bash
uv run python -c "from ce_types import PlatformData, ExtractionResult; print('OK:', PlatformData.__name__)"
```

Expected: `OK: PlatformData`

- [ ] **Step 3: Commit**

```bash
git add templates/jd/ce_types.py
git commit -m "refactor(jd): extract PlatformData and ExtractionResult to ce_types.py"
```

---

### Task 3: Write merge priority tests (TDD — tests first)

**Files:**
- Create: `templates/tests/test_ce_merge.py`

These tests target functions that don't exist yet in `ce_merge.py`. They will fail until Task 5.

- [ ] **Step 1: Write test_ce_merge.py**

```python
"""Unit tests for ce_merge — merge priority logic and markdown generation."""
import pytest

from ce_types import PlatformData


def _make(platform, **kwargs):
    """Helper: create PlatformData with defaults."""
    return PlatformData(platform=platform, source_url=f"https://{platform}.test", company_name="TestCo", **kwargs)


class TestMergePlatformData:
    """Tests for merge_platform_data priority rules."""

    def test_wanted_salary_over_saramin(self):
        """Wanted salary has priority (국민연금 기반)."""
        from ce_merge import merge_platform_data

        result = merge_platform_data([_make("wanted", avg_salary=5000), _make("saramin", avg_salary=4000)])
        assert result["avg_salary"] == 5000

    def test_thevc_investment_over_wanted(self):
        """TheVC investment data has priority."""
        from ce_merge import merge_platform_data

        result = merge_platform_data([_make("wanted", investment_round="Series A"), _make("thevc", investment_round="Series B")])
        assert result["investment_round"] == "Series B"

    def test_saramin_industry_over_wanted(self):
        """Saramin industry uses standard classification."""
        from ce_merge import merge_platform_data

        result = merge_platform_data([_make("wanted", industry="IT"), _make("saramin", industry="소프트웨어 개발")])
        assert result["industry"] == "소프트웨어 개발"

    def test_saramin_benefits_over_wanted(self):
        """Saramin benefits are richest."""
        from ce_merge import merge_platform_data

        result = merge_platform_data([_make("wanted", benefits=["식대"]), _make("saramin", benefits=["식대", "통근버스", "자기개발비"])])
        assert result["benefits"] == ["식대", "통근버스", "자기개발비"]

    def test_jd_investment_lowest_priority(self):
        """JD file extraction is fallback for investment."""
        from ce_merge import merge_platform_data

        result = merge_platform_data([_make("jd", investment_round="Seed"), _make("wanted", investment_round="Series A")])
        assert result["investment_round"] == "Series A"

    def test_jd_fallback_when_no_other_source(self):
        """JD fills investment when no other platform has it."""
        from ce_merge import merge_platform_data

        result = merge_platform_data([_make("wanted"), _make("jd", investment_round="Series B", investment_total="100억원")])
        assert result["investment_round"] == "Series B"
        assert result["investment_total"] == "100억원"

    def test_single_platform(self):
        """Single source fills all available fields."""
        from ce_merge import merge_platform_data

        result = merge_platform_data([_make("wanted", avg_salary=5000, founded_year=2018, employee_count=150)])
        assert result["avg_salary"] == 5000
        assert result["founded_year"] == 2018
        assert result["employee_count"] == 150

    def test_empty_input(self):
        """Empty list returns all-None/empty merged dict."""
        from ce_merge import merge_platform_data

        result = merge_platform_data([])
        assert result["company_name"] == ""
        assert result["avg_salary"] is None
        assert result["investors"] == []

    def test_saramin_raw_extra_fields(self):
        """Saramin-only fields (ceo, location) via raw_extra."""
        from ce_merge import merge_platform_data

        result = merge_platform_data([_make("saramin", raw_extra={"ceo": "홍길동", "location": "서울"})])
        assert result["raw_extra"]["ceo"] == "홍길동"
        assert result["raw_extra"]["location"] == "서울"

    def test_source_urls_accumulated(self):
        """All platform source URLs are collected."""
        from ce_merge import merge_platform_data

        result = merge_platform_data([_make("wanted"), _make("saramin"), _make("thevc")])
        assert len(result["source_urls"]) == 3


class TestFmt:
    def test_none_returns_info_missing(self):
        from ce_merge import fmt

        assert fmt(None) == "정보 없음"

    def test_value_with_suffix(self):
        from ce_merge import fmt

        assert fmt(150, "명") == "150명"

    def test_value_without_suffix(self):
        from ce_merge import fmt

        assert fmt("IT") == "IT"


class TestBuildEnrichedMarkdown:
    def test_contains_company_info_section(self):
        from ce_merge import build_enriched_markdown, merge_platform_data

        merged = merge_platform_data([_make("wanted", industry="IT", founded_year=2020)])
        md = build_enriched_markdown(merged, "테스트회사", ["https://example.com"])
        assert "## 기업 정보" in md
        assert "| 업종 | IT |" in md

    def test_salary_bold_format(self):
        """Salary must be in **N만원** bold format for validator compatibility."""
        from ce_merge import build_enriched_markdown, merge_platform_data

        merged = merge_platform_data([_make("wanted", avg_salary=5200)])
        md = build_enriched_markdown(merged, "A", [])
        assert "**5,200만원**" in md

    def test_no_investment_section_when_empty(self):
        """투자 정보 section is omitted when no investment data."""
        from ce_merge import build_enriched_markdown, merge_platform_data

        merged = merge_platform_data([_make("wanted")])
        md = build_enriched_markdown(merged, "A", [])
        assert "## 투자 정보" not in md

    def test_investment_section_present(self):
        from ce_merge import build_enriched_markdown, merge_platform_data

        merged = merge_platform_data([_make("thevc", investment_round="Series A", investment_total="50억원")])
        md = build_enriched_markdown(merged, "A", [])
        assert "## 투자 정보" in md
        assert "Series A" in md
```

- [ ] **Step 2: Run tests — verify they fail (ce_merge doesn't exist yet)**

```bash
uv run python -m pytest templates/tests/test_ce_merge.py -v 2>&1 | head -5
```

Expected: FAIL — `ModuleNotFoundError: No module named 'ce_merge'`

- [ ] **Step 3: Commit test file**

```bash
git add templates/tests/test_ce_merge.py
git commit -m "test(jd): add merge priority and markdown generation tests (red)"
```

---

### Task 4: Write roundtrip tests (TDD — tests first)

**Files:**
- Create: `templates/tests/test_ce_merge_roundtrip.py`

Tests that generate markdown via `build_enriched_markdown` then parse it back via `company_validator.parse_company_file`. Verifies the 11 coupled fields.

- [ ] **Step 1: Write test_ce_merge_roundtrip.py**

```python
"""Roundtrip tests: build_enriched_markdown -> parse_company_file.

Verifies markdown format stays compatible with company_validator regex parsing.
Currently 0 existing roundtrip coverage. These 11 fields are coupled by
format (bold salary **만원**, section headers ## 기업 정보, year format YYYY년).
"""
import tempfile
from pathlib import Path

from ce_types import PlatformData
from company_validator import parse_company_file


def _make(platform="wanted", **kwargs):
    return PlatformData(platform=platform, source_url="https://test.com", company_name="테스트회사", **kwargs)


def _roundtrip(data_list, company_name="테스트회사"):
    """Generate markdown -> write temp file -> parse back -> return CompanyData."""
    from ce_merge import build_enriched_markdown, merge_platform_data

    merged = merge_platform_data(data_list)
    markdown = build_enriched_markdown(merged, company_name, ["https://example.com"])
    tmp = tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False, encoding="utf-8")
    tmp.write(markdown)
    tmp.close()
    return parse_company_file(Path(tmp.name))


class TestRoundTrip:
    def test_company_name(self):
        result = _roundtrip([_make()])
        assert result.name == "테스트회사"

    def test_company_name_en(self):
        result = _roundtrip([_make(company_name_en="TestCo")])
        assert result.name_en == "TestCo"

    def test_industry(self):
        result = _roundtrip([_make(industry="소프트웨어 개발")])
        assert result.industry == "소프트웨어 개발"

    def test_founded_year(self):
        result = _roundtrip([_make(founded_year=2018)])
        assert result.founded_year == 2018

    def test_employee_count(self):
        result = _roundtrip([_make(employee_count=150)])
        assert result.employee_current == 150

    def test_employee_joined(self):
        result = _roundtrip([_make(employee_joined_1y=30)])
        assert result.employee_joined_1y == 30

    def test_employee_left(self):
        result = _roundtrip([_make(employee_left_1y=10)])
        assert result.employee_left_1y == 10

    def test_salary_bold_format(self):
        """Validator regex requires **N만원** bold format."""
        result = _roundtrip([_make(avg_salary=5200)])
        assert result.avg_salary == 5200

    def test_salary_percentile(self):
        result = _roundtrip([_make(avg_salary=5200, salary_percentile="15")])
        # parse_company_file returns float for percentile
        assert result.salary_percentile == "15"

    def test_investment_round(self):
        result = _roundtrip([_make(platform="thevc", investment_round="Series B")])
        assert result.investment_round == "Series B"

    def test_investment_total(self):
        result = _roundtrip([_make(platform="thevc", investment_total="298억원")])
        assert result.investment_total is not None

    def test_full_data_roundtrip(self):
        """All 11 coupled fields in one roundtrip."""
        data = _make(
            company_name_en="TestCo",
            industry="IT",
            founded_year=2020,
            employee_count=200,
            employee_joined_1y=50,
            employee_left_1y=20,
            avg_salary=6000,
            salary_percentile="10",
        )
        thevc = _make(platform="thevc", investment_round="Series A", investment_total="100억원")
        result = _roundtrip([data, thevc])
        assert result.name == "테스트회사"
        assert result.founded_year == 2020
        assert result.employee_current == 200
        assert result.avg_salary == 6000
        assert result.investment_round == "Series A"
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run python -m pytest templates/tests/test_ce_merge_roundtrip.py -v 2>&1 | head -5
```

Expected: FAIL — `ModuleNotFoundError: No module named 'ce_merge'`

- [ ] **Step 3: Commit**

```bash
git add templates/tests/test_ce_merge_roundtrip.py
git commit -m "test(jd): add roundtrip tests for markdown gen <-> validator parse (red)"
```

---

### Task 5: Create `ce_merge.py` — make tests green

**Files:**
- Create: `templates/jd/ce_merge.py`

Move the three functions from `company_extractor.py` lines 659-936. Remove underscore prefix. Use relative imports.

- [ ] **Step 1: Write ce_merge.py**

Copy lines 659-936 from `company_extractor.py` into new file with these changes:
- Add module docstring and imports (`from __future__ import annotations`, `from datetime import date`, `from .ce_types import PlatformData`)
- `_merge_platform_data` -> `merge_platform_data`
- `_build_enriched_markdown` -> `build_enriched_markdown`
- `_fmt` -> `fmt`
- No other code changes — identical logic

```python
"""Pure computation: merge multi-platform company data and generate markdown.

Zero I/O. All functions are pure — given inputs, produce outputs.
The markdown format is coupled with company_validator.parse_company_file regex.
See test_ce_merge_roundtrip.py for format contract verification.
"""
from __future__ import annotations

from datetime import date

from .ce_types import PlatformData


def merge_platform_data(data_list: list[PlatformData]) -> dict:
    # ... exact copy of lines 660-790 from company_extractor.py
    # (only change: function name, no underscore prefix)


def fmt(value, suffix: str = "") -> str:
    # ... exact copy of lines 793-797


def build_enriched_markdown(merged: dict, company_name: str, source_urls: list[str]) -> str:
    # ... exact copy of lines 800-936
    # (internal call: _fmt -> fmt)
```

Full source: copy verbatim from `company_extractor.py:659-936`, applying only the renames listed above.

- [ ] **Step 2: Run ce_merge tests**

```bash
uv run python -m pytest templates/tests/test_ce_merge.py templates/tests/test_ce_merge_roundtrip.py -v
```

Expected: all PASS

- [ ] **Step 3: Run full test suite to check no regressions**

```bash
uv run python -m pytest templates/tests/ -v
```

Expected: same pass count as baseline (Task 1)

- [ ] **Step 4: Commit**

```bash
git add templates/jd/ce_merge.py
git commit -m "feat(jd): add ce_merge.py with merge priority logic and markdown generation (green)"
```

---

### Task 6: Rewire `company_extractor.py`

**Files:**
- Modify: `templates/jd/company_extractor.py:22-27` (imports)
- Modify: `templates/jd/company_extractor.py:41-71` (delete dataclass defs)
- Modify: `templates/jd/company_extractor.py:655-936` (delete moved functions)
- Modify: `templates/jd/company_extractor.py:1037-1038` (update call sites)

- [ ] **Step 1: Add ce_types and ce_merge imports**

In `company_extractor.py`, add to the `try/except` import block (after line 21):

```python
try:
    from .ce_types import ExtractionResult, PlatformData
    from .ce_merge import build_enriched_markdown, fmt, merge_platform_data
    from .company_validator import COMPANY_INFO_DIR, parse_company_file, validate_company
    from .naming import slugify_company as _slugify_company
except ImportError:
    from ce_types import ExtractionResult, PlatformData
    from ce_merge import build_enriched_markdown, fmt, merge_platform_data
    from company_validator import COMPANY_INFO_DIR, parse_company_file, validate_company
    from naming import slugify_company as _slugify_company
```

- [ ] **Step 2: Delete dataclass definitions (lines 41-71)**

Remove the `PlatformData` and `ExtractionResult` class definitions. They now live in `ce_types.py`.

- [ ] **Step 3: Delete merge/markdown functions (lines 655-936)**

Remove:
- `_merge_platform_data` function (lines 659-790)
- `_fmt` function (lines 793-797)
- `_build_enriched_markdown` function (lines 800-936)
- The section comment `# Merge + Markdown generation` (lines 655-657)

- [ ] **Step 4: Update call sites (around line 1037-1038)**

```python
# Before:
merged = _merge_platform_data(data_list)
markdown = _build_enriched_markdown(merged, company_name, source_urls)

# After:
merged = merge_platform_data(data_list)
markdown = build_enriched_markdown(merged, company_name, source_urls)
```

- [ ] **Step 5: Run full test suite**

```bash
uv run python -m pytest templates/tests/ -v
```

Expected: all PASS (same count as baseline + new ce_merge tests)

- [ ] **Step 6: Verify CLI still works**

```bash
uv run python templates/jd/company_extractor.py --help
```

Expected: prints help text without errors

- [ ] **Step 7: Verify no circular imports**

```bash
uv run python -c "from ce_types import PlatformData; print('ce_types OK')"
uv run python -c "from ce_merge import merge_platform_data; print('ce_merge OK')"
uv run python -c "from company_extractor import extract_company_info; print('company_extractor OK')"
```

Expected: all print OK

- [ ] **Step 8: Verify LOC reduction**

```bash
wc -l templates/jd/ce_types.py templates/jd/ce_merge.py templates/jd/company_extractor.py
```

Expected: `~30 + ~180 + ~830 = ~1040` (vs 1,111 before)

- [ ] **Step 9: Commit**

```bash
git add templates/jd/company_extractor.py
git commit -m "refactor(jd): rewire company_extractor.py to use ce_types and ce_merge"
```

---

### Task 7: Final verification

**Files:** (none modified)

- [ ] **Step 1: Full test suite with coverage**

```bash
uv run python -m pytest templates/tests/ -v --tb=short
```

Expected: all PASS

- [ ] **Step 2: Verify dependency graph (no cycles)**

```bash
uv run python -c "
from ce_types import PlatformData, ExtractionResult
from ce_merge import merge_platform_data, build_enriched_markdown, fmt
from company_extractor import extract_company_info
# If this runs without ImportError, no circular imports
print('Dependency graph: OK')
print(f'PlatformData fields: {len(PlatformData.__dataclass_fields__)}')
print(f'merge_platform_data: {merge_platform_data.__module__}')
print(f'extract_company_info: {extract_company_info.__module__}')
"
```

Expected:
```
Dependency graph: OK
PlatformData fields: 19
merge_platform_data: ce_merge
extract_company_info: company_extractor
```
