"""D10 (#6506) fail-closed probes, units, and two launcher contracts.

Any git failure while deciding whether a plugin root is this repository halts
with exit 3. Also pins two launcher contracts the last review found untested:
approval never unblocks a diverged launcher target, and a wrong but valid
``--harness`` drops a missing or directory target's payload (ADR-059 R1
residual, CR6).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.skills.github.dynamic_load_helpers import gate
from tests.skills.github.same_repository_helpers import (
    SCRIPT_REL,
    clear_plugin_roots,
    commit_as_trusted,
    completed,
    git,
    launcher,
    linked_worktree,
    make_repo,
    trusted_repo,
    verify,
    write,
    write_config,
)


@pytest.fixture(autouse=True)
def _no_plugin_root(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_plugin_roots(monkeypatch)


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return make_repo(tmp_path, monkeypatch)


class TestProbeFailureBlocks:
    """Any git failure while deciding sameness halts with exit 3 (fail closed)."""

    @staticmethod
    def _fail_when(monkeypatch, predicate, result) -> None:
        real = gate._run_git

        def run_git(args, cwd):
            if predicate(args, Path(cwd)):
                return result(args)
            return real(args, cwd)

        monkeypatch.setattr(gate, "_run_git", run_git)

    @pytest.mark.parametrize(
        ("which", "result"),
        [
            pytest.param("ours", lambda a: completed(a, 128), id="our-rev-parse"),
            pytest.param("theirs", lambda a: completed(a, 128), id="their-rev-parse"),
            pytest.param("theirs", lambda a: completed(a, 0, b"/only-one-line\n"), id="short"),
        ],
    )
    def test_rev_parse_failure_blocks(
        self, repo, tmp_path, monkeypatch, capsys, which, result
    ) -> None:
        trusted_repo(repo, launcher())
        sibling = linked_worktree(repo, tmp_path, monkeypatch)
        target = repo if which == "ours" else sibling

        def predicate(args, cwd):
            return "--git-common-dir" in args and cwd.resolve().is_relative_to(target.resolve())

        self._fail_when(monkeypatch, predicate, result)

        rc, _, err = verify(repo, capsys, "--harness", "copilot")

        assert rc == 3

    def test_origin_lookup_failure_blocks(self, repo, tmp_path, monkeypatch, capsys) -> None:
        trusted_repo(repo, launcher())
        linked_worktree(repo, tmp_path, monkeypatch)
        self._fail_when(
            monkeypatch,
            lambda args, cwd: args[:2] == ["config", "--get"],
            lambda a: completed(a, 2),
        )

        rc, _, err = verify(repo, capsys, "--harness", "copilot")

        assert rc == 3
        assert "remote.origin.url" in err

    def test_sibling_tracked_probe_failure_blocks(
        self, repo, tmp_path, monkeypatch, capsys
    ) -> None:
        trusted_repo(repo, launcher())
        sibling = linked_worktree(repo, tmp_path, monkeypatch)
        self._fail_when(
            monkeypatch,
            lambda args, cwd: args[0] == "ls-files" and cwd.resolve() == sibling.resolve(),
            lambda a: completed(a, 128),
        )

        rc, _, err = verify(repo, capsys, "--harness", "copilot")

        assert rc == 3

    def test_sibling_shadow_probe_failure_blocks(self, repo, tmp_path, monkeypatch, capsys) -> None:
        trusted_repo(repo, launcher())
        sibling = linked_worktree(repo, tmp_path, monkeypatch)
        monkeypatch.setattr(gate, "_shadowing_import_files", lambda rels, root: ["x.pyc"])
        real = gate._tracked_subset

        def tracked_subset(rels, root):
            if rels == ["x.pyc"] and root.resolve() == sibling.resolve():
                return set(), "git ls-files failed: shadow probe"
            return real(rels, root)

        monkeypatch.setattr(gate, "_tracked_subset", tracked_subset)

        rc, _, err = verify(repo, capsys, "--harness", "copilot")

        assert rc == 3
        assert "shadow probe" in err

    def test_sibling_compare_failure_blocks(self, repo, tmp_path, monkeypatch, capsys) -> None:
        trusted_repo(repo, launcher())
        linked_worktree(repo, tmp_path, monkeypatch)
        real = gate._verify_worktree_file_trust

        def fake_trust(rel_path, toplevel, ref, *, source_root=None):
            if source_root is not None:
                return False, "cannot read sibling file"
            return real(rel_path, toplevel, ref)

        monkeypatch.setattr(gate, "_verify_worktree_file_trust", fake_trust)

        rc, _, err = verify(repo, capsys, "--harness", "copilot")

        assert rc == 3
        assert "cannot read sibling file" in err

    def test_unprobeable_git_marker_blocks(self, repo, tmp_path, monkeypatch, capsys) -> None:
        trusted_repo(repo, launcher())
        sibling = linked_worktree(repo, tmp_path, monkeypatch)
        real_lstat = os.lstat

        def lstat(path, *args, **kwargs):
            if Path(path) == sibling / ".git":
                raise PermissionError(13, "Permission denied", str(path))
            return real_lstat(path, *args, **kwargs)

        monkeypatch.setattr(gate.os, "lstat", lstat)

        rc, _, err = verify(repo, capsys, "--harness", "copilot")

        assert rc == 3
        assert "cannot probe" in err


class TestSameRepositoryUnits:
    def test_unreadable_source_root_file_is_an_error(self, repo, tmp_path) -> None:
        """A file missing from the other work tree is a verification error, named by path."""
        trusted_repo(repo, launcher())
        empty = tmp_path / "empty"
        empty.mkdir()

        is_trusted, error = gate._verify_worktree_file_trust(
            SCRIPT_REL,
            repo,
            "origin/main",
            source_root=empty,
        )

        assert is_trusted is False
        assert f"cannot read work-tree file {empty / SCRIPT_REL}" in error

    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            ("https://github.com/Owner/Repo.git", "github.com/owner/repo"),
            ("git@github.com:owner/repo.git\n", "github.com/owner/repo"),
            ("ssh://git@github.com/owner/repo/", "github.com/owner/repo"),
            ("https://user@github.com/owner/repo", "github.com/owner/repo"),
            ("/srv/git/repo.git", "/srv/git/repo"),
        ],
    )
    def test_normalized_remote(self, url: str, expected: str) -> None:
        assert gate._normalized_remote(url) == expected

    def test_inside_git_work_tree_false_without_marker(self, tmp_path: Path) -> None:
        assert gate._inside_git_work_tree(tmp_path / "a" / "b.py") == (False, "")

    def test_same_repository_root_is_none_for_another_repository(self, tmp_path: Path) -> None:
        other = tmp_path / "other"
        other.mkdir()
        git(other, "init", "-q")
        ours = gate._RepositoryIdentity(tmp_path, tmp_path / "not-the-common-dir", "x/y")

        assert gate._same_repository_root(other / "f.py", ours) == (None, "")

    def test_verified_flags_a_diverged_same_repository_file(self, tmp_path: Path) -> None:
        """The external branch of the launcher check honors ``untrusted_files``."""
        external = tmp_path / "sibling" / "run.py"
        external.parent.mkdir()
        external.write_text("x\n", encoding="utf-8")
        toplevel = tmp_path / "work"
        toplevel.mkdir()
        value = str(external.resolve())
        flagged = gate.CommandTrustCheck("untrusted", [value], [value], [], [], "")
        clean = gate.CommandTrustCheck("trusted", [value], [], [], [], "")

        assert gate._launcher_target_verified(value, flagged, toplevel) is False
        assert gate._launcher_target_verified(value, clean, toplevel) is True


class TestApprovalNeverUnblocksALauncher:
    """QA gap: the ``not in untrusted_files`` conjunct under approval."""

    def test_diverged_in_tree_launcher_target_stays_blocking(self, repo, capsys) -> None:
        trusted_repo(repo, launcher())
        write(repo, SCRIPT_REL, "print('rewritten by the PR')\n")

        rc, payload, err = verify(
            repo, capsys, "--harness", "copilot", "--approve-untrusted-config"
        )

        assert rc == 0
        assert payload["command_trust"] == "untrusted"
        assert SCRIPT_REL in payload["checked_files"]
        assert len(payload["blocking_unverifiable_command_tokens"]) == 1

    def test_diverged_sibling_launcher_target_stays_blocking(
        self, repo, tmp_path, monkeypatch, capsys
    ) -> None:
        trusted_repo(repo, launcher())
        sibling = linked_worktree(repo, tmp_path, monkeypatch)
        write(sibling, SCRIPT_REL, "print('PR branch code')\n")

        rc, payload, err = verify(
            repo, capsys, "--harness", "copilot", "--approve-untrusted-config"
        )

        assert rc == 0
        assert str((sibling / SCRIPT_REL).resolve()) in payload["checked_files"]
        assert len(payload["blocking_unverifiable_command_tokens"]) == 1


class TestWrongHarnessDropsTheMissingTarget:
    """CR6: a wrong but valid ``--harness`` fails open, as ADR-059 R1 records."""

    @pytest.mark.parametrize("shape", ["missing", "directory"])
    def test_blocks_under_copilot_and_drops_under_claude_code(self, repo, capsys, shape) -> None:
        config = write_config(repo, launcher())
        commit_as_trusted(repo, config)
        if shape == "directory":
            (repo / SCRIPT_REL).mkdir(parents=True)

        rc_copilot, copilot, _ = verify(repo, capsys, "--harness", "copilot")
        rc_claude, claude, _ = verify(repo, capsys, "--harness", "claude_code")

        assert (rc_copilot, rc_claude) == (0, 0)
        assert len(copilot["blocking_unverifiable_command_tokens"]) == 1
        assert claude["blocking_unverifiable_command_tokens"] == []
        assert claude["unverifiable_command_tokens"] == copilot["unverifiable_command_tokens"]
