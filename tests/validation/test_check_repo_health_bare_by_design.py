"""A legitimately bare repository must not be told to repair itself.

Split from ``test_check_repo_health.py``, which pins detection, to keep both
files under the 500-line taste ceiling. These cases pin the opposite obligation:
the layouts where ``core.bare = true`` is correct, and where the repair the gate
prints for issue #4698 would destroy a healthy repository.

The layout that matters is ordinary git::

    git clone --bare seed bareA.git
    git -C bareA.git worktree add wtA

``wtA`` is a live checkout. ``git -C wtA status`` works. Its local config scope
reads ``true``, inherited from the bare parent through the shared config, and
its ``.git`` marker names a private git directory under
``bareA.git/worktrees/wtA``. An earlier discriminator anchored on
``git rev-parse --absolute-git-dir`` found that marker, called the repository
corrupted, and printed ``Fix: git config core.bare false``. That command writes
into the bare parent's shared config, so running it breaks ``bareA.git`` and
every sibling worktree at once.
``test_the_printed_repair_would_break_the_bare_parent`` measures that damage and
is the reason the verdict here has to be exit 0.

The second layout is a bare repository stored at a path literally named
``.git``. git derives a bare repository's main-worktree path by stripping a
trailing ``.git`` component, so ``git clone --bare seed dirD/.git`` reports
``worktree dirD``, which is the same shape a poisoned checkout at
``corrupt/seed`` reports. Path alone cannot separate them.

Content alone cannot either, and that was a live false positive: nothing stops
a bare repository's holding directory carrying a README, a log, or a deploy
script, and reading the listing alone called such a layout a checkout that had
lost its files. The separating fact is repository metadata. A checkout has a
staged index at ``<common>/index``; a bare repository has none, including one
that has handed out linked worktrees, whose indexes live under
``<common>/worktrees/<name>/``. ``TestTheStagedIndexSeparatesACheckoutFromABare
Repository`` pins that measurement, and the content read stays as a second
condition for the bare repository someone ran ``git read-tree`` inside.

Coverage:

- positive: a linked worktree of a genuinely bare repository, the bare parent
  read through that worktree, a bare repository at a ``.git``-named path, and
  that same repository with an unrelated file beside it each exit 0 and print
  no repair, through ``main`` and through the CLI process.
- negative: the discriminating controls. A poisoned main checkout read from its
  own linked worktree still exits 1, and a real checkout reported under the
  same ``worktree holder`` shape still exits 1, so the exit-0 cases above are
  not passing because the gate stopped detecting anything.
- edge: ``_has_main_work_tree_index`` on a bare repository, a checkout, a bare
  repository with a linked worktree, and a missing path;
  ``_holds_checked_out_content`` on a directory holding only ``.git``, on a
  missing directory, and on a real checkout.
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

# The exact command the gate prints for a genuinely corrupted checkout.
_REPAIR = "--replace-all core.bare false"

# A broader marker for "no repair was printed" checks in this file. Without
# the `--replace-all` flag, so it still catches a regression to the older,
# unsafe `git config core.bare false` spelling appearing where no repair
# should print at all -- narrowing this to `_REPAIR` would let that
# regression through by no longer matching the string it emits. No stream
# may carry either form for any layout in this file.
_REPAIR_MARKER = "core.bare false"


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
    result = _try_git(cwd, *args)
    assert result.returncode == 0, f"git {args} failed: {result.stderr}"
    return result


def _try_git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run git without asserting, for cases where the failure is the evidence."""
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        env=_git_test_env(),
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture(autouse=True)
def _use_scratch_git_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the gate's own git calls off the host's global and system config."""
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)


def _make_repo(root: Path, name: str = "seed") -> Path:
    """Create a scratch checkout with one commit."""
    repo = root / name
    repo.mkdir(parents=True)
    _git(repo, "init", "-q")
    (repo / "tracked.txt").write_text("content\n", encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


def _make_bare_with_worktree(tmp_path: Path) -> tuple[Path, Path]:
    """Return ``(bare repository, its linked worktree)`` for a standard layout."""
    seed = _make_repo(tmp_path)
    bare = tmp_path / "bareA.git"
    _git(tmp_path, "clone", "-q", "--bare", str(seed), str(bare))
    linked = tmp_path / "wtA"
    _git(bare, "worktree", "add", "-q", "--detach", str(linked))
    return bare, linked


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


class TestALinkedWorktreeOfABareRepositoryIsHealthy:
    """Positive: the standard bare-plus-worktree layout is not the incident."""

    def test_the_layout_under_test_is_a_working_checkout(self, tmp_path: Path) -> None:
        """The premise: this is a live work tree reading ``local true``."""
        _bare, linked = _make_bare_with_worktree(tmp_path)

        assert _try_git(linked, "status", "--short").returncode == 0
        scopes = _git(linked, "config", "--show-scope", "--get-all", "core.bare")
        assert scopes.stdout.strip() == "local\ttrue"

    def test_the_printed_repair_would_break_the_bare_parent(self, tmp_path: Path) -> None:
        """Why exit 0 is required: the repair is destructive on this layout."""
        bare, linked = _make_bare_with_worktree(tmp_path)
        assert _try_git(linked, "status", "--short").returncode == 0

        _git(bare, "config", "core.bare", "false")

        broken = _try_git(bare, "status", "--short")
        assert broken.returncode != 0
        assert "must be run in a work tree" in broken.stderr

    def test_the_linked_worktree_exits_zero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _bare, linked = _make_bare_with_worktree(tmp_path)

        code = check_repo_health.main([str(linked)])

        assert code == 0
        assert "bare repository with no work tree" in capsys.readouterr().out

    def test_the_bare_parent_itself_exits_zero(self, tmp_path: Path) -> None:
        """A bare repository that has handed out a worktree is still bare."""
        bare, _linked = _make_bare_with_worktree(tmp_path)

        assert check_repo_health.main([str(bare)]) == 0

    def test_no_repair_reaches_either_stream(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The gate must never hand this reader a command that destroys the repo."""
        _bare, linked = _make_bare_with_worktree(tmp_path)

        check_repo_health.main([str(linked)])

        captured = capsys.readouterr()
        assert _REPAIR_MARKER not in captured.out
        assert _REPAIR_MARKER not in captured.err
        assert "Fix:" not in captured.err

    def test_the_cli_process_exits_zero_and_prints_no_repair(self, tmp_path: Path) -> None:
        """A return value cannot block a hook; the process status can."""
        _bare, linked = _make_bare_with_worktree(tmp_path)

        result = _run_cli(linked)

        assert result.returncode == 0, result.stdout + result.stderr
        assert _REPAIR_MARKER not in result.stdout + result.stderr

    def test_the_classifier_reports_no_work_tree(self, tmp_path: Path) -> None:
        """``work_tree`` is what ``_report_corruption`` would name in the repair."""
        _bare, linked = _make_bare_with_worktree(tmp_path)

        health = check_repo_health.diagnose(linked)

        assert health.status == "bare_by_design"
        assert health.work_tree is None

    def test_a_poisoned_main_checkout_is_still_caught_from_its_linked_worktree(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The discriminating control for every exit-0 case above.

        Same vantage point, same ``local true`` reading, same private ``.git``
        marker. Only the main worktree differs: here it is a real checkout, so
        the value is corruption and the repair is correct.
        """
        seed = _make_repo(tmp_path)
        linked = tmp_path / "poisoned-linked"
        _git(seed, "worktree", "add", "-q", "--detach", str(linked))
        _git(seed, "config", "core.bare", "true")

        code = check_repo_health.main([str(linked)])

        assert code == 1
        err = capsys.readouterr().err
        assert f"Fix: git config {_REPAIR}" in err
        assert str(seed) in err


class TestABareRepositoryStoredAtADotGitPath:
    """A bare repository named ``.git`` is not a checkout that lost its files."""

    @staticmethod
    def _bare_at_dot_git(tmp_path: Path) -> Path:
        seed = _make_repo(tmp_path)
        holder = tmp_path / "dirD"
        holder.mkdir()
        _git(tmp_path, "clone", "-q", "--bare", str(seed), str(holder / ".git"))
        return holder

    def test_git_names_the_holding_directory_as_the_main_worktree(
        self, tmp_path: Path
    ) -> None:
        """The premise: path alone cannot tell this from a poisoned checkout."""
        holder = self._bare_at_dot_git(tmp_path)

        listing = _git(holder / ".git", "worktree", "list", "--porcelain")

        assert listing.stdout.splitlines()[0] == f"worktree {holder}"
        assert sorted(entry.name for entry in holder.iterdir()) == [".git"]

    def test_it_exits_zero_and_prints_no_repair(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        holder = self._bare_at_dot_git(tmp_path)

        code = check_repo_health.main([str(holder / ".git")])

        assert code == 0
        captured = capsys.readouterr()
        assert "bare repository with no work tree" in captured.out
        assert _REPAIR_MARKER not in captured.out + captured.err

    def test_an_unrelated_file_beside_the_bare_repository_still_exits_zero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Nothing stops a bare repository's holding directory holding a file.

        A README, a log, or a deploy script sitting beside ``holder/.git`` is
        ordinary. Reading the listing alone called that a checkout that had lost
        its files and printed the repair that destroys the repository, which is
        the false positive ``_has_main_work_tree_index`` exists to close.
        """
        holder = self._bare_at_dot_git(tmp_path)
        (holder / "README.md").write_text("unrelated\n", encoding="utf-8")

        code = check_repo_health.main([str(holder / ".git")])

        assert code == 0
        captured = capsys.readouterr()
        assert _REPAIR_MARKER not in captured.out + captured.err

    def test_the_listing_alone_would_have_called_that_layout_a_checkout(
        self, tmp_path: Path
    ) -> None:
        """The control for the case above: the old read really did see content."""
        holder = self._bare_at_dot_git(tmp_path)
        (holder / "README.md").write_text("unrelated\n", encoding="utf-8")

        assert check_repo_health._holds_checked_out_content(holder) is True
        assert check_repo_health._has_main_work_tree_index(holder / ".git") is False

    def test_a_real_checkout_at_the_same_path_shape_still_exits_one(
        self, tmp_path: Path
    ) -> None:
        """The discriminating control: same reported shape, real staged index.

        ``git worktree list`` names ``holder`` for both layouts, so if this
        passed, the exit-0 cases above would prove only that the gate had
        stopped detecting anything.
        """
        seed = _make_repo(tmp_path)
        holder = tmp_path / "holder"
        _git(tmp_path, "clone", "-q", str(seed), str(holder))
        _git(holder, "config", "core.bare", "true")

        listing = _try_git(holder / ".git", "worktree", "list", "--porcelain")
        assert listing.stdout.splitlines()[0] == f"worktree {holder}"
        assert check_repo_health._has_main_work_tree_index(holder / ".git") is True
        assert check_repo_health.main([str(holder / ".git")]) == 1


class TestTheStagedIndexSeparatesACheckoutFromABareRepository:
    """Edge: the repository metadata that a directory listing cannot supply.

    Measured on git 2.43.0 and pinned here so a git version that starts
    creating an index for a bare repository fails a test that names the reason
    rather than silently widening the corrupted verdict.
    """

    def test_a_bare_repository_has_no_index(self, tmp_path: Path) -> None:
        seed = _make_repo(tmp_path)
        bare = tmp_path / "origin.git"
        _git(tmp_path, "clone", "-q", "--bare", str(seed), str(bare))

        assert check_repo_health._has_main_work_tree_index(bare) is False

    def test_a_checkout_has_an_index(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)

        assert check_repo_health._has_main_work_tree_index(repo / ".git") is True

    def test_a_bare_repository_that_handed_out_a_worktree_still_has_none(
        self, tmp_path: Path
    ) -> None:
        """The linked worktree's index sits under ``worktrees/<name>/``."""
        bare, _linked = _make_bare_with_worktree(tmp_path)

        assert check_repo_health._has_main_work_tree_index(bare) is False
        assert (bare / "worktrees" / "wtA" / "index").is_file()

    def test_a_missing_common_directory_has_no_index(self, tmp_path: Path) -> None:
        """Ambiguity resolves toward bare by design, so an absent path is False."""
        assert check_repo_health._has_main_work_tree_index(tmp_path / "absent") is False


class TestContentSeparatesAWorkTreeFromAPhantomOne:
    """Edge: the second condition, for a bare repository that gained an index."""

    def test_a_directory_holding_only_a_git_entry_holds_no_content(
        self, tmp_path: Path
    ) -> None:
        holder = tmp_path / "dirD"
        (holder / ".git").mkdir(parents=True)

        assert check_repo_health._holds_checked_out_content(holder) is False

    def test_a_checkout_holds_content(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)

        assert check_repo_health._holds_checked_out_content(repo) is True

    def test_a_missing_directory_holds_no_content(self, tmp_path: Path) -> None:
        """Ambiguity resolves toward bare by design, so an unreadable path is False."""
        assert check_repo_health._holds_checked_out_content(tmp_path / "absent") is False

    def test_a_dotfile_beside_the_git_entry_counts_as_content(
        self, tmp_path: Path
    ) -> None:
        """``.gitignore`` is tracked content; only ``.git`` itself is excluded."""
        holder = tmp_path / "dirD"
        (holder / ".git").mkdir(parents=True)
        (holder / ".gitignore").write_text("*.log\n", encoding="utf-8")

        assert check_repo_health._holds_checked_out_content(holder) is True
