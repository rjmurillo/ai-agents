"""Audit manifest writes, CLI exit codes, and the collector flag (epic #7248, M1)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import audit_manifest as am
import pytest
from session_test_helpers import run_collector, write_jsonl
from test_audit_manifest import manifest_for, write_skill
from test_repository_scope import UPSTREAM, add_worktree, make_clone


@pytest.fixture
def family(tmp_path):
    main = make_clone(tmp_path / "clones" / "widgets", UPSTREAM)
    feature = add_worktree(main, tmp_path / "trees" / "feature-a", "feature-a")
    return {"tmp": tmp_path, "main": main, "feature": feature}


def test_write_manifest_is_atomic_and_leaves_no_temp_files(tmp_path):
    target = tmp_path / "out" / "audit_manifest.json"
    manifest = manifest_for([tmp_path])

    am.write_manifest(target, manifest)

    assert json.loads(target.read_text(encoding="utf-8")) == manifest
    assert [p.name for p in target.parent.iterdir()] == ["audit_manifest.json"]


def test_failed_replace_keeps_the_previous_manifest_and_cleans_up(tmp_path, monkeypatch):
    target = tmp_path / "audit_manifest.json"
    target.write_text("previous", encoding="utf-8")

    def boom(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        am.write_manifest(target, manifest_for([tmp_path]))

    assert target.read_text(encoding="utf-8") == "previous"
    assert [p.name for p in tmp_path.iterdir()] == ["audit_manifest.json"]


def test_cli_exit_zero_for_a_valid_manifest(tmp_path, capsys):
    path = tmp_path / "m.json"
    am.write_manifest(path, manifest_for([tmp_path]))

    assert am.main([str(path)]) == 0
    assert "valid: manifest_version" in capsys.readouterr().out


def test_cli_exit_one_for_an_invalid_manifest(tmp_path, capsys):
    manifest = manifest_for([tmp_path])
    manifest["attribution"]["verified_count"] = 1
    path = tmp_path / "m.json"
    am.write_manifest(path, manifest)

    assert am.main([str(path)]) == 1
    assert "invalid:" in capsys.readouterr().err


def test_cli_exit_two_for_json_that_does_not_parse(tmp_path):
    path = tmp_path / "m.json"
    path.write_text("{not json", encoding="utf-8")

    assert am.main([str(path)]) == 2


def test_cli_exit_two_for_bad_arguments_and_unreadable_files(tmp_path, capsys):
    assert am.main([]) == 2
    assert am.main([str(tmp_path / "missing.json")]) == 2
    assert am.main([str(tmp_path)]) == 2
    assert "cannot read" in capsys.readouterr().err


def _copilot_session(home: Path, repo: Path) -> None:
    write_jsonl(
        home / "session-state" / "one" / "events.jsonl",
        [
            {"type": "session.start", "data": {"context": {"cwd": str(repo)}}},
            {"type": "assistant.message", "data": {"content": "Inspect"}},
            {"type": "tool.execution_start", "data": {"toolName": "view", "arguments": {}}},
        ],
    )


def test_collector_flag_writes_a_valid_manifest_next_to_inventory(family):
    tmp = family["tmp"]
    write_skill(family["main"], "demo", "Demo")
    _copilot_session(tmp / "home", family["main"])

    result = run_collector(
        tmp, tmp / "home", "--harness", "copilot", "--repo", str(family["main"]), "--audit-manifest"
    )

    assert result.returncode == 0, result.stderr
    manifest = json.loads((tmp / "report" / "audit_manifest.json").read_text(encoding="utf-8"))
    assert am.validate_manifest(manifest) == []
    assert manifest["declared_inputs"]["explicit_repos"] == [str(family["main"])]
    assert [e["name"] for e in manifest["catalog"]] == ["demo"]
    assert "audit manifest:" in result.stdout


def test_collector_default_run_writes_no_manifest_and_keeps_inventory_fields(family):
    tmp = family["tmp"]
    _copilot_session(tmp / "home", family["main"])

    result = run_collector(tmp, tmp / "home", "--harness", "copilot", "--repo", str(family["main"]))

    assert result.returncode == 0, result.stderr
    assert not (tmp / "report" / "audit_manifest.json").exists()
    inventory = json.loads((tmp / "report" / "inventory.json").read_text(encoding="utf-8"))
    assert "audit_manifest" not in inventory and "scope_resolution" in inventory
