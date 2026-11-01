"""AC-36: one fixture through both adapters gives one answer.

REQ-048 AC-36: when one fixture of 20 or fewer events runs through the
transcript adapter (consumer B) and through CheckFailures input (consumer A),
the classifier shall return the same FailureTally and the same per-target
ChurnCycle counts for both.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

HERE = str(Path(__file__).resolve().parent)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from stuck_failure_events import fc, mod

# (tool, tool_input, is_error, result_text). Covers a failure-repeat, a reset
# by a successful retry, three churn cycles on one file, a failed edit, a
# permission denial, and an unfingerprinted failure.
TEST = {"command": "pytest tests/a.py"}
EDIT_A = {"file_path": "./src/a.py", "old_string": "x", "new_string": "y"}
FIXTURE: list[tuple[str, dict[str, Any] | None, bool, str]] = [
    ("Bash", TEST, True, "FAILED test_a - exit code 1"),
    ("Edit", EDIT_A, False, "ok"),
    ("Bash", TEST, True, "FAILED test_a - exit code 1"),
    ("Edit", EDIT_A, False, "ok"),
    ("Bash", TEST, True, "FAILED test_a - exit code 1"),
    ("Edit", EDIT_A, False, "ok"),
    ("Bash", TEST, True, "FAILED test_a - exit code 1"),
    ("Edit", {"file_path": "src/b.py", "old_string": "q"}, True, "old_string not found"),
    ("Bash", {"command": "make build"}, True, "make: *** [all] Error 2"),
    ("Bash", {"command": "make build"}, False, "built"),
    ("Bash", {"command": "rm -rf build"}, True, "Permission denied by policy"),
    ("Bash", {"command": "true"}, True, ""),
    ("Write", {"file_path": "src\\c.py", "content": "z"}, False, "ok"),
    ("Bash", {"command": "npm test"}, True, "Error at 0xDEADBEEF1"),
    # No input: keyless in both adapters, so never a retry.
    ("Bash", None, True, "no input given"),
    ("Bash", None, True, "no input given"),
]


def transcript_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index, (tool, tool_input, is_error, text) in enumerate(FIXTURE):
        use_id = f"toolu_{index}"
        use: dict[str, Any] = {"type": "tool_use", "id": use_id, "name": tool}
        if tool_input is not None:
            use["input"] = tool_input
        block: dict[str, Any] = {"type": "tool_result", "tool_use_id": use_id, "content": text}
        if is_error:
            block["is_error"] = True
        records.append({"type": "assistant", "isSidechain": False, "message": {"content": [use]}})
        records.append({"type": "user", "isSidechain": False, "message": {"content": [block]}})
    return records


def check_failures_input() -> list[dict[str, Any]]:
    """The same calls as a caller would hand `check-failures`."""
    events: list[dict[str, Any]] = []
    for tool, tool_input, is_error, text in FIXTURE:
        event: dict[str, Any] = {"tool": tool, "ok": not is_error, "error": text}
        if tool_input is not None:
            # AC-39: the caller's own JSON, unsorted and spaced, canonicalizes
            # to the key the transcript adapter builds.
            event["input"] = json.dumps(tool_input)
            path = tool_input.get("file_path")
            if fc.normalize_tool(tool) in fc.EDIT_TOOLS and path:
                event["target"] = path
        events.append(event)
    return events


def test_fixture_is_within_the_ac36_bound() -> None:
    assert len(FIXTURE) <= 20


def test_both_adapters_emit_the_same_events() -> None:
    assert fc.events_from_records(transcript_records()) == mod.parse_events(check_failures_input())


def test_both_consumers_get_the_same_tally_and_churn() -> None:
    via_b = fc.classify(fc.events_from_records(transcript_records()))
    via_a = fc.classify(mod.parse_events(check_failures_input()))
    assert via_a.tally == via_b.tally
    assert via_a.churn_totals() == via_b.churn_totals()
    # Non-vacuous: the fixture exercises both signals.
    assert via_b.churn_totals() == {
        "src/a.py": {"bash|failed test_a - exit code N": 3},
        "src/c.py": {"bash|error at H": 1},
    }
    assert via_b.repeat_totals()["bash|failed test_a - exit code N"] == 4
    assert (via_b.permission_denial, via_b.unfingerprinted) == (1, 1)


def test_check_failures_reports_from_the_shared_tally() -> None:
    result = mod.check_failures(mod.parse_events(check_failures_input()))
    assert result["stuck"] is True
    assert {s["signal"] for s in result["signals"]} == {"failure-repeat", "edit-churn"}
