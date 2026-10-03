"""Evidence written by the emitter survives the fetch and satisfies the gate.

The fetch tests build records by hand. This one starts from the emitter's own
output, so a field the emitter leaves empty and the gate requires cannot pass
unnoticed (a PASS with no examined count reads as missing evidence at the gate).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.validation.emit_validator_evidence import build_outcome
from scripts.validation.evidence import EvidenceState
from scripts.validation.promotion_evidence import Candidate, bind_records, load_evidence_dir
from scripts.validation.promotion_fetch import fetch_verified_evidence
from scripts.validation.promotion_findings import collect_findings, missing_outcomes
from tests.validation.promotion_fetch_helpers import SHA, FakeReader, _entry, _good, _zip

NAME = "run_python_tests"


def _emitted(status: str, ran: bool = True) -> str:
    outcome = build_outcome(
        validator=NAME, job_status=status, ran=ran, revision=SHA, scope="job test-result on push"
    )
    return json.dumps(outcome.to_dict())


def _gate_view(tmp_path: Path, reader: FakeReader):
    fetch_verified_evidence(
        reader, repo="owner/repo", candidate_sha=SHA, default_branch="main",
        entries=[_entry()], evidence_dir=tmp_path / "ev",
    )  # fmt: skip
    records, rejected = load_evidence_dir(tmp_path / "ev")
    bound = bind_records(records, Candidate(SHA), frozenset())
    synthesized = missing_outcomes([NAME], bound.bound, Candidate(SHA))
    return rejected, bound, synthesized


def test_a_green_job_from_the_emitter_is_not_read_as_missing(tmp_path: Path) -> None:
    reader = _good(archives={77: _zip(f"{NAME}.json", _emitted("success"))})
    rejected, bound, synthesized = _gate_view(tmp_path, reader)
    assert rejected == ()
    assert [r.outcome.state for r in bound.bound] == [EvidenceState.PASS]
    assert synthesized == ()
    assert collect_findings(bound.bound, synthesized) == ()


@pytest.mark.parametrize("status", ["failure", "cancelled", "skipped"])
def test_a_job_that_did_not_succeed_is_a_finding_at_the_gate(tmp_path: Path, status: str) -> None:
    reader = _good(archives={77: _zip(f"{NAME}.json", _emitted(status))})
    _, bound, synthesized = _gate_view(tmp_path, reader)
    assert len(collect_findings(bound.bound, synthesized)) == 1


def test_a_short_circuited_job_is_a_finding_at_the_gate(tmp_path: Path) -> None:
    reader = _good(archives={77: _zip(f"{NAME}.json", _emitted("success", ran=False))})
    _, bound, synthesized = _gate_view(tmp_path, reader)
    assert len(collect_findings(bound.bound, synthesized)) == 1
