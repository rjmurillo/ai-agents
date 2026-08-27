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
import re
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
        text=True, encoding="utf-8",
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


def test_vm_bootstrap_has_no_bare_apt_get_or_unguarded_dpkg_i() -> None:
    """Pin Issue #5169's fix: every apt-get/dpkg-i call site routes through
    the quiet wrappers, so a future edit cannot silently reintroduce a bare
    call that dumps unpack-log noise into every SessionStart session."""
    text = VM_BOOTSTRAP_PATH.read_text(encoding="utf-8")

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if "apt-get" in stripped:
            assert stripped.startswith(("quiet_apt_get", "quiet_run sudo apt-get")), (
                f"apt-get call bypasses the quiet wrapper: {stripped!r}"
            )
        if "dpkg -i" in stripped:
            assert stripped.startswith("quiet_run sudo dpkg -i"), (
                f"dpkg -i call bypasses the quiet wrapper: {stripped!r}"
            )


class TestQuietAptGet:
    """Exercise the real quiet_run/quiet_apt_get bash functions (Issue #5169)
    against fake sudo/apt-get/dpkg executables. Extracts the function bodies
    verbatim from bootstrap-vm.sh rather than reimplementing them, so a
    behavioral regression in the shipped script fails these tests instead of
    a copy that has silently drifted from it (see .claude/rules/
    canonical-source-mirror.md on self-referential test mirrors).
    """

    @staticmethod
    def _extract_helpers() -> str:
        text = VM_BOOTSTRAP_PATH.read_text(encoding="utf-8")
        markers = [
            (r'^APT_LOG="\$\(mktemp\)"$', r"^trap cleanup_tmp EXIT$"),
            (r"^quiet_run\(\) \{$", r"^\}$"),
            (r"^quiet_apt_get\(\) \{$", r"^\}$"),
        ]
        lines = text.splitlines()
        blocks: list[str] = []
        for start_pat, end_pat in markers:
            start_re = re.compile(start_pat)
            end_re = re.compile(end_pat)
            start_idx = next(i for i, line in enumerate(lines) if start_re.match(line))
            end_idx = next(
                i for i in range(start_idx, len(lines)) if end_re.match(lines[i])
            )
            block = "\n".join(lines[start_idx : end_idx + 1])
            assert block, f"empty extraction for {start_pat!r}"
            blocks.append(block)
        return "\n\n".join(blocks)

    @staticmethod
    def _fake_bin(tmp_path: Path, name: str, body: str) -> None:
        script = tmp_path / name
        script.write_text(f"#!/usr/bin/env bash\n{body}\n", encoding="utf-8")
        script.chmod(0o755)

    def _run(
        self, tmp_path: Path, apt_get_body: str, bash_call: str
    ) -> subprocess.CompletedProcess[str]:
        self._fake_bin(tmp_path, "sudo", 'exec "$@"')
        self._fake_bin(tmp_path, "apt-get", apt_get_body)
        helpers = self._extract_helpers()
        full_script = f"set -euo pipefail\n{helpers}\n{bash_call}\n"
        env = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"}
        return subprocess.run(
            ["bash", "-c", full_script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            env=env,
            check=False,
        )

    def test_quiet_on_success(self, tmp_path: Path) -> None:
        result = self._run(
            tmp_path,
            apt_get_body='echo "Unpacking somepkg (noise)"\nexit 0',
            bash_call='quiet_apt_get install -y -qq somepkg\necho MARKER_OK',
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "MARKER_OK"
        assert result.stderr == ""

    def test_warnings_surface_even_on_zero_exit(self, tmp_path: Path) -> None:
        result = self._run(
            tmp_path,
            apt_get_body=(
                'echo "Hit:1 http://archive.ubuntu.com noble InRelease"\n'
                'echo "W: GPG error: https://example.test NO_PUBKEY ABC123"\n'
                "exit 0"
            ),
            bash_call='quiet_apt_get update -qq\necho MARKER_OK',
        )
        assert result.returncode == 0, result.stderr
        assert "MARKER_OK" in result.stdout
        assert "NO_PUBKEY ABC123" in result.stderr

    def test_failure_dumps_log_and_aborts(self, tmp_path: Path) -> None:
        result = self._run(
            tmp_path,
            apt_get_body=(
                'echo "Unpacking failpkg (noise)"\n'
                'echo "E: some apt error" >&2\n'
                "exit 100"
            ),
            bash_call='quiet_apt_get install -y -qq failpkg\necho SHOULD_NOT_PRINT',
        )
        assert result.returncode != 0
        assert "SHOULD_NOT_PRINT" not in result.stdout
        assert "E: some apt error" in result.stderr

    def test_apt_log_removed_on_exit(self, tmp_path: Path) -> None:
        result = self._run(
            tmp_path,
            apt_get_body="exit 0",
            bash_call='quiet_apt_get update -qq\necho "$APT_LOG"',
        )
        assert result.returncode == 0, result.stderr
        log_path = Path(result.stdout.strip())
        assert not log_path.exists(), "APT_LOG was not cleaned up by the EXIT trap"


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


def test_worktrunk_post_create_installs_worktree_safe_lefthook_shims() -> None:
    """A new worktree must not install lefthook's env-probed shim (issue #4789).

    Git shares one hooks directory across every worktree, so a bare
    ``lefthook install`` from a new worktree points the shared hook at that
    worktree's own ``.venv`` and breaks every other checkout.
    """
    text = WORKTRUNK_CONFIG_PATH.read_text(encoding="utf-8")
    installer = "python scripts/maintenance/install_lefthook_worktree_safe.py"

    assert (
        f'configure-hooks = "uv run --frozen --extra dev {installer} '
        f'&& uv run --frozen --extra dev {installer} --check"' in text
    )
    assert "lefthook install --reset-hooks-path" not in text
    assert "core.hooksPath" not in text
