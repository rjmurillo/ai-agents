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
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from scripts.ci import verify_code_env as verify

# The canonical bootstrap module lives outside any importable package, so we
# load it directly via importlib.util to avoid coupling these tests to the
# sys.path manipulation that production hooks perform.
REPO_ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP_PATH = REPO_ROOT / ".claude" / "lib" / "bootstrap.py"


VM_BOOTSTRAP_PATH = REPO_ROOT / "scripts" / "bootstrap-vm.sh"
SETUP_ACTION_PATH = REPO_ROOT / ".github" / "actions" / "setup-code-env" / "action.yml"


WORKTRUNK_CONFIG_PATH = REPO_ROOT / ".config" / "wt.toml"
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"


def _load_bootstrap():
    spec = importlib.util.spec_from_file_location("bootstrap_under_test", BOOTSTRAP_PATH)
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


def test_vm_bootstrap_installs_lefthook_after_dependency_sync() -> None:
    text = VM_BOOTSTRAP_PATH.read_text(encoding="utf-8")

    sync = text.index("uv sync --frozen --extra dev")
    install = text.index("uv run --frozen lefthook install --reset-hooks-path")
    assert sync < install
    assert "git config core.hooksPath" not in text


def test_setup_action_preserves_input_and_installs_lefthook_after_dependencies() -> None:
    text = SETUP_ACTION_PATH.read_text(encoding="utf-8")

    validation = text.index("- name: Validate git hook inputs")
    dependencies = text.index("- name: Install Python dependencies")
    install = text.index("- name: Enable git hooks")
    assert "enable-git-hooks:" in text
    assert validation < dependencies < install
    assert "if: inputs.enable-git-hooks == 'true' && inputs.enable-python != 'true'" in text
    assert "enable-git-hooks=true requires enable-python=true" in text
    assert "exit 2" in text
    assert "if: inputs.enable-git-hooks == 'true' && inputs.enable-python == 'true'" in text
    assert "uv run --frozen --extra dev lefthook install --reset-hooks-path" in text
    assert "scripts/ci/verify_code_env.py" in text
    assert "git config core.hooksPath" not in text


def test_setup_action_verification_gates_lefthook_on_both_inputs(monkeypatch) -> None:
    """The lefthook check runs only when git hooks and Python are both enabled.

    This replaces three assertions against the PowerShell that used to live in
    the action's verify step (extracted under ADR-006, issue #3532). The
    contract is the same; it is now measured by running the code rather than by
    grepping the shell that used to implement it.
    """
    calls: list[int] = []

    def _verify_lefthook() -> int:
        calls.append(1)
        return 0

    monkeypatch.setattr(verify, "verify_lefthook", _verify_lefthook)
    monkeypatch.setattr(verify.shutil, "which", lambda _name: None)
    monkeypatch.setenv("ENABLE_PESTER", "false")
    for hooks, python, expected in [
        ("true", "true", 1),
        ("true", "false", 0),
        ("false", "true", 0),
    ]:
        calls.clear()
        monkeypatch.setenv("ENABLE_GIT_HOOKS", hooks)
        monkeypatch.setenv("ENABLE_PYTHON", python)
        verify.main([])
        assert len(calls) == expected, (hooks, python)


def test_setup_action_verification_propagates_lefthook_exit_code(monkeypatch) -> None:
    """A failed lefthook check fails the step with its own exit code."""
    monkeypatch.setattr(
        verify, "_run", lambda _argv: subprocess.CompletedProcess(args=[], returncode=5, stdout="")
    )
    monkeypatch.setattr(verify.shutil, "which", lambda _name: None)
    monkeypatch.setenv("ENABLE_GIT_HOOKS", "true")
    monkeypatch.setenv("ENABLE_PYTHON", "true")
    monkeypatch.setenv("ENABLE_PESTER", "false")

    assert verify.verify_lefthook() == 5
    assert verify.main([]) == 5, "main must propagate the failing exit code, not swallow it"


def test_workflows_choose_hook_installation_explicitly() -> None:
    missing_input: list[str] = []

    for workflow_path in sorted(WORKFLOW_DIR.glob("*.yml")):
        workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
        for job in workflow.get("jobs", {}).values():
            for step in job.get("steps", []):
                if step.get("uses") != "./.github/actions/setup-code-env":
                    continue
                if "enable-git-hooks" not in step.get("with", {}):
                    missing_input.append(workflow_path.name)

    assert missing_input == []


def test_worktrunk_post_create_installs_lefthook() -> None:
    text = WORKTRUNK_CONFIG_PATH.read_text(encoding="utf-8")

    assert (
        'configure-hooks = "uv run --frozen --extra dev lefthook install '
        '--reset-hooks-path && uv run --frozen --extra dev lefthook check-install"' in text
    )
    assert "core.hooksPath" not in text
