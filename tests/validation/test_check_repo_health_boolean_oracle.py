"""The gate's verdict must be git's boolean reading, not a list of spellings.

Split from ``test_check_repo_health.py`` to keep both files under the 500-line
taste ceiling. Every expectation in this file is derived from git at run time
rather than written down, because a written-down list is what the gate got
wrong.

The gate used to compare ``core.bare`` against ``frozenset({"", "true", "yes",
"on", "1"})``. That set is wrong at both ends, measured on git 2.43.0:

* ``git_parse_maybe_bool`` falls through to integer parsing, so ``2``, ``42``
  and ``-1`` are all true to git. The gate read them as false and printed
  ``core.bare read in 1 config scope(s), none set true`` for a repository whose
  ``git status`` already fatals.
* An explicitly empty value (``bare = ``) is false to git, but the empty string
  was in the set, so the gate exited 1 on a healthy repository. Because
  repo-health runs first in both the pre-commit and pre-push job lists, that
  blocked every commit and every push, and the diagnosis it printed was
  fabricated: it asserted every work-tree command fails when ``git status``
  works fine.

The test that was supposed to cover this parametrized over ``["true", "yes",
"on", "1"]``, which is the implementation constant minus the empty string. It
mirrored the code rather than git, so it passed identically whether or not the
parser was correct and could not fail for either defect above.

So the oracle here is ``git rev-parse --is-bare-repository``, asked of the same
repository under test. It is an independent reading of the same question: git's
own answer to whether this repository is bare. The expected exit code is
derived from it, so a future edit that reintroduces a hand-rolled parser fails
these cases without anyone having to remember which spellings git accepts.

The two spellings that need a hand-written config line are the ones
``--get-all`` cannot distinguish: it prints an identical empty field for a
valueless variable (``bare``) and an explicitly empty one (``bare = ``), while
git reads the first as true and the second as false. They are still
oracle-derived here; only the way they are written into the file differs.

Coverage:

- positive: the healthy spellings (``0``, ``false``, ``no``, ``off``, and an
  explicitly empty value) exit 0, matching the oracle.
- negative: the bare spellings (``true``, ``yes``, ``on``, ``1``, the nonzero
  integers ``2``, ``42`` and ``-1``, and a valueless variable) exit 1, matching
  the oracle.
- edge: ``extensions.worktreeConfig`` is read through the same boolean flag, so
  a nonzero integer enables the worktree-scoped immunization line exactly when
  git accepts a ``--worktree`` write.
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

# Every spelling git accepts as a boolean, including the nonzero integers the
# retired parser read as false. The expected verdict is never written here; it
# comes from the oracle.
_BOOLEAN_SPELLINGS = ["true", "yes", "on", "1", "2", "42", "-1", "0", "false", "no", "off"]


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


def _rewrite_bare_line(repo: Path, replacement: str) -> None:
    """Replace the ``bare = false`` line ``git init`` wrote with ``replacement``.

    ``git config`` cannot write either spelling this reaches: a valueless
    variable and an explicitly empty one both have to be put in the file by
    hand.
    """
    config = repo / ".git" / "config"
    config.write_text(
        config.read_text(encoding="utf-8").replace("bare = false", replacement),
        encoding="utf-8",
    )


def _oracle(repo: Path) -> str:
    """Ask git whether this repository is bare. The gate must agree."""
    return _git(repo, "rev-parse", "--is-bare-repository").stdout.strip()


class TestTheVerdictTracksGitsOwnBooleanReading:
    """The expected exit code is derived from git, never from a spelling list."""

    @pytest.mark.parametrize("spelling", _BOOLEAN_SPELLINGS)
    def test_a_written_value_exits_as_git_reads_it(
        self, spelling: str, tmp_path: Path
    ) -> None:
        repo = _make_repo(tmp_path)
        _git(repo, "config", "core.bare", spelling)

        expected = 1 if _oracle(repo) == "true" else 0

        assert check_repo_health.main([str(repo)]) == expected

    def test_a_nonzero_integer_is_bare_to_git_and_to_the_gate(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The all-clear the retired parser printed for a repository git refuses."""
        repo = _make_repo(tmp_path)
        _git(repo, "config", "core.bare", "42")

        assert _oracle(repo) == "true"
        code = check_repo_health.main([str(repo)])

        assert code == 1
        captured = capsys.readouterr()
        assert "none set true" not in captured.out
        assert "core.bare is set true" in captured.err

    def test_an_explicitly_empty_value_is_healthy_and_does_not_block(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """``bare = `` is false to git, so blocking on it blocks a healthy repo."""
        repo = _make_repo(tmp_path)
        _rewrite_bare_line(repo, "bare = ")

        assert _oracle(repo) == "false"
        code = check_repo_health.main([str(repo)])

        assert code == 0
        assert "none set true" in capsys.readouterr().out

    def test_a_valueless_variable_is_bare_to_git_and_to_the_gate(
        self, tmp_path: Path
    ) -> None:
        """The control for the case above: same empty field, opposite verdict."""
        repo = _make_repo(tmp_path)
        _rewrite_bare_line(repo, "bare")

        assert _oracle(repo) == "true"

        assert check_repo_health.main([str(repo)]) == 1


class TestTheWorktreeConfigExtensionIsReadTheSameWay:
    """The immunization line is offered exactly when ``--worktree`` would work."""

    @staticmethod
    def _poisoned_with_extension(tmp_path: Path, enabled: str) -> Path:
        repo = _make_repo(tmp_path)
        _git(repo, "config", "extensions.worktreeConfig", enabled)
        _git(repo, "worktree", "add", "-q", str(tmp_path / "linked"), "-b", "feature")
        _git(repo, "config", "core.bare", "true")
        return repo

    def test_a_nonzero_integer_enables_the_immunization_line(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """git accepts ``2`` as enabling the extension, so the hint is real advice."""
        repo = self._poisoned_with_extension(tmp_path, "2")

        assert check_repo_health.main([str(repo)]) == 1
        assert "in every worktree" in capsys.readouterr().err

    def test_a_disabled_extension_withholds_it(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The control: ``0`` is false to git, and ``--worktree`` then exits 128."""
        repo = self._poisoned_with_extension(tmp_path, "0")

        assert check_repo_health.main([str(repo)]) == 1
        assert "in every worktree" not in capsys.readouterr().err
