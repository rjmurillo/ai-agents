"""A licensed FAIL must not read as a blocking FAIL beside a pass banner.

``pre_pr`` printed ``[FAIL]`` for an advisory finding (a FAIL the pre-PR policy
licenses) and then ``Pre-PR checks passed`` under it. Both were true: the exit
code is 0 by design. A reader scanning the run still saw the word "FAIL" and the
word "passed" together and could not tell which one governed the push.

These drive the real ``main`` and read its stdout, so what is pinned is the
process's own output (``.claude/rules/testing.md`` MUST 8). The typed state in
the JSON summary stays ``FAIL``; only the console label changes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from scripts.validation.evidence import (
    REASON_ADVISORY_FINDINGS,
    WORKING_TREE,
    CheckOutcome,
)
from scripts.validation.pre_pr import main, run_all_validations

_GATE = run_all_validations.__globals__["_Gate"]

_ADVISORY_VALIDATOR = "validate_canonical_citations"


def _sequence(*outcomes: Any) -> tuple[Any, ...]:
    return tuple(
        _GATE(f"Gate {index}", lambda _root, _args, value=outcome: value)
        for index, outcome in enumerate(outcomes)
    )


def _run(
    capsys: pytest.CaptureFixture[str], *outcomes: Any, argv: tuple[str, ...] = ()
) -> tuple[int, str]:
    with patch("pre_pr_sequence._SEQUENCE", _sequence(*outcomes)):
        code = main(["--quick", *argv])
    return code, capsys.readouterr().out


def _passing() -> CheckOutcome:
    return CheckOutcome.passed("clean_gate", revision=WORKING_TREE, scope="the tree", examined=3)


def _advisory(findings: int = 2) -> CheckOutcome:
    """The exact FAIL row the pre-PR policy licenses for an uncited mirror claim."""
    return CheckOutcome.failed(
        _ADVISORY_VALIDATOR,
        reason=REASON_ADVISORY_FINDINGS,
        findings=findings,
        detail="2 uncited mirror claims",
    )


def _blocking() -> CheckOutcome:
    return CheckOutcome.failed("lint_gate", reason="lint.violation", findings=1, detail="bad")


class TestAdvisoryLabel:
    """The console names a non-blocking finding ADVISORY and a blocking one FAIL."""

    def test_an_advisory_row_is_labelled_advisory_and_never_fail(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Discriminating case: every row line printed ``[FAIL]`` before the fix."""
        code, out = _run(capsys, _passing(), _advisory())

        assert code == 0
        assert "[ADVISORY] Gate 1 completed" in out
        assert "[ADVISORY] Gate 1" in out.split("=== Detailed Results ===")[1]
        assert "[ADVISORY]" in out
        assert "[FAIL]" not in out

    def test_the_banner_carries_the_advisory_count(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _, out = _run(capsys, _passing(), _advisory(), _advisory())

        assert "Pre-PR checks passed with 2 advisory finding(s), not blocking." in out

    def test_the_summary_counts_advisory_apart_from_fail(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _, out = _run(capsys, _passing(), _advisory())

        assert "FAIL: 0" in out
        assert "ADVISORY: 1" in out

    def test_the_result_line_breakdown_says_advisory(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _, out = _run(capsys, _passing(), _advisory())

        assert "1 of 2 did not prove their contract (ADVISORY: 1)" in out
        assert "FAIL: 1" not in out

    def test_the_lefthook_banner_carries_the_count_too(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SKIP_AUTOFIX", "1")

        _, out = _run(capsys, _passing(), _advisory())

        assert (
            "pre_pr validations passed with 1 advisory finding(s), not blocking "
            "(push outcome depends on sibling hook jobs)."
        ) in out

    def test_the_evidence_line_says_advisory(self, capsys: pytest.CaptureFixture[str]) -> None:
        _, out = _run(capsys, _advisory())

        assert f"  [ADVISORY] {_ADVISORY_VALIDATOR} reason={REASON_ADVISORY_FINDINGS}" in out
        assert "Advisory: 2 uncited mirror claims" in out
        assert "Error: 2 uncited" not in out

    def test_the_json_summary_keeps_the_typed_fail_state(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        """Negative control on scope: the label is console-only."""
        destination = tmp_path / "summary.json"

        code, _ = _run(capsys, _passing(), _advisory(), argv=("--summary-json", str(destination)))

        data = json.loads(destination.read_text(encoding="utf-8"))
        assert code == 0
        assert data["counts"]["FAIL"] == 1
        assert [r["state"] for r in data["results"]] == ["PASS", "FAIL"]


class TestBlockingFailUnchanged:
    """A FAIL that blocks keeps its name, so the label means something."""

    def test_a_blocking_fail_still_prints_fail_and_exits_one(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code, out = _run(capsys, _passing(), _blocking())

        assert code == 1
        assert "[FAIL] Gate 1 completed" in out
        assert "Error: bad" in out
        assert "[ADVISORY]" not in out
        assert "Pre-PR checks passed" not in out

    def test_a_mixed_run_counts_each_kind_once(self, capsys: pytest.CaptureFixture[str]) -> None:
        code, out = _run(capsys, _advisory(), _blocking())

        assert code == 1
        assert "FAIL: 1" in out
        assert "ADVISORY: 1" in out
        assert "[ADVISORY] Gate 0" in out
        assert "[FAIL] Gate 1" in out

    def test_an_unlicensed_reason_on_an_advisory_validator_still_blocks(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Edge: the licence is per reason, so a new reason code is a real FAIL."""
        widened = CheckOutcome.failed(_ADVISORY_VALIDATOR, reason="lint.violation", findings=1)

        code, out = _run(capsys, widened)

        assert code == 1
        assert "[FAIL] Gate 0 completed" in out
        assert "[ADVISORY]" not in out


class TestCleanRunUnchanged:
    def test_a_clean_run_keeps_its_banner_words(self, capsys: pytest.CaptureFixture[str]) -> None:
        code, out = _run(capsys, _passing())

        assert code == 0
        assert "RESULT: All validations passed" in out
        assert "Pre-PR checks passed. Verify the push landed before opening a PR:" in out
        assert "advisory finding" not in out
        assert "ADVISORY: 0" in out
