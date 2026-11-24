#!/usr/bin/env python3
"""Unit tests for the memory recall shim (issue #7493, ADR-109 amendment 2026-11-20).

The shim finds ``memory_enhancement`` at ``<plugin root>/lib`` and re-executes
under the project ``.venv`` only on a direct run. Inside the grouped dispatcher
(``claude_hook_dispatch`` in ``sys.modules``) it never re-executes, whatever
plugin-root variable the host exports.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = REPO_ROOT / "src" / "claude"
SHIM_PATH = PLUGIN_ROOT / "hooks" / "UserPromptSubmit" / "invoke_memory_recall.py"


@pytest.fixture(autouse=True)
def _restore_sys_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """main() prepends the plugin lib dir to sys.path; keep that out of other tests."""
    monkeypatch.setattr(sys, "path", list(sys.path))


@pytest.fixture(autouse=True)
def _direct_run_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Other tests import the dispatcher. A direct run has it absent and no opt-out set."""
    monkeypatch.delitem(sys.modules, "claude_hook_dispatch", raising=False)
    monkeypatch.delenv("AI_AGENTS_MEMORY_RECALL", raising=False)


def _run_under_dispatcher(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "claude_hook_dispatch", ModuleType("claude_hook_dispatch"))


@pytest.fixture
def shim() -> ModuleType:
    spec = importlib.util.spec_from_file_location("invoke_memory_recall_under_test", SHIM_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def fake_hook(monkeypatch: pytest.MonkeyPatch, shim: ModuleType) -> MagicMock:
    """Replace the recall hook module so main() runs no search."""
    hook = MagicMock()
    hook.main.return_value = 0
    real_import = shim.importlib.import_module
    monkeypatch.setattr(
        shim.importlib,
        "import_module",
        lambda name: hook if name.startswith("memory_enhancement.hooks.") else real_import(name),
    )
    return hook


def test_package_path_is_the_lib_dir_of_the_plugin_root(shim: ModuleType) -> None:
    assert shim._lib_dir() == PLUGIN_ROOT / "lib"
    assert (shim._lib_dir() / "memory_enhancement" / "__init__.py").is_file()


def test_package_path_resolves_the_same_for_the_install_copy() -> None:
    install_shim = REPO_ROOT / ".claude" / "hooks" / "UserPromptSubmit" / "invoke_memory_recall.py"
    spec = importlib.util.spec_from_file_location("install_shim_under_test", install_shim)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    lib_dir = module._lib_dir()

    assert lib_dir == REPO_ROOT / ".claude" / "lib"
    assert (lib_dir / "memory_enhancement" / "interpreter.py").is_file()


def test_reexec_is_not_attempted_under_the_dispatcher(
    monkeypatch: pytest.MonkeyPatch, shim: ModuleType, fake_hook: MagicMock
) -> None:
    import memory_enhancement.interpreter as interpreter

    reexec = MagicMock()
    monkeypatch.setattr(interpreter, "reexec_under_project_venv", reexec)
    _run_under_dispatcher(monkeypatch)

    assert shim.main() == 0

    reexec.assert_not_called()
    fake_hook.main.assert_called_once()


def test_reexec_is_attempted_with_the_project_dir_on_a_direct_run(
    monkeypatch: pytest.MonkeyPatch, shim: ModuleType, fake_hook: MagicMock, tmp_path: Path
) -> None:
    import memory_enhancement.interpreter as interpreter

    reexec = MagicMock()
    monkeypatch.setattr(interpreter, "reexec_under_project_venv", reexec)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

    assert shim.main() == 0

    reexec.assert_called_once_with(tmp_path)


@pytest.mark.parametrize("root_variable", ["CLAUDE_PLUGIN_ROOT", "COPILOT_PLUGIN_ROOT"])
def test_a_direct_run_still_reexecs_when_the_host_exports_a_plugin_root(
    monkeypatch: pytest.MonkeyPatch,
    shim: ModuleType,
    fake_hook: MagicMock,
    tmp_path: Path,
    root_variable: str,
) -> None:
    import memory_enhancement.interpreter as interpreter

    reexec = MagicMock()
    monkeypatch.setattr(interpreter, "reexec_under_project_venv", reexec)
    monkeypatch.setenv(root_variable, str(PLUGIN_ROOT))
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

    shim.main()

    reexec.assert_called_once_with(tmp_path)


def test_project_dir_falls_back_to_the_checkout_root_above_the_install_copy(
    monkeypatch: pytest.MonkeyPatch, shim: ModuleType
) -> None:
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)

    assert shim._project_dir() == SHIM_PATH.resolve().parents[3]


def _project_with_a_venv(tmp_path: Path) -> Path:
    interpreter = tmp_path / ".venv" / "bin" / "python3"
    interpreter.parent.mkdir(parents=True)
    interpreter.write_text("", encoding="utf-8")
    return tmp_path


def test_execv_is_called_on_a_direct_run_when_the_dependency_is_missing(
    monkeypatch: pytest.MonkeyPatch, shim: ModuleType, fake_hook: MagicMock, tmp_path: Path
) -> None:
    import memory_enhancement.interpreter as interpreter

    execv = MagicMock()
    monkeypatch.setattr(os, "execv", execv)
    monkeypatch.setattr(interpreter, "dependency_available", lambda *_a: False)
    monkeypatch.setattr(interpreter, "running_under_venv", lambda _d: False)
    monkeypatch.delenv(interpreter.REENTRY_GUARD, raising=False)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(_project_with_a_venv(tmp_path)))

    shim.main()

    execv.assert_called_once()
    assert execv.call_args.args[0] == str(tmp_path / ".venv" / "bin" / "python3")


def test_execv_is_not_called_under_the_dispatcher_even_with_a_venv_and_a_missing_dependency(
    monkeypatch: pytest.MonkeyPatch, shim: ModuleType, fake_hook: MagicMock, tmp_path: Path
) -> None:
    """Negative control: the same state as above, inside the dispatcher."""
    import memory_enhancement.interpreter as interpreter

    execv = MagicMock()
    monkeypatch.setattr(os, "execv", execv)
    monkeypatch.setattr(interpreter, "dependency_available", lambda *_a: False)
    monkeypatch.setattr(interpreter, "running_under_venv", lambda _d: False)
    monkeypatch.delenv(interpreter.REENTRY_GUARD, raising=False)
    _run_under_dispatcher(monkeypatch)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(_project_with_a_venv(tmp_path)))

    shim.main()

    execv.assert_not_called()


def test_copilot_transformed_flag_selects_the_transformed_hook(
    monkeypatch: pytest.MonkeyPatch, shim: ModuleType
) -> None:
    requested: list[str] = []
    hook = MagicMock()
    hook.main.return_value = 0
    real_import = shim.importlib.import_module

    def record(name: str) -> object:
        if name.startswith("memory_enhancement.hooks."):
            requested.append(name)
            return hook
        return real_import(name)

    monkeypatch.setattr(shim.importlib, "import_module", record)
    _run_under_dispatcher(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["invoke_memory_recall.py", "--copilot-transformed"])

    shim.main()

    assert requested == ["memory_enhancement.hooks.user_prompt_transformed_memory"]


def test_missing_package_prints_one_stderr_line_naming_the_path_and_exits_zero(
    monkeypatch: pytest.MonkeyPatch,
    shim: ModuleType,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(shim, "_lib_dir", lambda: tmp_path / "lib")
    monkeypatch.setitem(sys.modules, "memory_enhancement", None)
    monkeypatch.setitem(sys.modules, "memory_enhancement.interpreter", None)

    code = shim.main()

    err_lines = [line for line in capsys.readouterr().err.splitlines() if line.strip()]
    assert code == 0
    assert len(err_lines) == 1
    assert str(tmp_path / "lib") in err_lines[0]
    assert "memory_enhancement" in err_lines[0]


@pytest.mark.parametrize("value", ["0", "off", "false", "OFF", "False", " 0 "])
def test_opt_out_exits_zero_before_importing_anything(
    monkeypatch: pytest.MonkeyPatch,
    shim: ModuleType,
    capsys: pytest.CaptureFixture[str],
    value: str,
) -> None:
    monkeypatch.setenv("AI_AGENTS_MEMORY_RECALL", value)
    importer = MagicMock()
    monkeypatch.setattr(shim.importlib, "import_module", importer)
    # Any import of the package would now fail loudly, so none may happen.
    monkeypatch.setitem(sys.modules, "memory_enhancement", None)
    monkeypatch.setattr(sys, "path", [p for p in sys.path if p != str(PLUGIN_ROOT / "lib")])

    code = shim.main()

    captured = capsys.readouterr()
    assert code == 0
    assert (captured.out, captured.err) == ("", "")
    importer.assert_not_called()
    assert str(PLUGIN_ROOT / "lib") not in sys.path


@pytest.mark.parametrize("value", ["", "1", "on", "true", "yes"])
def test_other_values_do_not_opt_out(
    monkeypatch: pytest.MonkeyPatch, shim: ModuleType, fake_hook: MagicMock, value: str
) -> None:
    """Negative control: only 0, off, and false disable recall."""
    _run_under_dispatcher(monkeypatch)
    monkeypatch.setenv("AI_AGENTS_MEMORY_RECALL", value)

    shim.main()

    fake_hook.main.assert_called_once()
