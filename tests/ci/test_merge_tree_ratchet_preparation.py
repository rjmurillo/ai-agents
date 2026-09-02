"""``resolve_default_base_ref`` in ``scripts/ci/merge_tree_ratchet_preparation.py``.

Issue #5441 review (minor finding): the standalone ``merge-tree-ratchet``
Lefthook job used to hardcode ``--base-ref origin/main``, measuring a branch
stacked on a non-main base against the wrong target. Fixing that means
resolving the base ref dynamically the way ``checks_ratchet.py`` does, which
in turn requires normalizing ``refs/remotes/origin/HEAD``: that symbolic ref
is not itself a fetchable branch name, and ``_refresh_base_ref`` treats the
segment after ``origin/`` as one. An earlier version of this fix resolved the
default but skipped the normalization, and broke the fetch (``couldn't find
remote ref refs/heads/HEAD``) on every checkout where ``gh pr view`` found no
PR to read a base branch from.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.ci import merge_tree_ratchet_preparation as _prep
from scripts.validation import checks_common as _common
from scripts.validation import checks_ratchet


def _git(repo: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *argv],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@e.com"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
    (repo / "a.txt").write_text("x\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")


# shutil.which, not `git --version`: subprocess.run raises FileNotFoundError
# when the executable is absent, and check=False does not suppress that. A
# decorator argument is evaluated at import, so the raise would fail collection
# of this whole module instead of skipping this class. Matches the pattern in
# tests/ci/test_merge_tree_materialization.py:138 and
# tests/ci/test_count_ratchet_concurrent_merge.py:90.
@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
class TestResolveDefaultBaseRef:
    def test_passes_through_a_non_symbolic_ref(self, tmp_path: Path) -> None:
        """A resolved ref that is already concrete needs no git call."""
        repo = tmp_path / "repo"
        _init_repo(repo)
        with patch.object(_prep, "_resolve_default_base_ref", return_value="origin/main"):
            assert _prep.resolve_default_base_ref(repo) == "origin/main"

    def test_normalizes_symbolic_origin_head(self, tmp_path: Path) -> None:
        """A clone's refs/remotes/origin/HEAD resolves to a real branch name."""
        origin = tmp_path / "origin"
        _init_repo(origin)
        work = tmp_path / "work"
        subprocess.run(["git", "clone", "-q", str(origin), str(work)], check=True)

        with patch.object(
            _prep, "_resolve_default_base_ref", return_value="refs/remotes/origin/HEAD"
        ):
            assert _prep.resolve_default_base_ref(work) == "origin/main"

    def test_unresolvable_symbolic_head_returns_none(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """No origin remote at all: the symbolic-ref lookup fails closed."""
        repo = tmp_path / "repo"
        _init_repo(repo)
        with patch.object(
            _prep, "_resolve_default_base_ref", return_value="refs/remotes/origin/HEAD"
        ):
            assert _prep.resolve_default_base_ref(repo) is None
        assert "cannot resolve remote HEAD" in capsys.readouterr().err

    def test_none_from_the_underlying_resolver_passes_through(self, tmp_path: Path) -> None:
        """No candidate resolved at all (no PR, no remote, no local main)."""
        repo = tmp_path / "repo"
        _init_repo(repo)
        with patch.object(_prep, "_resolve_default_base_ref", return_value=None):
            assert _prep.resolve_default_base_ref(repo) is None


class TestRemoteBranch:
    """``_remote_branch`` decides whether ``_refresh_base_ref`` fetches at all.

    Issue #5441 review: returning None means "not a remote branch, nothing to
    refresh", so a name that reaches None is never fetched and the ratchet then
    reads a stale local tracking ref.
    """

    @pytest.mark.parametrize(
        ("base_ref", "expected"),
        [
            ("origin/main", "main"),
            ("refs/remotes/origin/main", "main"),
            # The stacked-PR shape checks_common's `gh pr view` branch emits.
            ("origin/feat/parent", "feat/parent"),
            ("refs/remotes/origin/feat/parent", "feat/parent"),
            ("origin/a/b/c/d", "a/b/c/d"),
        ],
    )
    def test_names_a_remote_branch(self, base_ref: str, expected: str) -> None:
        assert _prep._remote_branch(base_ref) == expected

    @pytest.mark.parametrize(
        "base_ref",
        [
            "main",
            "refs/heads/main",
            "upstream/main",
            # Prefix present but nothing follows it: no branch is named.
            "origin/",
            "refs/remotes/origin/",
            "",
        ],
    )
    def test_names_no_remote_branch(self, base_ref: str) -> None:
        assert _prep._remote_branch(base_ref) is None

    def test_a_malformed_name_is_fetched_not_skipped(self) -> None:
        """A name this function cannot vouch for must reach git, not skip.

        git rejects a component starting with a dot. Returning None here would
        report "already up to date" for a ref that was never refreshed, which
        is the silent failure this function exists to avoid.
        """
        assert _prep._remote_branch("origin/.hidden") == ".hidden"


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
class TestRefreshBaseRef:
    """``_refresh_base_ref`` must attempt the fetch for a nested branch name."""

    def test_fetches_a_nested_branch(self, tmp_path: Path) -> None:
        origin = tmp_path / "origin"
        _init_repo(origin)
        _git(origin, "branch", "feat/parent")
        work = tmp_path / "work"
        subprocess.run(["git", "clone", "-q", str(origin), str(work)], check=True)

        assert _prep._refresh_base_ref(work, "origin/feat/parent") is True
        listed = _git(work, "rev-parse", "--verify", "refs/remotes/origin/feat/parent")
        assert listed.returncode == 0, listed.stderr

    def test_reports_a_fetch_that_fails(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A branch the remote does not carry fails loudly, and returns False."""
        origin = tmp_path / "origin"
        _init_repo(origin)
        work = tmp_path / "work"
        subprocess.run(["git", "clone", "-q", str(origin), str(work)], check=True)

        assert _prep._refresh_base_ref(work, "origin/feat/absent") is False
        assert "failed to refresh origin/feat/absent" in capsys.readouterr().err

    def test_skips_a_ref_that_names_no_remote_branch(self, tmp_path: Path) -> None:
        """A local ref has nothing to refresh, so no fetch is attempted."""
        repo = tmp_path / "repo"
        _init_repo(repo)
        with patch.object(_prep, "_git") as fetch:
            assert _prep._refresh_base_ref(repo, "refs/heads/main") is True
        fetch.assert_not_called()


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
class TestIsFastForwardCleanAgainstRealGit:
    """The predicate that decides whether the working tree needs its own pass.

    Issue #5441 review: the working-tree tests mock ``is_fast_forward_clean``
    and their fixture adds only an untracked file, which ``git diff HEAD --``
    ignores. A regression that returned True for a staged or unstaged tracked
    edit would pass those tests and silently drop pre_pr's working-tree
    coverage, which is the exact bug the working-tree pass exists to close.
    These drive real git instead.
    """

    def _repo_ahead_of_base(self, tmp_path: Path) -> tuple[Path, str]:
        repo = tmp_path / "repo"
        _init_repo(repo)
        base = _git(repo, "rev-parse", "HEAD").stdout.strip()
        (repo / "b.txt").write_text("y\n", encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-qm", "second")
        return repo, base

    def test_clean_tree_ahead_of_base_is_fast_forward_clean(
        self, tmp_path: Path
    ) -> None:
        repo, base = self._repo_ahead_of_base(tmp_path)
        assert _prep.is_fast_forward_clean(repo, base) is True

    def test_an_unstaged_tracked_edit_is_not_clean(self, tmp_path: Path) -> None:
        repo, base = self._repo_ahead_of_base(tmp_path)
        (repo / "a.txt").write_text("modified\n", encoding="utf-8")
        assert _prep.is_fast_forward_clean(repo, base) is False

    def test_a_staged_tracked_edit_is_not_clean(self, tmp_path: Path) -> None:
        repo, base = self._repo_ahead_of_base(tmp_path)
        (repo / "a.txt").write_text("staged\n", encoding="utf-8")
        _git(repo, "add", "a.txt")
        assert _prep.is_fast_forward_clean(repo, base) is False

    def test_a_staged_new_file_is_not_clean(self, tmp_path: Path) -> None:
        repo, base = self._repo_ahead_of_base(tmp_path)
        (repo / "added.txt").write_text("new\n", encoding="utf-8")
        _git(repo, "add", "added.txt")
        assert _prep.is_fast_forward_clean(repo, base) is False

    def test_an_untracked_file_alone_stays_clean(self, tmp_path: Path) -> None:
        """Documents the boundary: git diff HEAD does not see untracked files.

        This is why the working-tree tests' untracked-only fixture could not
        have caught a regression in this predicate.
        """
        repo, base = self._repo_ahead_of_base(tmp_path)
        (repo / "untracked.txt").write_text("new\n", encoding="utf-8")
        assert _prep.is_fast_forward_clean(repo, base) is True

    def test_a_base_that_is_not_an_ancestor_is_not_clean(
        self, tmp_path: Path
    ) -> None:
        """The ordinary state of a branch main has moved past."""
        repo, _ = self._repo_ahead_of_base(tmp_path)
        _git(repo, "checkout", "-q", "-b", "side")
        (repo / "c.txt").write_text("z\n", encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-qm", "diverge")
        diverged = _git(repo, "rev-parse", "HEAD").stdout.strip()
        _git(repo, "checkout", "-q", "main")
        assert _prep.is_fast_forward_clean(repo, diverged) is False


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
class TestStackedBaseIsFetchedBeforeResolution:
    """A stacked PR base must not degrade to origin/main just for being unfetched.

    Issue #5441 review: ``checks_common._resolve_default_base_ref`` validates
    each candidate with ``git rev-parse --verify --quiet`` and takes the first
    that resolves. On a checkout that never fetched ``origin/feat/parent`` the
    PR's own base fails that check, so the resolver falls through to
    ``origin/main`` and the whole evaluation measures against the wrong target
    without saying so.
    """

    def _clone_without_the_nested_branch(self, tmp_path: Path) -> Path:
        origin = tmp_path / "origin"
        _init_repo(origin)
        _git(origin, "branch", "feat/parent")
        work = tmp_path / "work"
        subprocess.run(
            ["git", "clone", "-q", "--single-branch", "--branch", "main",
             str(origin), str(work)],
            check=True,
        )
        # Precondition: the nested base is genuinely absent locally.
        assert _git(work, "rev-parse", "--verify", "--quiet",
                    "origin/feat/parent").returncode != 0
        return work

    def test_the_pr_base_is_fetched_and_then_resolves(self, tmp_path: Path) -> None:
        work = self._clone_without_the_nested_branch(tmp_path)

        # Both readers see one answer, as they do in production where
        # checks_common._gh_base_ref caches it.
        with (
            patch.object(_prep, "_gh_base_ref", return_value="origin/feat/parent"),
            patch.object(_common, "_gh_base_ref", return_value="origin/feat/parent"),
        ):
            resolved = _prep.resolve_default_base_ref(work)

        assert resolved == "origin/feat/parent"
        assert _git(work, "rev-parse", "--verify", "--quiet",
                    "origin/feat/parent").returncode == 0

    def test_no_pr_base_fetches_nothing(self, tmp_path: Path) -> None:
        work = self._clone_without_the_nested_branch(tmp_path)

        with (
            patch.object(_prep, "_gh_base_ref", return_value=None),
            patch.object(_prep, "_refresh_base_ref") as fetch,
        ):
            _prep.resolve_default_base_ref(work)

        fetch.assert_not_called()

    def test_an_already_present_base_is_not_refetched(self, tmp_path: Path) -> None:
        origin = tmp_path / "origin"
        _init_repo(origin)
        work = tmp_path / "work"
        subprocess.run(["git", "clone", "-q", str(origin), str(work)], check=True)

        with (
            patch.object(_prep, "_gh_base_ref", return_value="origin/main"),
            patch.object(_prep, "_refresh_base_ref") as fetch,
        ):
            _prep.resolve_default_base_ref(work)

        fetch.assert_not_called()

    def test_a_failed_fetch_falls_back_rather_than_blocking(
        self, tmp_path: Path
    ) -> None:
        """Best effort: offline, the resolver behaves as it did before."""
        work = self._clone_without_the_nested_branch(tmp_path)

        with (
            patch.object(_prep, "_gh_base_ref", return_value="origin/feat/absent"),
            patch.object(_common, "_gh_base_ref", return_value="origin/feat/absent"),
        ):
            resolved = _prep.resolve_default_base_ref(work)

        assert resolved == "origin/main"


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
class TestChecksRatchetResolvesTheSameBase:
    """The twin path must pin the same base this module's resolver returns.

    Issue #5441 review. ``scripts/validation/checks_ratchet.py`` pins its own
    base OID for the individual ratchets and the merge-tree backstop, and it
    resolved that base through ``checks_common._resolve_default_base_ref``
    directly. That resolver discards an unfetched stacked base, so ``pre_pr``
    and a bare ``checks_ratchet.py`` run measured a stacked PR against
    ``origin/main`` while the standalone merge-tree job measured it against
    the real base. A fix on one path and not its twin leaves the defect.

    ``checks_ratchet`` imports its dependencies by bare name off ``sys.path``,
    which is a second module object for the same file, so the patches below
    target the module that its resolver actually closes over rather than the
    package-path copy the tests above use.
    """

    def _stacked_clone(self, tmp_path: Path) -> tuple[Path, str, str]:
        """A clone with ``origin/feat/parent`` absent and ahead of ``main``."""
        origin = tmp_path / "origin"
        _init_repo(origin)
        _git(origin, "checkout", "-q", "-b", "feat/parent")
        (origin / "b.txt").write_text("y\n", encoding="utf-8")
        _git(origin, "add", "-A")
        _git(origin, "commit", "-qm", "the parent branch moves ahead of main")
        parent_oid = _git(origin, "rev-parse", "HEAD").stdout.strip()
        _git(origin, "checkout", "-q", "main")
        main_oid = _git(origin, "rev-parse", "HEAD").stdout.strip()

        work = tmp_path / "work"
        subprocess.run(
            ["git", "clone", "-q", "--single-branch", "--branch", "main",
             str(origin), str(work)],
            check=True,
        )
        assert _git(work, "rev-parse", "--verify", "--quiet",
                    "origin/feat/parent").returncode != 0
        assert parent_oid != main_oid
        return work, parent_oid, main_oid

    def test_an_unfetched_stacked_base_is_pinned_not_replaced_by_main(
        self, tmp_path: Path
    ) -> None:
        work, parent_oid, main_oid = self._stacked_clone(tmp_path)
        bare_prep = sys.modules[checks_ratchet._resolve_default_base_ref.__module__]

        with (
            patch.object(bare_prep, "_gh_base_ref", return_value="origin/feat/parent"),
            patch.object(_common, "_gh_base_ref", return_value="origin/feat/parent"),
        ):
            base_ref, base_oid = checks_ratchet._prepare_base_oid(work)

        assert base_ref == "origin/feat/parent"
        assert base_oid == parent_oid
        # The pre-fix answer, stated so a regression cannot pass quietly.
        assert base_oid != main_oid

    def test_no_pr_base_still_falls_back_to_the_default_branch(
        self, tmp_path: Path
    ) -> None:
        """Edge: the fallback is correct when there is no PR base to fetch."""
        work, _parent_oid, main_oid = self._stacked_clone(tmp_path)
        bare_prep = sys.modules[checks_ratchet._resolve_default_base_ref.__module__]

        with (
            patch.object(bare_prep, "_gh_base_ref", return_value=None),
            patch.object(_common, "_gh_base_ref", return_value=None),
        ):
            base_ref, base_oid = checks_ratchet._prepare_base_oid(work)

        assert base_ref in ("origin/main", "refs/remotes/origin/HEAD")
        assert base_oid == main_oid
