"""The `security-scan` budget ADR-054 states must equal the `lefthook.yml` timeout.

Issue #5555 found two accepted ADRs giving one pre-push job incompatible
budgets. The 2026-09-29 amendment to ADR-054 resolved it: 900 seconds is the
per-job kill ceiling, ADR-104's 300 seconds is the target for the whole hook,
and both stand. That settles the prose. It does not stop the number drifting
again, because the figure in ADR-054's Performance Budget table and the
`timeout:` on the `security-scan` job in `lefthook.yml` are two literals in two
files that nothing compared.

Coverage:

- positive: the table figure and the job timeout agree on the real files.
- negative: a changed timeout, a changed table figure, and a different unit
  spelling of an unequal value each produce a mismatch message naming both
  numbers.
- edge: a missing row, a duplicated row, a missing job, and a job without a
  timeout fail loudly rather than skipping, since a guard that finds nothing to
  compare has stopped guarding.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
import yaml

from scripts.ci.lefthook_budget_model import (
    LEFTHOOK,
    REPO_ROOT,
    flatten,
    load_config,
    seconds,
)

ADR_054 = REPO_ROOT / ".project-toolkit" / "architecture" / "ADR-054-local-security-scanning.md"
HOOK = "pre-push"
JOB = "security-scan"

# One Performance Budget table row: `| Lefthook `security-scan` job | 900 seconds |`.
_ROW = re.compile(
    r"^\|\s*Lefthook\s+`security-scan`\s+job\s*\|\s*(?P<value>\d+)\s+seconds\s*\|\s*$",
    re.MULTILINE,
)


def adr_budget_seconds(text: str) -> float:
    """The `security-scan` job budget stated in ADR-054's budget table."""
    matches = _ROW.findall(text)
    if len(matches) != 1:
        raise ValueError(
            f"expected exactly one 'Lefthook `security-scan` job | N seconds' row in "
            f"ADR-054, found {len(matches)}. If the table was reworded, update the "
            "pattern in this module in the same change."
        )
    return float(matches[0])


def lefthook_timeout_seconds(config: dict[str, Any]) -> float:
    """The `timeout:` of the `security-scan` job in the pre-push hook, in seconds."""
    jobs = [
        job
        for entry in config[HOOK]["jobs"]
        if isinstance(entry, dict)
        for job in flatten(entry)
        if job.get("name") == JOB
    ]
    if len(jobs) != 1:
        raise ValueError(f"expected exactly one {JOB!r} job in {HOOK}, found {len(jobs)}.")
    timeout = jobs[0].get("timeout")
    if timeout is None:
        raise ValueError(f"the {JOB!r} job in {HOOK} declares no timeout.")
    return seconds(timeout)


def mismatch(adr_seconds: float, hook_seconds: float) -> str | None:
    """Message naming both figures, or None when they agree."""
    if adr_seconds == hook_seconds:
        return None
    return (
        f"ADR-054 states a {adr_seconds:.0f}s budget for the {JOB} job but lefthook.yml "
        f"sets {hook_seconds:.0f}s. Change one to match the other. A raised cap needs "
        "the ci-scripts.md MUST-16 accounting and the declared-total ratchet in "
        "tests/ci/test_lefthook_declared_budget.py updated."
    )


def _adr_text() -> str:
    return ADR_054.read_text(encoding="utf-8")


def test_adr_budget_matches_the_lefthook_timeout() -> None:
    failure = mismatch(adr_budget_seconds(_adr_text()), lefthook_timeout_seconds(load_config()))
    assert failure is None, failure


def test_the_real_figures_are_the_ones_the_amendment_names() -> None:
    """Pin the parse to the known value so a regex that matches wrongly cannot agree by accident."""
    assert adr_budget_seconds(_adr_text()) == 900.0
    assert lefthook_timeout_seconds(load_config()) == 900.0


@pytest.mark.parametrize("raw", ["14m", "16m", "899s", "901", "1h"])
def test_a_changed_timeout_is_reported(raw: str) -> None:
    config = yaml.safe_load(LEFTHOOK.read_text(encoding="utf-8"))
    for entry in config[HOOK]["jobs"]:
        if isinstance(entry, dict) and entry.get("name") == JOB:
            entry["timeout"] = raw
            break
    else:  # pragma: no cover - the real-file test above asserts the job exists
        pytest.fail(f"{JOB} is missing from {HOOK}.")
    hook_seconds = lefthook_timeout_seconds(config)
    failure = mismatch(adr_budget_seconds(_adr_text()), hook_seconds)
    assert failure is not None
    assert "900s" in failure
    assert f"{hook_seconds:.0f}s" in failure


def test_a_changed_adr_figure_is_reported() -> None:
    text = _adr_text()
    mutated = text.replace(
        "| Lefthook `security-scan` job | 900 seconds |",
        "| Lefthook `security-scan` job | 300 seconds |",
    )
    assert mutated != text, "the mutation did not apply, so this test would grade unmutated text."
    failure = mismatch(adr_budget_seconds(mutated), lefthook_timeout_seconds(load_config()))
    assert failure is not None
    assert "300s" in failure and "900s" in failure


def test_equal_budgets_in_different_units_agree() -> None:
    config = {HOOK: {"jobs": [{"name": JOB, "timeout": "15m"}]}}
    text = "| Lefthook `security-scan` job | 900 seconds |"
    assert mismatch(adr_budget_seconds(text), lefthook_timeout_seconds(config)) is None


def test_a_missing_adr_row_fails_loudly() -> None:
    with pytest.raises(ValueError, match="found 0"):
        adr_budget_seconds("| Python Semgrep child process | 840 seconds |")


def test_a_duplicated_adr_row_fails_loudly() -> None:
    row = "| Lefthook `security-scan` job | 900 seconds |\n"
    with pytest.raises(ValueError, match="found 2"):
        adr_budget_seconds(row + row)


def test_a_missing_job_fails_loudly() -> None:
    with pytest.raises(ValueError, match="found 0"):
        lefthook_timeout_seconds({HOOK: {"jobs": [{"name": "other", "timeout": "1m"}]}})


def test_a_job_without_a_timeout_fails_loudly() -> None:
    with pytest.raises(ValueError, match="declares no timeout"):
        lefthook_timeout_seconds({HOOK: {"jobs": [{"name": JOB}]}})


def test_a_job_inside_a_group_is_found() -> None:
    config = {
        HOOK: {
            "jobs": [
                {"group": {"parallel": True, "jobs": [{"name": JOB, "timeout": "2m"}]}},
            ]
        }
    }
    assert lefthook_timeout_seconds(config) == 120.0
