"""The repo-health gate refuses a commit or push into a bare-flagged repository.

Issue #4698: something during ``git push`` writes ``core.bare = true`` into the
shared ``.git/config``, and every git command needing a work tree then fails
with ``fatal: this operation must be run in a work tree``. It broke the main
checkout and three of five linked worktrees at once and surfaced as four
unrelated-looking failures, so the gate's job is to put one accurate message
ahead of all of them.

Two design decisions are pinned here because both are counterintuitive.

The gate reads config scopes, not the effective ``--is-bare-repository``
answer. A worktree that carries the worktree-scoped ``false`` GOTCHAS
prescribes still resolves usable while its siblings are dead, so the effective
answer reports that checkout healthy and says nothing about the repository.
``TestAPoisonedSharedConfigIsReportedFromAWorktreeThatStillWorks`` is that case.

Bareness is only a defect where a work tree is meant to exist, and a genuine
bare repository sets ``core.bare = true`` too, so the discriminator is a
``.git`` marker naming this repository's git directory.

Every repository under test is a scratch repository under ``tmp_path``. Running
``git config core.bare true`` against this checkout would write to a
``.git/config`` shared with every live agent worktree and break all of them,
which is the incident this gate exists to detect.

Coverage:

- positive: a healthy checkout and a healthy linked worktree exit 0 and name
  what was read.
- negative: a bare-flagged checkout, linked worktree, subdirectory, and
  ``--separate-git-dir`` checkout each exit 1 and name a repair for the scope
  that carries the value; a poisoned shared config is reported from an
  immunized worktree; a value git cannot parse exits 1 and says why no ``git
  config`` can clear it; the CLI process itself exits nonzero, against a
  healthy control.
- edge: a genuine bare repository, a bare repository nested inside a healthy
  checkout, and a non-repository exit 0; an invalid root exits 2; missing git
  and timeouts exit 3; a valueless ``core.bare`` is read as true, and an
  explicit ``false`` is not read as bare.

``test_check_repo_health_reporting.py`` covers the failure report itself: the
repair each config scope needs, and when the worktree-scoped immunization line
is withheld. ``test_check_repo_health_boolean_oracle.py`` covers which values
count as bare at all, deriving every expectation from ``git rev-parse
--is-bare-repository`` rather than from a list of spellings.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Import the way production imports (issue #2223): prepend ``scripts/validation``
# to ``sys.path`` and import by bare name.
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))
import check_repo_health

GUARD = _VALIDATION_DIR / "check_repo_health.py"


def _git_test_env() -> dict[str, str]:
    """Return a host-independent environment for scratch Git repositories."""
    return {
        "PATH": os.environ.get("PATH", ""),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_AUTHOR_NAME": "test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
    }


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        env=_git_test_env(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"git {args} failed: {result.stderr}"
    return result


@pytest.fixture(autouse=True)
def _use_scratch_git_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the gate's own git calls off the host's global and system config."""
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)


def _make_repo(root: Path, name: str = "repo") -> Path:
    """Create a scratch checkout with one commit."""
    repo = root / name
    repo.mkdir(parents=True)
    _git(repo, "init", "-q")
    (repo / "tracked.txt").write_text("content\n", encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


def _add_worktree(repo: Path, path: Path, branch: str = "feature") -> Path:
    _git(repo, "worktree", "add", "-q", str(path), "-b", branch)
    return path


def _run_cli(repo: Path) -> subprocess.CompletedProcess[str]:
    """Drive the script as lefthook does, so the process exit code is asserted."""
    return subprocess.run(
        [sys.executable, str(GUARD), str(repo)],
        cwd=str(repo),
        env={**_git_test_env(), "PYTHONPATH": str(REPO_ROOT)},
        capture_output=True,
        text=True,
        check=False,
    )


class TestHealthyRepositoriesPass:
    """Positive: nothing flagged bare exits 0 and reports what it read."""

    def test_a_healthy_checkout_exits_zero_and_names_the_repository(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        repo = _make_repo(tmp_path)

        code = check_repo_health.main([str(repo)])

        assert code == 0
        out = capsys.readouterr().out
        assert str(repo) in out
        assert "core.bare read in 1 config scope(s), none set true" in out

    def test_a_healthy_linked_worktree_exits_zero(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        linked = _add_worktree(repo, tmp_path / "linked")

        assert check_repo_health.main([str(linked)]) == 0

    def test_an_explicit_false_is_not_read_as_bare(self, tmp_path: Path) -> None:
        """The control for the true-spelling cases below."""
        repo = _make_repo(tmp_path)
        _git(repo, "config", "core.bare", "false")

        assert check_repo_health.main([str(repo)]) == 0


class TestBareFlaggedWorkTreesFail:
    """Negative: bareness plus a work tree is the incident, and it blocks."""

    def test_a_bare_flagged_checkout_exits_one_and_names_the_repair(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        repo = _make_repo(tmp_path)
        _git(repo, "config", "core.bare", "true")

        code = check_repo_health.main([str(repo)])

        assert code == 1
        err = capsys.readouterr().err
        assert "core.bare is set true (local=true)" in err
        assert "fatal: this operation must be run in a work tree" in err
        assert "Fix: git config core.bare false" in err
        assert "4698" in err

    def test_a_bare_flagged_linked_worktree_exits_one(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        _git(repo, "config", "extensions.worktreeConfig", "true")
        linked = _add_worktree(repo, tmp_path / "linked")
        _git(repo, "config", "core.bare", "true")

        assert check_repo_health.main([str(linked)]) == 1

    def test_a_subdirectory_of_a_bare_flagged_checkout_exits_one(
        self, tmp_path: Path
    ) -> None:
        repo = _make_repo(tmp_path)
        nested = repo / "scripts" / "validation"
        nested.mkdir(parents=True)
        _git(repo, "config", "core.bare", "true")

        assert check_repo_health.main([str(nested)]) == 1

    def test_a_separate_git_dir_checkout_is_still_detected(self, tmp_path: Path) -> None:
        """A ``.git`` file outside a linked worktree still marks a work tree."""
        work = tmp_path / "work"
        work.mkdir()
        _git(tmp_path, "init", "-q", "--separate-git-dir", str(tmp_path / "gitdir"), str(work))
        (work / "tracked.txt").write_text("content\n", encoding="utf-8")
        _git(work, "add", "tracked.txt")
        _git(work, "commit", "-q", "-m", "init")
        _git(work, "config", "core.bare", "true")

        assert check_repo_health.main([str(work)]) == 1

    def test_a_valueless_core_bare_is_read_as_true(self, tmp_path: Path) -> None:
        """git reads a variable with no value as true, so the gate must too."""
        repo = _make_repo(tmp_path)
        config = repo / ".git" / "config"
        config.write_text(
            config.read_text(encoding="utf-8").replace("bare = false", "bare"),
            encoding="utf-8",
        )

        assert check_repo_health.main([str(repo)]) == 1

    def test_the_cli_process_exits_nonzero(self, tmp_path: Path) -> None:
        """A gate that only returns a code to a caller cannot block a hook."""
        repo = _make_repo(tmp_path)
        _git(repo, "config", "core.bare", "true")

        result = _run_cli(repo)

        assert result.returncode == 1, result.stdout + result.stderr
        assert "core.bare" in result.stderr

    def test_the_cli_process_exits_zero_on_a_healthy_checkout(self, tmp_path: Path) -> None:
        """The negative control for the CLI test above."""
        repo = _make_repo(tmp_path)

        result = _run_cli(repo)

        assert result.returncode == 0, result.stdout + result.stderr


class TestAPoisonedSharedConfigIsReportedFromAWorktreeThatStillWorks:
    """The only state a hook can speak from, and the state the incident left.

    Measured on lefthook 2.1.10: lefthook runs ``git rev-parse
    --path-format=absolute --show-toplevel ...`` before its first job and exits
    128 from a bare-flagged worktree, so a job there never runs. A worktree
    carrying the worktree-scoped ``false`` GOTCHAS prescribes does run, and it
    is the one that has to raise the alarm for its dead siblings.
    """

    @staticmethod
    def _immunized_checkout(tmp_path: Path) -> Path:
        repo = _make_repo(tmp_path)
        _git(repo, "config", "extensions.worktreeConfig", "true")
        _add_worktree(repo, tmp_path / "linked")
        _git(repo, "config", "--worktree", "core.bare", "false")
        _git(repo, "config", "core.bare", "true")
        return repo

    def test_the_effective_answer_alone_would_call_this_checkout_healthy(
        self, tmp_path: Path
    ) -> None:
        """The control: this is why the gate does not read --is-bare-repository."""
        repo = self._immunized_checkout(tmp_path)

        effective = subprocess.run(
            ["git", "rev-parse", "--is-bare-repository"],
            cwd=str(repo),
            env=_git_test_env(),
            capture_output=True,
            text=True,
            check=True,
        )

        assert effective.stdout.strip() == "false"

    def test_the_gate_still_fails_and_names_the_sibling_damage(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        repo = self._immunized_checkout(tmp_path)

        code = check_repo_health.main([str(repo)])

        assert code == 1
        err = capsys.readouterr().err
        assert "local=true" in err
        assert "already broken" in err
        assert "Fix: git config core.bare false" in err


class TestRepairNamesEveryScopeThatCarriesTheValue:
    """A repair aimed at the wrong config file leaves the checkout broken."""

    def test_a_worktree_scoped_value_gets_a_worktree_scoped_repair(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        repo = _make_repo(tmp_path)
        _git(repo, "config", "extensions.worktreeConfig", "true")
        _add_worktree(repo, tmp_path / "linked")
        _git(repo, "config", "--worktree", "core.bare", "true")

        code = check_repo_health.main([str(repo)])

        assert code == 1
        assert "Fix: git config --worktree core.bare false" in capsys.readouterr().err


class TestRepositoriesWithNoWorkTreeAreOutOfScope:
    """Edge: bareness is only a defect where a work tree is meant to exist."""

    def test_a_genuine_bare_repository_exits_zero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        bare = tmp_path / "origin.git"
        _git(tmp_path, "init", "-q", "--bare", str(bare))

        code = check_repo_health.main([str(bare)])

        assert code == 0
        assert "bare repository with no work tree" in capsys.readouterr().out

    def test_a_bare_repository_inside_a_checkout_is_not_blamed_on_it(
        self, tmp_path: Path
    ) -> None:
        """The ancestor walk must compare git directories, not just find a marker."""
        repo = _make_repo(tmp_path)
        nested = repo / "vendor" / "mirror.git"
        nested.parent.mkdir(parents=True)
        _git(tmp_path, "init", "-q", "--bare", str(nested))

        assert check_repo_health.main([str(nested)]) == 0

    def test_a_non_repository_reads_no_scopes_and_exits_zero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        plain = tmp_path / "plain"
        plain.mkdir()

        code = check_repo_health.main([str(plain)])

        assert code == 0
        assert "core.bare read in 0 config scope(s)" in capsys.readouterr().out

    def test_a_global_core_bare_outside_a_repository_exits_zero(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A global value is readable anywhere; only a repository can be broken."""
        global_config = tmp_path / "gitconfig"
        global_config.write_text("[core]\n\tbare = true\n", encoding="utf-8")
        monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(global_config))
        plain = tmp_path / "plain"
        plain.mkdir()

        code = check_repo_health.main([str(plain)])

        assert code == 0
        assert "not a git repository" in capsys.readouterr().out


class TestUnverifiableStatesFailClosed:
    """Edge: a state the gate cannot read is not a verified pass."""

    def test_an_invalid_root_exits_two(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = check_repo_health.main([str(tmp_path / "absent")])

        assert code == 2
        assert "Invalid repository root" in capsys.readouterr().err

    def test_missing_git_exits_three(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        repo = _make_repo(tmp_path)
        monkeypatch.setattr(check_repo_health.shutil, "which", lambda _name: None)

        code = check_repo_health.main([str(repo)])

        assert code == 3
        assert "git executable not found" in capsys.readouterr().err

    def test_a_git_timeout_exits_three(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        repo = _make_repo(tmp_path)

        def _timeout(*_args: object, **_kwargs: object) -> None:
            raise subprocess.TimeoutExpired(cmd="git", timeout=1)

        monkeypatch.setattr(check_repo_health.subprocess, "run", _timeout)

        code = check_repo_health.main([str(repo)])

        assert code == 3
        assert "could not be verified" in capsys.readouterr().err

    def test_an_unparseable_core_bare_value_exits_one(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """git refuses every command here, ``git config --unset-all`` included."""
        repo = _make_repo(tmp_path)
        _git(repo, "config", "core.bare", "notabool")

        code = check_repo_health.main([str(repo)])

        assert code == 1
        err = capsys.readouterr().err
        assert "unusable core.bare value" in err
        assert "by hand" in err


class TestDiagnoseClassifiesWithoutPrinting:
    """The classifier is separable from the report, so both can be pinned."""

    def test_a_healthy_checkout_is_usable(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)

        assert check_repo_health.diagnose(repo).status == "usable"

    def test_a_bare_flagged_checkout_is_corrupted(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        _git(repo, "config", "core.bare", "true")

        health = check_repo_health.diagnose(repo)

        assert health.status == "corrupted"
        assert health.work_tree == repo
        assert health.bare_scopes == (("local", "true"),)
        assert health.effective_bare is True

    def test_an_immunized_checkout_is_corrupted_but_not_effectively_bare(
        self, tmp_path: Path
    ) -> None:
        repo = _make_repo(tmp_path)
        _git(repo, "config", "extensions.worktreeConfig", "true")
        _add_worktree(repo, tmp_path / "linked")
        _git(repo, "config", "--worktree", "core.bare", "false")
        _git(repo, "config", "core.bare", "true")

        health = check_repo_health.diagnose(repo)

        assert health.status == "corrupted"
        assert health.effective_bare is False
        assert ("local", "true") in health.bare_scopes

    def test_a_bare_repository_is_bare_by_design(self, tmp_path: Path) -> None:
        bare = tmp_path / "origin.git"
        _git(tmp_path, "init", "-q", "--bare", str(bare))

        assert check_repo_health.diagnose(bare).status == "bare_by_design"

    def test_a_marker_file_with_no_gitdir_line_resolves_to_nothing(
        self, tmp_path: Path
    ) -> None:
        marker = tmp_path / ".git"
        marker.write_text("not a gitdir pointer\n", encoding="utf-8")

        assert check_repo_health._marker_git_dir(marker) is None

    def test_a_relative_gitdir_pointer_resolves_against_the_marker(
        self, tmp_path: Path
    ) -> None:
        target = tmp_path / "elsewhere"
        target.mkdir()
        marker = tmp_path / ".git"
        marker.write_text("gitdir: elsewhere\n", encoding="utf-8")

        assert check_repo_health._marker_git_dir(marker) == target.resolve()

    def test_an_unreadable_marker_resolves_to_nothing(self, tmp_path: Path) -> None:
        marker = tmp_path / ".git"
        marker.mkdir()

        assert check_repo_health._marker_git_dir(marker) is None
