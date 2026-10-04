"""Codex 0.160.0 rollout captures against the 0.160.0 pin (issue #5423).

Captured 2026-10-03 with native codex-cli 0.160.0, the version installed that
day. The pin tracks the installed CLI: a codex auto-update invalidates it.
"""

from __future__ import annotations

import json
from pathlib import Path

from tests.eval._harness_capability_test_support import MATRIX, recorded_cli

PLAN = MATRIX.parent / "harness-capability-recorded-captures-0.160.0.json"
WAIT, NOWAIT, RESET = 0, 1, 2


def _codex_cell(report: dict[str, object], capability: str) -> dict[str, object]:
    harnesses = report["harnesses"]
    assert isinstance(harnesses, list)
    codex = next(h for h in harnesses if h["harness"] == "codex")
    return codex["capabilities"][capability]


def _captures(report: dict[str, object]) -> list[dict[str, object]]:
    items = report["recorded_captures"]
    assert isinstance(items, list)
    return items


def test_the_matrix_pins_the_version_the_captures_were_taken_on() -> None:
    document = json.loads(MATRIX.read_text(encoding="utf-8"))
    codex = next(h for h in document["harnesses"] if h["harness"] == "codex")
    assert codex["version"] == "codex-cli 0.160.0"


def test_the_waited_run_verifies_the_limit_at_the_configured_three() -> None:
    report = recorded_cli.run(MATRIX, PLAN)

    assert _captures(report)[WAIT]["status"] == "VERIFIED"
    cell = _codex_cell(report, "concurrency_limit")
    assert cell["status"] == "VERIFIED" and cell["value"] == 3
    assert "2 further spawn(s) were refused" in str(_captures(report)[WAIT]["detail"])


def test_the_compaction_capture_verifies_context_reset_observability() -> None:
    report = recorded_cli.run(MATRIX, PLAN)

    assert _captures(report)[RESET]["status"] == "VERIFIED"
    assert "recorded 4 compaction(s)" in str(_captures(report)[RESET]["detail"])
    assert _codex_cell(report, "context_reset_observability")["status"] == "VERIFIED"


def test_a_parent_that_does_not_wait_yields_no_ceiling() -> None:
    """Negative control: children end in turn_aborted, so no spawn refusal is read.

    The parent did hold refusals (see the stdout fixture), which is the reader
    defect tracked in the issue filed for it. This test pins the current output.
    """
    report = recorded_cli.run(MATRIX, PLAN)

    capture = _captures(report)[NOWAIT]
    assert capture["status"] == "UNVERIFIED" and capture["value"] is None
    assert "No rollout capture shows a spawn refused" in str(capture["detail"])


def test_a_capture_from_another_version_moves_no_cell(tmp_path: Path) -> None:
    document = json.loads(MATRIX.read_text(encoding="utf-8"))
    for record in document["harnesses"]:
        if record["harness"] == "codex":
            record["version"] = "codex-cli 0.161.0"
    other = tmp_path / "matrix.json"
    other.write_text(json.dumps(document), encoding="utf-8")

    report = recorded_cli.run(other, PLAN)

    assert {c["status"] for c in _captures(report)} == {"UNVERIFIED"}
