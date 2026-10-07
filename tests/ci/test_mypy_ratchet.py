from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.ci import mypy_ratchet
from scripts.validation.git_hook_policy import MYPY_RATCHET_BASE_REF_ENV

SAMPLE_PATH = "app/sample.py"
PRE_EXISTING_ERROR = 'def legacy() -> int:\n    return "not an int"\n'


def _check_git(repo: Path, *argv: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *argv],
        capture_output=True,
        text=True,
        errors="replace",
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _write(repo: Path, relative_path: str, content: str) -> None:
    path = repo / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _commit(repo: Path, message: str) -> str:
    _check_git(repo, "add", "-A")
    _check_git(repo, "commit", "-qm", message)
    return _check_git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo_with_type_debt(tmp_path: Path) -> tuple[Path, str]:
    """A repository whose base commit already carries one mypy error."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _check_git(repo, "init", "-q", "-b", "main")
    _check_git(repo, "config", "user.email", "test@example.com")
    _check_git(repo, "config", "user.name", "Test")
    _check_git(repo, "config", "commit.gpgsign", "false")
    _write(repo, "pyproject.toml", '[tool.mypy]\npython_version = "3.14"\n')
    _write(repo, SAMPLE_PATH, PRE_EXISTING_ERROR)
    _write(repo, "README.md", "fixture\n")
    return repo, _commit(repo, "base with type debt")


def _error_at(line: int) -> str:
    """Render the prefix mypy prints for an error in the fixture file."""
    return f"{SAMPLE_PATH}:{line}: error"


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    # main() writes MYPY_RATCHET_BASE_REF into os.environ. delenv on an absent
    # key records nothing to restore, so setenv first: teardown then removes
    # the value main() wrote instead of leaking it into later tests.
    for name in ("GITHUB_EVENT_NAME", MYPY_RATCHET_BASE_REF_ENV):
        monkeypatch.setenv(name, "")
        monkeypatch.delenv(name)
    return monkeypatch


def test_default_base_ref_reads_the_environment(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv(MYPY_RATCHET_BASE_REF_ENV, "abc123")

    assert mypy_ratchet.default_base_ref() == "abc123"


def test_default_base_ref_falls_back_when_unset(clean_env: pytest.MonkeyPatch) -> None:
    assert mypy_ratchet.default_base_ref() == "origin/main"


def test_default_base_ref_falls_back_for_zero_sha(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv(MYPY_RATCHET_BASE_REF_ENV, "0" * 40)

    assert mypy_ratchet.default_base_ref() == "origin/main"


def test_default_base_ref_uses_origin_main_on_push(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("GITHUB_EVENT_NAME", "push")
    clean_env.setenv(MYPY_RATCHET_BASE_REF_ENV, "abc123")

    assert mypy_ratchet.default_base_ref() == "origin/main"


def test_main_rejects_a_directory_that_is_not_a_git_worktree(
    clean_env: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = mypy_ratchet.main(["--repo-root", str(tmp_path), "--base-ref", "HEAD"])

    assert exit_code == 2
    assert "is not a git worktree" in capsys.readouterr().err


def test_main_returns_external_error_when_git_cannot_list_files(
    clean_env: pytest.MonkeyPatch, repo_with_type_debt: tuple[Path, str]
) -> None:
    repo, _base = repo_with_type_debt
    clean_env.setattr(mypy_ratchet, "changed_python_files", lambda _ref, _root: (3, [], "x"))

    def fail_if_called(_paths: object, _root: object) -> int:
        raise AssertionError("run_mypy must not run when the file list is unknown")

    clean_env.setattr(mypy_ratchet, "run_mypy", fail_if_called)

    assert mypy_ratchet.main(["--repo-root", str(repo), "--base-ref", "HEAD"]) == 3


def test_main_passes_and_says_so_when_no_python_file_changed(
    clean_env: pytest.MonkeyPatch,
    repo_with_type_debt: tuple[Path, str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo, base = repo_with_type_debt
    _write(repo, "README.md", "fixture, edited\n")
    _commit(repo, "docs only")

    exit_code = mypy_ratchet.main(["--repo-root", str(repo), "--base-ref", base])

    assert exit_code == 0
    assert "0 Python files changed" in capsys.readouterr().out


def test_main_pins_run_mypy_to_the_resolved_base_and_propagates_its_exit(
    clean_env: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / ".git").mkdir()
    clean_env.setattr(
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

    clean_env.setattr(mypy_ratchet, "run_mypy", fake_run_mypy)

    exit_code = mypy_ratchet.main(["--repo-root", str(tmp_path), "--base-ref", "stale-sha"])

    assert exit_code == 1
    assert seen == {
        "paths": [SAMPLE_PATH],
        "root": tmp_path.resolve(),
        "base": "origin/main",
    }
    assert "Mypy ratchet failed (exit 1)" in capsys.readouterr().err


def test_main_passes_when_the_only_error_predates_the_change(
    clean_env: pytest.MonkeyPatch,
    repo_with_type_debt: tuple[Path, str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo, base = repo_with_type_debt
    _write(repo, SAMPLE_PATH, PRE_EXISTING_ERROR + "\n\ndef added() -> int:\n    return 1\n")
    _commit(repo, "add a well-typed function")

    exit_code = mypy_ratchet.main(["--repo-root", str(repo), "--base-ref", base])

    out = capsys.readouterr().out
    assert exit_code == 0, out
    assert _error_at(2) in out, "pre-existing debt must stay visible"
    assert "Mypy ratchet passed for 1 changed Python file(s)" in out


def test_main_blocks_an_error_on_an_added_line(
    clean_env: pytest.MonkeyPatch,
    repo_with_type_debt: tuple[Path, str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo, base = repo_with_type_debt
    _write(
        repo,
        SAMPLE_PATH,
        PRE_EXISTING_ERROR + '\n\ndef added() -> int:\n    return "also wrong"\n',
    )
    _commit(repo, "add a mistyped function")

    exit_code = mypy_ratchet.main(["--repo-root", str(repo), "--base-ref", base])

    captured = capsys.readouterr()
    assert exit_code == 1, captured.out
    assert _error_at(6) in captured.out
    assert "Mypy ratchet failed (exit 1)" in captured.err


def test_cli_exits_nonzero_so_the_workflow_step_fails(
    clean_env: pytest.MonkeyPatch, repo_with_type_debt: tuple[Path, str]
) -> None:
    repo, base = repo_with_type_debt
    _write(repo, SAMPLE_PATH, PRE_EXISTING_ERROR + '\nVALUE: int = "wrong"\n')
    _commit(repo, "add a mistyped constant")
    script = Path(mypy_ratchet.__file__).resolve()
    clean_env.setenv(MYPY_RATCHET_BASE_REF_ENV, base)

    result = subprocess.run(
        [mypy_ratchet.sys.executable, str(script), "--repo-root", str(repo)],
        capture_output=True,
        text=True,
        errors="replace",
        encoding="utf-8",
        check=False,
        cwd=repo,
    )

    assert result.returncode == 1, result.stdout + result.stderr
    assert _error_at(4) in result.stdout


def test_cli_falls_back_from_a_stale_base_and_judges_against_it(
    clean_env: pytest.MonkeyPatch, repo_with_type_debt: tuple[Path, str]
) -> None:
    repo, base = repo_with_type_debt
    _check_git(repo, "update-ref", "refs/remotes/origin/main", base)
    _write(repo, SAMPLE_PATH, PRE_EXISTING_ERROR + "\nVALUE: int = 1\n")
    _commit(repo, "add a well-typed constant")
    # A SHA the repository does not hold, like a force-pushed-away `before`.
    clean_env.setenv(MYPY_RATCHET_BASE_REF_ENV, "1" * 40)

    exit_code = mypy_ratchet.main(["--repo-root", str(repo)])

    # Without repinning the base to origin/main, run_mypy would read the stale
    # SHA, lose the line map, and block on the pre-existing error at line 2.
    assert exit_code == 0
    assert mypy_ratchet.os.environ[MYPY_RATCHET_BASE_REF_ENV] == "origin/main"
