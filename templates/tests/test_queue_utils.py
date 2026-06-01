"""Tests for queue_utils status validation and queue state transitions."""

import pytest

import queue_utils
from queue_utils import QueueItem, QueueStatus, load_queue, save_queue, update_item_status


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
