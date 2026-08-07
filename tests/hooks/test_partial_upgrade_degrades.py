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
        removed = 0
        for event in ("PreToolUse", "PostToolUse"):
            dispatcher = source / "hooks" / event / "_dispatch.py"
            if dispatcher.exists():
                dispatcher.unlink()
                removed += 1
        assert removed == 2, "fixture did not remove both dispatchers"

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
        _REPO_ROOT / "src" / "copilot-cli" / "hooks" / "PostToolUse" / "_dispatch.py",
    ],
    ids=["source", "copilot-pre", "copilot-post"],
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
