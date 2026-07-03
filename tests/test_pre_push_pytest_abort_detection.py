#!/usr/bin/env python3
"""Regression coverage for issue #2827 pre-push pytest abort reporting."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PRE_PUSH = REPO_ROOT / ".githooks" / "pre-push"


def _run_git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        check=True,
        text=True,
        timeout=30,
    )
    return result.stdout.strip()


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _make_repo(tmp_path: Path, *, pytest_mode: str) -> tuple[Path, str, str, dict[str, str]]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _run_git(repo, "init")
    _run_git(repo, "checkout", "-b", "main")
    _run_git(repo, "config", "user.name", "Pre Push Test")
    _run_git(repo, "config", "user.email", "pre-push-test@example.invalid")

    hook_dir = repo / ".githooks"
    hook_dir.mkdir()
    _write_executable(hook_dir / "pre-push", PRE_PUSH.read_text(encoding="utf-8"))

    (repo / "README.md").write_text("# fixture\n", encoding="utf-8")
    _run_git(repo, "add", ".")
    _run_git(repo, "commit", "-m", "test: base")
    base_sha = _run_git(repo, "rev-parse", "HEAD")
    _run_git(repo, "update-ref", "refs/remotes/origin/main", base_sha)
    _run_git(repo, "checkout", "-b", "feature/pytest-abort")

    (repo / "pkg.py").write_text("value = 1\n", encoding="utf-8")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_pkg.py").write_text("def test_pkg(): pass\n", encoding="utf-8")
    _run_git(repo, "add", ".")
    _run_git(repo, "commit", "-m", "test: add python change")
    head_sha = _run_git(repo, "rev-parse", "HEAD")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_executable(bin_dir / "uv", "#!/usr/bin/env bash\nexit 1\n")
    _write_executable(bin_dir / "ruff", "#!/usr/bin/env bash\nexit 0\n")
    _write_executable(bin_dir / "mypy", "#!/usr/bin/env bash\nexit 0\n")
    _write_executable(
        bin_dir / "python3",
        """#!/usr/bin/env bash
if [ "$1" = "-c" ]; then
    exit 0
fi
if [ "$1" = "-m" ] && [ "$2" = "pytest" ]; then
    case "$PYTEST_FAKE_MODE" in
        aborted)
            printf 'tests/test_security_scan_vulnerabilities.py::test_get_language_shebang_fallback[#!/bin/bash\\n-bash] '
            exit 137
            ;;
        failed)
            cat <<'OUT'
============================= test session starts ==============================
tests/test_pkg.py F
=========================== short test summary info ============================
FAILED tests/test_pkg.py::test_pkg - AssertionError
========================= 1 failed, 1 passed in 0.10s ==========================
OUT
            exit 1
            ;;
    esac
fi
exit 0
""",
    )

    scratch = tmp_path / "scratch"
    scratch.mkdir()
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env["PYTEST_FAKE_MODE"] = pytest_mode
    env["TMPDIR"] = str(scratch)
    return repo, base_sha, head_sha, env


def _run_pre_push(
    repo: Path,
    base_sha: str,
    head_sha: str,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(repo / ".githooks" / "pre-push")],
        cwd=repo,
        input=f"refs/heads/feature/pytest-abort {head_sha} "
        f"refs/heads/feature/pytest-abort {base_sha}\n",
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )


def test_aborted_pytest_reports_aborted_run_not_failed_test(tmp_path: Path) -> None:
    repo, base_sha, head_sha, env = _make_repo(tmp_path, pytest_mode="aborted")

    result = _run_pre_push(repo, base_sha, head_sha, env)

    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert "ERROR: Python tests aborted before pytest summary (exit 137, signal 9)" in output
    assert "last streamed test may be innocent" in output
    assert "Fix failing tests before pushing." not in output


def test_pytest_failure_with_summary_keeps_test_failure_guidance(tmp_path: Path) -> None:
    repo, base_sha, head_sha, env = _make_repo(tmp_path, pytest_mode="failed")

    result = _run_pre_push(repo, base_sha, head_sha, env)

    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert "ERROR: Python tests failed" in output
    assert "Fix failing tests before pushing." in output
    assert "Python tests aborted before pytest summary" not in output
