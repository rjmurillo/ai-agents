"""Tests for ai-agents-diagnostics-toolkit baseline_snapshot.py. Subprocess calls are mocked."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / ".claude/skills/ai-agents-diagnostics-toolkit/scripts/baseline_snapshot.py"
spec = importlib.util.spec_from_file_location("baseline_snapshot", SCRIPT)
assert spec is not None and spec.loader is not None
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

BUDGET = json.dumps({"skills": 121, "total_chars": 49269, "total_tokens_est": 12318})
SIZE = (
    "Found 120 SKILL.md file(s) to check.\n  Passed:   120\n  Warnings: 64\n"
    "  Failed:   0\n  Limit:    500 lines / 24576 bytes\n"
)
ORPHAN = (
    json.dumps(
        {
            "Data": {
                "counts": {
                    "files_scanned": 492,
                    "refs_checked": 1538,
                    "findings_total": 0,
                    "directive_suppressed": 316,
                }
            }
        },
        indent=2,
    )
    + "\nVERDICT: PASS\n"
)
GOLDEN = json.dumps({"files_scanned": 13872, "error_count": 7, "warning_count": 74})


def _proc(out: str, rc: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], rc, stdout=out, stderr="")


def _fake(outputs: dict[str, subprocess.CompletedProcess[str]]):
    def run(argv, repo):
        if argv[0] == "git":
            return _proc("42e409325\n")
        for key, argv_ in mod.INSTRUMENT_ARGV.items():
            if argv == argv_:
                return outputs[key]
        raise AssertionError(f"unexpected argv {argv}")

    return run


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / ".git").mkdir()
    return tmp_path


def good() -> dict[str, subprocess.CompletedProcess[str]]:
    return {
        "description_budget": _proc(BUDGET),
        "skill_size": _proc(SIZE),
        "orphan_refs": _proc(ORPHAN),
        "golden_principles": _proc(GOLDEN, 10),
    }


def test_ai_agents_diagnostics_toolkit_snapshot_positive(monkeypatch, repo, capsys):
    monkeypatch.setattr(mod, "_run", _fake(good()))
    assert mod.main(["--repo", str(repo)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["head"] == "42e409325" and out["examined"] == 4
    ins = out["instruments"]
    assert ins["description_budget"]["total_tokens_est"] == 12318
    assert ins["skill_size"] == {
        "skills": 120,
        "warnings": 64,
        "failed": 0,
        "line_limit": 500,
        "byte_limit": 24576,
        "exit": 0,
    }
    assert ins["orphan_refs"]["directive_suppressed"] == 316
    assert ins["orphan_refs"]["verdict"] == "PASS"
    assert ins["golden_principles"]["errors"] == 7 and ins["golden_principles"]["exit"] == 10


def test_unreadable_output_exits_1(monkeypatch, repo, capsys):
    outputs = good()
    outputs["skill_size"] = _proc("garbage")
    monkeypatch.setattr(mod, "_run", _fake(outputs))
    assert mod.main(["--repo", str(repo)]) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["unreadable"] == ["skill_size"]
    assert "error" in out["instruments"]["skill_size"]


def test_orphan_output_without_verdict_is_unreadable(monkeypatch, repo, capsys):
    outputs = good()
    outputs["orphan_refs"] = _proc("{}")
    monkeypatch.setattr(mod, "_run", _fake(outputs))
    assert mod.main(["--repo", str(repo)]) == 1
    assert json.loads(capsys.readouterr().out)["unreadable"] == ["orphan_refs"]


def test_instrument_failing_to_start_exits_3(monkeypatch, repo, capsys):
    def run(argv, repo):
        raise mod.StartError("uv: not found")

    monkeypatch.setattr(mod, "_run", run)
    assert mod.main(["--repo", str(repo)]) == 3
    assert "not found" in capsys.readouterr().err


def test_git_failure_exits_3(monkeypatch, repo):
    def run(argv, repo):
        return subprocess.CompletedProcess(argv, 128, stdout="", stderr="fatal")

    monkeypatch.setattr(mod, "_run", run)
    assert mod.main(["--repo", str(repo)]) == 3


def test_not_a_repository_exits_2(tmp_path, capsys):
    assert mod.main(["--repo", str(tmp_path)]) == 2
    assert "not a git repository" in capsys.readouterr().err


def test_never_invokes_build_all_check():
    flat = [tok for argv in mod.INSTRUMENT_ARGV.values() for tok in argv]
    assert not any("build_all" in tok for tok in flat)


def test_help_exits_0():
    with pytest.raises(SystemExit) as exc:
        mod.main(["--help"])
    assert exc.value.code == 0
