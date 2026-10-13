"""Tests for the shared lefthook resolver and every module that drives the binary (Issue #5568)."""

from __future__ import annotations

import ast
import importlib.util
import os
import sysconfig
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from tests.support.lefthook_binary import resolve_lefthook

pytestmark = pytest.mark.windows_path

TESTS_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_MODULE = TESTS_ROOT / "ci" / "test_lefthook_prepush_fast_fail_runtime.py"
RUNNER_MODULE = TESTS_ROOT / "test_lefthook_runner.py"
INTEGRATION_MODULE = TESTS_ROOT / "test_lefthook_integration.py"
CONSUMERS = (RUNTIME_MODULE, RUNNER_MODULE, INTEGRATION_MODULE)
RESOLVER_MODULE = "tests.support.lefthook_binary"


def _stub_lefthook(directory: Path) -> Path:
    """Create an executable file named like lefthook inside ``directory``."""
    directory.mkdir(parents=True, exist_ok=True)
    stub = directory / ("lefthook.bat" if os.name == "nt" else "lefthook")
    stub.write_text("", encoding="utf-8")
    stub.chmod(0o755)
    return stub


def _scripts_dir_is(monkeypatch: pytest.MonkeyPatch, directory: Path) -> None:
    """Point the interpreter's ``scripts`` path at ``directory``, leave other paths alone."""
    real_get_path = sysconfig.get_path

    def fake_get_path(name: str, *args: Any, **kwargs: Any) -> str | None:
        if name == "scripts":
            return str(directory)
        return real_get_path(name, *args, **kwargs)

    monkeypatch.setattr(sysconfig, "get_path", fake_get_path)


def _load(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"_probe_{path.stem}", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_resolve_lefthook_prefers_the_interpreter_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Positive and negative control: the scripts directory beats PATH.

    Reverting the helper to a bare ``shutil.which("lefthook")`` returns the PATH
    copy here and fails this assertion, which is the whole point: an IDE that
    runs ``.venv/bin/pytest`` directly leaves PATH pointing at whatever global
    lefthook the developer installed, and the behavioral assertions in the
    lefthook test modules would then describe a release nobody pinned.
    """
    pinned = _stub_lefthook(tmp_path / "env")
    monkeypatch.setenv("PATH", str(_stub_lefthook(tmp_path / "elsewhere").parent))

    resolved = resolve_lefthook(str(pinned.parent))

    # samefile, not string equality: Windows resolution applies PATHEXT and can
    # return an extension whose case does not match the file on disk.
    assert resolved is not None
    assert Path(resolved).samefile(pinned)


def test_resolve_lefthook_defaults_to_the_interpreter_scripts_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Positive: with no argument, the running interpreter's scripts path is used."""
    pinned = _stub_lefthook(tmp_path / "env")
    monkeypatch.setenv("PATH", str(_stub_lefthook(tmp_path / "elsewhere").parent))
    _scripts_dir_is(monkeypatch, pinned.parent)

    resolved = resolve_lefthook()

    assert resolved is not None
    assert Path(resolved).samefile(pinned)


def test_resolve_lefthook_falls_back_to_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Negative: an environment without the dev extra still finds a lefthook."""
    on_path = _stub_lefthook(tmp_path / "elsewhere")
    monkeypatch.setenv("PATH", str(on_path.parent))

    resolved = resolve_lefthook(str(tmp_path / "empty"))

    assert resolved is not None
    assert Path(resolved).samefile(on_path)


def test_resolve_lefthook_returns_none_when_no_binary_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Edge: neither source has one, so callers see None and fail loudly."""
    monkeypatch.setenv("PATH", str(tmp_path / "nothing"))

    assert resolve_lefthook(str(tmp_path / "empty")) is None


@pytest.mark.parametrize("module", CONSUMERS, ids=lambda path: path.name)
def test_consumer_module_has_no_bare_path_lookup(module: Path) -> None:
    """Negative control: no lefthook test module calls ``shutil.which("lefthook")``."""
    tree = ast.parse(module.read_text(encoding="utf-8"))
    bare_lookups = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "which"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "lefthook"
    ]

    assert bare_lookups == []


@pytest.mark.parametrize("module", CONSUMERS, ids=lambda path: path.name)
def test_consumer_module_imports_the_shared_resolver(module: Path) -> None:
    """Positive: each module imports the one resolver, so there are no private copies."""
    tree = ast.parse(module.read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == RESOLVER_MODULE
        for alias in node.names
    }
    defined = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and "lefthook" in node.name and "resolve" in node.name
    }

    assert imported == {"resolve_lefthook"}
    assert defined == set()


@pytest.mark.parametrize(
    ("module", "attribute"),
    [(RUNTIME_MODULE, "_LEFTHOOK_BIN"), (RUNNER_MODULE, "_LEFTHOOK")],
    ids=lambda value: value.name if isinstance(value, Path) else value,
)
def test_consumer_binary_is_the_pinned_one_when_an_impostor_leads_path(
    module: Path, attribute: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Behavior: loading the module with an impostor first on PATH still binds the pinned binary."""
    pinned = _stub_lefthook(tmp_path / "env")
    monkeypatch.setenv("PATH", str(_stub_lefthook(tmp_path / "impostor").parent))
    _scripts_dir_is(monkeypatch, pinned.parent)

    bound = getattr(_load(module), attribute)

    assert bound is not None
    assert Path(bound).samefile(pinned)


def test_host_without_any_lefthook_binds_none_in_the_runtime_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Edge: with no lefthook anywhere the constant is None, so its assert fails loudly."""
    monkeypatch.setenv("PATH", str(tmp_path / "nothing"))
    _scripts_dir_is(monkeypatch, tmp_path / "empty")

    assert _load(RUNTIME_MODULE)._LEFTHOOK_BIN is None
