"""Tests for load_skill_paths and its _resolve_skill_paths_lib helper.

The helper picks the first lib with paths.py: Copilot root, Claude root,
then the caller's own lib. load_skill_paths loads that file and puts the
calling script's directory first on sys.path (issue #7657).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from tests.test_bootstrap import _load_bootstrap


@pytest.fixture
def bootstrap_module():
    return _load_bootstrap()


def _make_lib(root: Path, marker: str) -> Path:
    """Create <root>/lib/paths.py that records which lib it came from."""
    lib = root / "lib"
    lib.mkdir(parents=True)
    (lib / "paths.py").write_text(f"ORIGIN = {marker!r}\n", encoding="utf-8")
    return lib


def test_resolve_skill_paths_lib_prefers_copilot_then_claude_then_own(
    bootstrap_module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    copilot = _make_lib(tmp_path / "copilot", "copilot")
    claude = _make_lib(tmp_path / "claude", "claude")
    own = _make_lib(tmp_path / "own", "own")
    monkeypatch.setenv("COPILOT_PLUGIN_ROOT", str(copilot.parent))
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(claude.parent))

    assert bootstrap_module._resolve_skill_paths_lib(own) == copilot.resolve()

    monkeypatch.delenv("COPILOT_PLUGIN_ROOT")
    assert bootstrap_module._resolve_skill_paths_lib(own) == claude.resolve()

    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT")
    assert bootstrap_module._resolve_skill_paths_lib(own) == own.resolve()


def test_resolve_skill_paths_lib_skips_root_without_paths_py(
    bootstrap_module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A harness root whose lib lacks paths.py falls through to the next one."""
    (tmp_path / "copilot" / "lib").mkdir(parents=True)
    own = _make_lib(tmp_path / "own", "own")
    monkeypatch.setenv("COPILOT_PLUGIN_ROOT", str(tmp_path / "copilot"))
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", "")

    assert bootstrap_module._resolve_skill_paths_lib(own) == own.resolve()


def test_resolve_skill_paths_lib_raises_listing_candidates(
    bootstrap_module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COPILOT_PLUGIN_ROOT", str(tmp_path / "copilot"))
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    own = tmp_path / "own" / "lib"

    with pytest.raises(RuntimeError, match="paths.py not found") as excinfo:
        bootstrap_module._resolve_skill_paths_lib(own)

    message = str(excinfo.value)
    assert str(tmp_path / "copilot" / "lib") in message
    assert str(own) in message


def test_load_skill_paths_loads_module_and_puts_script_dir_first(
    bootstrap_module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("COPILOT_PLUGIN_ROOT", raising=False)
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path / "claude"))
    _make_lib(tmp_path / "claude", "claude")
    own = _make_lib(tmp_path / "own", "own")
    script_dir = tmp_path / "skill" / "scripts"
    script_dir.mkdir(parents=True)
    script = script_dir / "tool.py"
    resolved_dir = str(script_dir.resolve())
    monkeypatch.setattr(sys, "path", [*sys.path, resolved_dir])

    paths = bootstrap_module.load_skill_paths(own, str(script))
    paths_again = bootstrap_module.load_skill_paths(own, str(script))

    assert paths.ORIGIN == "claude"
    assert paths_again.ORIGIN == "claude"
    assert sys.path[0] == resolved_dir
    assert sys.path.count(resolved_dir) == 1
