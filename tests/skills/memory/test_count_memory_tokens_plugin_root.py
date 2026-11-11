"""Runtime-contract tests for memory script plugin-root resolution (issue #7277).

Another plugin can export its own CLAUDE_PLUGIN_ROOT (context-mode does inside
ctx_execute). The memory scripts must use an env root only when it holds this
plugin's hook_utilities.path_safety module, and otherwise fall back to the lib
beside the script. Each case runs the script in a fresh interpreter with the
env a host would set.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
MEMORY_SCRIPTS = REPO_ROOT / "src" / "claude" / "skills" / "memory" / "scripts"
SCRIPTS = [MEMORY_SCRIPTS / "count_memory_tokens.py", MEMORY_SCRIPTS / "test_memory_size.py"]
OWN_LIB = REPO_ROOT / "src" / "claude" / "lib"

_GUARD = "if _PLUGIN_ROOT and os.path.isfile(os.path.join(_PLUGIN_ROOT, _ROOT_MARKER)):"
_RESOLVE = (
    "import runpy, sys; ns = runpy.run_path(sys.argv[1], run_name='probe'); print(ns['_LIB_DIR'])"
)

all_scripts = pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
both_variables = pytest.mark.parametrize("variable", ["CLAUDE_PLUGIN_ROOT", "COPILOT_PLUGIN_ROOT"])


def _run(script: Path, env_extra: dict[str, str], cwd: Path) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if not k.endswith("_PLUGIN_ROOT")}
    env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-c", _RESOLVE, str(script)],
        env=env,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )


def _foreign_root(tmp_path: Path) -> Path:
    """A plugin root that is not this plugin: has a lib dir but no hook_utilities."""
    root = tmp_path / "context-mode" / "2.1.7"
    (root / "lib").mkdir(parents=True)
    return root


@all_scripts
@both_variables
def test_empty_foreign_root_falls_back_to_own_lib(
    tmp_path: Path, script: Path, variable: str
) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()

    result = _run(script, {variable: str(empty)}, tmp_path)

    assert result.returncode == 0, result.stderr
    assert Path(result.stdout.strip()) == OWN_LIB


@all_scripts
@both_variables
def test_foreign_root_with_lib_but_no_hook_utilities_falls_back(
    tmp_path: Path, script: Path, variable: str
) -> None:
    foreign = _foreign_root(tmp_path)

    result = _run(script, {variable: str(foreign)}, tmp_path)

    assert result.returncode == 0, result.stderr
    assert Path(result.stdout.strip()) == OWN_LIB


@all_scripts
def test_root_with_hook_utilities_but_no_path_safety_falls_back(
    tmp_path: Path, script: Path
) -> None:
    """An older co-installed toolkit has the package dir but not the imported module."""
    root = tmp_path / "old-toolkit"
    (root / "lib" / "hook_utilities").mkdir(parents=True)

    result = _run(script, {"CLAUDE_PLUGIN_ROOT": str(root)}, tmp_path)

    assert result.returncode == 0, result.stderr
    assert Path(result.stdout.strip()) == OWN_LIB


@all_scripts
def test_missing_foreign_root_path_falls_back(tmp_path: Path, script: Path) -> None:
    result = _run(script, {"CLAUDE_PLUGIN_ROOT": str(tmp_path / "does-not-exist")}, tmp_path)

    assert result.returncode == 0, result.stderr
    assert Path(result.stdout.strip()) == OWN_LIB


@all_scripts
def test_valid_plugin_root_is_still_honored(tmp_path: Path, script: Path) -> None:
    root = tmp_path / "project-toolkit"
    util = root / "lib" / "hook_utilities"
    util.mkdir(parents=True)
    (util / "__init__.py").write_text("", encoding="utf-8")
    (util / "path_safety.py").write_text(
        "def validate_path_no_traversal(path):\n    return path\n", encoding="utf-8"
    )

    result = _run(script, {"CLAUDE_PLUGIN_ROOT": str(root)}, tmp_path)

    assert result.returncode == 0, result.stderr
    assert Path(result.stdout.strip()) == root / "lib"


@all_scripts
def test_unvalidated_bootstrap_fails_under_foreign_root(tmp_path: Path, script: Path) -> None:
    """Negative control: the pre-fix bootstrap trusts the env root and dies."""
    source = script.read_text(encoding="utf-8")
    assert source.count(_GUARD) == 1, "DID-NOT-APPLY: guard line moved, update this control"
    legacy = tmp_path / f"legacy_{script.name}"
    legacy.write_text(source.replace(_GUARD, "if _PLUGIN_ROOT:"), encoding="utf-8")
    foreign = _foreign_root(tmp_path)

    result = _run(legacy, {"CLAUDE_PLUGIN_ROOT": str(foreign)}, tmp_path)

    assert result.returncode != 0
    assert "No module named 'hook_utilities'" in result.stderr
