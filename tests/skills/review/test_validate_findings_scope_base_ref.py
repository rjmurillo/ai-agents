"""Base-reference handling for the ``/review`` findings-scope validator (issue #7399).

The help text documented ``--base-branch origin/main`` while the script always
prepended ``origin/``, so the documented call diffed ``origin/origin/main`` and
exited 0 having checked nothing. These tests pin three behaviors:

- a bare name (``main``) and a remote-prefixed name (``origin/main``) both diff
  against the same commit;
- a base present only as a local branch still resolves;
- a base that names no commit exits 2 and never reports a passed check.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git CLI not installed")

from tests.skills.claude_skills_import import PROJECT_ROOT, import_skill_script

mod = import_skill_script(
    ".claude/skills/review/scripts/validate_findings_scope.py",
    module_name="validate_findings_scope_base_ref",
)

SCRIPT = Path(PROJECT_ROOT) / ".claude/skills/review/scripts/validate_findings_scope.py"
IN_SCOPE = "VERDICT: PASS\n- severity: LOW\n  location: changed.py:1\n"
OUT_OF_SCOPE = "VERDICT: CRITICAL_FAIL\n- severity: CRITICAL\n  location: unrelated.py:1\n"


def _git(args: list[str], cwd: Path) -> None:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Scope Test",
        "GIT_AUTHOR_EMAIL": "scope-test@example.com",
        "GIT_COMMITTER_NAME": "Scope Test",
        "GIT_COMMITTER_EMAIL": "scope-test@example.com",
    }
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )
    assert result.returncode == 0, f"git {' '.join(args)} failed: {result.stderr}"


def _commit(repo: Path, name: str) -> None:
    (repo / name).write_text(f"{name}\n", encoding="utf-8")
    _git(["add", name], repo)
    _git(["commit", "-m", name], repo)


@pytest.fixture
def repo_with_origin(tmp_path: Path) -> Path:
    """A clone whose ``origin/<base>`` exists, on a feature branch with one change."""
    remote = tmp_path / "remote.git"
    work = tmp_path / "work"
    _git(["init", "--bare", "-b", "master", str(remote)], tmp_path)
    _git(["init", "-b", "master", str(work)], tmp_path)
    _commit(work, "README.md")
    _git(["remote", "add", "origin", str(remote)], work)
    _git(["push", "-u", "origin", "master"], work)
    _git(["checkout", "-b", "feature"], work)
    _commit(work, "changed.py")
    return work


@pytest.fixture
def repo_without_remote(tmp_path: Path) -> Path:
    """A repo with a local ``trunk`` branch and no remote at all."""
    work = tmp_path / "local"
    _git(["init", "-b", "trunk", str(work)], tmp_path)
    _commit(work, "README.md")
    _git(["checkout", "-b", "feature"], work)
    _commit(work, "changed.py")
    return work


def _run_cli(
    worktree: Path, base: str, text: str = OUT_OF_SCOPE
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--worktree",
            str(worktree),
            "--base-branch",
            base,
            "--text",
            text,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


class TestGetDiffFiles:
    @pytest.mark.parametrize("base", ["master", "origin/master"])
    def test_bare_and_remote_prefixed_base_diff_the_same_files(
        self, repo_with_origin: Path, base: str
    ) -> None:
        assert mod.get_diff_files(str(repo_with_origin), base) == ["changed.py"]

    def test_local_only_base_resolves_without_a_remote(self, repo_without_remote: Path) -> None:
        assert mod.get_diff_files(str(repo_without_remote), "trunk") == ["changed.py"]

    @pytest.mark.parametrize(
        "base", ["no-such-branch", "origin/no-such-branch", "", "-x", "--output=/tmp/pwn"]
    )
    def test_unresolvable_base_raises_instead_of_returning_none(
        self, repo_with_origin: Path, base: str
    ) -> None:
        with pytest.raises(LookupError) as excinfo:
            mod.get_diff_files(str(repo_with_origin), base)
        assert repr(base) in str(excinfo.value)


class TestCliExitCodes:
    def test_documented_remote_prefixed_base_runs_the_scope_check(
        self, repo_with_origin: Path
    ) -> None:
        result = _run_cli(repo_with_origin, "origin/master")

        assert result.returncode == 1, result.stderr
        assert "unrelated.py" in result.stderr
        assert "origin/origin" not in result.stderr
        assert "skipping scope check" not in result.stderr

    def test_bare_base_runs_the_scope_check(self, repo_with_origin: Path) -> None:
        result = _run_cli(repo_with_origin, "master")

        assert result.returncode == 1, result.stderr
        assert "unrelated.py" in result.stderr

    def test_unresolvable_base_exits_two_and_says_the_check_did_not_run(
        self, repo_with_origin: Path
    ) -> None:
        result = _run_cli(repo_with_origin, "origin/no-such-branch")

        assert result.returncode == 2
        assert "did not resolve" in result.stderr
        assert "scope check did not run" in result.stderr

    def test_main_returns_two_for_unresolvable_base(self, repo_with_origin: Path) -> None:
        rc = mod.main(
            [
                "--worktree",
                str(repo_with_origin),
                "--base-branch",
                "no-such-branch",
                "--text",
                OUT_OF_SCOPE,
            ]
        )

        assert rc == 2


class TestGitFailureStillDegrades:
    """A git failure is not a bad base argument: it keeps the exit-0 degrade path."""

    def test_non_repository_worktree_returns_none(self, tmp_path: Path) -> None:
        assert mod.get_diff_files(str(tmp_path), "main") is None

    def test_non_repository_worktree_exits_zero_with_warning(self, tmp_path: Path) -> None:
        result = _run_cli(tmp_path, "main")

        assert result.returncode == 0
        assert "skipping scope check" in result.stderr
        assert "did not resolve" not in result.stderr


class TestInScopeEndToEnd:
    def test_in_scope_finding_with_remote_prefixed_base_exits_zero(
        self, repo_with_origin: Path
    ) -> None:
        result = _run_cli(repo_with_origin, "origin/master", IN_SCOPE)

        assert result.returncode == 0, result.stderr
        assert "skipping scope check" not in result.stderr
        assert "OUT-OF-SCOPE" not in result.stderr
