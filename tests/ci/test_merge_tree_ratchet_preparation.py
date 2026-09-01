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


@pytest.mark.skipif(
    subprocess.run(["git", "--version"], capture_output=True, check=False).returncode != 0,
    reason="git is not installed",
)
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
