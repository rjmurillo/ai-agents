"""Tests for the canonical bootstrap helper at .claude/lib/bootstrap.py.

Covers:
- ``resolve_plugin_lib_dir`` env-var path
- ``resolve_plugin_lib_dir`` manifest walk-up success
- ``resolve_plugin_lib_dir`` walk-up exhausted (returns None)
- ``resolve_plugin_lib_dir`` with ``hook_file=None`` (stack-inspection path)
- ``setup_hook_lib_path`` adds lib to ``sys.path``
- ``setup_hook_lib_path`` exits with ``fail_exit_code`` when lib missing
- ``setup_hook_lib_path`` is idempotent (second call does not double-insert)
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest

# The canonical bootstrap module lives outside any importable package, so we
# load it directly via importlib.util to avoid coupling these tests to the
# sys.path manipulation that production hooks perform.
REPO_ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP_PATH = REPO_ROOT / ".claude" / "lib" / "bootstrap.py"


def _load_bootstrap():
    spec = importlib.util.spec_from_file_location(
        "bootstrap_under_test", BOOTSTRAP_PATH
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def bootstrap_module():
    return _load_bootstrap()


@pytest.fixture
def fake_plugin_tree(tmp_path: Path) -> Path:
    """Create a minimal plugin layout: <root>/.claude-plugin/plugin.json + lib/."""
    (tmp_path / ".claude-plugin").mkdir()
    (tmp_path / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
    (tmp_path / "lib").mkdir()
    (tmp_path / "hooks").mkdir()
    (tmp_path / "hooks" / "fake_hook.py").write_text("# fake", encoding="utf-8")
    return tmp_path


def test_resolve_uses_claude_plugin_root_env_var(
    bootstrap_module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plugin_root = tmp_path / "plugin"
    plugin_root.mkdir()
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(plugin_root))

    result = bootstrap_module.resolve_plugin_lib_dir(hook_file=str(tmp_path / "x.py"))

    assert result == str(plugin_root.resolve() / "lib")


def test_resolve_walks_up_to_plugin_marker(
    bootstrap_module, fake_plugin_tree: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    hook_file = fake_plugin_tree / "hooks" / "fake_hook.py"

    result = bootstrap_module.resolve_plugin_lib_dir(hook_file=str(hook_file))

    assert result == str(fake_plugin_tree / "lib")


def test_resolve_returns_none_when_walk_up_exhausted(
    bootstrap_module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    # tmp_path has no .claude-plugin/plugin.json anywhere up the tree, so the
    # walk should reach the filesystem root and return None.
    isolated = tmp_path / "no_marker_here"
    isolated.mkdir()
    hook_file = isolated / "hook.py"
    hook_file.write_text("# fake", encoding="utf-8")

    # Walk up will eventually hit /, which obviously has no plugin marker.
    # We cannot guarantee the entire ancestor chain is marker-free on a real
    # checkout, so this test is only safe if no ancestor has the marker.
    cur = isolated
    while cur.parent != cur:
        if (cur / ".claude-plugin" / "plugin.json").is_file():
            pytest.skip(
                "ancestor of pytest tmp_path has a plugin marker; "
                "cannot test walk-up exhaustion in this environment"
            )
        cur = cur.parent

    result = bootstrap_module.resolve_plugin_lib_dir(hook_file=str(hook_file))

    assert result is None


def test_resolve_uses_caller_file_when_hook_file_none(
    bootstrap_module, fake_plugin_tree: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When hook_file is None the resolver falls back to inspect.currentframe."""
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)

    # Write a tiny script that imports the bootstrap module and calls
    # resolve_plugin_lib_dir() with no arguments, then prints the result.
    # Running it as a subprocess gives the inspect.currentframe() path a real
    # __file__ to walk up from.
    hook_dir = fake_plugin_tree / "hooks"
    runner = hook_dir / "runner.py"
    runner.write_text(
        f"""import sys, importlib.util
spec = importlib.util.spec_from_file_location("bs", r"{BOOTSTRAP_PATH}")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
print(m.resolve_plugin_lib_dir())
""",
        encoding="utf-8",
    )

    import subprocess

    proc = subprocess.run(
        [sys.executable, str(runner)],
        check=True,
        capture_output=True,
        text=True,
        env={k: v for k, v in os.environ.items() if k != "CLAUDE_PLUGIN_ROOT"},
    )

    assert proc.stdout.strip() == str(fake_plugin_tree / "lib")


def test_setup_hook_lib_path_adds_lib_to_sys_path(
    bootstrap_module, fake_plugin_tree: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    lib_dir = str(fake_plugin_tree / "lib")
    # Ensure we start clean in case a prior test added the path.
    while lib_dir in sys.path:
        sys.path.remove(lib_dir)

    hook_file = fake_plugin_tree / "hooks" / "fake_hook.py"
    result = bootstrap_module.setup_hook_lib_path(str(hook_file), fail_exit_code=2)

    assert result == lib_dir
    assert sys.path[0] == lib_dir

    # cleanup so we do not leak state to other tests
    while lib_dir in sys.path:
        sys.path.remove(lib_dir)


def test_setup_hook_lib_path_exits_when_lib_missing(
    bootstrap_module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the resolver returns a path that does not exist, exit with the
    requested code rather than continuing into an ImportError."""
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path / "nonexistent_plugin"))

    hook_file = tmp_path / "fake_hook.py"
    hook_file.write_text("# fake", encoding="utf-8")

    with pytest.raises(SystemExit) as excinfo:
        bootstrap_module.setup_hook_lib_path(str(hook_file), fail_exit_code=2)

    assert excinfo.value.code == 2


def test_setup_hook_lib_path_is_idempotent(
    bootstrap_module, fake_plugin_tree: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Calling setup_hook_lib_path twice must not duplicate the entry in sys.path."""
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    lib_dir = str(fake_plugin_tree / "lib")
    while lib_dir in sys.path:
        sys.path.remove(lib_dir)

    hook_file = fake_plugin_tree / "hooks" / "fake_hook.py"
    bootstrap_module.setup_hook_lib_path(str(hook_file), fail_exit_code=2)
    bootstrap_module.setup_hook_lib_path(str(hook_file), fail_exit_code=2)

    occurrences = sum(1 for entry in sys.path if entry == lib_dir)
    assert occurrences == 1

    while lib_dir in sys.path:
        sys.path.remove(lib_dir)
