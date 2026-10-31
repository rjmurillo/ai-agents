"""Equivalence tests for the concurrent lookups in the closeout gate (issue #6734)."""

from __future__ import annotations

import random
import subprocess
import threading
import time
from pathlib import Path

import pytest

from scripts.validation import active_plan_closeout
from scripts.validation.active_plan_closeout import (
    DEFAULT_REPO,
    KNOWN_STATES,
    active_plan_warnings,
    gh_issue_state,
    validate_active_plan_closeout,
)
from scripts.validation.evidence import (
    REASON_ADVISORY_FINDINGS,
    REASON_LOOKUP_FAILED,
    WORKING_TREE,
    CheckOutcome,
    EvidenceState,
)


def write_active_plan(repo_root: Path, name: str, body: str) -> Path:
    """Create an active plan fixture."""
    path = repo_root / ".project-toolkit" / "plans" / "active" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _issue_from_command(command: list[str]) -> int:
    return int(command[3])


def _reference_serial_validate(repo_root: Path) -> CheckOutcome:
    """The pre-#6734 validator: one serial ``gh_issue_state`` call per reference."""
    lookups = 0
    unresolved = 0

    def counted_lookup(issue: int) -> str | None:
        nonlocal lookups, unresolved
        lookups += 1
        state = gh_issue_state(issue, repo=DEFAULT_REPO)
        if active_plan_closeout._normalize_state(state) not in KNOWN_STATES:
            unresolved += 1
        return state

    warnings = active_plan_warnings(repo_root, issue_state_lookup=counted_lookup)
    if warnings:
        print("[WARNING] Active execution plans have closed tracking issues:")
        for warning in warnings:
            print(f"  - {warning.format()}")
        print("Note: advisory only. Exit code unchanged.")
        return CheckOutcome.failed(
            active_plan_closeout._VALIDATOR,
            reason=REASON_ADVISORY_FINDINGS,
            revision=WORKING_TREE,
            scope=active_plan_closeout._SCOPE,
            examined=lookups,
            findings=len(warnings),
            detail=active_plan_closeout._findings_detail(len(warnings), unresolved, lookups),
        )
    if unresolved:
        print(
            "[WARNING] Active plan closeout advisory: "
            f"{unresolved} of {lookups} issue lookup(s) returned no usable state"
        )
        return CheckOutcome.blocked(
            active_plan_closeout._VALIDATOR,
            reason=REASON_LOOKUP_FAILED,
            scope=active_plan_closeout._SCOPE,
            detail=f"{unresolved} of {lookups} issue lookup(s) returned no usable state",
        )
    print("[PASS] Active plan closeout advisory: no active plans with all tracking issues closed")
    return CheckOutcome.passed(
        active_plan_closeout._VALIDATOR,
        revision=WORKING_TREE,
        scope=active_plan_closeout._SCOPE,
        examined=lookups,
    )


def _fake_gh(responses: dict[int, tuple[int, str, str]], calls: list[int], delay: bool = False):
    """Build a ``subprocess.run`` stand-in answering from ``responses``."""
    lock = threading.Lock()

    def run(command, **kwargs):
        issue = _issue_from_command(command)
        if delay:
            # Low issue numbers finish last, so completion order reverses plan order.
            time.sleep(max(0.0, 0.05 - issue * 0.001))
        with lock:
            calls.append(issue)
        returncode, stdout, stderr = responses[issue]
        return subprocess.CompletedProcess(command, returncode, stdout, stderr)

    return run


def test_prefetch_looks_up_each_distinct_issue_once_but_counts_every_reference(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    write_active_plan(tmp_path, "a.md", "# Plan\n\n#101 #102\n")
    write_active_plan(tmp_path, "b.md", "# Plan\n\n#102 #103\n")
    calls: list[int] = []
    responses = {n: (0, "CLOSED\n", "") for n in (101, 102, 103)}
    monkeypatch.setattr(
        "scripts.validation.active_plan_closeout.subprocess.run", _fake_gh(responses, calls)
    )

    outcome = validate_active_plan_closeout(tmp_path)

    assert sorted(calls) == [101, 102, 103]
    assert outcome.state is EvidenceState.FAIL
    assert outcome.examined == 4
    assert outcome.findings == 2
    assert capsys.readouterr().out.count(".project-toolkit/plans/active/") == 2


def test_lookups_run_concurrently(tmp_path: Path, monkeypatch) -> None:
    """A serial loop never reaches the barrier with four parties, so it breaks."""
    write_active_plan(tmp_path, "a.md", "# Plan\n\n#101 #102 #103 #104\n")
    barrier = threading.Barrier(4, timeout=10)

    def run(command, **kwargs):
        barrier.wait()
        return subprocess.CompletedProcess(command, 0, "OPEN\n", "")

    monkeypatch.setattr("scripts.validation.active_plan_closeout.subprocess.run", run)

    outcome = validate_active_plan_closeout(tmp_path)

    assert outcome.state is EvidenceState.PASS
    assert outcome.examined == 4


def test_advisory_lines_print_in_plan_order_whatever_order_lookups_finish(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    write_active_plan(tmp_path, "a.md", "# Plan\n\n#10 #20 #30 #40\n")
    responses = {n: (1, "", f"boom {n}") for n in (10, 20, 30, 40)}
    monkeypatch.setattr(
        "scripts.validation.active_plan_closeout.subprocess.run",
        _fake_gh(responses, [], delay=True),
    )

    validate_active_plan_closeout(tmp_path)

    lines = capsys.readouterr().out.splitlines()
    inspected = [line.split("could not inspect ")[1].split(":")[0] for line in lines[:4]]
    assert inspected == ["#10", "#20", "#30", "#40"]


def test_a_repeated_failing_issue_prints_its_advisory_once_per_reference(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    write_active_plan(tmp_path, "a.md", "# Plan\n\n#101 #102\n")
    write_active_plan(tmp_path, "b.md", "# Plan\n\n#101 #103\n")
    responses = {101: (1, "", "gone"), 102: (0, "CLOSED\n", ""), 103: (0, "CLOSED\n", "")}
    monkeypatch.setattr(
        "scripts.validation.active_plan_closeout.subprocess.run", _fake_gh(responses, [])
    )

    outcome = validate_active_plan_closeout(tmp_path)

    out = capsys.readouterr().out
    assert out.count("could not inspect #101: gh lookup failed: gone") == 2
    assert outcome.state is EvidenceState.BLOCKED
    assert outcome.reason == REASON_LOOKUP_FAILED


def test_one_unresolved_issue_blocks_the_closeout_warning(tmp_path: Path, monkeypatch) -> None:
    write_active_plan(tmp_path, "a.md", "# Plan\n\n#101 #102 #103\n")
    responses = {101: (0, "CLOSED\n", ""), 102: (1, "", "nope"), 103: (0, "MERGED\n", "")}
    monkeypatch.setattr(
        "scripts.validation.active_plan_closeout.subprocess.run", _fake_gh(responses, [])
    )

    outcome = validate_active_plan_closeout(tmp_path)

    assert outcome.state is EvidenceState.BLOCKED
    assert outcome.findings in (None, 0)


def test_worker_exception_propagates_like_the_serial_run(tmp_path: Path, monkeypatch) -> None:
    write_active_plan(tmp_path, "a.md", "# Plan\n\n#101 #102 #103\n")

    def run(command, **kwargs):
        if _issue_from_command(command) == 102:
            raise ValueError("embedded null byte")
        return subprocess.CompletedProcess(command, 0, "OPEN\n", "")

    monkeypatch.setattr("scripts.validation.active_plan_closeout.subprocess.run", run)

    with pytest.raises(ValueError, match="embedded null byte"):
        validate_active_plan_closeout(tmp_path)
    # The worker's capture buffer must not leak onto this thread.
    assert not hasattr(active_plan_closeout._advisory_sink, "lines")


def test_unreadable_plan_still_raises_after_prefetch_is_skipped(tmp_path: Path) -> None:
    path = write_active_plan(tmp_path, "bad.md", "# Plan\n")
    path.write_bytes(b"\xff\xfe\x00 #101 invalid utf-8 \xff")

    with pytest.raises(UnicodeDecodeError):
        validate_active_plan_closeout(tmp_path)


def test_no_active_directory_makes_no_lookups(tmp_path: Path, monkeypatch) -> None:
    def run(*args, **kwargs):
        raise AssertionError("no lookup expected")

    monkeypatch.setattr("scripts.validation.active_plan_closeout.subprocess.run", run)

    outcome = validate_active_plan_closeout(tmp_path)

    assert outcome.state is EvidenceState.PASS
    assert outcome.examined == 0


@pytest.mark.parametrize("seed", range(25))
def test_concurrent_validator_matches_the_serial_reference(
    seed: int, tmp_path: Path, monkeypatch, capsys
) -> None:
    """Same stdout, verdict, reason, counts, and detail as the serial loop on random inputs."""
    rng = random.Random(seed)
    pool = list(range(100, 100 + rng.randint(2, 14)))
    for index in range(rng.randint(1, 5)):
        refs = rng.sample(pool, rng.randint(1, min(6, len(pool))))
        write_active_plan(
            tmp_path, f"plan-{index}.md", "# Plan\n\n" + " ".join(f"#{r}" for r in refs)
        )
    outcomes = [
        (0, "CLOSED\n", ""),
        (0, "MERGED\n", ""),
        (0, "open\n", ""),
        (0, "WEIRD\n", ""),
        (0, "\n", ""),
        (1, "", "HTTP 404"),
    ]
    weights = [6, 3, 2, 1, 1, 1]
    responses = {n: rng.choices(outcomes, weights)[0] for n in pool}
    monkeypatch.setattr(
        "scripts.validation.active_plan_closeout.subprocess.run",
        _fake_gh(responses, [], delay=bool(seed % 2)),
    )

    reference = _reference_serial_validate(tmp_path)
    reference_out = capsys.readouterr().out
    actual = validate_active_plan_closeout(tmp_path)
    actual_out = capsys.readouterr().out

    assert actual_out == reference_out
    assert actual == reference
