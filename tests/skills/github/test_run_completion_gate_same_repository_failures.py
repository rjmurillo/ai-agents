"""D10 (#6506): probe failures while deciding same-repository trust fail closed.

A git that cannot start, hangs, or a ``.git`` entry that cannot be probed must
halt as "cannot decide" (exit 3), never grant install trust and never escape
as a traceback at exit 1. A spelling that cannot be resolved is refused.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from tests.skills.github.dynamic_load_helpers import gate
from tests.skills.github.same_repository_helpers import (
    clear_plugin_roots,
    git,
    linked_worktree,
    make_repo,
    plain,
    trusted_repo,
    write,
)

CONFIG_REL = ".claude/skills/pr-review/pr-review-config.yaml"


@pytest.fixture(autouse=True)
def _no_plugin_root(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_plugin_roots(monkeypatch)


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return make_repo(tmp_path, monkeypatch)


def _sibling_config(repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    trusted_repo(repo, plain())
    sibling = linked_worktree(repo, tmp_path, monkeypatch)
    config = write(sibling, CONFIG_REL, "x: 1\n")
    root = sibling / ".claude"
    monkeypatch.setenv("COPILOT_PLUGIN_ROOT", str(root))
    monkeypatch.setattr(
        gate,
        "_DISPATCHER_PATH",
        root.resolve() / "skills/github/scripts/pr/run_completion_gate.py",
    )
    return config


class TestConfigProbeFailures:
    @pytest.mark.parametrize(
        "error",
        [
            subprocess.TimeoutExpired(["git"], 30),
            FileNotFoundError("git not found"),
        ],
    )
    def test_git_that_cannot_run_is_not_trust(self, repo, tmp_path, monkeypatch, error) -> None:
        """A hung or missing git during the identity probe raises the exit-3 error.

        Earlier git calls (the consumer work tree lookup) have their own
        handling, so only the D10 identity probe is made to fail here.
        """
        config = _sibling_config(repo, tmp_path, monkeypatch)

        def fail(work_tree):
            raise error

        monkeypatch.setattr(gate, "_repository_identity", fail)

        with pytest.raises(gate.WorkTreeUnavailableError, match="git probe for"):
            gate._install_trusted_root(str(config))

    def test_same_repository_root_error_is_not_trust(self, repo, tmp_path, monkeypatch) -> None:
        """The second probe failing also raises; it never reads as "not ours"."""
        config = _sibling_config(repo, tmp_path, monkeypatch)
        monkeypatch.setattr(
            gate,
            "_same_repository_root",
            lambda path, ours: (None, f"cannot probe {path}/.git: denied"),
        )

        with pytest.raises(gate.WorkTreeUnavailableError, match="cannot probe"):
            gate._install_trusted_root(str(config))


class TestSameRepositoryRootProbe:
    def test_unprobeable_inner_git_entry_is_an_error(self, repo, monkeypatch) -> None:
        """A ``.git`` lstat failure other than absence is an error, not an absence."""
        git(repo, "commit", "-q", "--allow-empty", "-m", "base")
        ours, error = gate._repository_identity(repo)
        assert error == ""
        inner = repo / "pkg"
        inner.mkdir()
        denied = inner / ".git"
        real_lstat = os.lstat

        def lstat(path, *args, **kwargs):
            if Path(path) == denied:
                raise PermissionError(13, "Permission denied", str(path))
            return real_lstat(path, *args, **kwargs)

        monkeypatch.setattr(gate.os, "lstat", lstat)

        root, error = gate._same_repository_root(inner / "f.py", ours)

        assert root is None
        assert error.startswith(f"cannot probe {denied}")


class TestUnpinnedLinkResolveFailure:
    @pytest.mark.parametrize("error", [OSError("io"), RuntimeError("loop")])
    def test_unresolvable_ancestor_refuses_the_spelling(self, tmp_path, monkeypatch, error) -> None:
        """No scan is possible, so the spelling itself is returned as the refusal."""
        literal = tmp_path / "alias" / "skills" / "x.py"
        real_resolve = Path.resolve

        def resolve(self: Path, strict: bool = False) -> Path:
            if self == literal.parent:
                raise error
            return real_resolve(self, strict=strict)

        monkeypatch.setattr(Path, "resolve", resolve)

        assert gate._unpinned_link_in(literal, tmp_path.resolve()) == literal
