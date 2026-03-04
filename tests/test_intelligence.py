"""Tests for the intelligence module."""

from __future__ import annotations

from trackyr.intelligence import _fmt_duration, parse_window_title


def test_fmt_duration_minutes():
    assert _fmt_duration(300) == "5m"


def test_fmt_duration_hours():
    assert _fmt_duration(3661) == "1h 1m"


def test_fmt_duration_zero():
    assert _fmt_duration(0) == "0m"


def test_parse_vscode_title():
    result = parse_window_title(
        "api.py - trackyr - Visual Studio Code",
        "Code.exe"
    )
    assert result["project"] == "trackyr"
    assert result["file"] == "api.py"


def test_parse_chrome_github():
    result = parse_window_title(
        "bse-ai/trackyr: Desktop activity tracker - GitHub - Google Chrome",
        "chrome.exe"
    )
    assert result["process"] == "chrome.exe"
    assert "context" in result


def test_parse_none_title():
    result = parse_window_title(None, "explorer.exe")
    assert result["process"] == "explorer.exe"
    assert result["context"] == ""


def test_parse_slack_title():
    result = parse_window_title(
        "general | team-workspace - Slack",
        "slack.exe"
    )
    assert result["process"] == "slack.exe"
    assert "context" in result
