# Pyright Basic Evaluation

Date: 2026-06-01

## Scope

- Installed `pyright` as a dev dependency with `uv add --dev pyright`.
- Evaluated `templates/jd` and `templates/build` with Pyright 1.1.409.
- Pyright 1.1.409 does not expose a literal `--basic` CLI flag; the evaluation uses `typeCheckingMode = "basic"` in `[tool.pyright]`, which is the supported equivalent.

## Configuration Added

`pyproject.toml` now enables basic type checking for:

- `templates/jd`
- `templates/build`

It also mirrors the existing pytest import paths through `extraPaths`:

- `templates/build`
- `templates/jd`
- `example/interview`

## Result

Command:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache uv run pyright --outputjson templates/jd templates/build
```

Summary:

- Files analyzed: 68
- Errors: 40
- Warnings: 0
- Information diagnostics: 0

The issue count is under the roadmap threshold of 50 distinct issues, so keeping the basic config is reasonable.

## Error Categories

| Rule | Count | Main files |
| --- | ---: | --- |
| `reportOptionalOperand` | 9 | `templates/build/headhunter_filler.py`, `templates/jd/search.py` |
| `reportArgumentType` | 9 | `templates/jd/search_quick.py`, `templates/build/verify_content.py`, `templates/jd/search.py` |
| `reportAttributeAccessIssue` | 5 | `templates/jd/search_quick.py`, `templates/jd/auto_company.py` |
| `reportInvalidTypeForm` | 4 | `templates/jd/verdict.py` |
| `reportCallIssue` | 4 | `templates/jd/search_quick.py` |
| `reportOptionalMemberAccess` | 3 | `templates/jd/auto.py`, `templates/jd/company_extractor.py`, `templates/jd/dedup_company_info.py` |
| `reportOperatorIssue` | 3 | `templates/jd/search.py`, `templates/jd/search_quick.py` |
| `reportGeneralTypeIssues` | 2 | `templates/jd/company_extractor.py` |
| `reportOptionalIterable` | 1 | `templates/jd/search.py` |

## Hotspots

| File | Error count | Notes |
| --- | ---: | --- |
| `templates/jd/search_quick.py` | 14 | Ambiguous return shape, list-vs-dict use, and numeric value typing. |
| `templates/build/headhunter_filler.py` | 7 | Optional values are used in string concatenation paths. |
| `templates/jd/search.py` | 6 | Optional config values need normalization before arithmetic, comparison, and iteration. |
| `templates/jd/verdict.py` | 4 | Dynamic variable aliases are used in type expressions. |
| `templates/jd/company_extractor.py` | 3 | Runtime callability/type checks and optional Playwright object access confuse Pyright. |
| `templates/build/verify_content.py` | 3 | Helper signatures do not accept `None` defaults that callers pass. |

## Recommendation

Defer adding Pyright to blocking CI for now. The basic configuration is useful for local evaluation, but CI would currently fail on 40 existing errors. A practical path is to fix the hotspots above in small follow-up patches, then add a CI job once `uv run pyright templates/jd templates/build` exits cleanly.
