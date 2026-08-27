"""Tests for the worktree-safe lefthook shim installer.

Git keeps one hooks directory per repository and every linked worktree reads it,
so a shim carrying an absolute path probed from one worktree's environment is
wrong for every other checkout. Measured in this repository on 2026-08-27: the
shared ``pre-commit`` named worktree ``wf_54440bac-347-6``'s ``.venv`` while
worktree ``wf_54440bac-347-8`` was the reader, and installing from ``-8``
rewrote the same shared line to ``-8``. Refs issue #4789.

These tests use real git repositories with real linked worktrees, because the
shared-hooks-directory behaviour is the thing under test and a mock of it would
assert the premise instead of checking it.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from scripts.maintenance.install_lefthook_worktree_safe import (
    GIT_CLIENT_HOOKS,
    config_path,
    declared_hooks,
    find_defects,
    hook_shim,
    hooks_dir,
    main,
    shim_defect,
    write_shims,
)

# Resolved at import time so @pytest.mark.skipif can read it at collection
# (.claude/rules/testing.md MUST 13). The `lefthook` wheel ships the binary
# under <package>/bin/lefthook-<os>-<arch>/lefthook.
try:  # pragma: no cover - import shape differs per install
    import lefthook as _lefthook_package

    _LEFTHOOK_BINARY = next(
        iter(sorted(Path(_lefthook_package.__file__).parent.glob("bin/*/lefthook*"))),
        None,
    )
except ImportError:  # pragma: no cover - lefthook is a dev dependency
    _LEFTHOOK_BINARY = None

_CONFIG = "pre-commit:\n  jobs:\n    - name: noop\n      run: true\n"

# The shape lefthook 2.1.10 generates, reduced to the branch that carries the
# defect: an absolute path into one checkout's virtual environment. The real
# shim spells the tail out as
# ``lib/python3.14/site-packages/lefthook/bin/lefthook-linux-x86_64/lefthook``;
# that suffix is elided here because the defect signature is the ``/.venv/``
# prefix. ``TestAgainstRealLefthook`` covers the unabridged article.
_POISONED_SHIM = """#!/bin/sh
call_lefthook()
{{
  if test -n "$LEFTHOOK_BIN"
  then
    "$LEFTHOOK_BIN" "$@"
  elif {venv}/bin/lefthook -h >/dev/null 2>&1
  then
    {venv}/bin/lefthook "$@"
  fi
}}

call_lefthook run "pre-commit" "$@"
"""


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=True,
        timeout=30,
    )
    return result.stdout.strip()


@pytest.fixture
def primary(tmp_path: Path) -> Path:
    """A real git repository that configures lefthook."""
    root = tmp_path / "primary"
    root.mkdir()
    _git(root, "init", "-q", ".")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "test")
    (root / "lefthook.yml").write_text(_CONFIG, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    return root


@pytest.fixture
def linked(primary: Path, tmp_path: Path) -> Path:
    """A linked worktree of ``primary``, sharing its hooks directory."""
    root = tmp_path / "linked"
    _git(primary, "worktree", "add", "-q", str(root), "-b", "sibling")
    return root


class TestShimContent:
    """The shim body is the contract: it may name no worktree-specific path."""

    @pytest.mark.parametrize("hook", sorted(GIT_CLIENT_HOOKS))
    def test_no_hook_shim_names_a_virtual_environment(self, hook: str) -> None:
        assert "/.venv/" not in hook_shim(hook)

    @pytest.mark.parametrize("hook", sorted(GIT_CLIENT_HOOKS))
    def test_no_hook_shim_executes_an_absolute_path(self, hook: str) -> None:
        executed = [
            line.strip()
            for line in hook_shim(hook).splitlines()
            if line.strip().startswith("exec ")
        ]
        assert executed, "the shim must exec something"
        for line in executed:
            target = line.split()[1].strip('"')
            assert not target.startswith("/"), line

    def test_the_shim_dispatches_to_its_own_hook_name(self) -> None:
        assert 'run "pre-push"' in hook_shim("pre-push")
        assert 'run "pre-push"' not in hook_shim("pre-commit")

    def test_the_shim_honours_the_lefthook_skip_switch(self) -> None:
        assert '"$LEFTHOOK" = "0"' in hook_shim("pre-commit")


class TestDeclaredHooks:
    """Only top-level keys naming a client-side git hook count as hooks."""

    def test_reads_hook_keys_in_file_order(self, tmp_path: Path) -> None:
        config = tmp_path / "lefthook.yml"
        config.write_text("pre-push:\n  jobs: []\npre-commit:\n  jobs: []\n", encoding="utf-8")

        assert declared_hooks(config) == ["pre-push", "pre-commit"]

    def test_ignores_top_level_keys_that_are_not_git_hooks(self, tmp_path: Path) -> None:
        config = tmp_path / "lefthook.yml"
        config.write_text(
            "lefthook: uv run --frozen lefthook\ncolors: false\npre-commit:\n  jobs: []\n",
            encoding="utf-8",
        )

        assert declared_hooks(config) == ["pre-commit"]

    def test_ignores_a_hook_name_that_is_not_a_top_level_key(self, tmp_path: Path) -> None:
        config = tmp_path / "lefthook.yml"
        config.write_text(
            "pre-commit:\n  jobs:\n    - name: mention\n      run: echo pre-push:\n",
            encoding="utf-8",
        )

        assert declared_hooks(config) == ["pre-commit"]

    def test_returns_empty_for_a_config_declaring_no_hooks(self, tmp_path: Path) -> None:
        config = tmp_path / "lefthook.yml"
        config.write_text("colors: false\n", encoding="utf-8")

        assert declared_hooks(config) == []


class TestShimDefect:
    """Positive, negative, and edge classification of one hook file."""

    def test_accepts_the_shim_this_installer_writes(self, tmp_path: Path) -> None:
        path = tmp_path / "pre-commit"
        path.write_text(hook_shim("pre-commit"), encoding="utf-8")
        path.chmod(0o755)

        assert shim_defect("pre-commit", path) is None

    def test_reports_a_missing_hook(self, tmp_path: Path) -> None:
        defect = shim_defect("pre-commit", tmp_path / "pre-commit")

        assert defect is not None
        assert "is missing" in defect

    def test_reports_a_non_executable_hook(self, tmp_path: Path) -> None:
        path = tmp_path / "pre-commit"
        path.write_text(hook_shim("pre-commit"), encoding="utf-8")
        path.chmod(0o644)

        defect = shim_defect("pre-commit", path)

        assert defect is not None
        assert "not executable" in defect

    def test_reports_a_baked_virtual_environment_path(self, tmp_path: Path) -> None:
        path = tmp_path / "pre-commit"
        path.write_text(_POISONED_SHIM.format(venv="/somewhere/wt-6/.venv"), encoding="utf-8")
        path.chmod(0o755)

        defect = shim_defect("pre-commit", path)

        assert defect is not None
        assert "/.venv/" in defect

    def test_reports_unrelated_content_without_claiming_a_venv_path(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "pre-commit"
        path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        path.chmod(0o755)

        defect = shim_defect("pre-commit", path)

        assert defect is not None
        assert "/.venv/" not in defect
        assert "worktree-safe shim" in defect

    def test_reports_a_hook_that_is_not_decodable_text(self, tmp_path: Path) -> None:
        path = tmp_path / "pre-commit"
        path.write_bytes(b"\xff\xfe\x00binary")
        path.chmod(0o755)

        defect = shim_defect("pre-commit", path)

        assert defect is not None
        assert "could not be read as text" in defect


class TestSharedHooksDirectory:
    """The premise: one hooks directory serves the primary clone and its worktrees."""

    def test_a_linked_worktree_resolves_to_the_same_hooks_directory(
        self, primary: Path, linked: Path
    ) -> None:
        assert hooks_dir(linked).resolve() == hooks_dir(primary).resolve()

    def test_a_linked_worktree_finds_the_shared_lefthook_config(
        self, primary: Path, linked: Path
    ) -> None:
        assert config_path(linked) is not None
        assert config_path(primary) is not None


class TestWorktreeIsolationRegression:
    """A sibling worktree's install must not break any other checkout."""

    def test_a_sibling_install_is_reported_as_a_defect_by_the_primary_clone(
        self, primary: Path, linked: Path
    ) -> None:
        # Arrange: exactly what `lefthook install` from `linked` leaves behind.
        shared = hooks_dir(primary) / "pre-commit"
        shared.parent.mkdir(parents=True, exist_ok=True)
        shared.write_text(
            _POISONED_SHIM.format(venv=f"{linked}/.venv"), encoding="utf-8"
        )
        shared.chmod(0o755)

        # Act
        defects, examined = find_defects(primary)

        # Assert: the primary clone, which installed nothing, is the victim.
        assert examined == 1
        assert len(defects) == 1
        assert str(linked) in shared.read_text(encoding="utf-8")
        assert "/.venv/" in defects[0]

    def test_the_check_cli_exits_one_on_a_sibling_poisoned_shim(
        self, primary: Path, linked: Path
    ) -> None:
        shared = hooks_dir(primary) / "pre-commit"
        shared.parent.mkdir(parents=True, exist_ok=True)
        shared.write_text(
            _POISONED_SHIM.format(venv=f"{linked}/.venv"), encoding="utf-8"
        )
        shared.chmod(0o755)

        assert main(["--check", "--repo-root", str(primary)]) == 1

    def test_writing_the_shims_clears_the_defect_for_every_worktree_at_once(
        self, primary: Path, linked: Path
    ) -> None:
        shared = hooks_dir(primary) / "pre-commit"
        shared.parent.mkdir(parents=True, exist_ok=True)
        shared.write_text(
            _POISONED_SHIM.format(venv=f"{linked}/.venv"), encoding="utf-8"
        )
        shared.chmod(0o755)

        written = write_shims(primary, ["pre-commit"])

        assert written == [shared]
        assert find_defects(primary) == ([], 1)
        assert find_defects(linked) == ([], 1)
        assert str(linked) not in shared.read_text(encoding="utf-8")
        assert main(["--check", "--repo-root", str(linked)]) == 0

    def test_a_rewrite_leaves_the_hook_executable(self, primary: Path) -> None:
        write_shims(primary, ["pre-commit"])
        shared = hooks_dir(primary) / "pre-commit"

        assert os.access(shared, os.X_OK)

    def test_rewriting_a_clean_shim_is_a_no_op(self, primary: Path) -> None:
        write_shims(primary, ["pre-commit"])

        assert write_shims(primary, ["pre-commit"]) == []


class TestCliExitCodes:
    """ADR-035 codes, asserted on ``main`` rather than on a helper (testing MUST 8)."""

    def test_check_exits_zero_when_every_shim_is_safe(self, primary: Path) -> None:
        write_shims(primary, ["pre-commit"])

        assert main(["--check", "--repo-root", str(primary)]) == 0

    def test_check_exits_one_when_the_hook_is_absent(self, primary: Path) -> None:
        assert main(["--check", "--repo-root", str(primary)]) == 1

    def test_exits_two_without_a_lefthook_config(self, primary: Path) -> None:
        (primary / "lefthook.yml").unlink()

        assert main(["--check", "--repo-root", str(primary)]) == 2

    def test_exits_two_outside_a_git_repository(self, tmp_path: Path) -> None:
        outside = tmp_path / "plain"
        outside.mkdir()

        assert main(["--check", "--repo-root", str(outside)]) == 2

    def test_check_names_the_repair_command_on_failure(
        self, primary: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        main(["--check", "--repo-root", str(primary)])

        assert "install_lefthook_worktree_safe.py" in capsys.readouterr().err

    def test_check_reports_the_examined_count_when_clean(
        self, primary: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        write_shims(primary, ["pre-commit"])
        main(["--check", "--repo-root", str(primary)])

        assert "1 of 1 examined hooks" in capsys.readouterr().out

    def test_check_never_mutates_the_hooks_directory(self, primary: Path) -> None:
        shared = hooks_dir(primary) / "pre-commit"
        assert not shared.exists()

        main(["--check", "--repo-root", str(primary)])

        assert not shared.exists()


@pytest.mark.skipif(
    _LEFTHOOK_BINARY is None, reason="the lefthook binary is not installed here"
)
class TestAgainstRealLefthook:
    """Control: the real tool still produces the shim shape this fix replaces."""

    def test_a_real_install_from_a_worktree_leaves_the_shared_shim_unsafe(
        self, primary: Path, linked: Path
    ) -> None:
        assert _LEFTHOOK_BINARY is not None
        subprocess.run(
            [str(_LEFTHOOK_BINARY), "install", "--reset-hooks-path"],
            cwd=str(linked),
            check=True,
            capture_output=True,
            timeout=60,
        )

        defects, examined = find_defects(primary)

        assert examined == 1
        assert defects, "lefthook's own shim must not pass the worktree-safe check"

    def test_the_installer_repairs_what_a_real_install_leaves(
        self, primary: Path, linked: Path
    ) -> None:
        assert _LEFTHOOK_BINARY is not None
        subprocess.run(
            [str(_LEFTHOOK_BINARY), "install", "--reset-hooks-path"],
            cwd=str(linked),
            check=True,
            capture_output=True,
            timeout=60,
        )

        write_shims(primary, ["pre-commit"])

        assert find_defects(primary) == ([], 1)
        assert find_defects(linked) == ([], 1)
