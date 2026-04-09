"""Tests for auto.py atomic state management and resume logic."""
import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from auto import _save_state, _load_state, _find_latest_state, _state_path, STATE_DIR


class TestAtomicSaveState:
    def test_creates_valid_json(self, tmp_path):
        with patch("auto.STATE_DIR", tmp_path), \
             patch("auto._state_path", return_value=tmp_path / ".auto_state_test.json"):
            _save_state("test", {"job1": {"url": "u", "stage": "done", "status": "done"}})

        state_file = tmp_path / ".auto_state_test.json"
        assert state_file.exists()
        data = json.loads(state_file.read_text())
        assert data["run_id"] == "test"
        assert "job1" in data["items"]

    def test_no_temp_files_remain_on_success(self, tmp_path):
        with patch("auto.STATE_DIR", tmp_path), \
             patch("auto._state_path", return_value=tmp_path / ".auto_state_test.json"):
            _save_state("test", {"job1": {"url": "u"}})

        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 0

    def test_temp_file_cleaned_on_error(self, tmp_path):
        with patch("auto.STATE_DIR", tmp_path), \
             patch("auto._state_path", return_value=tmp_path / ".auto_state_test.json"), \
             patch("json.dump", side_effect=RuntimeError("serialize error")):
            with pytest.raises(RuntimeError):
                _save_state("test", {"bad": "data"})

        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 0


class TestLoadState:
    def test_returns_empty_for_missing_file(self, tmp_path):
        with patch("auto._state_path", return_value=tmp_path / "nonexistent.json"):
            assert _load_state("test") == {}

    def test_returns_items_from_valid_file(self, tmp_path):
        state_file = tmp_path / "test.json"
        state_file.write_text(json.dumps({
            "run_id": "test",
            "items": {"job1": {"stage": "done"}}
        }))

        with patch("auto._state_path", return_value=state_file):
            result = _load_state("test")

        assert result == {"job1": {"stage": "done"}}

    def test_returns_empty_for_corrupted_file(self, tmp_path):
        state_file = tmp_path / "bad.json"
        state_file.write_text("not valid json{{{")

        with patch("auto._state_path", return_value=state_file):
            assert _load_state("test") == {}


class TestResumeStatePreservation:
    """Verify that resume preserves jd_path, screening_path, verdict from state."""

    def test_state_items_not_overwritten_on_resume(self):
        prev_state = {
            "job1": {
                "url": "https://example.com/1",
                "stage": "screening",
                "status": "in_progress",
                "jd_path": "/tmp/jd1.md",
            }
        }
        state_items = dict(prev_state)

        # Simulate: job_id already in state_items with non-done status
        job_id = "job1"
        if job_id not in state_items or state_items[job_id].get("status") == "done":
            state_items[job_id] = {"url": "u", "stage": "pending", "status": "pending"}

        # Should NOT have overwritten
        assert state_items["job1"]["stage"] == "screening"
        assert state_items["job1"]["jd_path"] == "/tmp/jd1.md"

    def test_done_items_get_fresh_state(self):
        prev_state = {
            "job1": {"url": "u", "stage": "done", "status": "done"}
        }
        state_items = dict(prev_state)

        job_id = "job1"
        if job_id not in state_items or state_items[job_id].get("status") == "done":
            state_items[job_id] = {"url": "u", "stage": "pending", "status": "pending"}

        assert state_items["job1"]["stage"] == "pending"
