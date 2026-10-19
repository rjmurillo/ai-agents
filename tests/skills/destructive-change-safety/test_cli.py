"""End-to-end fixtures: scan, preview, evidence, gate through the CLI."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

import destructive_gate
import pytest

SCRIPT = Path(destructive_gate.__file__)


def run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run the script the way a plugin consumer does: a fresh interpreter."""
    return subprocess.run(
        [sys.executable, "-I", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=cwd,
        check=False,
    )


def write_json(path: Path, data: object) -> str:
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


def make_db(path: Path, rows: int) -> None:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, active INTEGER)")
    conn.executemany("INSERT INTO users VALUES (?, 0)", [(i,) for i in range(rows)])
    conn.commit()
    conn.close()


def evidence_for(measured: int, expected: int, location: str) -> dict[str, Any]:
    return {
        "sinks": [{"location": location, "trace": ["main", "purge"]}],
        "preflight": {"command": "preview-sql", "exit_code": 0, "measured": measured},
        "expected": expected,
        "rollback": {"kind": "snapshot", "ref": "snap-1"},
        "checks": [{"command": "pytest -q", "exit_code": 0}],
    }


def scan_file_for(tmp_path: Path, location: str) -> str:
    scan = {"decision": "activate", "sinks": [{"location": location}]}
    return write_json(tmp_path / "scan.json", scan)


def test_direct_database_delete_with_count_preflight_passes(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    make_db(db, rows=5)
    preview = run("preview-sql", "--database", str(db), "--statement", "DELETE FROM users")
    assert preview.returncode == 0
    measured = json.loads(preview.stdout)["count"]
    evidence = write_json(tmp_path / "ev.json", evidence_for(measured, 5, "store.py:3"))
    gate = run("gate", "--evidence", evidence, "--scan", scan_file_for(tmp_path, "store.py:3"))
    assert gate.returncode == 0
    assert json.loads(gate.stdout)["verdict"] == "PASS"


def test_unexpected_cardinality_blocks_the_delete(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    make_db(db, rows=5000)
    preview = run("preview-sql", "--database", str(db), "--statement", "DELETE FROM users")
    measured = json.loads(preview.stdout)["count"]
    evidence = write_json(tmp_path / "ev.json", evidence_for(measured, 5, "store.py:3"))
    gate = run("gate", "--evidence", evidence, "--scan", scan_file_for(tmp_path, "store.py:3"))
    assert gate.returncode == 1
    assert "measured 5000, expected 5" in json.loads(gate.stdout)["reasons"][0]


def test_unavailable_preflight_blocks_with_unknown_scope(tmp_path: Path) -> None:
    result = run(
        "preview-sql",
        "--database",
        str(tmp_path / "missing.db"),
        "--statement",
        "DELETE FROM users",
    )
    assert result.returncode == 1
    assert "scope unknown" in json.loads(result.stdout)["reasons"][0]


def test_indirect_path_scan_feeds_the_gate(indirect_repo: Path, tmp_path: Path) -> None:
    scan = run("scan", ".", "--base", ".", "--changed", "load_config", "run", cwd=indirect_repo)
    assert scan.returncode == 0
    report = json.loads(scan.stdout)
    (sink,) = report["sinks"]
    assert sink["chains"] == ["main -> run -> purge_files"]
    assert sink["reached_from_changed"] == "run -> purge_files"
    scan_file = write_json(tmp_path / "scan.json", report)
    traced = write_json(tmp_path / "traced.json", evidence_for(2, 2, sink["location"]))
    untraced = write_json(tmp_path / "untraced.json", evidence_for(2, 2, "elsewhere.py:1"))
    assert run("gate", "--evidence", traced, "--scan", scan_file).returncode == 0
    blocked = run("gate", "--evidence", untraced, "--scan", scan_file)
    assert blocked.returncode == 1
    assert "adapter.py:6 is missing" in json.loads(blocked.stdout)["reasons"][0]


def test_file_cleanup_preview_excludes_the_sentinel(tmp_path: Path) -> None:
    (tmp_path / "cache").mkdir()
    (tmp_path / "cache" / "a.tmp").write_text("a", encoding="utf-8")
    (tmp_path / "sentinel.txt").write_text("keep", encoding="utf-8")
    result = run("preview-files", "--root", str(tmp_path), "--pattern", "cache/*.tmp")
    assert json.loads(result.stdout)["files"] == ["cache/a.tmp"]


def test_read_only_change_skips_cleanly(read_only_repo: Path, tmp_path: Path) -> None:
    scan = run("scan", ".", cwd=read_only_repo)
    assert json.loads(scan.stdout)["decision"] == "skip"
    scan_file = write_json(tmp_path / "scan.json", json.loads(scan.stdout))
    gate = run("gate", "--evidence", write_json(tmp_path / "ev.json", {}), "--scan", scan_file)
    assert gate.returncode == 0
    assert json.loads(gate.stdout)["verdict"] == "SKIP"


def test_gate_without_a_scan_is_a_usage_error(tmp_path: Path) -> None:
    """``--scan`` is required: a missing flag is bad arguments (exit 2), not a BLOCK verdict."""
    gate = run("gate", "--evidence", write_json(tmp_path / "ev.json", {}))
    assert gate.returncode == 2
    assert gate.stdout == ""
    assert "--scan" in gate.stderr


def test_gate_with_declared_sinks_and_no_scan_is_a_usage_error(tmp_path: Path) -> None:
    """Issue #6506 review: a declared sink does not excuse the scan that catches the rest."""
    evidence = write_json(tmp_path / "ev.json", evidence_for(5, 5, "store.py:3"))
    gate = run("gate", "--evidence", evidence)
    assert gate.returncode == 2
    assert "--scan" in gate.stderr


def test_gate_blocks_a_scan_file_without_a_decision(tmp_path: Path) -> None:
    gate = run(
        "gate",
        "--evidence",
        write_json(tmp_path / "ev.json", {}),
        "--scan",
        write_json(tmp_path / "scan.json", {"sinks": []}),
    )
    assert gate.returncode == 1
    assert "no known `decision`" in json.loads(gate.stdout)["reasons"][0]


def test_irreversible_operation_blocks_until_a_human_approves(tmp_path: Path) -> None:
    evidence = evidence_for(1, 1, "revoke.py:9")
    evidence["rollback"] = {"kind": "irreversible"}
    path = write_json(tmp_path / "ev.json", evidence)
    scan = scan_file_for(tmp_path, "revoke.py:9")
    blocked = run("gate", "--evidence", path, "--scan", scan)
    assert blocked.returncode == 1
    assert "needs human approval" in json.loads(blocked.stdout)["reasons"][0]
    evidence["approval"] = {"human": "owner approved in issue"}
    path = write_json(tmp_path / "ev2.json", evidence)
    assert run("gate", "--evidence", path, "--scan", scan).returncode == 0


def test_unparsable_source_exits_one(tmp_path: Path) -> None:
    (tmp_path / "broken.py").write_text("def (:\n", encoding="utf-8")
    result = run("scan", ".", cwd=tmp_path)
    assert result.returncode == 1
    assert json.loads(result.stdout)["decision"] == "unknown"


def test_missing_scan_path_is_a_config_error(tmp_path: Path) -> None:
    result = run("scan", "nope", cwd=tmp_path)
    assert result.returncode == 2
    assert "path does not exist" in result.stderr


def test_directory_of_unsupported_language_exits_one(tmp_path: Path) -> None:
    (tmp_path / "clean.ps1").write_text("Remove-Item -Recurse -Force x\n", encoding="utf-8")
    result = run("scan", ".", cwd=tmp_path)
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["decision"] == "unknown"
    assert payload["unscanned"] == ["clean.ps1"]


def test_directory_with_nothing_to_scan_is_a_config_error(tmp_path: Path) -> None:
    (tmp_path / "notes.md").write_text("DELETE FROM users\n", encoding="utf-8")
    result = run("scan", ".", cwd=tmp_path)
    assert result.returncode == 2
    assert "no scannable file" in result.stderr


def test_main_reports_empty_scope_as_config_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert destructive_gate.main(["scan", str(tmp_path)]) == 2
    assert "no scannable file" in capsys.readouterr().err


@pytest.mark.parametrize("content", ["not json", "[1, 2]"])
def test_unusable_evidence_file_is_a_config_error(tmp_path: Path, content: str) -> None:
    path = tmp_path / "ev.json"
    path.write_text(content, encoding="utf-8")
    scan = scan_file_for(tmp_path, "store.py:3")
    result = run("gate", "--evidence", str(path), "--scan", scan)
    assert result.returncode == 2
    assert "config error" in result.stderr


def test_missing_evidence_file_is_a_config_error(tmp_path: Path) -> None:
    scan = scan_file_for(tmp_path, "store.py:3")
    assert run("gate", "--evidence", str(tmp_path / "gone.json"), "--scan", scan).returncode == 2


def test_main_returns_codes_in_process(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "ok.py").write_text("x = 1\n", encoding="utf-8")
    assert destructive_gate.main(["scan", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)["decision"] == "skip"
    assert destructive_gate.main(["preview-files", "--root", str(tmp_path), "--pattern", "*"]) == 0
    assert destructive_gate.main(["preview-files", "--root", str(tmp_path), "--pattern", ".."]) == 1


def test_in_process_gate_scan_and_sql_paths(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = tmp_path / "app.db"
    make_db(db, rows=2)
    assert (
        destructive_gate.main(
            ["preview-sql", "--database", str(db), "--statement", "DELETE FROM users"]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["count"] == 2
    assert (
        destructive_gate.main(["preview-sql", "--database", str(db), "--statement", "SELECT 1"])
        == 1
    )
    capsys.readouterr()
    evidence = write_json(tmp_path / "ev.json", evidence_for(2, 3, "store.py:3"))
    scan = scan_file_for(tmp_path, "store.py:3")
    assert destructive_gate.main(["gate", "--evidence", evidence, "--scan", scan]) == 1
    assert json.loads(capsys.readouterr().out)["verdict"] == "BLOCK"
    gone = str(tmp_path / "gone.json")
    assert destructive_gate.main(["gate", "--evidence", gone, "--scan", scan]) == 2
    assert destructive_gate.main(["scan", str(tmp_path / "gone")]) == 2
    (tmp_path / "broken.py").write_text("def (:\n", encoding="utf-8")
    assert destructive_gate.main(["scan", str(tmp_path / "broken.py")]) == 1
    capsys.readouterr()
    destructive_gate.emit({"b": 1})
    assert json.loads(capsys.readouterr().out) == {"b": 1}
    with pytest.raises(SystemExit):
        destructive_gate.main([])


def test_in_process_rejects_a_json_array_as_evidence(tmp_path: Path) -> None:
    path = tmp_path / "ev.json"
    path.write_text("[1]", encoding="utf-8")
    scan = scan_file_for(tmp_path, "store.py:3")
    assert destructive_gate.main(["gate", "--evidence", str(path), "--scan", scan]) == 2


def test_directory_pattern_preview_gates_a_tree_delete(tmp_path: Path) -> None:
    for index in range(50):
        target = tmp_path / "build" / "sub" / f"f{index}.o"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x", encoding="utf-8")
    bare = run("preview-files", "--root", str(tmp_path), "--pattern", "build")
    assert bare.returncode == 0
    assert json.loads(bare.stdout)["count"] == 50


def test_directory_scan_with_hidden_script_and_workflow_is_unknown(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def pure(x):\n    return x\n", encoding="utf-8")
    script = tmp_path / "bin" / "cleanup"
    script.parent.mkdir()
    script.write_text('#!/bin/bash\nrm -rf "$TARGET"\n', encoding="utf-8")
    workflow = tmp_path / ".github" / "workflows" / "x.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("jobs:\n  j:\n    steps:\n      - run: git push -f origin main\n")
    result = run("scan", ".", "--base", ".", cwd=tmp_path)
    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["decision"] == "unknown"
    assert report["unscanned"] == [".github/workflows/x.yml", "bin/cleanup"]
