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

from scripts.maintenance import _gc_anchors, _gc_files, _gc_parse, _gc_stale
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
        return decide(worktree, _MAIN, _BASE, cwds=frozenset(), checkout_present=lambda _: present)


def _parse(text: str) -> list[Worktree]:
    """Run the real porcelain parser over canned ``git worktree list`` output."""
    return _gc_parse.list_worktrees(lambda _: text)


def _stale(
    path: str = "/gone/wt",
    *,
    branch: str | None = None,
    head: str | None = _SHA,
    locked: bool = False,
    bare: bool = False,
    detached: bool = True,
    prunable: str | None = "gitdir file points to non-existent location",
) -> Worktree:
    """Build a stale-entry ``Worktree``, one field at a time.

    Spelled out rather than splatted from a dict so that a typo in a field
    name fails here instead of silently constructing a different worktree.
    """
    return Worktree(
        path=path,
        branch=branch,
        head=head,
        locked=locked,
        bare=bare,
        detached=detached,
        prunable=prunable,
    )


class TestRegularFileProbe:
    """``regular_file`` separates "not there" from "could not ask"."""

    def test_a_real_file_is_true(self, tmp_path):
        target = tmp_path / "index"
        target.write_bytes(b"x")
        assert _gc_files.regular_file(target) is True

    def test_an_absent_file_is_false(self, tmp_path):
        assert _gc_files.regular_file(tmp_path / "missing") is False

    def test_a_path_under_a_file_is_unknown(self, tmp_path):
        """``a/b`` where ``a`` is a file is a corrupt record, not an empty one.

        ``stat`` raises ``NotADirectoryError`` here, not ``ENOENT``. Reading
        that as absence says "no index, nothing staged" about an admin
        directory that has been overwritten by a regular file, which is the
        state most likely to be hiding something.
        """
        (tmp_path / "a").write_bytes(b"x")
        assert _gc_files.regular_file(tmp_path / "a" / "b") is None

    def test_a_directory_is_unknown_not_absent(self, tmp_path):
        """A directory where an index belongs is corrupt, not empty."""
        (tmp_path / "index").mkdir()
        assert _gc_files.regular_file(tmp_path / "index") is None

    def test_a_stat_failure_is_unknown(self, tmp_path):
        """A permission denial is the case ``Path.is_file`` hides."""
        with patch.object(Path, "stat", side_effect=PermissionError(13, "denied")):
            assert _gc_files.regular_file(tmp_path / "index") is None

    def test_a_broken_symlink_is_unknown(self, tmp_path):
        """Something occupies the path, so this is not absence.

        ``stat`` follows the link and raises ``ENOENT``, the same error a
        genuinely empty path raises. ``lstat`` separates them: the link itself
        is a directory entry. A reflog behind a dangling link is a record this
        probe cannot read, not a record that is not there.
        """
        link = tmp_path / "index"
        link.symlink_to(tmp_path / "nowhere")
        assert _gc_files.regular_file(link) is None

    def test_only_an_empty_path_is_absent(self, tmp_path):
        """The one case that earns ``False``, stated next to its near-misses."""
        assert _gc_files.regular_file(tmp_path / "missing") is False
        assert _gc_files.nothing_at(tmp_path / "missing") is True


class TestReflogProbeUnknowns:
    """An unreadable reflog is not an empty one."""

    def test_an_unreadable_reflog_is_unknown_not_empty(self, tmp_path):
        with patch(
            "scripts.maintenance._gc_anchors.regular_file",
            return_value=None,
        ):
            assert _gc_stale.unreachable_admin_commits(tmp_path, "/repo", 5.0) is None

    def test_an_absent_reflog_holds_nothing(self, tmp_path):
        assert _gc_stale.unreachable_admin_commits(tmp_path, "/repo", 5.0) == []


class TestStagedContentProbe:
    """``staged_content_state`` is three-valued because git has three answers."""

    @staticmethod
    def _probe(returncode: int, index_exists: bool | None = True):
        """``index_exists=None`` means the ``stat`` itself failed."""
        with (
            patch(
                "scripts.maintenance._gc_stale.regular_file",
                return_value=index_exists,
            ),
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

    def test_an_unreadable_index_is_unknown_not_clean(self):
        """A stat that fails is not evidence the index is absent.

        ``Path.is_file`` answers ``False`` for a permission denial exactly as
        it does for a file that is not there. Reading the first as "no index,
        nothing staged" hands back a clean bill for a question git was never
        asked.
        """
        assert self._probe(1, index_exists=None) == _gc_stale.UNKNOWN

    def test_a_timeout_is_unknown(self):
        with (
            patch("scripts.maintenance._gc_stale.regular_file", return_value=True),
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
            patch("scripts.maintenance._gc_stale.regular_file", return_value=True),
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
    """``unreachable_admin_commits`` answers with a list, or admits it cannot."""

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
            return _gc_stale.unreachable_admin_commits(admin, "/repo", 5.0)

    def test_a_missing_reflog_is_no_risk(self, tmp_path):
        (tmp_path / "wt").mkdir()
        assert _gc_stale.unreachable_admin_commits(tmp_path / "wt", "/repo", 5.0) == []

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
            assert _gc_stale.unreachable_admin_commits(admin, "/repo", 5.0) is None

    def test_a_timeout_is_unknown_not_safe(self, tmp_path):
        admin = tmp_path / "wt"
        (admin / "logs").mkdir(parents=True)
        (admin / "logs" / "HEAD").write_text(f"{'a' * 40} {'b' * 40} x\n", encoding="utf-8")
        with patch(
            "scripts.maintenance._gc_stale.subprocess.run",
            side_effect=subprocess.TimeoutExpired("git", 5.0),
        ):
            assert _gc_stale.unreachable_admin_commits(admin, "/repo", 5.0) is None

    def test_a_reflog_of_only_null_oids_costs_no_subprocess(self, tmp_path):
        admin = tmp_path / "wt"
        (admin / "logs").mkdir(parents=True)
        (admin / "logs" / "HEAD").write_text(f"{'0' * 40} {'0' * 40} x\n", encoding="utf-8")
        with patch("scripts.maintenance._gc_stale.subprocess.run") as run:
            assert _gc_stale.unreachable_admin_commits(admin, "/repo", 5.0) == []
        run.assert_not_called()


class TestWorktreeLocalRefProbe:
    """``refs/`` under the admin directory is an anchor no main-repo query sees."""

    @staticmethod
    def _admin(tmp_path, name: str | None = None, content: str = "") -> Path:
        admin = tmp_path / "wt"
        (admin / "logs").mkdir(parents=True, exist_ok=True)
        (admin / "logs" / "HEAD").write_text("", encoding="utf-8")
        if name is not None:
            ref = admin / "refs" / name
            ref.parent.mkdir(parents=True, exist_ok=True)
            ref.write_text(content, encoding="utf-8")
        return admin

    def test_no_refs_directory_is_no_risk(self, tmp_path):
        assert _gc_anchors.worktree_ref_oids(self._admin(tmp_path)) == []

    def test_a_ref_file_contributes_its_object_id(self, tmp_path):
        oid = "d" * 40
        admin = self._admin(tmp_path, "worktree/mywork", f"{oid}\n")
        assert _gc_anchors.worktree_ref_oids(admin) == [oid]

    def test_a_symbolic_ref_anchors_nothing_on_its_own(self, tmp_path):
        admin = self._admin(tmp_path, "worktree/alias", "ref: refs/heads/main\n")
        assert _gc_anchors.worktree_ref_oids(admin) == []

    def test_the_null_oid_is_not_a_commit(self, tmp_path):
        admin = self._admin(tmp_path, "bisect/bad", f"{'0' * 40}\n")
        assert _gc_anchors.worktree_ref_oids(admin) == []

    def test_a_ref_file_that_does_not_parse_answers_unknown(self, tmp_path):
        admin = self._admin(tmp_path, "worktree/broken", "not an object id\n")
        assert _gc_anchors.worktree_ref_oids(admin) is None

    @pytest.mark.skipif(os.geteuid() == 0, reason="root ignores the mode bits")
    def test_an_unreadable_ref_answers_unknown_rather_than_no_risk(self, tmp_path):
        """A real chmod, not a patched read: the failure has to come from the OS."""
        admin = self._admin(tmp_path, "worktree/mywork", f"{'e' * 40}\n")
        ref = admin / "refs" / "worktree" / "mywork"
        ref.chmod(0o000)
        try:
            assert _gc_anchors.worktree_ref_oids(admin) is None
        finally:
            ref.chmod(0o644)

    def test_an_unknown_ref_makes_the_whole_answer_unknown(self, tmp_path):
        admin = self._admin(tmp_path, "worktree/broken", "not an object id\n")
        assert _gc_stale.unreachable_admin_commits(admin, "/repo", 5.0) is None
