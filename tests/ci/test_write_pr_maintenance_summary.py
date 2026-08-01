"""Tests for scripts/ci/write_pr_maintenance_summary.py."""

from __future__ import annotations

import json

import scripts.ci.write_pr_maintenance_summary as wpms

# ---------------------------------------------------------------------------
# build_next_steps
# ---------------------------------------------------------------------------


def test_build_next_steps_single_pr(capsys):
    prs = [{"number": 42, "reason": "stale review"}]
    result = wpms.build_next_steps(prs)
    assert "### Next Steps" in result
    assert "| #42 | stale review | `/pr-review 42` |" in result
    out = capsys.readouterr().out
    assert "::notice::Action required for PRs: #42" in out
    assert "Run: /pr-review 42" in out


def test_build_next_steps_multiple_prs(capsys):
    prs = [{"number": 1, "reason": "r1"}, {"number": 2, "reason": "r2"}]
    result = wpms.build_next_steps(prs)
    assert "| #1 | r1 | `/pr-review 1` |" in result
    assert "| #2 | r2 | `/pr-review 2` |" in result
    out = capsys.readouterr().out
    assert "#1" in out and "#2" in out


# ---------------------------------------------------------------------------
# main - config error
# ---------------------------------------------------------------------------


def test_main_missing_summary_path(monkeypatch):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    assert wpms.main() == wpms.EXIT_CONFIG


# ---------------------------------------------------------------------------
# main - no SUMMARY_JSON
# ---------------------------------------------------------------------------


def test_main_empty_summary_json(tmp_path, monkeypatch):
    summary_file = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))
    monkeypatch.delenv("SUMMARY_JSON", raising=False)
    assert wpms.main() == wpms.EXIT_SUCCESS
    assert not summary_file.exists()


# ---------------------------------------------------------------------------
# main - invalid JSON
# ---------------------------------------------------------------------------


def test_main_invalid_json(tmp_path, monkeypatch):
    summary_file = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))
    monkeypatch.setenv("SUMMARY_JSON", "not json")
    assert wpms.main() == wpms.EXIT_SUCCESS
    assert not summary_file.exists()


# ---------------------------------------------------------------------------
# main - no agent-controlled PRs
# ---------------------------------------------------------------------------


def test_main_no_agent_controlled_prs(tmp_path, monkeypatch):
    summary_file = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))
    data = {"prs": [{"number": 5, "category": "stale", "reason": "old"}]}
    monkeypatch.setenv("SUMMARY_JSON", json.dumps(data))
    assert wpms.main() == wpms.EXIT_SUCCESS
    assert not summary_file.exists()


# ---------------------------------------------------------------------------
# main - writes next steps for agent-controlled PRs
# ---------------------------------------------------------------------------


def test_main_writes_next_steps(tmp_path, monkeypatch):
    summary_file = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))
    data = {
        "prs": [
            {"number": 10, "category": "agent-controlled", "reason": "needs review"},
            {"number": 11, "category": "stale", "reason": "old"},
            {"number": 12, "category": "agent-controlled", "reason": "unresolved"},
        ]
    }
    monkeypatch.setenv("SUMMARY_JSON", json.dumps(data))
    assert wpms.main() == wpms.EXIT_SUCCESS
    content = summary_file.read_text(encoding="utf-8")
    assert "### Next Steps" in content
    assert "| #10 | needs review | `/pr-review 10` |" in content
    assert "| #12 | unresolved | `/pr-review 12` |" in content
    # Stale PR should NOT be in next steps
    assert "#11" not in content


def test_main_appends_to_existing_file(tmp_path, monkeypatch):
    summary_file = tmp_path / "summary.md"
    summary_file.write_text("existing content\n", encoding="utf-8")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))
    data = {"prs": [{"number": 3, "category": "agent-controlled", "reason": "r"}]}
    monkeypatch.setenv("SUMMARY_JSON", json.dumps(data))
    wpms.main()
    content = summary_file.read_text(encoding="utf-8")
    assert content.startswith("existing content")
    assert "### Next Steps" in content
