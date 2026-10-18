"""bootstrap_drift: the check-count cap, the total deadline, and the timeout status."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[3]
    / ".claude"
    / "skills"
    / "skill-bootstrap"
    / "scripts"
    / "bootstrap_drift.py"
)
_spec = importlib.util.spec_from_file_location("bootstrap_drift_limits", SCRIPT)
assert _spec is not None and _spec.loader is not None
drift = importlib.util.module_from_spec(_spec)
sys.modules["bootstrap_drift_limits"] = drift
_spec.loader.exec_module(drift)

PY = sys.executable


@pytest.fixture
def repo_and_skills(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "AGENTS.md").write_text("x\n", encoding="utf-8")
    skills = tmp_path / "skills"
    (skills / "s1").mkdir(parents=True)
    return repo, skills


def _run(
    repo: Path, skills: Path, checks: list[dict[str, Any]], capsys, *extra: str
) -> tuple[int, dict[str, Any]]:
    (skills / "s1" / "reverify.json").write_text(json.dumps({"checks": checks}), encoding="utf-8")
    code = drift.main(["check", "--repo", str(repo), "--skills-root", str(skills), *extra])
    return code, json.loads(capsys.readouterr().out)


def _paths(count: int) -> list[dict[str, Any]]:
    return [{"id": f"P{i}", "kind": "path_exists", "path": "AGENTS.md"} for i in range(count)]


def test_checks_at_the_cap_are_evaluated(repo_and_skills, capsys):
    repo, skills = repo_and_skills

    code, payload = _run(repo, skills, _paths(drift.MAX_CHECKS), capsys)

    assert code == 0
    assert payload["examined"]["checks"] == drift.MAX_CHECKS


def test_checks_over_the_cap_are_malformed(repo_and_skills, capsys):
    repo, skills = repo_and_skills

    code, payload = _run(repo, skills, _paths(drift.MAX_CHECKS + 1), capsys)

    skill = payload["skills"][0]
    assert code == 1
    assert skill["status"] == "malformed"
    assert f"over the {drift.MAX_CHECKS} limit" in skill["detail"]
    assert payload["update_candidates"] == ["s1"]


def test_path_checks_after_the_deadline_are_not_run(repo_and_skills, capsys, monkeypatch):
    repo, skills = repo_and_skills
    monkeypatch.setattr(drift, "TOTAL_DEADLINE_S", -1)

    code, payload = _run(repo, skills, _paths(2), capsys)

    statuses = [c["status"] for c in payload["skills"][0]["checks"]]
    assert statuses == ["timeout", "timeout"]
    assert "total deadline" in payload["skills"][0]["checks"][0]["detail"]
    assert payload["skills"][0]["status"] == "fail"
    assert code == 1


def test_command_after_the_deadline_is_not_started(repo_and_skills, capsys, monkeypatch, tmp_path):
    repo, skills = repo_and_skills
    marker = tmp_path / "ran"
    monkeypatch.setattr(drift, "TOTAL_DEADLINE_S", -1)
    command = {
        "id": "C1",
        "kind": "command",
        "argv": [PY, "-c", f"open({str(marker)!r}, 'w').close()"],
    }

    code, payload = _run(repo, skills, [command], capsys, "--allow-commands")

    assert code == 1
    assert payload["skills"][0]["checks"][0]["status"] == "timeout"
    assert not marker.exists()


def test_skipped_command_stays_skipped_after_the_deadline(repo_and_skills, capsys, monkeypatch):
    repo, skills = repo_and_skills
    monkeypatch.setattr(drift, "TOTAL_DEADLINE_S", -1)
    command = {"id": "C1", "kind": "command", "argv": [PY, "-c", "pass"]}

    code, payload = _run(repo, skills, [command], capsys)

    assert payload["skills"][0]["checks"][0]["status"] == "skipped"
    assert payload["skills"][0]["status"] == "skipped"
    assert code == 0


def test_deadline_shortens_a_running_command(repo_and_skills, capsys, monkeypatch):
    repo, skills = repo_and_skills
    monkeypatch.setattr(drift, "TOTAL_DEADLINE_S", 0.3)
    sleeper = {"id": "C1", "kind": "command", "argv": [PY, "-c", "import time; time.sleep(30)"]}

    code, payload = _run(repo, skills, [sleeper, *_paths(1)], capsys, "--allow-commands")

    checks = payload["skills"][0]["checks"]
    assert code == 1
    assert checks[0]["status"] == "timeout"
    assert checks[0]["detail"].startswith("timed out after 0.")
    assert checks[1]["status"] == "timeout"
    assert "total deadline" in checks[1]["detail"]


def test_timeout_alone_does_not_make_a_passing_skill_pass(repo_and_skills, capsys, monkeypatch):
    repo, skills = repo_and_skills
    monkeypatch.setattr(drift, "COMMAND_TIMEOUT_S", 0.2)
    sleeper = {"id": "C1", "kind": "command", "argv": [PY, "-c", "import time; time.sleep(30)"]}

    code, payload = _run(repo, skills, [*_paths(1), sleeper], capsys, "--allow-commands")

    assert [c["status"] for c in payload["skills"][0]["checks"]] == ["pass", "timeout"]
    assert payload["skills"][0]["status"] == "fail"
    assert code == 1
