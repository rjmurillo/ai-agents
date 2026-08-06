"""The probes behind the stale-entry warnings, in ``_gc_stale.py``.

Each probe answers one question about an admin directory whose worktree is
gone: where the admin directory is, whether its index holds staged blobs, and
which commits its reflog anchors that no ref reaches. Every one of them must
answer UNKNOWN rather than guess, because a wrong "nothing here" is what makes
the caller delete recoverable work.

What ``decide`` does with those answers is tested in
``test_gc_worktrees_stale.py``.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from scripts.maintenance import _gc_parse, _gc_stale
from scripts.maintenance.gc_worktrees import (
    Decision,
    Worktree,
    decide,
)

_MAIN = "/repo/main"
_BASE = "origin/main"
_SHA = "f30c6952bf2da328bcff0aecc74ff05de3558df7"

_MODULE = "scripts.maintenance.gc_worktrees"


_STUB_HEAD = "f" * 40


@pytest.fixture(autouse=True)
def _stub_pre_removal_head():
    """Unit tests name paths that do not exist, so the pre-removal HEAD read is stubbed.

    ``apply_removals`` reads each candidate's HEAD twice, once with the recheck
    and once immediately before removing it, and refuses when the two differ.
    Against a fabricated path both reads fail and every removal is withheld,
    which would hide what these tests are actually about. Tests that care about
    the comparison patch it again with their own values.
    """
    with patch(f"{_MODULE}._gc_apply._head_of", return_value=_STUB_HEAD):
        yield


def _decide(
    worktree: Worktree,
    *,
    reachable: bool = True,
    staged: str = "clean",
    admin: str | None = "/a",
    present: bool = False,
) -> Decision:
    """Decide with the stale diagnostics stubbed to a clean, locatable entry.

    The diagnostics have their own tests below. Pinning them here keeps these
    cases about the decision rather than about what the index happened to hold.

    ``present`` states whether the worktree directory is on disk. It is a
    parameter rather than a real ``stat`` so a case says what it means instead
    of depending on whether ``/gone/wt`` happens to be absent from the machine
    running the suite. It defaults to ``False`` because every worktree in this
    file is stale.
    """
    with (
        patch(f"{_MODULE}._gc_reasons.stale_head_is_reachable", return_value=reachable),
        patch(
            f"{_MODULE}._gc_reasons._gc_stale.admin_dir_for",
            return_value=None if admin is None else Path(admin),
        ),
        patch(f"{_MODULE}._gc_reasons._gc_stale.staged_content_state", return_value=staged),
    ):
        return decide(worktree, _MAIN, _BASE, cwds=frozenset(), path_exists=lambda _: present)


def _parse(text: str) -> list[Worktree]:
    """Run the real porcelain parser over canned ``git worktree list`` output."""
    return _gc_parse.list_worktrees(lambda _: text)


def _stale(path: str = "/gone/wt", **kwargs) -> Worktree:
    fields = {
        "branch": None,
        "head": _SHA,
        "detached": True,
        "prunable": "gitdir file points to non-existent location",
    }
    fields.update(kwargs)
    return Worktree(path=path, **fields)


class TestStagedContentProbe:
    """``staged_content_state`` is three-valued because git has three answers."""

    @staticmethod
    def _probe(returncode: int, index_exists: bool = True):
        with (
            patch("pathlib.Path.is_file", return_value=index_exists),
            patch(
                "scripts.maintenance._gc_stale.subprocess.run",
                return_value=SimpleNamespace(returncode=returncode),
            ),
        ):
            return _gc_stale.staged_content_state(Path("/a"), _SHA, "/repo", 5.0)

    def test_exit_zero_is_clean(self):
        assert self._probe(0) == _gc_stale.CLEAN

    def test_exit_one_is_staged(self):
        assert self._probe(1) == _gc_stale.STAGED

    def test_a_fatal_exit_is_unknown_not_staged(self):
        """git rejects a bare admin dir with exit 128; that is not a difference."""
        assert self._probe(128) == _gc_stale.UNKNOWN

    def test_a_missing_index_is_clean(self):
        assert self._probe(1, index_exists=False) == _gc_stale.CLEAN

    def test_a_timeout_is_unknown(self):
        with (
            patch("pathlib.Path.is_file", return_value=True),
            patch(
                "scripts.maintenance._gc_stale.subprocess.run",
                side_effect=subprocess.TimeoutExpired("git", 5.0),
            ),
        ):
            assert _gc_stale.staged_content_state(Path("/a"), _SHA, "/repo", 5.0) == (
                _gc_stale.UNKNOWN
            )

    def test_the_probe_runs_in_the_repo_not_the_admin_directory(self):
        """git refuses the admin dir outright when safe.bareRepository is explicit."""
        with (
            patch("pathlib.Path.is_file", return_value=True),
            patch(
                "scripts.maintenance._gc_stale.subprocess.run",
                return_value=SimpleNamespace(returncode=0),
            ) as run,
        ):
            _gc_stale.staged_content_state(Path("/a/admin"), _SHA, "/repo", 5.0)
        assert run.call_args.kwargs["cwd"] == "/repo"
        assert run.call_args.kwargs["env"] == {**os.environ, "GIT_INDEX_FILE": "/a/admin/index"}


class TestAdminDirLookup:
    """A failed lookup silently drops the warning, so the lookup must be robust."""

    @staticmethod
    def _layout(tmp_path, gitdir_text: str):
        common = tmp_path / "repo" / ".git"
        admin = common / "worktrees" / "wt"
        admin.mkdir(parents=True)
        (admin / "gitdir").write_text(gitdir_text, encoding="utf-8")
        return admin

    def test_a_relative_common_dir_is_anchored_to_the_repo_not_the_process(self, tmp_path):
        """rev-parse answers a bare '.git' even under git -C, so it needs an anchor."""
        repo = tmp_path / "repo"
        wt = tmp_path / "wt"
        admin = self._layout(tmp_path, f"{wt}/.git\n")

        found = _gc_stale.admin_dir_for(str(wt), lambda _args: ".git", str(repo))

        assert found == admin

    def test_an_absolute_common_dir_is_left_alone(self, tmp_path):
        repo = tmp_path / "repo"
        wt = tmp_path / "wt"
        admin = self._layout(tmp_path, f"{wt}/.git\n")

        found = _gc_stale.admin_dir_for(str(wt), lambda _args: str(repo / ".git"), str(repo))

        assert found == admin

    def test_a_symlinked_worktree_path_still_matches(self, tmp_path):
        """The recorded path and the porcelain path can normalize differently."""
        repo = tmp_path / "repo"
        real = tmp_path / "real"
        real.mkdir()
        link = tmp_path / "link"
        link.symlink_to(real, target_is_directory=True)
        admin = self._layout(tmp_path, f"{real}/wt/.git\n")

        found = _gc_stale.admin_dir_for(f"{link}/wt", lambda _args: str(repo / ".git"), str(repo))

        assert found == admin

    def test_a_prefix_sharing_sibling_is_not_confused_for_the_target(self, tmp_path):
        """'wt' and 'wt-extra' must not collide; the '/.git' suffix separates them."""
        repo = tmp_path / "repo"
        admin = self._layout(tmp_path, f"{tmp_path}/wt-extra/.git\n")

        found = _gc_stale.admin_dir_for(
            f"{tmp_path}/wt", lambda _args: str(repo / ".git"), str(repo)
        )

        assert found is None
        assert admin.is_dir()

    def test_a_failed_rev_parse_reports_unknown_rather_than_guessing(self, tmp_path):
        def boom(_args):
            raise RuntimeError("not a git repository")

        assert _gc_stale.admin_dir_for("/gone", boom, str(tmp_path)) is None

    def test_a_missing_worktrees_container_reports_unknown(self, tmp_path):
        assert _gc_stale.admin_dir_for("/gone", lambda _args: str(tmp_path), str(tmp_path)) is None


class TestReflogProbe:
    """``unreachable_reflog_commits`` answers with a list, or admits it cannot."""

    @staticmethod
    def _probe(tmp_path, lines: str, existing: str, unreachable: str):
        admin = tmp_path / "wt"
        (admin / "logs").mkdir(parents=True)
        (admin / "logs" / "HEAD").write_text(lines, encoding="utf-8")
        outputs = [
            SimpleNamespace(returncode=0, stdout=existing),
            SimpleNamespace(returncode=0, stdout=unreachable),
        ]
        with patch("scripts.maintenance._gc_stale.subprocess.run", side_effect=outputs):
            return _gc_stale.unreachable_reflog_commits(admin, "/repo", 5.0)

    def test_a_missing_reflog_is_no_risk(self, tmp_path):
        (tmp_path / "wt").mkdir()
        assert _gc_stale.unreachable_reflog_commits(tmp_path / "wt", "/repo", 5.0) == []

    def test_the_null_oid_is_never_treated_as_a_commit(self, tmp_path):
        null, new = "0" * 40, "c" * 40
        found = self._probe(
            tmp_path,
            f"{null} {new} me <me@x> 0 +0000\tbranch: Created\n",
            f"{new} commit 100\n",
            f"{new}\n",
        )
        assert found == [new]

    def test_a_collected_object_is_dropped_rather_than_failing_the_whole_answer(self, tmp_path):
        """rev-list aborts on the first bad object, so filtering has to come first."""
        gone, live = "d" * 40, "e" * 40
        found = self._probe(
            tmp_path,
            f"{gone} {live} me <me@x> 0 +0000\tcommit: x\n",
            f"{gone} missing\n{live} commit 100\n",
            f"{live}\n",
        )
        assert found == [live]

    def test_nothing_unreachable_is_an_empty_list_not_none(self, tmp_path):
        live = "f" * 40
        found = self._probe(
            tmp_path, f"{live} {live} me <me@x> 0 +0000\tx\n", f"{live} commit 1\n", ""
        )
        assert found == []

    def test_a_git_failure_is_unknown_not_safe(self, tmp_path):
        admin = tmp_path / "wt"
        (admin / "logs").mkdir(parents=True)
        (admin / "logs" / "HEAD").write_text(f"{'a' * 40} {'b' * 40} x\n", encoding="utf-8")
        with patch(
            "scripts.maintenance._gc_stale.subprocess.run",
            return_value=SimpleNamespace(returncode=128, stdout=""),
        ):
            assert _gc_stale.unreachable_reflog_commits(admin, "/repo", 5.0) is None

    def test_a_timeout_is_unknown_not_safe(self, tmp_path):
        admin = tmp_path / "wt"
        (admin / "logs").mkdir(parents=True)
        (admin / "logs" / "HEAD").write_text(f"{'a' * 40} {'b' * 40} x\n", encoding="utf-8")
        with patch(
            "scripts.maintenance._gc_stale.subprocess.run",
            side_effect=subprocess.TimeoutExpired("git", 5.0),
        ):
            assert _gc_stale.unreachable_reflog_commits(admin, "/repo", 5.0) is None

    def test_a_reflog_of_only_null_oids_costs_no_subprocess(self, tmp_path):
        admin = tmp_path / "wt"
        (admin / "logs").mkdir(parents=True)
        (admin / "logs" / "HEAD").write_text(f"{'0' * 40} {'0' * 40} x\n", encoding="utf-8")
        with patch("scripts.maintenance._gc_stale.subprocess.run") as run:
            assert _gc_stale.unreachable_reflog_commits(admin, "/repo", 5.0) == []
        run.assert_not_called()
