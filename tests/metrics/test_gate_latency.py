"""Running one repetition and folding runs into a report (REQ-027).

Mirrors gate_latency_sampler.py. subprocess.run is monkeypatched throughout:
no test here runs a real lefthook hook. The shared patch-and-dispatch setup
lives in conftest.stub_lefthook; each test keeps its own assertions.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.metrics import gate_latency_sampler as gls_sampler
from tests.metrics.conftest import (
    REAL_CAPTURED_STDOUT,
    expected_lefthook_cmd,
    stub_lefthook,
    stub_lefthook_expecting,
)


def test_positive_run_repetition_records_all_four_fields(
    monkeypatch: pytest.MonkeyPatch, repo: Path
) -> None:
    """AC-02 and AC-03: every field a repetition must carry, on one real capture."""
    lefthook_cmd = ["lefthook"]
    expected_cmd = expected_lefthook_cmd("pre-commit")
    stub_lefthook_expecting(monkeypatch, expected_cmd, REAL_CAPTURED_STDOUT)

    run = gls_sampler._run_repetition(repo, lefthook_cmd, "pre-commit", (), 0)

    assert run.repetition_index == 0
    assert run.exit_code == 0
    assert run.wall_clock_seconds >= 0.0
    assert run.lefthook_reported_seconds == 0.20
    assert run.jobs_parsed == 1
    assert run.tree_mutated is False
    assert run.unknown_status_count == 0
    assert run.samples[0].name == "security-suppressions-staged"


def test_positive_unknown_marker_is_surfaced_via_unknown_status_count(
    monkeypatch: pytest.MonkeyPatch, repo: Path
) -> None:
    """A marker outside every known glyph family is counted, never silently absorbed."""
    stub_lefthook(monkeypatch, "summary: (done in 0.01 seconds)\n? mystery-job (0.01 seconds)\n")

    run = gls_sampler._run_repetition(repo, ["lefthook"], "pre-commit", (), 0)

    assert run.jobs_parsed == 1
    assert run.samples[0].status == "unknown"
    assert run.unknown_status_count == 1


def test_positive_run_repetition_passes_change_class_files_as_file_args(
    monkeypatch: pytest.MonkeyPatch, repo: Path
) -> None:
    """AC-08: the class's files reach lefthook as repeated --file arguments."""
    lefthook_cmd = ["lefthook"]
    expected_cmd = expected_lefthook_cmd("pre-commit", files=("README.md",))
    stub_lefthook_expecting(monkeypatch, expected_cmd, REAL_CAPTURED_STDOUT)

    run = gls_sampler._run_repetition(repo, lefthook_cmd, "pre-commit", ("README.md",), 0)

    assert run.jobs_parsed == 1


def test_edge_tree_mutated_true_when_digest_changes(
    monkeypatch: pytest.MonkeyPatch, repo: Path
) -> None:
    """AC-12: a job that writes to the tree makes later repetitions measure a different one."""
    stub_lefthook(
        monkeypatch,
        REAL_CAPTURED_STDOUT,
        porcelain=lambda call: "" if call == 1 else " M some-file.txt\n",
    )

    run = gls_sampler._run_repetition(repo, ["lefthook"], "pre-commit", (), 0)

    assert run.tree_mutated is True


def test_edge_tree_mutated_false_when_digest_unchanged(
    monkeypatch: pytest.MonkeyPatch, repo: Path
) -> None:
    """The control for the case above: an unchanged digest must not read as mutation."""
    stub_lefthook(monkeypatch, REAL_CAPTURED_STDOUT)

    run = gls_sampler._run_repetition(repo, ["lefthook"], "pre-commit", (), 0)

    assert run.tree_mutated is False
