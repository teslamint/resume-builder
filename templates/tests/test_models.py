"""Tests for shared domain models and dataclass inheritance."""
from dataclasses import asdict

import pytest

from models import DiscoveredJob
from search import JobPosting
from queue_utils import QueueItem


class TestDiscoveredJob:
    def test_creation(self):
        j = DiscoveredJob(job_id="1", url="u", title="t", company="c", experience="e")
        assert j.job_id == "1"
        assert j.url == "u"

    def test_asdict(self):
        j = DiscoveredJob(job_id="1", url="u", title="t", company="c", experience="e")
        d = asdict(j)
        assert d == {"job_id": "1", "url": "u", "title": "t", "company": "c", "experience": "e"}


class TestJobPostingInheritance:
    def test_inherits_discovered_job_fields(self):
        p = JobPosting(job_id="1", url="u", title="t", company="c", experience="e")
        assert isinstance(p, DiscoveredJob)
        assert p.job_id == "1"
        assert p.is_new is True
        assert p.quick_filter_result is None

    def test_asdict_flat(self):
        p = JobPosting(job_id="1", url="u", title="t", company="c", experience="e", is_new=False)
        d = asdict(p)
        assert d["job_id"] == "1"
        assert d["is_new"] is False
        assert "quick_filter_result" in d


class TestQueueItemInheritance:
    def test_inherits_discovered_job_fields(self):
        q = QueueItem(
            job_id="1", url="u", title="t", company="c", experience="e",
            query="q", discovered_at="2026-01-01",
        )
        assert isinstance(q, DiscoveredJob)
        assert q.query == "q"
        assert q.discovered_at == "2026-01-01"
        assert q.status == "pending"
        assert q.platform == "wanted"

    def test_query_and_discovered_at_required(self):
        with pytest.raises(TypeError):
            QueueItem(job_id="1", url="u", title="t", company="c", experience="e")

    def test_to_dict(self):
        q = QueueItem(
            job_id="1", url="u", title="t", company="c", experience="e",
            query="q", discovered_at="d", platform="remember",
        )
        d = q.to_dict()
        assert d["job_id"] == "1"
        assert d["query"] == "q"
        assert d["platform"] == "remember"

    def test_asdict_flat_for_json(self):
        """asdict produces flat dict suitable for JSON serialization."""
        import json
        q = QueueItem(
            job_id="1", url="u", title="t", company="c", experience="e",
            query="q", discovered_at="d",
        )
        d = asdict(q)
        json_str = json.dumps(d)
        restored = json.loads(json_str)
        assert restored == d
