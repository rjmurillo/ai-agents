"""CI classification of detect_stale_bot_review.py fed by the real get_pr_checks producer.

The fixtures in test_detect_stale_bot_review.py are hand-built dicts. These tests run
get_pr_checks.build_output and pass its output to _ci_state, so the fixture shape cannot
drift from the producer (issue #6632, review round 3).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from tests.test_detect_stale_bot_review import (
    _mod as _detector,
)
from tests.test_detect_stale_bot_review import (
    _pr,
    _stale_cr,
)
from tests.test_detect_stale_bot_review_main import (
    _run_main,
    _siblings,
)

_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1] / ".claude" / "skills" / "github" / "scripts" / "pr"
)


def _load_producer():
    spec = importlib.util.spec_from_file_location(
        "get_pr_checks_for_ci_state", _SCRIPTS_DIR / "get_pr_checks.py"
    )
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


_build_output = _load_producer().build_output

_ci_state = _detector._ci_state
_GREEN = _detector._CI_GREEN
_FAILING = _detector._CI_FAILING
_UNKNOWN = _detector._CI_UNKNOWN


def _row(name: str, *, required: bool, passing: bool = True) -> dict[str, Any]:
    return {
        "Name": name,
        "Type": "CheckRun",
        "State": "COMPLETED" if passing else "WAITING",
        "Conclusion": "SUCCESS" if passing else "",
        "DetailsUrl": "",
        "IsRequired": required,
        "IsPending": not passing,
        "IsPassing": passing,
        "IsFailing": False,
    }


def _produce(
    rows: list[dict[str, Any]],
    *,
    ruleset: list[str] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "Number": 7,
        "HasChecks": True,
        "AllState": "SUCCESS",
        "Checks": rows,
    }
    data.update(extra)
    return _build_output(data, "o", "r", ruleset_contexts=ruleset)


class TestCiStateFromProducerOutput:
    def test_green_required_row_is_green(self):
        out = _produce([_row("req", required=True)], ruleset=["req"])
        assert out["RequiredState"] == "SUCCESS"
        assert _ci_state(out) == _GREEN

    def test_optional_pending_row_does_not_move_a_green_required_set(self):
        rows = [_row("req", required=True), _row("deploy", required=False, passing=False)]
        out = _produce(rows, ruleset=["req"])
        assert out["AllPassing"] is False
        assert _ci_state(out) == _GREEN

    def test_stranded_required_check_with_no_required_rows_is_failing(self):
        # Ruleset requires "req", it never reported, the only row is optional.
        out = _produce([_row("opt", required=False)], ruleset=["req"])
        assert out["RequiredState"] == "FAILURE"
        assert out["MissingRequiredChecks"] == ["req"]
        assert not any(row["IsRequired"] for row in out["Checks"])
        assert _ci_state(out) == _FAILING

    def test_queued_required_check_with_no_required_rows_is_failing(self):
        recent = datetime.now(timezone.utc) - timedelta(seconds=5)
        out = _produce(
            [_row("opt", required=False)],
            ruleset=["req"],
            HeadCommittedAt=recent.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        assert out["RequiredState"] == "PENDING"
        assert _ci_state(out) == _FAILING

    def test_running_required_row_is_failing(self):
        out = _produce([_row("req", required=True, passing=False)], ruleset=["req"])
        assert out["RequiredState"] == "PENDING"
        assert _ci_state(out) == _FAILING

    def test_no_checks_reported_is_unknown(self):
        out = _produce([], HasChecks=False)
        assert out["RequiredState"] == "UNKNOWN"
        assert _ci_state(out) == _UNKNOWN

    def test_no_required_rows_and_no_ruleset_context_uses_all_passing(self):
        out = _produce([_row("opt", required=False)], ruleset=[])
        assert out["RequiredState"] == "SUCCESS"
        assert _ci_state(out) == _GREEN

    def test_unknown_required_state_with_required_row_is_unknown(self):
        out = _produce([_row("req", required=True)], ruleset=["req"], ChecksIncomplete=True)
        assert out["RequiredState"] == "UNKNOWN"
        assert _ci_state(out) == _UNKNOWN


class TestMergeStateComputing:
    @pytest.mark.parametrize(
        ("merge_state", "merge_state_status", "expected"),
        [
            ("MERGEABLE", "UNKNOWN", _UNKNOWN),
            ("UNKNOWN", "CLEAN", _UNKNOWN),
            ("UNKNOWN", "UNKNOWN", _UNKNOWN),
            ("MERGEABLE", None, _UNKNOWN),
            ("CONFLICTING", "DIRTY", _FAILING),
            ("CONFLICTING", "UNKNOWN", _FAILING),
            ("UNKNOWN", "DIRTY", _FAILING),
            ("MERGEABLE", "CLEAN", _GREEN),
            ("MERGEABLE", "BLOCKED", _GREEN),
        ],
        ids=[
            "status_unknown",
            "state_unknown",
            "both_unknown",
            "status_null",
            "conflicting_dirty",
            "conflicting_wins_over_unknown_status",
            "dirty_wins_over_unknown_state",
            "clean_is_green",
            "blocked_review_gate_is_green",
        ],
    )
    def test_green_required_row_by_merge_state(self, merge_state, merge_state_status, expected):
        out = _produce(
            [_row("req", required=True)],
            ruleset=["req"],
            MergeState=merge_state,
            MergeStateStatus=merge_state_status,
        )
        assert out["RequiredState"] == "SUCCESS"
        assert _ci_state(out) == expected

    def test_proven_required_pending_outranks_unknown_merge_state(self):
        out = _produce(
            [_row("req", required=True, passing=False)],
            ruleset=["req"],
            MergeStateStatus="UNKNOWN",
        )
        assert out["MergeRefUsable"] is False
        assert _ci_state(out) == _FAILING

    def test_proven_required_missing_outranks_unknown_merge_state(self):
        out = _produce([_row("opt", required=False)], ruleset=["req"], MergeState="UNKNOWN")
        assert out["RequiredState"] == "FAILURE"
        assert _ci_state(out) == _FAILING

    def test_unusable_merge_ref_without_merge_state_keys_is_failing(self):
        checks = {"MergeRefUsable": False, "RequiredState": "SUCCESS", "AllPassing": True}
        assert _ci_state(checks) == _FAILING


class TestCiVerdictThroughMain:
    def _verdict(self, checks: dict[str, Any], capsys) -> dict[str, Any]:
        fake = _siblings(_pr(), (0, checks), [_stale_cr()], [])
        assert _run_main(fake) == 0
        return json.loads(capsys.readouterr().out)["Data"]

    def test_stranded_required_check_reports_not_passing(self, capsys):
        out = _produce([_row("opt", required=False)], ruleset=["req"])
        data = self._verdict(out, capsys)
        assert data["verdict"] == "NOT_READY"
        assert data["reasons"] == ["CI is not passing"]
        assert data["handoff"] is None

    def test_merge_state_still_computing_reports_unknown(self, capsys):
        out = _produce([_row("req", required=True)], ruleset=["req"], MergeStateStatus="UNKNOWN")
        data = self._verdict(out, capsys)
        assert data["verdict"] == "NOT_READY"
        assert data["reasons"] == ["CI state is unknown"]
        assert data["handoff"] is None
