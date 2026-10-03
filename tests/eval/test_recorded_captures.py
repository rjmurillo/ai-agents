"""Capture-plan, CLI, pending-probe, and matrix-drift tests (issue #5423).

The default plan runs against the recorded fixtures with no CLI and no
network. The drift tests fail when a checked-in matrix cell stops agreeing with
what its recorded capture derives.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

from tests.eval._harness_capability_test_support import (
    MATRIX,
    capability,
    captures,
    pending,
    recorded_cli,
)
from tests.eval._rollout_test_support import FIXTURES, REFUSAL

PLAN = MATRIX.parent / "harness-capability-recorded-captures.json"
EXAMPLES = MATRIX.parent


def _matrix_at(tmp_path: Path, **versions: str) -> Path:
    document = json.loads(MATRIX.read_text(encoding="utf-8"))
    for record in document["harnesses"]:
        if record["harness"] in versions:
            record["version"] = versions[record["harness"]]
    path = tmp_path / "matrix.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _plan(tmp_path: Path, captures_value: object) -> Path:
    path = tmp_path / "plan.json"
    path.write_text(json.dumps({"captures": captures_value}), encoding="utf-8")
    return path


def _run(*argv: str) -> int:
    return recorded_cli.main(list(argv))


def _by_key(report: dict[str, object]) -> dict[tuple[str, str], dict[str, object]]:
    items = report["recorded_captures"]
    assert isinstance(items, list)
    return {(item["harness"], item["capability"]): item for item in items}


# --- Default plan --------------------------------------------------------------


def test_default_plan_reports_all_three_captures_as_unverified() -> None:
    report = recorded_cli.run(MATRIX, PLAN)

    found = _by_key(report)
    assert set(found) == {
        ("codex", "concurrency_limit"),
        ("codex", "context_reset_observability"),
        ("copilot", "context_reset_observability"),
    }
    assert {item["status"] for item in found.values()} == {"UNVERIFIED"}


def test_default_plan_leaves_the_checked_in_cells_unchanged() -> None:
    expected = capability.build_report(capability.load_matrix(MATRIX))

    report = recorded_cli.run(MATRIX, PLAN)

    assert report["harnesses"] == expected["harnesses"]


def test_the_cli_prints_the_report_and_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    assert _run() == 0

    assert "recorded_captures" in json.loads(capsys.readouterr().out)


def test_the_cli_writes_the_report_when_asked(tmp_path: Path) -> None:
    target = tmp_path / "out" / "report.json"

    assert _run("--output", str(target)) == 0

    assert json.loads(target.read_text(encoding="utf-8"))["schema_version"] == 1


def test_an_unwritable_output_is_an_external_failure(tmp_path: Path) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("file", encoding="utf-8")

    assert _run("--output", str(blocker / "report.json")) == 3


# --- Applying a verified capture -----------------------------------------------


def _plan_with_configured(tmp_path: Path, configured: object) -> Path:
    """Copy the default plan with absolute paths and a stated session cap."""
    document = json.loads(PLAN.read_text(encoding="utf-8"))
    document["captures"][0]["configured_max_threads"] = configured
    for entry in document["captures"]:
        for key in ("parent", "rollout", "events"):
            if key in entry:
                entry[key] = str((PLAN.parent / entry[key]).resolve())
        if "children" in entry:
            entry["children"] = [str((PLAN.parent / c).resolve()) for c in entry["children"]]
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _harness(report: dict[str, object], name: str) -> dict[str, Any]:
    harnesses = cast("list[dict[str, Any]]", report["harnesses"])
    return next(h for h in harnesses if h["harness"] == name)


def _codex(report: dict[str, object]) -> dict[str, Any]:
    return _harness(report, "codex")


def test_a_capture_at_the_pinned_version_replaces_the_context_reset_cell(tmp_path: Path) -> None:
    matrix = _matrix_at(tmp_path, codex="codex-cli 0.154.0")

    report = recorded_cli.run(matrix, PLAN)

    cell = _codex(report)["capabilities"]["context_reset_observability"]
    assert cell["status"] == "VERIFIED"
    assert cell["date"] == "2026-09-17"


def test_an_unstated_session_cap_leaves_the_concurrency_cell_unverified(tmp_path: Path) -> None:
    matrix = _matrix_at(tmp_path, codex="codex-cli 0.154.0")

    report = recorded_cli.run(matrix, PLAN)

    assert _codex(report)["capabilities"]["concurrency_limit"]["status"] == "UNVERIFIED"


def test_a_stated_session_cap_verifies_with_provenance(tmp_path: Path) -> None:
    matrix = _matrix_at(tmp_path, codex="codex-cli 0.154.0")

    report = recorded_cli.run(matrix, _plan_with_configured(tmp_path, 6))

    cell = _codex(report)["capabilities"]["concurrency_limit"]
    assert (cell["status"], cell["value"], cell["date"]) == ("VERIFIED", 6, "2026-09-10")
    assert "Sources: parent.rollout.jsonl, child-1.rollout.jsonl" in cell["detail"]
    assert cell["probe_command"] == captures.REGENERATE_COMMAND


def test_a_stated_session_cap_that_the_peak_missed_stays_unverified(tmp_path: Path) -> None:
    matrix = _matrix_at(tmp_path, codex="codex-cli 0.154.0")

    report = recorded_cli.run(matrix, _plan_with_configured(tmp_path, 5))

    assert _codex(report)["capabilities"]["concurrency_limit"]["status"] == "UNVERIFIED"


def test_verified_capabilities_stop_owing_their_live_probe(tmp_path: Path) -> None:
    matrix = _matrix_at(tmp_path, codex="codex-cli 0.154.0")

    report = recorded_cli.run(matrix, _plan_with_configured(tmp_path, 6))

    assert "pending_live_probes" not in _codex(report)


def test_an_unverified_capture_keeps_the_probe_it_would_have_replaced(tmp_path: Path) -> None:
    matrix = _matrix_at(tmp_path, codex="codex-cli 0.154.0")

    report = recorded_cli.run(matrix, PLAN)

    scopes = [p["scope"] for p in _codex(report)["pending_live_probes"]]
    assert scopes == ["codex concurrency_limit at 0.156.0"]


def test_a_verified_capture_does_not_touch_the_other_harness(tmp_path: Path) -> None:
    matrix = _matrix_at(tmp_path, codex="codex-cli 0.154.0")

    report = recorded_cli.run(matrix, PLAN)

    copilot = _harness(report, "copilot")
    assert copilot["capabilities"]["context_reset_observability"]["status"] == "UNVERIFIED"


def test_the_copilot_capture_verifies_at_its_own_pin(tmp_path: Path) -> None:
    matrix = _matrix_at(tmp_path, copilot="GitHub Copilot CLI 1.0.79-9.")

    report = recorded_cli.run(matrix, PLAN)

    copilot = _harness(report, "copilot")
    assert copilot["capabilities"]["context_reset_observability"]["status"] == "VERIFIED"


# --- Plan errors ---------------------------------------------------------------


@pytest.mark.parametrize(
    "entries",
    [
        [],
        "captures",
        ["not an object"],
        [{"harness": "copilot", "capability": "concurrency_limit"}],
        [{"harness": "claude", "capability": "context_reset_observability"}],
        [{"harness": "codex", "capability": "concurrency_limit", "parent": "p", "children": []}],
        [{"harness": "codex", "capability": "concurrency_limit", "children": ["c"]}],
        [{"harness": "codex", "capability": "context_reset_observability"}],
        *[
            [
                {
                    "harness": "codex",
                    "capability": "concurrency_limit",
                    "parent": "p",
                    "children": ["c"],
                    "configured_max_threads": bad,
                }
            ]
            for bad in (0, -1, True, "6", 2.5)
        ],
        [{"harness": "copilot", "capability": "context_reset_observability", "events": ""}],
        [
            {
                "harness": "codex",
                "capability": "context_reset_observability",
                "rollout": "gone.jsonl",
            }
        ],
        [
            {
                "harness": "copilot",
                "capability": "context_reset_observability",
                "events": "gone.jsonl",
            }
        ],
    ],
)
def test_bad_plans_exit_with_a_config_error(tmp_path: Path, entries: object) -> None:
    assert _run("--captures", str(_plan(tmp_path, entries))) == 2


def test_a_missing_plan_file_is_a_config_error(tmp_path: Path) -> None:
    assert _run("--captures", str(tmp_path / "nope.json")) == 2


def test_a_plan_that_is_not_an_object_is_a_config_error(tmp_path: Path) -> None:
    path = tmp_path / "plan.json"
    path.write_text("[]", encoding="utf-8")

    assert _run("--captures", str(path)) == 2


def test_a_malformed_capture_file_names_the_harness_and_capability(tmp_path: Path) -> None:
    bad = tmp_path / "bad.jsonl"
    bad.write_text("not json\n", encoding="utf-8")
    plan = _plan(
        tmp_path,
        [
            {
                "harness": "copilot",
                "capability": "context_reset_observability",
                "events": "bad.jsonl",
            }
        ],
    )

    with pytest.raises(captures.CapturePlanError, match="copilot context_reset_observability"):
        recorded_cli.run(MATRIX, plan)


def test_a_capture_for_a_harness_missing_from_the_matrix_is_refused(tmp_path: Path) -> None:
    document = json.loads(MATRIX.read_text(encoding="utf-8"))
    document["harnesses"] = [h for h in document["harnesses"] if h["harness"] != "copilot"]
    path = tmp_path / "matrix.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(captures.CapturePlanError, match="no record for harness"):
        recorded_cli.run(path, PLAN)


def test_a_relative_capture_path_resolves_against_the_plan_directory(tmp_path: Path) -> None:
    shutil.copy(FIXTURES / "copilot-1.0.79-9" / "compaction.events.jsonl", tmp_path / "e.jsonl")
    plan = _plan(
        tmp_path,
        [{"harness": "copilot", "capability": "context_reset_observability", "events": "e.jsonl"}],
    )

    report = recorded_cli.run(MATRIX, plan)

    assert _by_key(report)[("copilot", "context_reset_observability")]["sources"] == ["e.jsonl"]


# --- Pending live probes -------------------------------------------------------


def _entry(**overrides: object) -> dict[str, object]:
    return {"scope": "s", "blocker": "b", "command": "c", **overrides}


def test_absent_pending_probes_mean_none_are_owed() -> None:
    assert pending.load_pending_probes(None) == ()


def test_pending_probes_round_trip() -> None:
    loaded = pending.load_pending_probes([_entry()])

    assert [p.as_dict() for p in loaded] == [_entry()]


@pytest.mark.parametrize(
    "value",
    [
        "text",
        {"scope": "s"},
        ["text"],
        [_entry(scope="")],
        [_entry(blocker="  ")],
        [_entry(command=None)],
        [{"scope": "s", "blocker": "b"}],
        [_entry(), _entry()],
    ],
)
def test_malformed_pending_probes_fail_closed(value: object) -> None:
    with pytest.raises(pending.PendingProbeError):
        pending.load_pending_probes(value)


def test_the_matrix_loader_wraps_a_bad_pending_probe(tmp_path: Path) -> None:
    document = json.loads(MATRIX.read_text(encoding="utf-8"))
    document["harnesses"][0]["pending_live_probes"] = [{"scope": "s"}]
    path = tmp_path / "matrix.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(capability.HarnessCapabilityError, match=r"harnesses\[0\]"):
        capability.load_matrix(path)


def test_every_owed_live_probe_names_its_blocker_and_command() -> None:
    records = capability.load_matrix(MATRIX)

    owed = {r.harness: r.pending_live_probes for r in records}

    assert {h: len(p) for h, p in owed.items()} == {"codex": 2, "copilot": 0}
    assert all("0.157.1" in p.blocker for p in owed["codex"])


def test_the_report_carries_the_owed_probes() -> None:
    report = capability.build_report(capability.load_matrix(MATRIX))

    codex = _harness(report, "codex")
    assert codex["pending_live_probes"][0]["scope"].startswith("codex concurrency_limit")
    assert "pending_live_probes" not in _harness(report, "copilot")


def test_a_record_with_nothing_owed_omits_the_field() -> None:
    record = capability.load_matrix(MATRIX)[0]
    bare = replace(record, pending_live_probes=())

    assert "pending_live_probes" not in capability.build_report([bare])["harnesses"][0]


# --- Matrix drift --------------------------------------------------------------


def test_matrix_context_reset_cells_lead_with_what_the_capture_derives() -> None:
    report = recorded_cli.run(MATRIX, PLAN)
    found = _by_key(report)

    for record in capability.load_matrix(MATRIX):
        cell = record.capabilities["context_reset_observability"]
        derived = found[(record.harness, "context_reset_observability")]
        assert cell.status.value == derived["status"]
        assert cell.detail.startswith(str(derived["detail"]))


def test_matrix_concurrency_cell_states_the_recorded_bounds() -> None:
    cell = next(r for r in capability.load_matrix(MATRIX) if r.harness == "codex").capabilities[
        "concurrency_limit"
    ]

    assert cell.status is capability.CapabilityStatus.UNVERIFIED
    assert "between 6 and 6 child threads" in cell.detail
    assert REFUSAL in cell.detail
