"""D10 (#6506): a plugin root in another work tree of this repository is verified.

Install trust (#5112, D6) assumes the plugin root is a real install that no
pull request can write. A sibling linked worktree or a second clone of this
repository breaks that assumption: a PR branch can be checked out there. So a
script that resolves into such a tree is verified like an in-tree script
(tracked, and byte-equal to the trusted ref this gate run names) or it blocks.
A root that is not a git work tree, or belongs to another repository, keeps
install trust. Fail-closed probes and unit tests live in the ``_contracts``
module beside this one.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.skills.github.dynamic_load_helpers import gate
from tests.skills.github.same_repository_helpers import (
    LAUNCHED_REL,
    OURS_ORIGIN,
    SCRIPT_REL,
    clear_plugin_roots,
    commit_as_trusted,
    git,
    launcher,
    linked_worktree,
    make_repo,
    plain,
    sibling_clone,
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


class TestLinkedWorktreeRoot:
    def test_modified_script_blocks(self, repo, tmp_path, monkeypatch, capsys) -> None:
        trusted_repo(repo, launcher())
        sibling = linked_worktree(repo, tmp_path, monkeypatch)
        write(sibling, SCRIPT_REL, "print('PR branch code')\n")

        rc, payload, err = verify(repo, capsys, "--harness", "copilot")

        assert rc == 2
        assert payload == {}
        assert str((sibling / SCRIPT_REL).resolve()) in err

    def test_identical_tracked_script_passes(self, repo, tmp_path, monkeypatch, capsys) -> None:
        trusted_repo(repo, launcher())
        sibling = linked_worktree(repo, tmp_path, monkeypatch)

        rc, payload, err = verify(repo, capsys, "--harness", "copilot")

        assert rc == 0
        assert payload["command_trust"] == "trusted"
        assert payload["blocking_unverifiable_command_tokens"] == []
        assert payload["skipped_external_files"] == []
        assert str((sibling / SCRIPT_REL).resolve()) in payload["checked_files"]

    def test_two_scripts_in_one_sibling_are_both_compared(
        self, repo, tmp_path, monkeypatch, capsys
    ) -> None:
        other = "skills/demo/scripts/other.py"
        write(repo, f".claude/{other}")
        write(repo, SCRIPT_REL)
        config = write_config(repo, launcher(), claude=plain(other))
        commit_as_trusted(repo, config, SCRIPT_REL, f".claude/{other}")
        sibling = linked_worktree(repo, tmp_path, monkeypatch)
        write(sibling, f".claude/{other}", "print('PR branch code')\n")

        rc, _, err = verify(repo, capsys, "--harness", "copilot")

        assert rc == 2
        assert str((sibling / ".claude" / other).resolve()) in err
        assert str((sibling / SCRIPT_REL).resolve()) not in err

    def test_untracked_script_blocks(self, repo, tmp_path, monkeypatch, capsys) -> None:
        """An untracked in-tree plain token is skipped; a same-repository one is not."""
        config = write_config(repo, plain())
        commit_as_trusted(repo, config)
        sibling = linked_worktree(repo, tmp_path, monkeypatch)
        write(sibling, SCRIPT_REL)

        rc, _, err = verify(repo, capsys, "--harness", "copilot")

        assert rc == 2
        assert str((sibling / SCRIPT_REL).resolve()) in err

    def test_modified_plain_token_blocks(self, repo, tmp_path, monkeypatch, capsys) -> None:
        """Plain tokens share the external classification, so D10 covers them too."""
        trusted_repo(repo, plain())
        sibling = linked_worktree(repo, tmp_path, monkeypatch)
        write(sibling, SCRIPT_REL, "print('PR branch code')\n")

        rc, _, err = verify(repo, capsys, "--harness", "copilot")

        assert rc == 2

    def test_modified_imported_module_blocks(self, repo, tmp_path, monkeypatch, capsys) -> None:
        """The sibling script's import closure is compared, as in-tree."""
        write(repo, ".claude/skills/demo/scripts/helper.py", "VALUE = 1\n")
        trusted_repo(repo, launcher(), ".claude/skills/demo/scripts/helper.py")
        write(repo, SCRIPT_REL, "import helper\n")
        commit_as_trusted(repo, SCRIPT_REL)
        sibling = linked_worktree(repo, tmp_path, monkeypatch)
        write(sibling, ".claude/skills/demo/scripts/helper.py", "VALUE = 2\n")

        rc, _, err = verify(repo, capsys, "--harness", "copilot")

        assert rc == 2
        assert "helper.py" in err

    def test_pinned_links_in_the_sibling_are_followed(
        self, repo, tmp_path, monkeypatch, capsys
    ) -> None:
        """ADR-119 links the trusted ref pins are keyed against the sibling's root."""
        write(repo, "src/demo/scripts/run.py", "import shared\n")
        write(repo, "src/lib/shared/__init__.py", "VALUE = 1\n")
        (repo / ".claude" / "skills").mkdir(parents=True)
        (repo / ".claude" / "lib").mkdir(parents=True)
        os.symlink("../../src/demo", repo / ".claude" / "skills" / "demo")
        os.symlink("../../src/lib/shared", repo / ".claude" / "lib" / "shared")
        config = write_config(repo, launcher())
        commit_as_trusted(
            repo,
            config,
            "src/demo/scripts/run.py",
            "src/lib/shared/__init__.py",
            ".claude/skills/demo",
            ".claude/lib/shared",
        )
        sibling = linked_worktree(repo, tmp_path, monkeypatch)

        rc, payload, err = verify(repo, capsys, "--harness", "copilot")

        assert rc == 0, err
        assert payload["blocking_unverifiable_command_tokens"] == []
        assert str((sibling / "src/demo/scripts/run.py").resolve()) in payload["checked_files"]
        assert str((sibling / "src/lib/shared/__init__.py").resolve()) in payload["checked_files"]
        assert not gate._SAME_REPOSITORY_TREES


class TestSiblingCloneRoot:
    @pytest.mark.parametrize(
        "origin",
        [
            OURS_ORIGIN,
            "git@github.com:owner/repo",
            "ssh://git@github.com/owner/repo.git/",
        ],
    )
    def test_modified_script_blocks(self, repo, tmp_path, monkeypatch, capsys, origin) -> None:
        trusted_repo(repo, launcher())
        clone = sibling_clone(repo, tmp_path, monkeypatch, origin)
        write(clone, SCRIPT_REL, "print('PR branch code')\n")

        rc, payload, err = verify(repo, capsys, "--harness", "copilot")

        assert rc == 2
        assert payload == {}

    def test_identical_script_passes(self, repo, tmp_path, monkeypatch, capsys) -> None:
        trusted_repo(repo, launcher())
        clone = sibling_clone(repo, tmp_path, monkeypatch, OURS_ORIGIN)

        rc, payload, err = verify(repo, capsys, "--harness", "copilot")

        assert rc == 0
        assert str((clone / SCRIPT_REL).resolve()) in payload["checked_files"]
        assert payload["blocking_unverifiable_command_tokens"] == []


class TestInstallTrustIsKept:
    def test_installed_plugin_directory_passes(self, repo, tmp_path, monkeypatch, capsys) -> None:
        trusted_repo(repo, launcher())
        installed = tmp_path / "installed"
        script = write(installed, LAUNCHED_REL, "print('installed')\n")
        monkeypatch.setenv("COPILOT_PLUGIN_ROOT", str(installed))

        rc, payload, err = verify(repo, capsys, "--harness", "copilot")

        assert rc == 0
        assert payload["blocking_unverifiable_command_tokens"] == []
        assert payload["skipped_external_files"] == [str(script.resolve())]

    @pytest.mark.parametrize("origin", [None, "https://github.com/other/project.git"])
    def test_another_repository_keeps_install_trust(
        self, repo, tmp_path, monkeypatch, capsys, origin
    ) -> None:
        trusted_repo(repo, launcher())
        git(repo, "remote", "add", "origin", OURS_ORIGIN)
        other = tmp_path / "other"
        other.mkdir()
        git(other, "init", "-q")
        if origin is not None:
            git(other, "remote", "add", "origin", origin)
        script = write(other, SCRIPT_REL, "print('another repository')\n")
        git(other, "add", SCRIPT_REL)
        git(other, "commit", "-q", "-m", "other")
        monkeypatch.setenv("COPILOT_PLUGIN_ROOT", str(other / ".claude"))

        rc, payload, err = verify(repo, capsys, "--harness", "copilot")

        assert rc == 0
        assert payload["skipped_external_files"] == [str(script.resolve())]
        assert payload["blocking_unverifiable_command_tokens"] == []

    def test_no_origin_on_either_side_is_not_a_match(
        self, repo, tmp_path, monkeypatch, capsys
    ) -> None:
        """Two repositories with no origin are not "the same" by origin."""
        trusted_repo(repo, launcher())
        other = tmp_path / "other"
        other.mkdir()
        git(other, "init", "-q")
        script = write(other, SCRIPT_REL, "print('another repository')\n")
        monkeypatch.setenv("COPILOT_PLUGIN_ROOT", str(other / ".claude"))

        rc, payload, err = verify(repo, capsys, "--harness", "copilot")

        assert rc == 0
        assert payload["skipped_external_files"] == [str(script.resolve())]
