"""Tests for check_unused_arguments.py failure paths: exit codes 2 and 3 and the deadline."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts" / "validation"))

import check_unused_arguments
import pytest
from check_unused_arguments import Deadline, ExternalToolError, scan

from tests.validation.unused_arguments_helpers import (
    UNUSED_KEY,
    add_file,
    fake_run,
    git,
    make_repo,
    run_gate,
    write_baseline,
)


def test_main_config_error_outside_a_git_work_tree(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(tmp_path)
    (repo / ".git").rename(repo / "not-git")

    assert run_gate(repo, write_baseline(tmp_path, UNUSED_KEY)) == 2
    assert "git ls-files failed" in capsys.readouterr().err


def test_main_config_error_when_git_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(tmp_path)

    def no_git(*_args: object, **_kwargs: object) -> None:
        raise FileNotFoundError("git")

    monkeypatch.setattr(check_unused_arguments.subprocess, "run", no_git)

    assert run_gate(repo, write_baseline(tmp_path, UNUSED_KEY)) == 2
    assert "cannot run git" in capsys.readouterr().err


def _hide_ruff_from_the_interpreter(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make ``find_spec("ruff")`` miss, as in an environment without the dev extra."""
    hidden = SimpleNamespace(util=SimpleNamespace(find_spec=lambda _name: None))
    monkeypatch.setattr(check_unused_arguments, "importlib", hidden)


def test_main_config_error_when_ruff_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(tmp_path)
    _hide_ruff_from_the_interpreter(monkeypatch)
    monkeypatch.setattr(check_unused_arguments.shutil, "which", lambda _name: None)

    assert run_gate(repo, write_baseline(tmp_path, UNUSED_KEY)) == 2
    assert "ruff is not installed" in capsys.readouterr().err


def test_main_config_error_when_ruff_cannot_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(tmp_path)
    _hide_ruff_from_the_interpreter(monkeypatch)
    monkeypatch.setattr(
        check_unused_arguments.shutil, "which", lambda _name: str(tmp_path / "no-ruff")
    )

    assert run_gate(repo, write_baseline(tmp_path, UNUSED_KEY)) == 2
    assert "cannot run ruff" in capsys.readouterr().err


@pytest.mark.parametrize("tool", ["git", "ruff"])
def test_main_external_error_when_a_tool_times_out(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tool: str,
) -> None:
    repo = make_repo(tmp_path)
    expired = subprocess.TimeoutExpired(cmd=tool, timeout=1)
    monkeypatch.setattr(
        check_unused_arguments.subprocess,
        "run",
        fake_run(subprocess.run, **{tool: expired}),
    )

    assert run_gate(repo, write_baseline(tmp_path, UNUSED_KEY)) == 3
    err = capsys.readouterr().err
    assert "unused-argument gate" in err
    assert "timed out" in err
    assert tool in err


def test_every_subprocess_call_sets_a_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = make_repo(tmp_path)
    seen: dict[str, object] = {}
    real_run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run

    def spy(argv: list[str], *args: object, **kwargs: object) -> object:
        seen["git" if argv[0] == "git" else "ruff"] = kwargs.get("timeout")
        return real_run(argv, *args, **kwargs)

    monkeypatch.setattr(check_unused_arguments.subprocess, "run", spy)

    scan(repo)

    assert set(seen) == {"git", "ruff"}
    assert all(isinstance(value, int | float) and value > 0 for value in seen.values())


def test_main_config_error_when_ruff_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(tmp_path)
    failed = subprocess.CompletedProcess(["ruff"], 2, stdout="", stderr="bad config")
    monkeypatch.setattr(
        check_unused_arguments.subprocess, "run", fake_run(subprocess.run, ruff=failed)
    )

    assert run_gate(repo, write_baseline(tmp_path, UNUSED_KEY)) == 2
    assert "ruff exited 2: bad config" in capsys.readouterr().err


def test_main_config_error_when_ruff_prints_no_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(tmp_path)
    garbled = subprocess.CompletedProcess(["ruff"], 0, stdout="not json", stderr="")
    monkeypatch.setattr(
        check_unused_arguments.subprocess, "run", fake_run(subprocess.run, ruff=garbled)
    )

    assert run_gate(repo, write_baseline(tmp_path)) == 2
    assert "did not print JSON" in capsys.readouterr().err


def test_main_config_error_when_a_finding_names_no_argument(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(tmp_path)
    odd = subprocess.CompletedProcess(
        ["ruff"],
        1,
        stdout='[{"code": "ARG001", "filename": "x.py", "message": "Unused argument"}]',
        stderr="",
    )
    monkeypatch.setattr(
        check_unused_arguments.subprocess, "run", fake_run(subprocess.run, ruff=odd)
    )

    assert run_gate(repo, write_baseline(tmp_path)) == 2
    assert "names no argument" in capsys.readouterr().err


def test_main_config_error_on_syntax_error_source(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(tmp_path, source="def broken(:\n")

    assert run_gate(repo, write_baseline(tmp_path)) == 2
    assert "could not parse" in capsys.readouterr().err


def test_scan_merges_findings_across_batches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = make_repo(tmp_path)
    add_file(repo, "scripts/b.py", "def g(args):\n    return 1\n")
    add_file(repo, "scripts/c.py", "def h(data):\n    return 1\n")
    monkeypatch.setattr(check_unused_arguments, "RUFF_BATCH_SIZE", 1)

    result = scan(repo)

    assert result.scanned_files == 3
    assert result.keys == [
        "scripts/b.py: ARG001 args",
        "scripts/c.py: ARG001 data",
        UNUSED_KEY,
    ]


def test_main_config_error_when_nothing_scanned(tmp_path: Path) -> None:
    git(tmp_path, "init", "-q")

    assert run_gate(tmp_path, write_baseline(tmp_path)) == 2


def test_main_config_error_when_baseline_missing(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)

    assert run_gate(repo, tmp_path / "absent.txt") == 2


def test_main_config_error_when_baseline_is_not_utf8(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(tmp_path)
    baseline = tmp_path / "baseline.txt"
    baseline.write_bytes(b"scripts/mod.py: ARG001 \xff\n")

    assert run_gate(repo, baseline) == 2
    assert "cannot read baseline" in capsys.readouterr().err


def test_main_config_error_when_baseline_malformed(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)

    assert run_gate(repo, write_baseline(tmp_path, "not a key")) == 2


def test_deadline_clamps_each_call_to_the_time_left() -> None:
    now = [0.0]
    deadline = Deadline(10.0, clock=lambda: now[0])

    assert deadline.timeout_for(30, "git ls-files") == 10.0
    now[0] = 7.0
    assert deadline.timeout_for(60, "a ruff batch") == pytest.approx(3.0)
    assert deadline.timeout_for(1, "a ruff batch") == 1


def test_deadline_raises_once_spent() -> None:
    now = [0.0]
    deadline = Deadline(10.0, clock=lambda: now[0])
    now[0] = 10.0

    with pytest.raises(ExternalToolError, match="10s total deadline ran out before a ruff batch"):
        deadline.timeout_for(60, "a ruff batch")


def test_scan_stops_between_batches_when_the_deadline_runs_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Five 60s batches plus a 30s git call reached 330s against a 90s lefthook
    # cap. The shared deadline stops the run between calls instead.
    repo = make_repo(tmp_path)
    for index in range(3):
        add_file(repo, f"scripts/extra{index}.py", "x = 1\n")
    monkeypatch.setattr(check_unused_arguments, "RUFF_BATCH_SIZE", 1)
    now = [0.0]
    real_run = subprocess.run

    def slow(argv: list[str], *args: object, **kwargs: object) -> object:
        now[0] += 40.0
        return real_run(argv, *args, **kwargs)

    monkeypatch.setattr(check_unused_arguments.subprocess, "run", slow)

    with pytest.raises(ExternalToolError, match="total deadline ran out"):
        scan(repo, Deadline(90.0, clock=lambda: now[0]))


def test_main_exits_3_when_the_total_deadline_is_spent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(tmp_path)
    monkeypatch.setattr(check_unused_arguments, "Deadline", lambda: Deadline(0.0))

    assert run_gate(repo, write_baseline(tmp_path, UNUSED_KEY)) == 3
    assert "total deadline ran out" in capsys.readouterr().err


def test_resolve_ruff_prefers_the_interpreters_copy(monkeypatch: pytest.MonkeyPatch) -> None:
    present = SimpleNamespace(util=SimpleNamespace(find_spec=lambda _name: object()))
    monkeypatch.setattr(check_unused_arguments, "importlib", present)
    monkeypatch.setattr(check_unused_arguments.shutil, "which", lambda _name: "/usr/bin/ruff")

    assert check_unused_arguments.resolve_ruff() == [sys.executable, "-m", "ruff"]


def test_resolve_ruff_falls_back_to_path(monkeypatch: pytest.MonkeyPatch) -> None:
    _hide_ruff_from_the_interpreter(monkeypatch)
    monkeypatch.setattr(check_unused_arguments.shutil, "which", lambda _name: "/usr/bin/ruff")

    assert check_unused_arguments.resolve_ruff() == ["/usr/bin/ruff"]


def test_ruff_outside_path_is_found_through_the_interpreter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # pre-pr-validation runs ``uv run --frozen python`` and the venv bin
    # directory need not be on PATH.
    repo = make_repo(tmp_path)
    only_git = tmp_path / "only-git"
    only_git.mkdir()
    (only_git / "git").symlink_to(shutil.which("git") or "git")
    monkeypatch.setenv("PATH", str(only_git))
    assert shutil.which("ruff") is None

    assert scan(repo).keys == ["scripts/mod.py: ARG001 path"]


def test_main_config_error_when_ruff_reports_a_path_outside_the_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(tmp_path)
    outside = {
        "code": "ARG001",
        "filename": "/elsewhere/mod.py",
        "message": "Unused function argument: `path`",
        "location": {"row": 1, "column": 1},
    }
    completed = subprocess.CompletedProcess([], 1, json.dumps([outside]), "")
    monkeypatch.setattr(
        check_unused_arguments.subprocess, "run", fake_run(subprocess.run, ruff=completed)
    )

    assert run_gate(repo, write_baseline(tmp_path)) == 2
    assert "outside" in capsys.readouterr().err
