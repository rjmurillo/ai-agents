#!/usr/bin/env python3
"""Plugin lib resolution for resolve_pr_conflicts.py (issue #4961).

The merge-resolver script imports ``github_core`` out of a plugin ``lib``
directory it has to find first. Under the Copilot CLI the host may set
``CLAUDE_PLUGIN_ROOT`` to whichever plugin triggered the context-mode hook,
so a resolver that trusts one variable resolves support files from the wrong
plugin and exits 2 with a valid root still unexamined.

These tests pin the fixed contract: candidates are tried in order, each is
validated before use, and the run fails closed only when none is valid.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

mod = import_skill_script(".claude/skills/merge-resolver/scripts/resolve_pr_conflicts.py")

# Every environment variable the resolver reads. Cleared per test so a harness
# or CI runner value cannot decide the outcome. GITHUB_WORKSPACE is always set
# on a GitHub Actions runner and points at a checkout whose .claude/lib is
# valid, which would mask the fail-closed case (testing.md SHOULD 12).
_PLUGIN_ROOT_ENV_VARS = ("COPILOT_PLUGIN_ROOT", "CLAUDE_PLUGIN_ROOT", "GITHUB_WORKSPACE")

# The package resolve_pr_conflicts.py imports out of the plugin lib directory:
#     from github_core.api import RepoInfo
# Spelled out here rather than read from the module so the test pins the
# import contract instead of the module's own constant.
_CORE_PACKAGE_NAME = "github_core"

# The module file inside that package the import above names. A candidate that
# carries the package directory but not this file is not importable, so the
# resolver must reject it (PR #5000 review).
_CORE_MODULE_FILE_NAME = "api.py"

# This repository's own plugin lib, derived from this file's location
# (tests/skills/merge-resolver/ sits three levels below the repo root) rather
# than from the module under test.
_REPO_CLAUDE_LIB = Path(__file__).resolve().parents[3] / ".claude" / "lib"

# The script under test, at its canonical path.
_SCRIPT = (
    Path(__file__).resolve().parents[3]
    / ".claude"
    / "skills"
    / "merge-resolver"
    / "scripts"
    / "resolve_pr_conflicts.py"
)


_PLUGIN_IDENTITY_NAME = "project-toolkit"


def _add_plugin_manifest(root: Path) -> None:
    """Add the plugin identity manifest to a fixture root."""
    manifest_dir = root / ".claude-plugin"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "plugin.json").write_text(
        json.dumps({"name": _PLUGIN_IDENTITY_NAME}), encoding="utf-8"
    )


def _make_plugin_root(base: Path, name: str) -> Path:
    """Create a plugin root whose lib/ carries an importable github_core.

    The package holds the module the script imports, so a root built here is
    usable, not merely correctly named.
    """
    root = base / name
    package = root / "lib" / _CORE_PACKAGE_NAME
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / _CORE_MODULE_FILE_NAME).write_text(
        "class RepoInfo:\n    pass\n", encoding="utf-8"
    )
    _add_plugin_manifest(root)
    return root


def _make_partial_plugin_root(base: Path, name: str) -> Path:
    """Create a plugin root whose github_core package lacks the imported module.

    A broken or half-copied install has the right directory name and nothing
    to import. Accepting it raises ModuleNotFoundError at line 133 instead of
    falling through to a usable candidate (PR #5000 review).
    """
    root = base / name
    (root / "lib" / _CORE_PACKAGE_NAME).mkdir(parents=True)
    return root


def _make_transitively_broken_plugin_root(base: Path, name: str) -> Path:
    """Create a plugin root whose api.py imports a missing sibling module."""
    root = base / name
    package = root / "lib" / _CORE_PACKAGE_NAME
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / _CORE_MODULE_FILE_NAME).write_text(
        "from github_core.missing_dependency import value\n"
        "class RepoInfo:\n"
        "    pass\n",
        encoding="utf-8",
    )
    return root


def _make_early_exit_plugin_root(base: Path, name: str) -> Path:
    """Create a plugin root whose api.py exits zero during import."""
    root = base / name
    package = root / "lib" / _CORE_PACKAGE_NAME
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / _CORE_MODULE_FILE_NAME).write_text(
        "import sys\nsys.exit(0)\nclass RepoInfo:\n    pass\n",
        encoding="utf-8",
    )
    _add_plugin_manifest(root)
    return root


def _make_foreign_plugin_root(base: Path, name: str) -> Path:
    """Create a plugin root whose lib/ exists but carries no github_core.

    This is the Copilot context-mode shape: a real plugin that is not this
    plugin. Directory existence alone cannot tell it apart from ours.
    """
    root = base / name
    (root / "lib" / "context_mode_core").mkdir(parents=True)
    return root


def _clear_plugin_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove every plugin-root variable from the test process environment."""
    for name in _PLUGIN_ROOT_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


class TestLibDirCandidates:
    """Candidate order and membership (issue #4961 acceptance criteria)."""

    def test_order_is_copilot_then_claude_then_workspace_then_relative(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _clear_plugin_env(monkeypatch)
        monkeypatch.setenv("COPILOT_PLUGIN_ROOT", str(tmp_path / "copilot"))
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path / "claude"))
        monkeypatch.setenv("GITHUB_WORKSPACE", str(tmp_path / "workspace"))

        assert mod._lib_dir_candidates() == [
            str(tmp_path / "copilot" / "lib"),
            str(tmp_path / "claude" / "lib"),
            str(tmp_path / "workspace" / ".claude" / "lib"),
            str(_REPO_CLAUDE_LIB),
        ]

    def test_unset_variables_contribute_no_candidate(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _clear_plugin_env(monkeypatch)

        assert mod._lib_dir_candidates() == [str(_REPO_CLAUDE_LIB)]


class TestResolveLibDir:
    """Each candidate is validated before use, so a wrong root falls through."""

    def test_import_probe_reports_failure_without_stderr(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            mod.subprocess,
            "run",
            lambda *args, **kwargs: subprocess.CompletedProcess(args, 1, "", ""),
        )

        assert mod._core_import_error("/candidate/lib") == "process exited 1"

    def test_import_probe_reports_timeout(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def raise_timeout(*args: object, **kwargs: object) -> None:
            raise subprocess.TimeoutExpired("python", 30)

        monkeypatch.setattr(mod.subprocess, "run", raise_timeout)

        assert mod._core_import_error("/candidate/lib") == "import timed out"

    def test_prefers_copilot_plugin_root(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _clear_plugin_env(monkeypatch)
        copilot = _make_plugin_root(tmp_path, "copilot-plugin")
        claude = _make_plugin_root(tmp_path, "claude-plugin")
        monkeypatch.setenv("COPILOT_PLUGIN_ROOT", str(copilot))
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(claude))

        assert mod._resolve_lib_dir() == str(copilot / "lib")

    def test_uses_claude_plugin_root_when_copilot_is_unset(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _clear_plugin_env(monkeypatch)
        claude = _make_plugin_root(tmp_path, "claude-plugin")
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(claude))

        assert mod._resolve_lib_dir() == str(claude / "lib")

    def test_foreign_claude_root_falls_through_to_copilot_root(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Issue #4961 repro: Copilot CLI with a foreign CLAUDE_PLUGIN_ROOT.

        Before the fix CLAUDE_PLUGIN_ROOT was authoritative and unvalidated,
        so this combination exited 2 with a valid root still in the list.
        """
        _clear_plugin_env(monkeypatch)
        copilot = _make_plugin_root(tmp_path, "ai-agents-plugin")
        monkeypatch.setenv("COPILOT_PLUGIN_ROOT", str(copilot))
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path / "context-mode"))

        assert mod._resolve_lib_dir() == str(copilot / "lib")

    def test_missing_copilot_root_falls_through_to_claude_root(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _clear_plugin_env(monkeypatch)
        claude = _make_plugin_root(tmp_path, "claude-plugin")
        monkeypatch.setenv("COPILOT_PLUGIN_ROOT", str(tmp_path / "context-mode"))
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(claude))

        assert mod._resolve_lib_dir() == str(claude / "lib")

    def test_foreign_plugin_lib_without_core_package_is_rejected(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """A foreign plugin that ships its own lib/ must not be imported from."""
        _clear_plugin_env(monkeypatch)
        foreign = _make_foreign_plugin_root(tmp_path, "context-mode")
        claude = _make_plugin_root(tmp_path, "claude-plugin")
        monkeypatch.setenv("COPILOT_PLUGIN_ROOT", str(foreign))
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(claude))

        assert (foreign / "lib").is_dir()
        assert mod._resolve_lib_dir() == str(claude / "lib")

    def test_partial_core_package_without_the_imported_module_is_rejected(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """A github_core directory with no api.py is not importable.

        Name-only validation would accept it and the import would then raise
        ModuleNotFoundError, losing both the fallthrough and the exit 2.
        """
        _clear_plugin_env(monkeypatch)
        partial = _make_partial_plugin_root(tmp_path, "half-installed")
        claude = _make_plugin_root(tmp_path, "claude-plugin")
        monkeypatch.setenv("COPILOT_PLUGIN_ROOT", str(partial))
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(claude))

        assert (partial / "lib" / _CORE_PACKAGE_NAME).is_dir()
        assert mod._resolve_lib_dir() == str(claude / "lib")

    def test_api_with_missing_transitive_module_is_rejected(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """The candidate must support the real RepoInfo import."""
        _clear_plugin_env(monkeypatch)
        broken = _make_transitively_broken_plugin_root(tmp_path, "half-installed")
        claude = _make_plugin_root(tmp_path, "claude-plugin")
        monkeypatch.setenv("COPILOT_PLUGIN_ROOT", str(broken))
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(claude))

        assert (broken / "lib" / _CORE_PACKAGE_NAME / _CORE_MODULE_FILE_NAME).is_file()
        assert mod._resolve_lib_dir() == str(claude / "lib")

    def test_api_that_exits_zero_before_import_completion_is_rejected(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _clear_plugin_env(monkeypatch)
        broken = _make_early_exit_plugin_root(tmp_path, "early-exit")
        claude = _make_plugin_root(tmp_path, "claude-plugin")
        monkeypatch.setenv("COPILOT_PLUGIN_ROOT", str(broken))
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(claude))

        assert mod._resolve_lib_dir() == str(claude / "lib")

    def test_uses_github_workspace_when_no_plugin_root_is_valid(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _clear_plugin_env(monkeypatch)
        workspace = _make_plugin_root(tmp_path / "workspace", ".claude")
        monkeypatch.setenv("COPILOT_PLUGIN_ROOT", str(tmp_path / "context-mode"))
        monkeypatch.setenv("GITHUB_WORKSPACE", str(tmp_path / "workspace"))

        assert mod._resolve_lib_dir() == str(workspace / "lib")

    def test_falls_back_to_repository_lib_when_no_variable_is_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _clear_plugin_env(monkeypatch)

        assert mod._resolve_lib_dir() == str(_REPO_CLAUDE_LIB)

    def test_exits_2_when_no_candidate_carries_the_core_package(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Fail-closed is preserved and the message names every rejection."""
        absent = tmp_path / "absent" / "lib"
        foreign = _make_foreign_plugin_root(tmp_path, "context-mode") / "lib"
        partial = _make_partial_plugin_root(tmp_path, "half-installed") / "lib"
        monkeypatch.setattr(
            mod,
            "_lib_dir_candidates",
            lambda: [str(absent), str(foreign), str(partial)],
        )

        with pytest.raises(SystemExit) as excinfo:
            mod._resolve_lib_dir()

        assert excinfo.value.code == 2
        stderr = capsys.readouterr().err
        assert f"{absent} (no such directory)" in stderr
        assert f"{foreign} (no {_CORE_PACKAGE_NAME}/{_CORE_MODULE_FILE_NAME})" in stderr
        assert f"{partial} (no {_CORE_PACKAGE_NAME}/{_CORE_MODULE_FILE_NAME})" in stderr


class TestResolveLibDirCli:
    """End to end: the installed script resolves its lib before importing.

    The script is copied into a plugin-shaped tree whose own lib/ is absent,
    so the relative fallback cannot rescue a run and the environment decides
    the outcome. ``--help`` exercises module import, where resolution happens,
    without touching git or gh.
    """

    @staticmethod
    def _install_script(tmp_path: Path) -> Path:
        """Copy the script into <tmp>/plugin/skills/merge-resolver/scripts/."""
        scripts_dir = tmp_path / "plugin" / "skills" / "merge-resolver" / "scripts"
        scripts_dir.mkdir(parents=True)
        target = scripts_dir / _SCRIPT.name
        shutil.copy2(_SCRIPT, target)
        # The relative candidate for the copy, absent by construction: the
        # test must not hand the code the precondition it is proving.
        assert not (tmp_path / "plugin" / "lib").exists()
        return target

    @staticmethod
    def _run(script: Path, overrides: dict[str, str]) -> subprocess.CompletedProcess[str]:
        env = {k: v for k, v in os.environ.items() if k not in _PLUGIN_ROOT_ENV_VARS}
        env.update(overrides)
        return subprocess.run(
            [sys.executable, str(script), "--help"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=60,
            check=False,
        )

    def test_runs_under_copilot_root_with_foreign_claude_root(self, tmp_path: Path) -> None:
        """Issue #4961 end to end: the run survives a foreign CLAUDE_PLUGIN_ROOT."""
        script = self._install_script(tmp_path)
        result = self._run(
            script,
            {
                "COPILOT_PLUGIN_ROOT": str(_REPO_CLAUDE_LIB.parent),
                "CLAUDE_PLUGIN_ROOT": str(tmp_path / "context-mode"),
            },
        )

        assert result.returncode == 0, result.stderr
        assert "--branch-name" in result.stdout

    def test_exits_2_when_every_candidate_is_foreign_or_absent(self, tmp_path: Path) -> None:
        """Negative control: no valid root anywhere still fails closed."""
        script = self._install_script(tmp_path)
        foreign = _make_foreign_plugin_root(tmp_path, "context-mode")
        result = self._run(
            script,
            {
                "COPILOT_PLUGIN_ROOT": str(foreign),
                "CLAUDE_PLUGIN_ROOT": str(tmp_path / "absent-plugin"),
            },
        )

        assert result.returncode == 2, result.stdout
        assert "Plugin lib directory not found" in result.stderr
        assert (
            f"{foreign / 'lib'} (no {_CORE_PACKAGE_NAME}/{_CORE_MODULE_FILE_NAME})"
            in result.stderr
        )
        assert f"{tmp_path / 'absent-plugin' / 'lib'} (no such directory)" in result.stderr
        assert f"{tmp_path / 'plugin' / 'lib'} (no such directory)" in result.stderr

    def test_runs_when_a_partial_core_package_precedes_a_valid_root(
        self, tmp_path: Path
    ) -> None:
        """A half-installed github_core must not end the run at import time."""
        script = self._install_script(tmp_path)
        partial = _make_partial_plugin_root(tmp_path, "half-installed")
        result = self._run(
            script,
            {
                "COPILOT_PLUGIN_ROOT": str(partial),
                "CLAUDE_PLUGIN_ROOT": str(_REPO_CLAUDE_LIB.parent),
            },
        )

        assert result.returncode == 0, result.stderr
        assert "ModuleNotFoundError" not in result.stderr
        assert "--branch-name" in result.stdout

    def test_runs_when_api_has_a_missing_transitive_module(
        self, tmp_path: Path
    ) -> None:
        """A candidate that fails the real import must fall through."""
        script = self._install_script(tmp_path)
        broken = _make_transitively_broken_plugin_root(tmp_path, "half-installed")
        result = self._run(
            script,
            {
                "COPILOT_PLUGIN_ROOT": str(broken),
                "CLAUDE_PLUGIN_ROOT": str(_REPO_CLAUDE_LIB.parent),
            },
        )

        assert result.returncode == 0, result.stderr
        assert "ModuleNotFoundError" not in result.stderr
        assert "--branch-name" in result.stdout

    def test_runs_when_api_exits_zero_before_import_completion(
        self, tmp_path: Path
    ) -> None:
        script = self._install_script(tmp_path)
        broken = _make_early_exit_plugin_root(tmp_path, "early-exit")
        result = self._run(
            script,
            {
                "COPILOT_PLUGIN_ROOT": str(broken),
                "CLAUDE_PLUGIN_ROOT": str(_REPO_CLAUDE_LIB.parent),
            },
        )

        assert result.returncode == 0, result.stderr
        assert "--branch-name" in result.stdout
