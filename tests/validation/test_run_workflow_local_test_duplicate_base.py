"""act allowance for duplicate-code.yml's master fork-point failure.

act's synthetic payload names ``master`` as the default branch, so the
duplicate gate cannot name a fork point with ``origin/master`` and exits 3.
These tests pin the allowance to that job, that step, and that line only.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_VALIDATION_DIR = str(REPO_ROOT / "scripts" / "validation")
if _VALIDATION_DIR not in sys.path:
    sys.path.insert(0, _VALIDATION_DIR)

import run_workflow_local_test as w

_JOB = "[Duplicate Code Detection/Python duplication ratchet]"
_OTHER_JOB = "[Dependency Hygiene/Unused dependencies]"
_STEP = "Check Python duplication against the baseline"


def _failure(ref: str = "origin/master", step: str = _STEP, failing_job: str = _JOB) -> str:
    """Two lines copied from a real pre-push act log, parameterized."""
    return (
        f"      {_JOB}   | ERROR: git cannot name a fork point with '{ref}'\n"
        f"      {failing_job}   ❌  Failure - Main {step} [2.316727381s]\n"
        f"      {_JOB} exitcode '3': failure\n"
    )


def test_hint_matches_the_master_fork_point_failure() -> None:
    hint = w._act_limitation_hint(_failure())
    assert hint is not None
    assert "duplicate-code" in hint


@pytest.mark.parametrize(
    "text",
    [
        _failure(ref="origin/main"),
        _failure(ref="origin/mastery"),
        _failure(step="Install locked duplication detector"),
        _failure(failing_job=_OTHER_JOB),
        f"{_JOB}   | ERROR: git cannot name a fork point with 'origin/master'\n",
        f"{_JOB}   ❌  Failure - Main {_STEP} [5ms]\n",
        "",
    ],
)
def test_hint_ignores_other_failures(text: str) -> None:
    assert w._act_limitation_hint(text) is None


def test_hint_requires_the_two_lines_to_be_adjacent() -> None:
    first, second, _ = _failure().splitlines(keepends=True)
    interleaved = f"{first}      {_JOB}   | other output\n{second}"
    assert w._act_limitation_hint(interleaved) is None


def test_hint_rejects_a_failure_line_the_step_echoed() -> None:
    """Step output carries act's `| ` prefix, so it cannot stand in for act's line."""
    forged = (
        f"      {_JOB}   | ERROR: git cannot name a fork point with 'origin/master'\n"
        f"      {_JOB}   | ❌  Failure - Main {_STEP} [1ms]\n"
    )
    assert w._act_limitation_hint(forged) is None


def test_hint_rejects_trailing_text_after_the_ref() -> None:
    text = _failure().replace("'origin/master'", "'origin/master' and more", 1)
    assert w._act_limitation_hint(text) is None


def test_hint_blocks_when_another_step_also_failed() -> None:
    other = f"      {_OTHER_JOB}   ❌  Failure - Main Check unused dependencies [3ms]\n"
    assert w._act_limitation_hint(_failure() + other) is None


def test_the_rule_names_match_duplicate_code_yml() -> None:
    """The rule quotes duplicate-code.yml; a rename there must fail here."""
    workflow = yaml.safe_load(
        (REPO_ROOT / ".github" / "workflows" / "duplicate-code.yml").read_text(encoding="utf-8")
    )
    jobs = list(workflow["jobs"].values())
    assert len(jobs) == 1
    job = jobs[0]
    label = f"[{workflow['name']}/{job['name']}]"
    assert re.fullmatch(w._ACT_DUPLICATE_BASE_JOB_LABEL, label)
    step = next(s for s in job["steps"] if s.get("name") == w._ACT_DUPLICATE_BASE_STEP)
    assert step["env"]["BASE_REF"] == (
        "${{ github.base_ref || github.event.repository.default_branch }}"
    )
    assert 'check_duplicate_code.py --base-ref "origin/$BASE_REF"' in step["run"]


def test_the_rule_quotes_the_checker_error() -> None:
    """The matched text is what check_duplicate_code.py raises with exit 3."""
    source = (REPO_ROOT / "scripts" / "validation" / "check_duplicate_code.py").read_text(
        encoding="utf-8"
    )
    assert 'GateError(f"git cannot name a fork point with {ref!r}", 3)' in source


def test_a_limitation_is_not_retried_as_contention(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """act prints `docker pull` on every run; that alone must not trigger a retry.

    A retry of an explained failure can add a second, unrelated failure (a
    docker cp race with files a concurrent test run creates), which would then
    block the downgrade the first run qualified for.
    """
    first = (
        f"      {_JOB}   \U0001f433  docker pull image=catthehacker/ubuntu:full-latest\n"
        f"      {_JOB}   \U0001f433  docker create image=catthehacker/ubuntu:full-latest\n"
        + _failure()
    )
    retry = f"      {_JOB}   ❌  Failure - Main actions/checkout [1.2s]\n"
    calls: list[list[str]] = []

    def fake_run(cmd, *, timeout, cwd=None, env=None):
        calls.append(cmd)
        return 1, first if len(calls) == 1 else retry, ""

    monkeypatch.setattr(w, "_run", fake_run)
    res = w._act_full_stage([".github/workflows/duplicate-code.yml"], tmp_path)

    assert len(calls) == 1
    assert res.ok is True
    assert "duplicate-code job" in res.detail


def test_contention_without_a_limitation_still_retries(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd, *, timeout, cwd=None, env=None):
        calls.append(cmd)
        return (1, "", "failed to create container") if len(calls) == 1 else (0, "", "")

    monkeypatch.setattr(w, "_run", fake_run)
    res = w._act_full_stage([".github/workflows/duplicate-code.yml"], tmp_path)

    assert len(calls) == 2
    assert res.ok is True
