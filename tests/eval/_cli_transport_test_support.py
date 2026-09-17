"""Fake `subprocess.run` and payload builders for the CLI transport tests.

Shared by `test_cli_transport_helpers.py`, `test_claude_cli_provider.py`, and
`test_codex_cli_provider.py`. It lives in one module because all three fake
the same call: `_cli_transport` is the single place every transport reaches
`subprocess.run`, so a recorder installed there covers every provider without
any of them growing a test-only seam.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_EVAL_DIR = _REPO_ROOT / "scripts" / "eval"
_ORIGINAL_SYS_PATH = sys.path.copy()
sys.path.insert(0, str(_EVAL_DIR))
try:
    import _claude_cli
    import _cli_transport
    import _codex_cli
finally:
    sys.path[:] = _ORIGINAL_SYS_PATH

__all__ = [
    "MESSAGES",
    "Recorder",
    "claude_payload",
    "install_runner",
    "write_last_message",
    "_claude_cli",
    "_cli_transport",
    "_codex_cli",
]

MESSAGES = [{"role": "user", "content": "Say PONG"}]


class Recorder:
    """Stand-in for `subprocess.run` that records the call it was given."""

    def __init__(
        self,
        *,
        stdout: str = "",
        returncode: int = 0,
        stderr: str = "",
        side_effect: BaseException | None = None,
        on_call: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self._stdout = stdout
        self._returncode = returncode
        self._stderr = stderr
        self._side_effect = side_effect
        self._on_call = on_call

    def __call__(self, argv: list[str], **kwargs: Any) -> Any:
        record = {"argv": list(argv), **kwargs}
        self.calls.append(record)
        if self._on_call is not None:
            self._on_call(record)
        if self._side_effect is not None:
            raise self._side_effect
        return subprocess.CompletedProcess(
            argv, self._returncode, self._stdout, self._stderr
        )

    @property
    def argv(self) -> list[str]:
        return self.calls[-1]["argv"]


def install_runner(monkeypatch: pytest.MonkeyPatch, recorder: Recorder) -> None:
    """Replace the one `subprocess.run` every CLI transport calls."""
    monkeypatch.setattr(_cli_transport.subprocess, "run", recorder)


def claude_payload(
    model: str = "claude-haiku-4-5-20251001", result: str = "PONG"
) -> str:
    """Build the `--output-format json` envelope the Claude CLI emits."""
    return json.dumps(
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": result,
            "modelUsage": {model: {"inputTokens": 1, "outputTokens": 1}},
        }
    )


def write_last_message(text: str) -> Callable[[dict[str, Any]], None]:
    """Write `text` where `codex exec --output-last-message` would."""

    def _on_call(record: dict[str, Any]) -> None:
        argv = record["argv"]
        Path(argv[argv.index("--output-last-message") + 1]).write_text(
            text, encoding="utf-8"
        )

    return _on_call
