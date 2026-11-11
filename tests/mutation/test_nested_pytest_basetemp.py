"""Guard: nested pytest runs in mutation tests never share a pytest temp root.

Issue #7288. Without ``--basetemp`` a nested pytest uses
``$TMPDIR/pytest-of-<user>``, one directory shared by every nested run on the
machine. Pytest's ``cleanup_dead_symlinks`` checks ``is_symlink()``, then
``resolve().exists()``, then calls ``unlink()`` on ``pytest-current`` with no
lock and no ``missing_ok``, so two nested runs
racing under xdist can fail with ``FileNotFoundError: .../pytest-current``.

Three checks:

* ``private_basetemp`` hands out a fresh directory per call, outside the repo,
  and removes it afterwards;
* every mutation test that launches a nested pytest passes ``--basetemp`` to it
  (the launch is captured, so nothing nested runs). Dropping the argument from
  any one site fails that site's case;
* a real child pytest given ``--basetemp`` never creates ``pytest-of-<user>``
  in the shared ``TMPDIR``, and the same child without it does (the control).
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from tests.mutation import _adr_debate_harness as adr_harness
from tests.mutation import (
    test_mutate_baseline_ratchet_integrity as baseline_ratchet,
)
from tests.mutation import test_mutate_debate_log_path as debate_log_path
from tests.mutation import test_mutate_lefthook_ratchet_wiring as lefthook_wiring
from tests.mutation import (
    test_mutate_pr_description_what_changed as pr_description,
)
from tests.mutation import test_mutate_validate_findings_scope as findings_scope
from tests.mutation import test_worktree_path_mutations as worktree_path
from tests.mutation._nested_pytest import private_basetemp

REPO_ROOT = Path(__file__).resolve().parents[2]
_FLAG = "--basetemp="

_SITES: dict[str, Callable[[Path], object]] = {
    "validate_findings_scope": lambda root: findings_scope._run_tests(root),
    "lefthook_ratchet_wiring": lambda root: lefthook_wiring._run_wiring_tests(root),
    "pr_description_what_changed": lambda root: pr_description._run_tests(root),
    "baseline_ratchet_integrity": lambda root: baseline_ratchet._run_suite(root),
    "worktree_path_mutations": lambda root: worktree_path._run_tests(root, ["x.py"]),
    "debate_log_path": lambda root: debate_log_path._run_tests_in(root),
    "adr_debate_harness": lambda root: adr_harness._run_tests_in(root),
}


def _basetemp_values(cmd: list[str]) -> list[str]:
    return [arg[len(_FLAG) :] for arg in cmd if arg.startswith(_FLAG)]


def _capture_launches(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    launches: list[list[str]] = []

    def fake_run(cmd: list[str], *_a: Any, **_k: Any) -> subprocess.CompletedProcess[str]:
        launches.append(list(cmd))
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    return launches


def test_private_basetemp_is_fresh_per_call_and_outside_the_repo() -> None:
    with private_basetemp() as first, private_basetemp() as second:
        first_path = Path(first[len(_FLAG) :])
        second_path = Path(second[len(_FLAG) :])
        assert first.startswith(_FLAG)
        assert first_path != second_path
        assert first_path.parent.is_dir(), "parent must exist so pytest can mkdir the basetemp"
        assert not first_path.exists(), "pytest creates the basetemp itself"
        for path in (first_path, second_path):
            assert not path.resolve().is_relative_to(REPO_ROOT), f"{path} is inside the repo"
    assert not first_path.parent.exists(), "private temp dir leaked after the block"


@pytest.mark.parametrize("site", sorted(_SITES))
def test_nested_pytest_launch_passes_a_private_basetemp(
    site: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    launches = _capture_launches(monkeypatch)

    _SITES[site](tmp_path)
    _SITES[site](tmp_path)

    assert len(launches) == 2, f"{site}: expected two nested launches, saw {len(launches)}"
    values = [_basetemp_values(cmd) for cmd in launches]
    assert all(len(v) == 1 for v in values), f"{site}: need exactly one --basetemp: {launches}"
    first, second = values[0][0], values[1][0]
    assert first != second, f"{site}: two launches shared one basetemp {first}"
    assert not Path(first).resolve().is_relative_to(REPO_ROOT), f"{site}: basetemp in repo"
    assert not Path(first).resolve().is_relative_to(tmp_path.resolve()), (
        f"{site}: basetemp must not sit in the mutation worktree or fixture dir"
    )


def _child_pytest(
    project: Path, shared_tmpdir: Path, *extra: str
) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "TMPDIR": str(shared_tmpdir), "PYTHONDONTWRITEBYTECODE": "1"}
    for name in ("PYTEST_DEBUG_TEMPROOT", "PYTEST_NON_TMP_ROOT", "PYTEST_XDIST_WORKER"):
        env.pop(name, None)
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "-c",
            os.devnull,
            "--rootdir",
            str(project),
            *extra,
            "test_probe.py",
        ],
        cwd=project,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=120,
    )


@pytest.fixture()
def probe_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    (project / "test_probe.py").write_text(
        "def test_probe(tmp_path):\n    assert tmp_path.exists()\n", encoding="utf-8"
    )
    return project


def test_child_without_basetemp_uses_the_shared_pytest_root(
    probe_project: Path, tmp_path: Path
) -> None:
    """Control: proves the probe sees the shared root, so the next test can fail."""
    shared = tmp_path / "shared-tmp"
    shared.mkdir()

    proc = _child_pytest(probe_project, shared)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert list(shared.glob("pytest-of-*")), "control child did not touch the shared root"


def test_child_with_private_basetemp_never_touches_the_shared_pytest_root(
    probe_project: Path, tmp_path: Path
) -> None:
    shared = tmp_path / "shared-tmp"
    shared.mkdir()

    with private_basetemp() as basetemp:
        proc = _child_pytest(probe_project, shared, basetemp)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "1 passed" in proc.stdout, proc.stdout
    assert not list(shared.glob("pytest-of-*")), (
        "child created pytest-of-<user> in the shared TMPDIR: "
        f"{sorted(p.name for p in shared.iterdir())}"
    )
