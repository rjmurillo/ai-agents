"""The guard harness must not execute a dispatcher from outside the install root.

`install_root` arrives from the command line, so the resolved dispatcher path is
a boundary. The interpreter is invoked as an argument list with no shell, so a
shell metacharacter in the path cannot start a second command. What containment
prevents is different and real: a symlink under `hooks` pointing the interpreter
at a script outside the install tree. Refs #4672.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "ci"
    / "test_installed_plugin_hooks.py"
)


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("installed_plugin_hooks", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_MODULE = _load()
_find_dispatcher = _MODULE._find_dispatcher


def _make_dispatcher(root: Path, event: str) -> Path:
    target = root / "hooks" / event / "_dispatch.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("print('hook')\n", encoding="utf-8")
    return target


class TestDispatcherContainment:
    def test_finds_a_dispatcher_inside_the_root(self, tmp_path: Path) -> None:
        root = tmp_path / "install"
        expected = _make_dispatcher(root, "PreToolUse")
        assert _find_dispatcher(root, "PreToolUse") == expected.resolve()

    def test_missing_dispatcher_returns_none(self, tmp_path: Path) -> None:
        root = tmp_path / "install"
        root.mkdir()
        assert _find_dispatcher(root, "PreToolUse") is None

    def test_lowercase_variant_is_still_found(self, tmp_path: Path) -> None:
        root = tmp_path / "install"
        expected = _make_dispatcher(root, "preToolUse")
        assert _find_dispatcher(root, "PreToolUse") == expected.resolve()

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="symlink creation needs elevation on Windows",
    )
    def test_symlink_escaping_the_root_is_refused(self, tmp_path: Path) -> None:
        """The negative control: containment must reject, not silently run."""
        root = tmp_path / "install"
        (root / "hooks" / "PreToolUse").mkdir(parents=True)
        outside = tmp_path / "outside" / "_dispatch.py"
        outside.parent.mkdir(parents=True)
        outside.write_text("print('not ours')\n", encoding="utf-8")
        (root / "hooks" / "PreToolUse" / "_dispatch.py").symlink_to(outside)

        with pytest.raises(ValueError, match="resolves outside"):
            _find_dispatcher(root, "PreToolUse")
