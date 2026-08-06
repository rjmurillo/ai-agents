"""The anchor readers in ``_gc_anchors.py``.

``git worktree remove`` deletes the admin directory, and two kinds of anchor
die with it: the worktree's reflogs under ``logs/`` and its own refs under
``refs/``. Neither is visible to a ref query in the main repository, so a
commit only one of them names reads as unreachable.

Every reader is three-valued. These tests hold the line on the third value:
an anchor the probe could not open or could not parse has to answer "unknown",
never "nothing at risk". Where a read has to fail, it fails for real, by
``chmod`` or by a corrupt path, never by a patched helper.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from scripts.maintenance import _gc_anchors, _gc_stale


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


class TestWalkFiles:
    """``walk_files`` answers "unknown" for anything it could not fully read."""

    def test_an_absent_directory_holds_nothing(self, tmp_path):
        assert _gc_anchors.walk_files(tmp_path / "logs") == []

    def test_it_finds_files_at_every_depth_in_a_stable_order(self, tmp_path):
        root = tmp_path / "logs"
        (root / "refs" / "worktree").mkdir(parents=True)
        (root / "HEAD").write_text("a\n")
        (root / "refs" / "worktree" / "mywork").write_text("b\n")
        assert _gc_anchors.walk_files(root) == [
            root / "HEAD",
            root / "refs" / "worktree" / "mywork",
        ]

    def test_a_corrupt_admin_record_is_unknown_not_empty(self, tmp_path):
        """``<admin>`` is a regular file, so ``<admin>/logs`` raises ENOTDIR.

        ``Path.is_dir`` answers ``False`` here exactly as it does for a
        directory that is genuinely absent. Reading the first as "no reflogs,
        nothing at risk" is the silent all-clear this module exists to prevent.
        """
        admin = tmp_path / "admin"
        admin.write_text("not a directory\n")
        assert _gc_anchors.walk_files(admin / "logs") is None

    def test_something_that_is_not_a_directory_is_unknown(self, tmp_path):
        root = tmp_path / "logs"
        root.write_text("a file where a directory belongs\n")
        assert _gc_anchors.walk_files(root) is None

    def test_a_directory_symlink_is_unknown_because_rglob_will_not_enter_it(self, tmp_path):
        """git resolves refs through a symlinked directory; ``rglob`` does not.

        Walking past it would answer "nothing at risk" about anchors that were
        never opened, so the honest answer is that the walk failed.
        """
        real = tmp_path / "elsewhere"
        real.mkdir()
        (real / "mywork").write_text(f"{'f' * 40}\n")
        root = tmp_path / "refs"
        root.mkdir()
        (root / "worktree").symlink_to(real, target_is_directory=True)
        assert _gc_anchors.walk_files(root) is None

    @pytest.mark.skipif(os.geteuid() == 0, reason="root reads through mode 000")
    def test_an_unreadable_directory_is_unknown(self, tmp_path):
        root = tmp_path / "logs"
        root.mkdir()
        (root / "HEAD").write_text("a\n")
        root.chmod(0o000)
        try:
            assert _gc_anchors.walk_files(root) is None
        finally:
            root.chmod(0o755)

    def test_a_dangling_symlink_where_the_root_belongs_is_unknown(self, tmp_path):
        """``lstat`` sees it, so it is present; ``stat`` cannot say what it is."""
        root = tmp_path / "logs"
        root.symlink_to(tmp_path / "gone", target_is_directory=True)
        assert _gc_anchors.walk_files(root) is None


class TestReflogsBeyondHead:
    """``reflog_oids`` reads every reflog the removal deletes, not just HEAD."""

    def test_a_per_worktree_ref_reflog_contributes_its_ids(self, tmp_path):
        """``update-ref --create-reflog refs/worktree/x`` writes this file.

        The ref can move off a commit while its reflog goes on naming it, and
        the whole admin directory dies with ``git worktree remove``.
        """
        log = tmp_path / "logs" / "refs" / "worktree" / "mywork"
        log.parent.mkdir(parents=True)
        log.write_text(f"{'0' * 40} {'a' * 40} t <t> 0 +0000\tcreate\n")
        assert _gc_anchors.reflog_oids(tmp_path) == ["a" * 40]

    def test_head_and_a_ref_reflog_both_contribute(self, tmp_path):
        head = tmp_path / "logs" / "HEAD"
        head.parent.mkdir(parents=True)
        head.write_text(f"{'0' * 40} {'b' * 40} t <t> 0 +0000\tcommit\n")
        ref = tmp_path / "logs" / "refs" / "worktree" / "mywork"
        ref.parent.mkdir(parents=True)
        ref.write_text(f"{'b' * 40} {'c' * 40} t <t> 0 +0000\tmove\n")
        assert sorted(_gc_anchors.reflog_oids(tmp_path)) == ["b" * 40, "c" * 40]

    def test_one_unparsable_reflog_makes_the_whole_answer_unknown(self, tmp_path):
        head = tmp_path / "logs" / "HEAD"
        head.parent.mkdir(parents=True)
        head.write_text(f"{'0' * 40} {'b' * 40} t <t> 0 +0000\tcommit\n")
        ref = tmp_path / "logs" / "refs" / "worktree" / "mywork"
        ref.parent.mkdir(parents=True)
        ref.write_text("this is not a reflog\n")
        assert _gc_anchors.reflog_oids(tmp_path) is None


class TestReflogParsingIsPerLine:
    """One line a reader understands does not vouch for the rest of the file."""

    @staticmethod
    def _log(tmp_path: Path, body: str) -> Path:
        log = tmp_path / "logs" / "HEAD"
        log.parent.mkdir(parents=True)
        log.write_text(body, encoding="utf-8")
        return tmp_path

    def test_a_line_that_does_not_open_with_two_ids_is_not_understood(self, tmp_path):
        """A partial list reads downstream as "these are the only ids at risk".

        Judging the file as a whole let one good line clear a file whose
        remaining lines were never parsed, which is the silent all-clear this
        module exists to prevent.
        """
        admin = self._log(
            tmp_path,
            f"{'a' * 40} {'b' * 40} t <t> 0 +0000\tcommit\nthis is not a reflog\n",
        )
        assert _gc_anchors.reflog_oids(admin) is None

    def test_a_truncated_final_line_is_not_understood(self, tmp_path):
        """A reflog caught mid-write ends in a partial line."""
        admin = self._log(tmp_path, f"{'a' * 40} {'b' * 40} t <t> 0 +0000\tcommit\n{'c' * 40} ")
        assert _gc_anchors.reflog_oids(admin) is None

    def test_a_line_with_only_one_id_is_not_understood(self, tmp_path):
        admin = self._log(tmp_path, f"{'a' * 40} not-an-id t <t> 0 +0000\tcommit\n")
        assert _gc_anchors.reflog_oids(admin) is None

    def test_blank_lines_are_understood(self, tmp_path):
        admin = self._log(tmp_path, f"\n{'a' * 40} {'b' * 40} t <t> 0 +0000\tcommit\n\n")
        assert sorted(_gc_anchors.reflog_oids(admin)) == ["a" * 40, "b" * 40]

    def test_an_entirely_blank_reflog_is_understood_and_empty(self, tmp_path):
        assert _gc_anchors.reflog_oids(self._log(tmp_path, "\n\n")) == []

    def test_a_real_git_reflog_parses(self, tmp_path):
        """Guard against over-tightening: git's own output has to still read.

        Several entries, an amend, a checkout, and a branch move, so the file
        carries every message shape git writes on an ordinary session.
        """
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(tmp_path),
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t",
        }

        def run(*args: str) -> None:
            subprocess.run(
                ["git", "-C", str(tmp_path / "repo"), *args],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=env,
            )

        (tmp_path / "repo").mkdir()
        subprocess.run(
            ["git", "init", "-q", "-b", "main", str(tmp_path / "repo")],
            check=True,
            capture_output=True,
            env=env,
        )
        run("commit", "-q", "--allow-empty", "-m", "one")
        run("commit", "-q", "--allow-empty", "-m", "two")
        run("commit", "-q", "--allow-empty", "--amend", "-m", "two amended")
        run("checkout", "-q", "-b", "side")
        run("commit", "-q", "--allow-empty", "-m", "three")

        oids = _gc_anchors.reflog_oids(tmp_path / "repo" / ".git")
        assert oids is not None, "git's own reflog did not parse"
        assert len(oids) >= 3, oids


class TestAReflogThatVanishesMidWalk:
    """The walk already saw the file, so absence now means it went away."""

    def test_a_path_the_walk_found_and_then_lost_is_unknown(self, tmp_path):
        """``_reflog_text`` is handed a path ``walk_files`` returned.

        Reading a file that has since been deleted as an empty reflog would
        clear the worktree using a snapshot the probe already knows is stale.
        """
        assert _gc_anchors._reflog_text(tmp_path / "gone") is None
