"""Tests for config-driven JD rate limits."""

from __future__ import annotations

import importlib

import constants
import company_extractor
import ce_saramin
import ce_thevc
import ce_wanted
from ce_types import PlatformData


def _write_search_config(tmp_path, *, wanted=1.5, remember=1.5, thevc=1.5, saramin=1.5):
    config_path = tmp_path / "search_config.yaml"
    config_path.write_text(
        (
            "rate_limits:\n"
            f"  wanted: {wanted}\n"
            f"  remember: {remember}\n"
            f"  thevc: {thevc}\n"
            f"  saramin: {saramin}\n"
        ),
        encoding="utf-8",
    )
    return config_path


def _reload_company_modules():
    importlib.reload(ce_wanted)
    importlib.reload(ce_saramin)
    importlib.reload(ce_thevc)
    importlib.reload(company_extractor)


def test_get_rate_limit_reads_platform_value(tmp_path, monkeypatch):
    config_path = _write_search_config(tmp_path, wanted=2.25)
    monkeypatch.setattr(constants, "CONFIG_PATH", config_path)

    assert constants.get_rate_limit("wanted", 1.5) == 2.25
    assert constants.get_rate_limit("unknown", 1.5) == 1.5


def test_company_modules_bind_request_delay_from_config(tmp_path, monkeypatch):
    config_path = _write_search_config(
        tmp_path,
        wanted=2.1,
        thevc=2.2,
        saramin=2.3,
    )
    monkeypatch.setattr(constants, "CONFIG_PATH", config_path)

    _reload_company_modules()

    assert ce_wanted.REQUEST_DELAY == 2.1
    assert ce_thevc.REQUEST_DELAY == 2.2
    assert ce_saramin.REQUEST_DELAY == 2.3


def test_company_extractor_sleeps_with_platform_specific_rate_limit(tmp_path, monkeypatch):
    config_path = _write_search_config(
        tmp_path,
        wanted=1.7,
        thevc=2.4,
        saramin=2.8,
    )
    monkeypatch.setattr(constants, "CONFIG_PATH", config_path)
    _reload_company_modules()

    sleep_calls: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr(company_extractor.time, "sleep", fake_sleep)
    monkeypatch.setattr(
        company_extractor,
        "extract_from_jd_files",
        lambda company_name: None,
    )
    monkeypatch.setattr(
        company_extractor,
        "HTTP_EXTRACTORS",
        {"wanted": lambda company_name: PlatformData("wanted", "https://example.com/wanted", company_name)},
    )
    monkeypatch.setattr(
        company_extractor,
        "BROWSER_EXTRACTORS",
        {
            "saramin": lambda company_name, browser_context: PlatformData("saramin", "https://example.com/saramin", company_name),
            "thevc": lambda company_name, browser_context: PlatformData("thevc", "https://example.com/thevc", company_name),
        },
    )

    result = company_extractor.extract_company_info(
        "테스트회사",
        browser_context=object(),
        platforms=["wanted", "saramin", "thevc"],
        dry_run=True,
    )

    assert result.platforms_used == ["wanted", "saramin", "thevc"]
    assert sleep_calls == [2.8]
