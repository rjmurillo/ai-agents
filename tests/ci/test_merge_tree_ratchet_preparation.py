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
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.ci import merge_tree_ratchet_preparation as _prep


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
