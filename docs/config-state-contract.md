# JD Config and State File Contract

This contract separates user-authored inputs from derived runtime state in the
JD automation pipeline. Runtime code should write only the derived files listed
here.

## User-Authored Inputs

| File | Owner | Readers | Write contract |
|------|-------|---------|----------------|
| `private/job_postings/search_config.yaml` | User configuration | `templates/jd/search.py`, `templates/jd/search_quick.py`, `templates/jd/quick_filter.py`, `templates/jd/worker.py` through `templates/jd/constants.py::CONFIG_PATH` and `search_helpers._read_search_config()` | Runtime code reads this file only. Edit it manually when changing search queries, platform settings, quick filters, or state-file configuration. |
| `private/job_postings/jd-screening-rules.md` | User screening policy | `templates/jd/jd_content.py::load_screening_rules()` and screening/pre-screening flows | Runtime code reads this file only. Edit it manually when changing screening criteria. |

## Derived State

| File | Write owner | Readers | Lifecycle |
|------|-------------|---------|-----------|
| `private/job_postings/queue.json` | `templates/jd/queue_utils.py` write primitives: `save_queue()` and `update_item_status()` | `templates/jd/search_quick.py`, `templates/jd/worker.py` | Search quick mode creates queued items through `QueueItem` and persists them through `save_queue()`. Worker processing updates item status through `update_item_status()`. Other modules should not hand-edit queue JSON. |
| `private/jd_analysis/screening/SUMMARY.md` | `templates/jd/jd_content.py::update_summary()` | JD audit/status scripts and human review | Screening writes append summary rows through `update_summary()`. One-off maintenance scripts may repair legacy rows, but normal pipeline code should call `update_summary()` instead of writing the file directly. |
| `private/job_postings/.search_state.json` | `templates/jd/search.py::save_state()` and compatible search quick flows | Search flows | Stores seen job IDs and search counters so repeated searches can deduplicate previously observed postings. It is derived from search execution and can be rebuilt only by accepting duplicate discovery churn. |
| `private/job_postings/.auto_state_<run_id>.json` | `templates/jd/auto.py::_save_state()` and `_cleanup_state()` | `templates/jd/auto.py` resume flow | Stores per-run item progress for `--resume`. `auto.py` deletes the file on successful completion through `_cleanup_state()`. |
| `private/job_postings/auto_results/auto_<run_id>.json` | `templates/jd/auto.py::_save_result()` | Humans, automation memory, follow-up diagnostics | Immutable run summary for a completed or partially completed automation run. Use this as evidence for what a run actually did. |

## Rules

- Constants for canonical paths live in `templates/jd/constants.py` when shared
  across modules.
- User-authored inputs are not mutated by automation.
- Derived state writes should go through the module owner above so locking,
  timestamping, and status semantics stay centralized.
- Tests should patch these path constants or owner functions to temporary
  directories instead of writing under `private/`.
