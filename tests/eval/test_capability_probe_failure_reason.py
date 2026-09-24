"""Failure reasons a live probe carries into a matrix cell (issue #5423).

Probed 2026-09-24: Copilot CLI 1.0.89 exits 1 with empty stderr and reports
quota exhaustion only as a `session.error` event on stdout, and a codex run
under `RUST_LOG=tungstenite::protocol=trace` writes megabytes of stderr. The
reason must name the real cause in one bounded line either way.
"""

from __future__ import annotations

import json

from tests.eval._harness_capability_test_support import probes


def test_copilot_session_error_on_stdout_names_the_cause() -> None:
    stdout = "\n".join(
        json.dumps(event)
        for event in (
            {"type": "assistant.turn_start", "data": {}},
            {"type": "session.error", "data": {"message": "You have exceeded your monthly quota"}},
        )
    )

    reason = probes._failure_reason("copilot", 1, stdout, "")

    assert reason == "copilot probe exited with code 1: You have exceeded your monthly quota"


def test_codex_turn_failed_error_message_is_read() -> None:
    stdout = json.dumps({"type": "turn.failed", "error": {"message": "401 Unauthorized"}})

    reason = probes._failure_reason("codex", 1, stdout, "trace line\n" * 3)

    assert reason.endswith(": 401 Unauthorized")


def test_clap_error_line_wins_over_the_help_hint() -> None:
    stderr = (
        "error: invalid value 'ultra' for '--reasoning-effort <level>'\n"
        "  [possible values: none, minimal, low, medium, high, xhigh, max]\n\n"
        "For more information, try '--help'.\n"
    )

    reason = probes._failure_reason("copilot", 2, "", stderr)

    assert reason == (
        "copilot probe exited with code 2: "
        "error: invalid value 'ultra' for '--reasoning-effort <level>'"
    )


def test_huge_stderr_is_truncated_to_the_bound() -> None:
    stderr = "x" * (probes.MAX_FAILURE_REASON * 4)

    reason = probes._failure_reason("codex", 1, None, stderr)

    assert len(reason) <= len("codex probe exited with code 1: ") + probes.MAX_FAILURE_REASON


def test_no_output_falls_back_to_the_exit_code() -> None:
    assert probes._failure_reason("codex", 3, "", "") == "codex probe exited with code 3"


def test_non_json_stdout_lines_are_ignored() -> None:
    reason = probes._failure_reason("copilot", 1, "not json\n[1,2]\n", "last line")

    assert reason == "copilot probe exited with code 1: last line"
