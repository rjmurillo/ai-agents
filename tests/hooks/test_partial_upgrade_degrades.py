"""A partial upgrade must degrade, not deny, and the guard must not pass empty.

Two defects found by review on the #4672 branch, both of which recreate the
customer-wide denial the fail-open path exists to prevent.

`SystemExit` is a `BaseException`, so `except Exception` misses it. Every
`_bootstrap.py` shipped before that change calls `sys.exit(2)` for a missing
plugin root or lib directory, so a partial upgrade pairing the new dispatcher
with an old bootstrap exited 2 and denied every PreToolUse call. That arrived
through the one exception type the handler did not cover.

The guard that is supposed to catch this recorded `SKIP` when a dispatcher was
absent, so deleting both dispatchers left `failures == 0` and the workflow
reported success after executing nothing.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]


_SHIPPED_DISPATCHER = (
    _REPO_ROOT / "src" / "copilot-cli" / "hooks" / "PreToolUse" / "_dispatch.py"
)


def _write_dispatcher(event_dir: Path) -> Path:
    """Copy the shipped dispatcher into *event_dir*.

    The shipped artifact is used rather than a rebuilt one so the test
    exercises exactly what a consumer installs. A test that regenerates its
    own subject can pass while the shipped file differs.
    """
    event_dir.mkdir(parents=True, exist_ok=True)
    target = event_dir / "_dispatch.py"
    target.write_text(
        _SHIPPED_DISPATCHER.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (event_dir / "_manifest.json").write_text(
        '{"event": "PreToolUse", "shims": []}', encoding="utf-8"
    )
    return target


class TestBootstrapSystemExitDegrades:
    """An old bootstrap that calls sys.exit(2) must not deny the tool call."""

    def test_system_exit_from_bootstrap_degrades_to_allow(
        self, tmp_path: Path
    ) -> None:
        event_dir = tmp_path / "hooks" / "PreToolUse"
        dispatcher = _write_dispatcher(event_dir)

        # The pre-fix shape: a no-argument ensure_plugin_paths that exits 2.
        # Not a TypeError, which is what the earlier fixture raised and why
        # this path was never exercised.
        (event_dir / "_bootstrap.py").write_text(
            "import sys\n"
            "\n"
            "\n"
            "def ensure_plugin_paths() -> None:\n"
            "    sys.exit(2)\n",
            encoding="utf-8",
        )

        proc = subprocess.run(
            [sys.executable, "-u", str(dispatcher)],
            input=b'{"tool_name": "Bash", "tool_input": {"command": "echo hi"}}',
            capture_output=True,
            cwd=str(tmp_path),
            timeout=30,
        )

        assert proc.returncode == 0, (
            "an old bootstrap calling sys.exit(2) denied the tool call; this is "
            f"the customer-wide denial in #4672. stderr:\n"
            f"{proc.stderr.decode('utf-8', 'replace')}"
        )
        assert b"WARNING" in proc.stderr, (
            "degrading must tell the user the hooks are disabled"
        )

    def test_ordinary_bootstrap_still_runs_the_dispatcher(
        self, tmp_path: Path
    ) -> None:
        """The inverse control: degrading must not become the only path."""
        event_dir = tmp_path / "hooks" / "PreToolUse"
        dispatcher = _write_dispatcher(event_dir)
        (event_dir / "_bootstrap.py").write_text(
            "def ensure_plugin_paths() -> None:\n    return None\n",
            encoding="utf-8",
        )

        proc = subprocess.run(
            [sys.executable, "-u", str(dispatcher)],
            input=b'{"tool_name": "Bash", "tool_input": {"command": "echo hi"}}',
            capture_output=True,
            cwd=str(tmp_path),
            timeout=30,
        )

        # A healthy bootstrap must get past the bootstrap boundary. This
        # fixture has no lib directory, so the dispatcher then degrades on the
        # hook_dispatch import instead, which is the correct next failure. The
        # assertion is that the reason changed: a SystemExit from bootstrap no
        # longer decides the outcome.
        stderr = proc.stderr.decode("utf-8", "replace")
        assert proc.returncode == 0, stderr
        assert "SystemExit" not in stderr, (
            "a healthy bootstrap must not report a SystemExit failure. "
            f"stderr:\n{stderr}"
        )


class TestMissingDispatcherIsAFailure:
    """The guard must fail, not skip, when an expected dispatcher is absent."""

    def test_absent_dispatcher_fails_the_guard(self, tmp_path: Path) -> None:
        """A plugin whose dispatchers are missing must fail, not report empty.

        The guard materializes its own copy from --plugin-source, so the
        subject has to be a source tree with the dispatchers removed rather
        than an empty install root.
        """
        source = tmp_path / "plugin"
        shutil.copytree(_REPO_ROOT / "src" / "copilot-cli", source)
        # Remove every dispatcher the tree actually ships. Naming the events
        # inline went stale when issue #5154 retired the last PostToolUse
        # group; the property under test is that a plugin with no dispatcher
        # fails, whatever set of events it registers.
        dispatchers = sorted((source / "hooks").glob("*/_dispatch.py"))
        assert dispatchers, "fixture found no dispatchers to remove"
        for dispatcher in dispatchers:
            dispatcher.unlink()

        proc = subprocess.run(
            [
                sys.executable,
                str(_REPO_ROOT / "scripts" / "ci" / "test_installed_plugin_hooks.py"),
                "--plugin-source",
                str(source),
                "--install-root",
                str(tmp_path / "install"),
                "--consumer-cwd",
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
            timeout=180,
        )

        combined = proc.stdout + proc.stderr
        assert proc.returncode != 0, (
            "the guard reported success with no dispatchers present, so it "
            f"certified an empty run. output:\n{combined}"
        )
        assert "FAIL: no dispatcher" in combined, combined

    def test_intact_plugin_still_passes_the_guard(self, tmp_path: Path) -> None:
        """The inverse control: the guard must not fail on a healthy plugin."""
        proc = subprocess.run(
            [
                sys.executable,
                str(_REPO_ROOT / "scripts" / "ci" / "test_installed_plugin_hooks.py"),
                "--plugin-source",
                "src/copilot-cli",
                "--install-root",
                str(tmp_path / "install"),
                "--consumer-cwd",
                str(tmp_path),
            ],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=180,
        )

        assert proc.returncode == 0, proc.stdout + proc.stderr


@pytest.mark.parametrize(
    "dispatcher",
    [
        _REPO_ROOT / "build" / "scripts" / "generate_dispatcher.py",
        _REPO_ROOT / "src" / "copilot-cli" / "hooks" / "PreToolUse" / "_dispatch.py",
    ],
    ids=["source", "copilot-pre"],
)
def test_dispatcher_catches_system_exit(dispatcher: Path) -> None:
    """Source and every shipped copy must cover SystemExit.

    Asserting only on the source would pass while a stale generated copy still
    denied, which is the drift this guard exists to catch.
    """
    text = dispatcher.read_text(encoding="utf-8")
    assert "except (Exception, SystemExit) as exc:" in text, (
        f"{dispatcher} misses SystemExit at the bootstrap boundary. It is a "
        "BaseException, so a bare except Exception does not catch it, and "
        "every _bootstrap.py before this change calls sys.exit(2)."
    )


class TestLauncherFormsCoverTheSameFailures:
    """The bash and PowerShell launchers must guard the same conditions.

    Test-Path answers only "does it exist". A file blocked by Windows ACLs
    passes it, Python then exits 2 opening it, and the trailing
    `exit $LASTEXITCODE` denies every call. The bash form already checked -r,
    so testing existence only left the two launchers covering different
    failures on the platform the customer was running. Refs #4672.
    """

    def _launcher_commands(self) -> dict[str, str]:
        import json

        manifest = json.loads(
            (
                _REPO_ROOT / "src" / "copilot-cli" / "hooks" / "hooks.json"
            ).read_text(encoding="utf-8")
        )
        found: dict[str, str] = {}

        def _walk(node: object) -> None:
            if isinstance(node, dict):
                for key, value in node.items():
                    if key in ("bash", "powershell") and isinstance(value, str):
                        found.setdefault(key, "")
                        found[key] += value + "\n"
                    else:
                        _walk(value)
            elif isinstance(node, list):
                for item in node:
                    _walk(item)

        _walk(manifest)
        return found

    def test_both_forms_are_present(self) -> None:
        commands = self._launcher_commands()
        assert "bash" in commands and "powershell" in commands, commands.keys()

    def test_bash_checks_readability(self) -> None:
        assert "-r " in self._launcher_commands()["bash"]

    def test_powershell_checks_readability(self) -> None:
        powershell = self._launcher_commands()["powershell"]
        assert "OpenRead" in powershell, (
            "the PowerShell launcher checks existence but not readability, so "
            "an ACL-blocked dispatcher denies every call on Windows"
        )


class TestModuleLoadFailureDegrades:
    """A load failure is infrastructure, not a policy decision.

    Only ImportError counted as a load failure, so a hook_dispatch.py that
    exists but cannot compile fell through to the broad handler and was
    classified as a policy failure: exit 2, denying every PreToolUse call.
    A load failure cannot be a policy decision, because no policy ran.
    Refs #4672.
    """

    def _run_with_lib(
        self, tmp_path: Path, lib_source: str
    ) -> subprocess.CompletedProcess[bytes]:
        event_dir = tmp_path / "hooks" / "PreToolUse"
        dispatcher = _write_dispatcher(event_dir)
        (event_dir / "_bootstrap.py").write_text(
            "import sys\n"
            "from pathlib import Path\n"
            "\n"
            "\n"
            "def ensure_plugin_paths() -> None:\n"
            "    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'lib'))\n",
            encoding="utf-8",
        )
        lib = tmp_path / "lib"
        lib.mkdir(parents=True, exist_ok=True)
        (lib / "hook_dispatch.py").write_text(lib_source, encoding="utf-8")
        return subprocess.run(
            [sys.executable, "-u", str(dispatcher)],
            input=b'{"tool_name": "Bash", "tool_input": {"command": "echo hi"}}',
            capture_output=True,
            cwd=str(tmp_path),
            timeout=30,
        )

    def test_syntax_error_in_lib_degrades(self, tmp_path: Path) -> None:
        proc = self._run_with_lib(tmp_path, "def broken(:\n")

        stderr = proc.stderr.decode("utf-8", "replace")
        assert proc.returncode == 0, (
            "a hook_dispatch.py that cannot compile denied the tool call, "
            f"which is the customer-wide denial in #4672. stderr:\n{stderr}"
        )
        assert "hooks DISABLED" in stderr

    def test_raise_during_module_init_degrades(self, tmp_path: Path) -> None:
        proc = self._run_with_lib(tmp_path, "raise RuntimeError('boom')\n")

        stderr = proc.stderr.decode("utf-8", "replace")
        assert proc.returncode == 0, (
            f"a module raising during import denied the call. stderr:\n{stderr}"
        )
        assert "hooks DISABLED" in stderr


class TestClaudeEntrypointDegrades:
    """A missing lib directory must degrade, not deny, on the Claude harness.

    The bash launcher guards the plugin root and the dispatcher file but cannot
    check lib. The entrypoint caught that failure and exited 2, which Claude
    reads as a denial of the tool call, so every other infrastructure path
    degraded while this one denied. Refs #4672.
    """

    ENTRYPOINT = _REPO_ROOT / ".claude" / "hooks" / "invoke_dispatch_claude.py"

    def test_missing_lib_directory_degrades(self, tmp_path: Path) -> None:
        hooks = tmp_path / "hooks"
        hooks.mkdir(parents=True)
        entrypoint = hooks / "invoke_dispatch_claude.py"
        entrypoint.write_text(
            self.ENTRYPOINT.read_text(encoding="utf-8"), encoding="utf-8"
        )
        # No lib directory alongside hooks: the import must fail.

        proc = subprocess.run(
            [sys.executable, "-u", str(entrypoint), "--group", "anything"],
            input=b"{}",
            capture_output=True,
            cwd=str(tmp_path),
            timeout=30,
        )

        stderr = proc.stderr.decode("utf-8", "replace")
        assert proc.returncode == 0, (
            "a missing lib directory denied the tool call on the Claude "
            f"harness. stderr:\n{stderr}"
        )
        assert "hooks DISABLED" in stderr, stderr

    def test_entrypoint_does_not_exit_two_on_load_failure(self) -> None:
        """Pin the exit code in the source, so a regression is visible."""
        text = self.ENTRYPOINT.read_text(encoding="utf-8")
        assert "raise SystemExit(2) from None" not in text, (
            "the entrypoint exits 2 on an initialization failure, which Claude "
            "reads as a denial of every tool call"
        )
