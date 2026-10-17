"""bootstrap_drift: abbreviation refusal, read cap, and kill-group edge."""

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
_spec = importlib.util.spec_from_file_location("bootstrap_drift_hardening", SCRIPT)
assert _spec is not None and _spec.loader is not None
drift = importlib.util.module_from_spec(_spec)
sys.modules["bootstrap_drift_hardening"] = drift
_spec.loader.exec_module(drift)


@pytest.fixture
def repo_and_skills(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    skills = tmp_path / "skills"
    (skills / "s1").mkdir(parents=True)
    return repo, skills


def _check(repo: Path, skills: Path, check: dict[str, Any], capsys) -> dict[str, Any]:
    (skills / "s1" / "reverify.json").write_text(json.dumps({"checks": [check]}), encoding="utf-8")
    drift.main(["check", "--repo", str(repo), "--skills-root", str(skills)])
    result: dict[str, Any] = json.loads(capsys.readouterr().out)["skills"][0]["checks"][0]
    return result


@pytest.mark.parametrize("flag", ["--allow", "--allow-c", "--allow-com"])
def test_abbreviated_allow_commands_is_rejected(flag, repo_and_skills):
    repo, skills = repo_and_skills

    with pytest.raises(SystemExit) as exc:
        drift.main(["check", "--repo", str(repo), "--skills-root", str(skills), flag])

    assert exc.value.code == 2


def test_full_allow_commands_flag_still_parses(repo_and_skills):
    repo, skills = repo_and_skills

    assert (
        drift.build_parser()
        .parse_args(
            ["check", "--repo", str(repo), "--skills-root", str(skills), "--allow-commands"]
        )
        .allow_commands
    )


@pytest.mark.parametrize(
    "check",
    [
        {"id": "C1", "kind": "contains", "path": "big.txt", "text": "needle"},
        {"id": "C1", "kind": "line_count_at_least", "path": "big.txt", "min": 1},
    ],
)
def test_oversized_file_fails_with_a_clear_detail(check, repo_and_skills, monkeypatch, capsys):
    repo, skills = repo_and_skills
    (repo / "big.txt").write_text("needle\n" * 10, encoding="utf-8")
    monkeypatch.setattr(drift, "MAX_READ_BYTES", 16)

    result = _check(repo, skills, check, capsys)

    assert result["status"] == "fail"
    assert "read cap" in result["detail"]


def test_file_at_the_cap_is_still_read(repo_and_skills, monkeypatch, capsys):
    repo, skills = repo_and_skills
    (repo / "ok.txt").write_text("needle", encoding="utf-8")
    monkeypatch.setattr(drift, "MAX_READ_BYTES", 6)

    result = _check(
        repo, skills, {"id": "C1", "kind": "contains", "path": "ok.txt", "text": "needle"}, capsys
    )

    assert result["status"] == "pass"


class _Proc:
    pid = 99999999
    killed = waited = False

    def kill(self) -> None:
        self.killed = True

    def wait(self) -> None:
        self.waited = True


def test_kill_group_tolerates_killpg_oserror(monkeypatch):
    def gone(pid: int, sig: int) -> None:
        raise ProcessLookupError

    monkeypatch.setattr(drift.os, "killpg", gone)
    proc = _Proc()

    drift._kill_group(proc)  # type: ignore[arg-type]

    assert proc.killed and proc.waited


def test_kill_group_without_killpg_still_kills_the_child(monkeypatch):
    monkeypatch.delattr(drift.os, "killpg", raising=False)
    proc = _Proc()

    drift._kill_group(proc)  # type: ignore[arg-type]

    assert proc.killed and proc.waited
