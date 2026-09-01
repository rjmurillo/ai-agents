#!/usr/bin/env python3
"""Vendoring contract for the fix-markdown-fences skill.

Split out of test_fix_fences_contracts.py, which answers to the CommonMark
reference implementation. This file answers to a different external contract:
the command `SKILL.md` documents must run, as shipped, from a consumer's
working directory, with the plugin-root variables the host actually exports.

It reads the invocation line out of each tree's own `SKILL.md` and runs that
exact string through a shell, so a mirror whose `SKILL.md` drifted fails here.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class TestVendoredInvocation:
    """The command SKILL.md documents, executed as shipped through a shell.

    The other tests import the canonical module. This one reads the invocation
    line out of the SKILL.md that ships in each plugin root and runs that exact
    string through a POSIX shell, from a directory that is not the repository.
    The shell performs the plugin-root expansion, so a renamed variable, a
    reversed fallback order, or a bare relative path fails here rather than
    passing. Passing an already-resolved path would prove none of that.

    The no-variable case is the negative control: with neither variable set the
    documented form falls back to a bare relative path, which is exactly what
    breaks in a consumer install.
    """

    pytestmark = pytest.mark.skipif(
        sys.platform == "win32",
        reason="the documented invocation is a POSIX shell parameter expansion",
    )

    PLUGIN_REL = "skills/fix-markdown-fences/scripts/fix_fences.py"
    SKILL_REL = "skills/fix-markdown-fences/SKILL.md"
    PLACEHOLDER = "FILE_OR_DIR"
    ROOT_VARS = ("COPILOT_PLUGIN_ROOT", "CLAUDE_PLUGIN_ROOT")

    def _documented_command(self, plugin_root: Path) -> str:
        """Return the report invocation from *plugin_root*'s own SKILL.md.

        Read rather than restated so the test tracks the shipped text. Each
        plugin root is checked against its own copy, which also catches a
        mirror whose SKILL.md drifted from the canonical one.
        """
        skill_md = plugin_root / self.SKILL_REL
        for line in skill_md.read_text(encoding="utf-8").splitlines():
            candidate = line.strip()
            if (
                candidate.startswith("python3 ")
                and "PLUGIN_ROOT" in candidate
                and candidate.endswith(self.PLACEHOLDER)
            ):
                return candidate.replace(self.PLACEHOLDER, "doc.md")
        raise AssertionError(f"no plugin-root invocation in {skill_md}")

    def _consumer(self, tmp_path: Path) -> Path:
        workdir = tmp_path / "consumer"
        workdir.mkdir(exist_ok=True)
        (workdir / "doc.md").write_text("```py\nx\n```py\ny\n```\n", encoding="utf-8")
        return workdir

    def _env(self, tmp_path: Path, roots: dict[str, str]) -> dict[str, str]:
        """Both root variables cleared, then *roots* applied.

        `python3` is pinned to the interpreter running the tests through a PATH
        shim, so the documented command text stays byte-identical while the
        subprocess cannot pick up an unrelated interpreter.
        """
        bindir = tmp_path / "bin"
        bindir.mkdir(exist_ok=True)
        shim = bindir / "python3"
        if not shim.exists():
            shim.symlink_to(sys.executable)
        env = {k: v for k, v in os.environ.items() if k not in self.ROOT_VARS}
        env["PATH"] = f"{bindir}{os.pathsep}{env.get('PATH', '')}"
        env.update(roots)
        return env

    def _run(self, command: str, tmp_path: Path, **roots: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["sh", "-c", command],
            cwd=self._consumer(tmp_path),
            env=self._env(tmp_path, roots),
            capture_output=True,
            text=True,
            timeout=60,
        )

    @staticmethod
    def _unresolved(result: subprocess.CompletedProcess[str]) -> bool:
        return "can't open file" in result.stderr or "No such file" in result.stderr

    @pytest.mark.parametrize(
        ("root_var", "tree"),
        [
            ("CLAUDE_PLUGIN_ROOT", ".claude"),
            ("COPILOT_PLUGIN_ROOT", "src/copilot-cli"),
        ],
    )
    def test_documented_form_runs_from_a_foreign_cwd(
        self, tmp_path: Path, root_var: str, tree: str
    ) -> None:
        plugin_root = PROJECT_ROOT / tree
        assert (plugin_root / self.PLUGIN_REL).is_file(), f"missing: {plugin_root}"
        result = self._run(
            self._documented_command(plugin_root), tmp_path, **{root_var: str(plugin_root)}
        )
        assert result.returncode == 1, result.stderr
        assert "malformed_closing" in result.stdout

    def test_copilot_root_wins_when_both_are_set(self, tmp_path: Path) -> None:
        plugin_root = PROJECT_ROOT / "src/copilot-cli"
        result = self._run(
            self._documented_command(plugin_root),
            tmp_path,
            COPILOT_PLUGIN_ROOT=str(plugin_root),
            CLAUDE_PLUGIN_ROOT=str(tmp_path / "absent"),
        )
        assert result.returncode == 1, result.stderr
        assert "malformed_closing" in result.stdout

    def test_claude_root_does_not_override_copilot_root(self, tmp_path: Path) -> None:
        claude_root = PROJECT_ROOT / ".claude"
        result = self._run(
            self._documented_command(claude_root),
            tmp_path,
            COPILOT_PLUGIN_ROOT=str(tmp_path / "absent"),
            CLAUDE_PLUGIN_ROOT=str(claude_root),
        )
        assert result.returncode != 1
        assert self._unresolved(result), result.stderr

    def test_bare_relative_fallback_fails_from_a_foreign_cwd(self, tmp_path: Path) -> None:
        # Negative control. With neither variable set the documented form
        # expands to the bare relative path it replaced, which cannot resolve
        # from a consumer's working directory.
        result = self._run(self._documented_command(PROJECT_ROOT / ".claude"), tmp_path)
        assert result.returncode != 0
        assert self._unresolved(result), result.stderr
