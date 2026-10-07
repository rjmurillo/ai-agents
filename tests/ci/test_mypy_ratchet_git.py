"""The mypy ratchet against a real git repository and a real mypy run."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.ci import mypy_ratchet
from scripts.validation.git_hook_policy import MYPY_RATCHET_BASE_REF_ENV
from tests.ci.mypy_ratchet_git_harness import (
    PRE_EXISTING_ERROR,
    SAMPLE_PATH,
    check_git,
    commit,
    error_at,
    isolate_env,
    make_repo_with_type_debt,
    write,
)


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    isolate_env(monkeypatch)


def test_passes_and_says_so_when_no_python_file_changed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo, base = make_repo_with_type_debt(tmp_path)
    write(repo, "README.md", "fixture, edited\n")
    commit(repo, "docs only")

    exit_code = mypy_ratchet.main(["--repo-root", str(repo), "--base-ref", base])

    assert exit_code == 0
    assert "0 Python files changed" in capsys.readouterr().out


def test_passes_when_the_only_error_predates_the_change(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo, base = make_repo_with_type_debt(tmp_path)
    write(repo, SAMPLE_PATH, PRE_EXISTING_ERROR + "\n\ndef added() -> int:\n    return 1\n")
    commit(repo, "add a well-typed function")

    exit_code = mypy_ratchet.main(["--repo-root", str(repo), "--base-ref", base])

    out = capsys.readouterr().out
    assert exit_code == 0, out
    assert error_at(2) in out, "pre-existing debt must stay visible"
    assert "no blocking errors in 1 changed Python file(s)" in out


def test_blocks_an_error_on_an_added_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo, base = make_repo_with_type_debt(tmp_path)
    write(
        repo, SAMPLE_PATH, PRE_EXISTING_ERROR + '\n\ndef added() -> int:\n    return "also wrong"\n'
    )
    commit(repo, "add a mistyped function")

    exit_code = mypy_ratchet.main(["--repo-root", str(repo), "--base-ref", base])

    captured = capsys.readouterr()
    assert exit_code == 1, captured.out
    assert error_at(6) in captured.out
    assert "Mypy ratchet failed (exit 1)" in captured.err


def test_cli_exits_nonzero_so_the_workflow_step_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo, base = make_repo_with_type_debt(tmp_path)
    write(repo, SAMPLE_PATH, PRE_EXISTING_ERROR + '\nVALUE: int = "wrong"\n')
    commit(repo, "add a mistyped constant")
    monkeypatch.setenv(MYPY_RATCHET_BASE_REF_ENV, base)

    result = subprocess.run(
        [
            mypy_ratchet.sys.executable,
            str(Path(mypy_ratchet.__file__).resolve()),
            "--repo-root",
            str(repo),
        ],
        capture_output=True,
        text=True,
        errors="replace",
        encoding="utf-8",
        check=False,
        cwd=repo,
    )

    assert result.returncode == 1, result.stdout + result.stderr
    assert error_at(4) in result.stdout


def test_falls_back_from_a_stale_base_and_judges_against_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo, base = make_repo_with_type_debt(tmp_path)
    check_git(repo, "update-ref", "refs/remotes/origin/main", base)
    write(repo, SAMPLE_PATH, PRE_EXISTING_ERROR + "\nVALUE: int = 1\n")
    commit(repo, "add a well-typed constant")
    # A SHA the repository does not hold, like a force-pushed-away `before`.
    monkeypatch.setenv(MYPY_RATCHET_BASE_REF_ENV, "1" * 40)

    exit_code = mypy_ratchet.main(["--repo-root", str(repo)])

    # Without repinning the base to origin/main, run_mypy would read the stale
    # SHA, lose the line map, and block on the pre-existing error at line 2.
    assert exit_code == 0
    assert mypy_ratchet.os.environ[MYPY_RATCHET_BASE_REF_ENV] == "origin/main"
