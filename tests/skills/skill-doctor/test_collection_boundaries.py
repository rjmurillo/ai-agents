"""Regressions for scope, identity, and observable partial collection."""

import json
import os
import sys
from pathlib import Path

import collect_sessions as collector
import pytest
from session_common import (
    collect_diagnostics,
    collection_issue_counts,
    iter_jsonl_records,
)
from session_discovery import discover_skills, session_matches_repo
from session_test_helpers import run_collector, write_jsonl


def test_scope_requires_containment_not_name(tmp_path):
    repo = tmp_path / "approved" / "widget"
    other = tmp_path / "private" / "widget"
    repo.mkdir(parents=True)
    other.mkdir(parents=True)
    assert session_matches_repo(repo / "src", repo)
    assert session_matches_repo(str(repo), repo)
    assert not session_matches_repo(other / "src", repo)
    assert not session_matches_repo(repo.parent / "widget-extra", repo)
    assert not session_matches_repo(Path("widget/src"), repo)
    assert not session_matches_repo(None, repo)


def test_scope_resolves_symlink_escape(tmp_path):
    repo, private = tmp_path / "repo", tmp_path / "private"
    repo.mkdir()
    private.mkdir()
    try:
        (repo / "alias").symlink_to(private, target_is_directory=True)
    except OSError:
        pytest.skip("Symlink creation requires an OS capability unavailable here.")
    assert not session_matches_repo(repo / "alias" / "src", repo)


@pytest.mark.parametrize("conflict", [False, True])
def test_discovery_deduplicates_identical_but_excludes_ambiguous_names(tmp_path, conflict):
    repos = [tmp_path / name for name in ("first", "second", "third")]
    for index, repo in enumerate(repos):
        skill = repo / ".claude" / "skills" / "shared" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("Other" if conflict and index == 1 else "Same", encoding="utf-8")
    with collect_diagnostics():
        skills = discover_skills(repos, tmp_path / "codex", [], False)
        if conflict:
            assert "shared" not in skills
            assert collection_issue_counts() == {"ambiguous_skills": 1}
        else:
            assert skills["shared"]["path"].startswith(str(repos[0]))
            assert collection_issue_counts() == {}


def test_discovery_reports_unreadable_skill(tmp_path, monkeypatch):
    skill = tmp_path / ".claude" / "skills" / "broken" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("Synthetic", encoding="utf-8")
    original = Path.read_bytes

    def denied(path):
        if path == skill:
            raise PermissionError("synthetic")
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", denied)
    with collect_diagnostics():
        assert discover_skills([tmp_path], tmp_path / "codex", [], False) == {}
        assert collection_issue_counts() == {"skill_read_failures": 1}


def test_malformed_records_are_counted_without_contents(tmp_path, capsys):
    journal = tmp_path / "journal.jsonl"
    journal.write_text('{"valid": true}\nsecret-invalid\n[]\nnull\n\n', encoding="utf-8")
    with collect_diagnostics():
        assert list(iter_jsonl_records(journal)) == [{"valid": True}]
        assert collection_issue_counts() == {"malformed_records": 3}
    assert collection_issue_counts() == {}
    assert capsys.readouterr().err == ""
    assert list(iter_jsonl_records(journal)) == [{"valid": True}]
    assert capsys.readouterr().err == "warning: collection malformed_records: 3\n"


def _copilot_journal(home, repo, name):
    path = home / "session-state" / name / "events.jsonl"
    write_jsonl(
        path,
        [
            {"type": "session.start", "data": {"context": {"cwd": str(repo)}}},
            {"type": "assistant.message", "data": {"content": "Inspect"}},
            {"type": "tool.execution_start", "data": {"toolName": "view", "arguments": {}}},
        ],
    )
    return path


def test_cli_exposes_partial_inventory_and_preserves_healthy_records(tmp_path):
    home = tmp_path / "copilot"
    path = _copilot_journal(home, tmp_path, "healthy")
    with path.open("a", encoding="utf-8") as stream:
        stream.write("private-synthetic-invalid\n[]\n")
    result = run_collector(tmp_path, home, "--harness", "copilot", "--repo", str(tmp_path))
    assert result.returncode == 0, result.stderr
    inventory = json.loads((tmp_path / "report" / "inventory.json").read_text(encoding="utf-8"))
    assert inventory["collection_status"] == "partial"
    assert inventory["collection_issues"] == {"malformed_records": 2}
    assert inventory["stats"]["sessions_considered"] == 1
    assert "partial collection: malformed_records=2" in result.stderr
    assert "private-synthetic-invalid" not in result.stderr


def test_cli_read_failure_does_not_hide_other_sessions(tmp_path, monkeypatch, capsys):
    home = tmp_path / "copilot"
    blocked = _copilot_journal(home, tmp_path, "blocked")
    _copilot_journal(home, tmp_path, "healthy")
    original = Path.open

    def denied(path, *args, **kwargs):
        if path == blocked:
            raise PermissionError("sensitive exception detail")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", denied)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "collect_sessions.py",
            "--harness",
            "copilot",
            "--copilot-home",
            str(home),
            "--repo",
            str(tmp_path),
            "--out",
            str(tmp_path / "report"),
        ],
    )
    collector.main()
    inventory = json.loads((tmp_path / "report" / "inventory.json").read_text(encoding="utf-8"))
    assert inventory["collection_issues"] == {"read_failures": 1}
    assert inventory["stats"]["sessions_considered"] == 1
    stderr = capsys.readouterr().err
    assert "read_failures=1" in stderr
    assert "sensitive exception detail" not in stderr


def test_cli_clean_empty_source_has_no_failure_counter(tmp_path):
    home = tmp_path / "copilot"
    (home / "session-state").mkdir(parents=True)
    result = run_collector(tmp_path, home, "--harness", "copilot", "--all-conversations")
    assert result.returncode == 0, result.stderr
    inventory = json.loads((tmp_path / "report" / "inventory.json").read_text(encoding="utf-8"))
    assert inventory["collection_status"] == "complete"
    assert inventory["collection_issues"] == {}
    assert result.stderr == ""


def test_foreign_path_flavor_does_not_authorize_scope(tmp_path):
    foreign = "/other/widget" if os.name == "nt" else r"C:\other\widget"
    assert not session_matches_repo(foreign, tmp_path / "widget")
