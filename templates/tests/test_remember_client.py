"""Tests for remember_client — Remember REST API client."""
from unittest.mock import patch, MagicMock

from remember_client import (
    RememberAPIError,
    _request_post,
    search_jobs,
    format_experience,
    experience_values,
)


class TestRequestPost:
    @patch("remember_client.urllib.request.urlopen")
    def test_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"data": [{"id": 1}], "meta": {"total_count": 1}}'
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        result = _request_post("/job_postings/search", {"page": 1})
        assert result["data"][0]["id"] == 1

    @patch("remember_client.urllib.request.urlopen")
    def test_http_error(self, mock_urlopen):
        import urllib.error
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "url", 500, "error", {}, None
        )
        try:
            _request_post("/job_postings/search", {})
            assert False, "Should raise"
        except RememberAPIError as e:
            assert "HTTP 500" in str(e)

    @patch("remember_client.urllib.request.urlopen")
    def test_invalid_json(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"not json"
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        try:
            _request_post("/job_postings/search", {})
            assert False, "Should raise"
        except RememberAPIError as e:
            assert "Invalid JSON" in str(e)


class TestSearchJobs:
    @patch("remember_client._request_post")
    def test_single_page(self, mock_req):
        mock_req.return_value = {
            "data": [{"id": 1, "title": "Backend"}],
            "meta": {"total_count": 1, "total_pages": 1, "page": 1, "per": 30},
        }
        items, total = search_jobs(["백엔드"], max_items=10)
        assert len(items) == 1
        assert total == 1

    @patch("remember_client._request_post")
    def test_pagination(self, mock_req):
        mock_req.side_effect = [
            {
                "data": [{"id": i} for i in range(30)],
                "meta": {"total_count": 50, "total_pages": 2, "page": 1, "per": 30},
            },
            {
                "data": [{"id": i} for i in range(30, 50)],
                "meta": {"total_count": 50, "total_pages": 2, "page": 2, "per": 30},
            },
        ]
        items, total = search_jobs(["백엔드"], max_items=100, page_delay=0)
        assert len(items) == 50
        assert total == 50

    @patch("remember_client._request_post")
    def test_max_items_cap(self, mock_req):
        mock_req.return_value = {
            "data": [{"id": i} for i in range(30)],
            "meta": {"total_count": 100, "total_pages": 4, "page": 1, "per": 30},
        }
        items, total = search_jobs(["백엔드"], max_items=5, page_delay=0)
        assert len(items) == 5

    @patch("remember_client._request_post")
    def test_api_error_returns_partial(self, mock_req):
        mock_req.side_effect = [
            {
                "data": [{"id": 1}],
                "meta": {"total_count": 50, "total_pages": 2, "page": 1, "per": 30},
            },
            RememberAPIError("fail"),
        ]
        items, total = search_jobs(["백엔드"], max_items=100, page_delay=0)
        assert len(items) == 1

    @patch("remember_client._request_post")
    def test_first_page_error_raises(self, mock_req):
        mock_req.side_effect = RememberAPIError("HTTP 403")
        try:
            search_jobs(["백엔드"], max_items=10)
            assert False, "Should raise RememberAPIError"
        except RememberAPIError as e:
            assert "403" in str(e)

    @patch("remember_client._request_post")
    def test_empty_response(self, mock_req):
        mock_req.return_value = {
            "data": [],
            "meta": {"total_count": 0, "total_pages": 0, "page": 1, "per": 30},
        }
        items, total = search_jobs(["없는키워드"], max_items=10)
        assert items == []
        assert total == 0


class TestFormatExperience:
    def test_min_max_years(self):
        result = format_experience({"min_experience": 3, "max_experience": 7})
        assert result == "경력 3~7년"

    def test_no_experience(self):
        assert format_experience({"min_experience": 0, "max_experience": 0}) == "경력 무관"

    def test_new_to_max(self):
        assert format_experience({"min_experience": 0, "max_experience": 5}) == "신입~5년"

    def test_min_only(self):
        result = format_experience({"min_experience": 5, "max_experience": None})
        assert result == "경력 5년 이상"

    def test_empty(self):
        assert format_experience({}) == ""


class TestExperienceValues:
    def test_range(self):
        assert experience_values({"min_experience": 3, "max_experience": 7}) == (3, 7)

    def test_no_experience(self):
        assert experience_values({"min_experience": 0, "max_experience": 0}) == (None, None)

    def test_empty(self):
        assert experience_values({}) == (None, None)
