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

Scope after ADR-097: every case here that drove the GENERATED Copilot
dispatcher, its bootstrap, or its launcher forms was retired with that
artifact, which no longer exists. What remains is the Claude-side entrypoint
(still live, still used by the two SessionStart groups) and the dispatcher
source. The "a registered event with no dispatcher must fail" invariant moved
to `tests/ci/test_installed_plugin_zero_hook_state.py`, where it runs against a
synthetic registering tree instead of the deleted shipped one.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]


class TestMissingDispatcherIsAFailure:
    """The guard must fail, not skip, when an expected dispatcher is absent."""

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
    [_REPO_ROOT / "build" / "scripts" / "generate_dispatcher.py"],
    ids=["source"],
)
def test_dispatcher_catches_system_exit(dispatcher: Path) -> None:
    """The dispatcher source must cover SystemExit.

    The `copilot-pre` parameter covered the generated copy, because asserting
    only on the source would pass while a stale generated copy still denied.
    ADR-097 retired that copy along with every tool-call hook, so there is no
    generated dispatcher left to drift from this source. Should a tool-use hook
    ever be re-added, restore the shipped-copy parameter with it: the drift it
    guarded returns the moment a second copy exists.
    """
    text = dispatcher.read_text(encoding="utf-8")
    assert "except (Exception, SystemExit) as exc:" in text, (
        f"{dispatcher} misses SystemExit at the bootstrap boundary. It is a "
        "BaseException, so a bare except Exception does not catch it, and "
        "every _bootstrap.py before this change calls sys.exit(2)."
    )




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
