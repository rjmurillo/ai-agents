"""Codex 0.157.1 live captures against the 0.156.0 pin (issue #5423).

Captured 2026-10-03 with native codex-cli 0.157.1. The matrix pins 0.156.0, so
the captures are reported and move no cell. Re-pinning to 0.157.1 in a copy of
the matrix is the only change that lets them verify, which shows the pin is
the one blocker.
"""

from __future__ import annotations

import json
from pathlib import Path

from tests.eval._harness_capability_test_support import MATRIX, recorded_cli

PLAN = MATRIX.parent / "harness-capability-recorded-captures-0.157.1.json"
WAIT, NOWAIT, RESET, RESET_KILLED = 0, 1, 2, 3


def _matrix_pinned(tmp_path: Path, version: str) -> Path:
    document = json.loads(MATRIX.read_text(encoding="utf-8"))
    for record in document["harnesses"]:
        if record["harness"] == "codex":
            record["version"] = version
    path = tmp_path / "matrix.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _codex_cell(report: dict[str, object], capability: str) -> dict[str, object]:
    harnesses = report["harnesses"]
    assert isinstance(harnesses, list)
    codex = next(h for h in harnesses if h["harness"] == "codex")
    return codex["capabilities"][capability]


def _captures(report: dict[str, object]) -> list[dict[str, object]]:
    items = report["recorded_captures"]
    assert isinstance(items, list)
    return items


def test_pinned_0_156_0_the_captures_are_reported_and_move_no_cell() -> None:
    report = recorded_cli.run(MATRIX, PLAN)

    assert {c["status"] for c in _captures(report)} == {"UNVERIFIED"}
    for capability in ("concurrency_limit", "context_reset_observability"):
        assert _codex_cell(report, capability)["status"] == "UNVERIFIED"
    assert "pins 0.156.0" in str(_captures(report)[WAIT]["detail"])


def test_the_waited_run_bounds_the_limit_at_the_configured_three() -> None:
    report = recorded_cli.run(MATRIX, PLAN)

    detail = str(_captures(report)[WAIT]["detail"])
    assert "2 refused spawn(s) on 0.157.1" in detail
    assert "between 3 and 3 child threads" in detail


def test_the_no_wait_run_is_unmeasurable_because_children_were_aborted() -> None:
    report = recorded_cli.run(MATRIX, PLAN)

    assert _captures(report)[NOWAIT]["status"] == "UNVERIFIED"
    assert _captures(report)[NOWAIT]["value"] is None


def test_the_compaction_captures_count_what_the_rollouts_hold() -> None:
    report = recorded_cli.run(MATRIX, PLAN)

    assert "recorded 2 compaction(s)" in str(_captures(report)[RESET]["detail"])
    assert "recorded 4 compaction(s)" in str(_captures(report)[RESET_KILLED]["detail"])


def test_pinned_0_157_1_the_waited_run_and_the_compaction_verify(tmp_path: Path) -> None:
    report = recorded_cli.run(_matrix_pinned(tmp_path, "codex-cli 0.157.1"), PLAN)

    concurrency = _codex_cell(report, "concurrency_limit")
    assert concurrency["status"] == "VERIFIED"
    assert concurrency["value"] == 3
    assert _codex_cell(report, "context_reset_observability")["status"] == "VERIFIED"


def test_pinned_0_157_1_the_aborted_children_run_still_does_not_verify(tmp_path: Path) -> None:
    report = recorded_cli.run(_matrix_pinned(tmp_path, "codex-cli 0.157.1"), PLAN)

    assert _captures(report)[NOWAIT]["status"] == "UNVERIFIED"
