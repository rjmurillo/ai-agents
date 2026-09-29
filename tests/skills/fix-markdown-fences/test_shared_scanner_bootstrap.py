#!/usr/bin/env python3
"""ADR-047 bootstrap contract for the two scripts that share the scanner.

`fix_fences.py` and `prose_lint.py` import the CommonMark container model from
`hook_utilities` in the plugin lib (issue #5352). If the inline bootstrap
resolves the lib wrongly in a consumer install, the skill does not degrade, it
fails to start. So each script runs as a subprocess and the test asserts the
process exit code, not just that an import worked.

Cases, per script:

- ``CLAUDE_PLUGIN_ROOT`` set to a root that has a ``lib/``: runs, exit 0.
- ``CLAUDE_PLUGIN_ROOT`` set to a directory with no ``lib/`` (issue #3897, a
  different extension exporting its own root): the guard falls through to the
  script-relative lib, exit 0.
- Neither variable set: script-relative lib, exit 0.
- A vendored copy with no lib anywhere: config error, exit 2, named message.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_TREE = PROJECT_ROOT / ".claude"

SCRIPTS = {
    "fix_fences": "skills/fix-markdown-fences/scripts/fix_fences.py",
    "prose_lint": "skills/prose-self-check/scripts/prose_lint.py",
}
ROOT_VARS = ("COPILOT_PLUGIN_ROOT", "CLAUDE_PLUGIN_ROOT")


def _run(script: Path, cwd: Path, env_extra: dict[str, str]) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k not in ROOT_VARS}
    env.update(env_extra)
    (cwd / "doc.md").write_text("Plain text here.\n", encoding="utf-8")
    (cwd / "voice.md").write_text("## Banned Vocabulary\n\n`zzz`.\n", encoding="utf-8")
    args = [sys.executable, str(script)]
    if script.name == "prose_lint.py":
        args += ["--rules", str(cwd / "voice.md")]
    args.append(str(cwd / "doc.md"))
    return subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, timeout=60)


@pytest.fixture(params=sorted(SCRIPTS))
def script_rel(request: pytest.FixtureRequest) -> str:
    return SCRIPTS[request.param]


def test_plugin_root_with_lib_runs(script_rel: str, tmp_path: Path) -> None:
    result = _run(
        PLUGIN_TREE / script_rel, tmp_path, {"CLAUDE_PLUGIN_ROOT": str(PLUGIN_TREE)}
    )
    assert result.returncode == 0, result.stderr


def test_copilot_plugin_root_with_lib_runs(script_rel: str, tmp_path: Path) -> None:
    result = _run(
        PLUGIN_TREE / script_rel, tmp_path, {"COPILOT_PLUGIN_ROOT": str(PLUGIN_TREE)}
    )
    assert result.returncode == 0, result.stderr


def test_plugin_root_without_lib_falls_through_to_script_relative_lib(
    script_rel: str, tmp_path: Path
) -> None:
    """Issue #3897: a foreign CLAUDE_PLUGIN_ROOT must not trigger exit 2."""
    foreign = tmp_path / "foreign-extension"
    foreign.mkdir()
    result = _run(PLUGIN_TREE / script_rel, tmp_path, {"CLAUDE_PLUGIN_ROOT": str(foreign)})
    assert result.returncode == 0, result.stderr


def test_foreign_lib_with_hook_utilities_but_no_scanner_falls_through(
    script_rel: str, tmp_path: Path
) -> None:
    """A foreign root can ship its own ``lib/hook_utilities`` without the scanner."""
    foreign = tmp_path / "foreign-extension"
    (foreign / "lib" / "hook_utilities").mkdir(parents=True)
    (foreign / "lib" / "hook_utilities" / "__init__.py").write_text("", encoding="utf-8")

    result = _run(PLUGIN_TREE / script_rel, tmp_path, {"CLAUDE_PLUGIN_ROOT": str(foreign)})

    assert result.returncode == 0, result.stderr


def test_unset_plugin_root_uses_script_relative_lib(script_rel: str, tmp_path: Path) -> None:
    result = _run(PLUGIN_TREE / script_rel, tmp_path, {})
    assert result.returncode == 0, result.stderr


def test_vendored_copy_with_its_lib_runs(script_rel: str, tmp_path: Path) -> None:
    plugin = tmp_path / "plugin"
    target = plugin / script_rel
    target.parent.mkdir(parents=True)
    shutil.copy2(PLUGIN_TREE / script_rel, target)
    shutil.copytree(PLUGIN_TREE / "lib" / "hook_utilities", plugin / "lib" / "hook_utilities")

    result = _run(target, tmp_path, {"CLAUDE_PLUGIN_ROOT": str(plugin)})

    assert result.returncode == 0, result.stderr


def test_vendored_copy_without_any_lib_is_a_config_error(script_rel: str, tmp_path: Path) -> None:
    plugin = tmp_path / "plugin"
    target = plugin / script_rel
    target.parent.mkdir(parents=True)
    shutil.copy2(PLUGIN_TREE / script_rel, target)

    result = _run(target, tmp_path, {})

    assert result.returncode == 2
    assert "Plugin lib directory not found" in result.stderr
