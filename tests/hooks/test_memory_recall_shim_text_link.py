#!/usr/bin/env python3
"""The recall shim follows a .claude/lib link Git wrote as text (issue #7493).

With ``core.symlinks=false`` Git checks a symlink out as a file holding its
target. The shim follows that text only when it is the exact ADR-119 target.
"""

from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SHIM = REPO_ROOT / "src" / "claude" / "hooks" / "UserPromptSubmit" / "invoke_memory_recall.py"
LINK_TEXT = "../../src/claude/lib/memory_enhancement"


def _checkout(tmp_path: Path, link_text: str | None) -> ModuleType:
    hooks = tmp_path / ".claude" / "hooks" / "UserPromptSubmit"
    hooks.mkdir(parents=True)
    shutil.copy(SHIM, hooks / SHIM.name)
    package = tmp_path / "src" / "claude" / "lib" / "memory_enhancement"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    lib = tmp_path / ".claude" / "lib"
    lib.mkdir()
    if link_text is not None:
        (lib / "memory_enhancement").write_text(link_text, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("shim_text_link_under_test", hooks / SHIM.name)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_text_link_resolves_to_the_shipped_lib_tree(tmp_path: Path) -> None:
    shim = _checkout(tmp_path, LINK_TEXT)

    assert shim._lib_dir() == (tmp_path / "src" / "claude" / "lib").resolve()


@pytest.mark.parametrize(
    "link_text",
    [
        "../../../outside/memory_enhancement",
        "../../src/claude/lib/absent",
        "/etc/memory_enhancement",
        "../../src/claude/lib/memory_enhancement/../memory_enhancement",
        " ../../src/claude/lib/memory_enhancement",
        "../../src/claude/lib/memory_enhancement\n",
    ],
    ids=["leaves-checkout", "other-package", "absolute", "not-exact", "padded", "newline"],
)
def test_any_other_link_text_is_ignored(tmp_path: Path, link_text: str) -> None:
    shim = _checkout(tmp_path, link_text)

    assert shim._lib_dir() == (tmp_path / ".claude" / "lib").resolve()


def test_control_without_a_link_file_the_lib_dir_is_unchanged(tmp_path: Path) -> None:
    shim = _checkout(tmp_path, None)

    assert shim._lib_dir() == (tmp_path / ".claude" / "lib").resolve()
