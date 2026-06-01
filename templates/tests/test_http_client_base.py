"""Tests for http_client_base shared transport helpers."""
from unittest.mock import MagicMock, patch

import pytest

from http_client_base import DEFAULT_USER_AGENT, http_text_request


class TestHttpTextRequest:
    @patch("http_client_base.urllib.request.urlopen")
    def test_reads_text_response(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"<html>hello</html>"
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        result = http_text_request("https://example.com")

        assert result == "<html>hello</html>"
        request = mock_urlopen.call_args.args[0]
        assert request.headers["User-agent"] == DEFAULT_USER_AGENT

    @patch("http_client_base.urllib.request.urlopen")
    def test_respects_max_bytes_and_custom_headers(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.side_effect = lambda size=None: b"abcdef" if size is None else b"abcdef"[:size]
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        result = http_text_request(
            "https://example.com",
            headers={"Accept": "text/html"},
            max_bytes=3,
        )

        assert result == "abc"
        request = mock_urlopen.call_args.args[0]
        assert request.headers["User-agent"] == DEFAULT_USER_AGENT
        assert request.headers["Accept"] == "text/html"
        mock_resp.read.assert_called_once_with(3)

    @patch("http_client_base.urllib.request.urlopen")
    def test_propagates_transport_errors(self, mock_urlopen):
        import urllib.error

        mock_urlopen.side_effect = urllib.error.URLError("boom")

        with pytest.raises(urllib.error.URLError, match="boom"):
            http_text_request("https://example.com/fail")
