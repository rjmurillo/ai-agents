from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ci import mypy_ratchet
from scripts.validation.git_hook_policy import MYPY_RATCHET_BASE_REF_ENV
from tests.ci.mypy_ratchet_git_harness import SAMPLE_PATH, isolate_env


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    isolate_env(monkeypatch)


def test_main_rejects_a_directory_that_is_not_a_git_worktree(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = mypy_ratchet.main(["--repo-root", str(tmp_path), "--base-ref", "HEAD"])

    assert exit_code == 2
    assert "is not a git worktree" in capsys.readouterr().err


def test_main_returns_external_error_when_git_cannot_list_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(mypy_ratchet, "changed_python_files", lambda _ref, _root: (3, [], "x"))

    def fail_if_called(_paths: object, _root: object) -> int:
        raise AssertionError("run_mypy must not run when the file list is unknown")

    monkeypatch.setattr(mypy_ratchet, "run_mypy", fail_if_called)

    assert mypy_ratchet.main(["--repo-root", str(tmp_path), "--base-ref", "HEAD"]) == 3


def test_main_pins_run_mypy_to_the_resolved_base_and_propagates_its_exit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(
        mypy_ratchet,
        "changed_python_files",
        lambda _ref, _root: (0, [SAMPLE_PATH], "origin/main"),
    )
    seen: dict[str, object] = {}

    def fake_run_mypy(paths: list[str], root: Path) -> int:
        seen["paths"] = paths
        seen["root"] = root
        seen["base"] = mypy_ratchet.os.environ.get(MYPY_RATCHET_BASE_REF_ENV)
        return 1

    monkeypatch.setattr(mypy_ratchet, "run_mypy", fake_run_mypy)

    exit_code = mypy_ratchet.main(["--repo-root", str(tmp_path), "--base-ref", "stale-sha"])

    assert exit_code == 1
    assert seen == {"paths": [SAMPLE_PATH], "root": tmp_path.resolve(), "base": "origin/main"}
    assert "Mypy ratchet failed (exit 1)" in capsys.readouterr().err
