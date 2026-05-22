"""Tests for wanted_client — Wanted REST API client."""
from unittest.mock import patch, MagicMock

from wanted_client import (
    WantedAPIError,
    _request,
    search_jobs,
    format_experience,
    experience_values,
)


class TestRequest:
    @patch("wanted_client.urllib.request.urlopen")
    def test_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"data": [{"id": 1}]}'
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        result = _request("/jobs", {"search": "test"})
        assert result == {"data": [{"id": 1}]}

    @patch("wanted_client.urllib.request.urlopen")
    def test_http_error(self, mock_urlopen):
        import urllib.error
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "url", 500, "error", {}, None
        )
        try:
            _request("/jobs")
            assert False, "Should raise"
        except WantedAPIError as e:
            assert "HTTP 500" in str(e)

    @patch("wanted_client.urllib.request.urlopen")
    def test_invalid_json(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"not json"
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        try:
            _request("/jobs")
            assert False, "Should raise"
        except WantedAPIError as e:
            assert "Invalid JSON" in str(e)


class TestSearchJobs:
    @patch("wanted_client._request")
    def test_single_page(self, mock_req):
        mock_req.return_value = {
            "data": [{"id": 1, "position": "Backend"}],
            "links": {},
        }
        items = search_jobs("백엔드", max_items=10)
        assert len(items) == 1
        assert items[0]["id"] == 1

    @patch("wanted_client._request")
    def test_pagination(self, mock_req):
        mock_req.side_effect = [
            {"data": [{"id": i} for i in range(20)], "links": {"next": "url"}},
            {"data": [{"id": i} for i in range(20, 40)], "links": {"next": "url"}},
            {"data": [{"id": i} for i in range(40, 50)], "links": {}},
        ]
        items = search_jobs("백엔드", max_items=100, page_delay=0)
        assert len(items) == 50

    @patch("wanted_client._request")
    def test_max_items_cap(self, mock_req):
        mock_req.return_value = {
            "data": [{"id": i} for i in range(20)],
            "links": {"next": "url"},
        }
        items = search_jobs("백엔드", max_items=5, page_delay=0)
        assert len(items) == 5

    @patch("wanted_client._request")
    def test_api_error_returns_partial(self, mock_req):
        mock_req.side_effect = [
            {"data": [{"id": 1}], "links": {"next": "url"}},
            WantedAPIError("fail"),
        ]
        items = search_jobs("백엔드", max_items=100, page_delay=0)
        assert len(items) == 1

    @patch("wanted_client._request")
    def test_empty_response(self, mock_req):
        mock_req.return_value = {"data": [], "links": {}}
        items = search_jobs("없는키워드", max_items=10)
        assert items == []


class TestFormatExperience:
    def test_range(self):
        assert format_experience({"annual_from": 3, "annual_to": 7}) == "3~7년"

    def test_new_grad(self):
        assert format_experience({"annual_from": 0, "annual_to": 0}) == "신입"

    def test_new_to_max(self):
        assert format_experience({"annual_from": 0, "annual_to": 5}) == "신입~5년"

    def test_min_only(self):
        assert format_experience({"annual_from": 5, "annual_to": None}) == "5년 이상"

    def test_empty(self):
        assert format_experience({}) == ""


class TestExperienceValues:
    def test_range(self):
        assert experience_values({"annual_from": 3, "annual_to": 7}) == (3, 7)

    def test_new_grad(self):
        assert experience_values({"annual_from": 0, "annual_to": 0}) == (0, 0)

    def test_empty(self):
        assert experience_values({}) == (None, None)
