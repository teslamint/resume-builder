"""Tests for notifications module."""
from dataclasses import dataclass
from unittest.mock import patch
from subprocess import CompletedProcess

from notifications import send_notification, format_notification


@dataclass
class FakeResult:
    url: str = "https://example.com"
    verdict: str = ""
    title: str = ""
    company: str = ""
    job_id: str = "12345"


@dataclass
class FakeSummary:
    new: int = 0
    processed: int = 0
    recommended: int = 0
    hold: int = 0
    passed: int = 0


class TestFormatNotification:
    def test_basic_format(self):
        results = [FakeResult(verdict="지원 추천", title="Backend Dev", company="TestCo")]
        summary = FakeSummary(new=5, processed=3, recommended=1, hold=1, passed=1)
        msg = format_notification(results, summary)

        assert "JD 자동 파이프라인 결과" in msg
        assert "신규 URL: 5개" in msg
        assert "추천: 1개" in msg
        assert "[TestCo] Backend Dev" in msg

    def test_no_recommended(self):
        results = [FakeResult(verdict="지원 비추천")]
        summary = FakeSummary(new=1, processed=1, recommended=0)
        msg = format_notification(results, summary)
        assert "지원 추천 공고" not in msg


class TestSendNotification:
    def test_missing_channel(self):
        ok = send_notification("hello", {"notifications": {}})
        assert ok is False

    def test_missing_target(self):
        ok = send_notification("hello", {"notifications": {"channel": "slack"}})
        assert ok is False

    def test_success(self):
        config = {"notifications": {"channel": "slack", "target": "ch1"}}
        with patch(
            "notifications.subprocess.run",
            return_value=CompletedProcess(args=[], returncode=0),
        ):
            ok = send_notification("hello", config)
        assert ok is True
