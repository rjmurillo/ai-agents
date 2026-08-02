"""Tests for scripts/ci/write_pr_discovery_summary.py."""

from __future__ import annotations

import json

import scripts.ci.write_pr_discovery_summary as wds

# ---------------------------------------------------------------------------
# build_summary
# ---------------------------------------------------------------------------


def _make_parsed(total=5, action=2, blocked=1, derivatives=0, prs=None):
    return {
        "summary": {
            "total": total,
            "actionRequired": action,
            "blocked": blocked,
            "derivatives": derivatives,
        },
        "prs": prs or [],
    }


def test_build_summary_counts():
    parsed = _make_parsed(total=10, action=3, blocked=2, derivatives=1)
    out = wds.build_summary(parsed)
    assert "| Open PRs Scanned | 10 |" in out
    assert "| PRs Need Action | 3 |" in out
    assert "| Blocked (human) | 2 |" in out
    assert "| Derivative PRs | 1 |" in out


def test_build_summary_no_prs_omits_table():
    parsed = _make_parsed()
    out = wds.build_summary(parsed)
    assert "PRs Requiring Action" not in out


def test_build_summary_with_prs():
    prs = [
        {"number": 7, "category": "stale", "reason": "no activity", "hasConflicts": True},
        {"number": 8, "category": "conflicts", "reason": "merge conflict", "hasConflicts": False},
    ]
    parsed = _make_parsed(prs=prs)
    out = wds.build_summary(parsed)
    assert "### PRs Requiring Action" in out
    assert "| #7 | stale | no activity | :warning: |" in out
    assert "| #8 | conflicts | merge conflict | :white_check_mark: |" in out


def test_build_summary_empty_parsed():
    out = wds.build_summary({})
    assert "## PR Discovery Summary" in out
    assert "| Open PRs Scanned | 0 |" in out


# ---------------------------------------------------------------------------
# main - config error
# ---------------------------------------------------------------------------


def test_main_missing_summary_path(monkeypatch):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    assert wds.main() == wds.EXIT_CONFIG


# ---------------------------------------------------------------------------
# main - writes to GITHUB_STEP_SUMMARY
# ---------------------------------------------------------------------------


def test_main_writes_output(tmp_path, monkeypatch):
    summary_file = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))
    data = _make_parsed(total=3)
    monkeypatch.setenv("SUMMARY_JSON", json.dumps(data))
    assert wds.main() == wds.EXIT_SUCCESS
    content = summary_file.read_text(encoding="utf-8")
    assert "## PR Discovery Summary" in content
    assert "| Open PRs Scanned | 3 |" in content


def test_main_empty_json_uses_defaults(tmp_path, monkeypatch):
    summary_file = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))
    monkeypatch.delenv("SUMMARY_JSON", raising=False)
    assert wds.main() == wds.EXIT_SUCCESS


def test_main_invalid_json_uses_defaults(tmp_path, monkeypatch):
    summary_file = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))
    monkeypatch.setenv("SUMMARY_JSON", "not valid json")
    assert wds.main() == wds.EXIT_SUCCESS
    assert "## PR Discovery Summary" in summary_file.read_text(encoding="utf-8")


def test_main_appends_to_existing_file(tmp_path, monkeypatch):
    summary_file = tmp_path / "summary.md"
    summary_file.write_text("existing\n", encoding="utf-8")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))
    monkeypatch.setenv("SUMMARY_JSON", json.dumps(_make_parsed()))
    wds.main()
    content = summary_file.read_text(encoding="utf-8")
    assert content.startswith("existing")
    assert "## PR Discovery Summary" in content
