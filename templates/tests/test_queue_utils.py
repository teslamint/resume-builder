"""Tests for queue_utils status validation and queue state transitions."""

from unittest.mock import call, patch

import pytest

import queue_utils
from queue_utils import QueueItem, QueueStatus, _append_to_queue, load_queue, save_queue, update_item_status


def _queue_item(job_id: str = "job-1", status: QueueStatus = QueueStatus.PENDING) -> dict:
    return QueueItem(
        job_id=job_id,
        url=f"https://example.com/{job_id}",
        title="Backend Engineer",
        company="TestCo",
        experience="경력 무관",
        query="backend",
        discovered_at="2026-01-01T00:00:00",
        status=status,
    ).to_dict()


@pytest.fixture
def queue_path(tmp_path, monkeypatch):
    path = tmp_path / "queue.json"
    monkeypatch.setattr(queue_utils, "QUEUE_PATH", path)
    return path


def test_pending_processing_done_transition(queue_path):
    assert save_queue([_queue_item()])

    assert update_item_status("job-1", QueueStatus.PROCESSING)
    items = load_queue()
    assert items[0]["status"] == QueueStatus.PROCESSING.value

    assert update_item_status("job-1", QueueStatus.DONE, result="saved.md")
    items = load_queue()
    assert items[0]["status"] == QueueStatus.DONE.value
    assert items[0]["result"] == "saved.md"


def test_pending_processing_failed_transition(queue_path):
    assert save_queue([_queue_item()])

    assert update_item_status("job-1", QueueStatus.PROCESSING)
    assert update_item_status("job-1", QueueStatus.FAILED, result="extraction_failed")

    items = load_queue()
    assert items[0]["status"] == QueueStatus.FAILED.value
    assert items[0]["result"] == "extraction_failed"


def test_invalid_queue_item_status_raises_value_error():
    with pytest.raises(ValueError, match="Invalid queue status"):
        QueueItem(
            job_id="job-1",
            url="https://example.com/job-1",
            title="Backend Engineer",
            company="TestCo",
            experience="경력 무관",
            query="backend",
            discovered_at="2026-01-01T00:00:00",
            status="unknown",
        )


def test_invalid_update_status_raises_value_error(queue_path):
    assert save_queue([_queue_item()])

    with pytest.raises(ValueError, match="Invalid queue status"):
        update_item_status("job-1", "unknown")


def test_append_to_queue_appends_new_company(tmp_path):
    queue_path = tmp_path / "company_enrichment_saramin.txt"

    _append_to_queue(queue_path, "테스트회사")

    assert queue_path.exists()
    assert queue_path.read_text(encoding="utf-8").splitlines() == ["테스트회사"]


def test_append_to_queue_deduplicates_existing_company(tmp_path):
    queue_path = tmp_path / "company_enrichment_saramin.txt"
    queue_path.write_text("테스트회사\n", encoding="utf-8")

    _append_to_queue(queue_path, "테스트회사")
    _append_to_queue(queue_path, "테스트회사")

    lines = [line for line in queue_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert lines.count("테스트회사") == 1


def test_append_to_queue_appends_multiple_different_companies(tmp_path):
    queue_path = tmp_path / "company_enrichment_saramin.txt"

    _append_to_queue(queue_path, "회사A")
    _append_to_queue(queue_path, "회사B")

    lines = [line for line in queue_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert "회사A" in lines
    assert "회사B" in lines
    assert len(lines) == 2


def test_append_to_queue_uses_exclusive_lock(tmp_path):
    queue_path = tmp_path / "company_enrichment_thevc.txt"

    with patch.object(queue_utils.fcntl, "flock") as mock_flock:
        _append_to_queue(queue_path, "락테스트회사")

    assert mock_flock.call_count == 2
    assert mock_flock.mock_calls[0] == call(mock_flock.mock_calls[0].args[0], queue_utils.fcntl.LOCK_EX)
    assert mock_flock.mock_calls[1] == call(mock_flock.mock_calls[1].args[0], queue_utils.fcntl.LOCK_UN)
