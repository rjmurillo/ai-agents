"""The lefthook actionlint hook must share the Issue #2374 severity floor.

Three gates run actionlint: the lefthook pre-commit hook, ``pre_pr.py`` via
``checks_tooling.validate_workflow_yaml``, and ``run_workflow_local_test.py``.
Issue #2374 ruled shellcheck's ``info`` and ``style`` tiers advisory because
the workflow tree carries them on baseline. Two of the three gates raise the
floor to ``warning``; the hook did not, so it blocked any commit that staged
one of the six workflow files carrying baseline advisory findings.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SEVERITY_FLOOR = "--severity=warning"


def _pre_commit_jobs() -> list[dict[str, Any]]:
    config = yaml.safe_load((_REPO_ROOT / "lefthook.yml").read_text(encoding="utf-8"))
    jobs: list[dict[str, Any]] = []

    def collect(items: list[dict[str, Any]]) -> None:
        for item in items:
            group = item.get("group")
            if isinstance(group, dict):
                collect(group.get("jobs", []))
            else:
                jobs.append(item)

    collect(config["pre-commit"]["jobs"])
    return jobs


def _actionlint_job() -> dict[str, Any]:
    matches = [job for job in _pre_commit_jobs() if job.get("name") == "actionlint"]
    assert len(matches) == 1, "expected exactly one actionlint job in pre-commit"
    return matches[0]


def test_the_hook_raises_the_shellcheck_severity_floor() -> None:
    run = _actionlint_job()["run"]

    assert _SEVERITY_FLOOR in run
    assert "SHELLCHECK_OPTS=" in run
    assert "actionlint {staged_files}" in run


def test_the_hook_preserves_an_operator_set_shellcheck_opts() -> None:
    """An operator-set value must be merged, not clobbered.

    ``checks_tooling.validate_workflow_yaml`` prepends the existing value, so
    the hook uses the shell equivalent (``${VAR:+$VAR }``) rather than a bare
    assignment that would discard it.
    """
    run = _actionlint_job()["run"]

    assert "${SHELLCHECK_OPTS:+$SHELLCHECK_OPTS }" in run


def test_the_python_gate_still_applies_the_same_floor() -> None:
    """Pin the other two gates so the three cannot drift apart again."""
    tooling = (
        _REPO_ROOT / "scripts" / "validation" / "checks_tooling.py"
    ).read_text(encoding="utf-8")
    local_test = (
        _REPO_ROOT / "scripts" / "validation" / "run_workflow_local_test.py"
    ).read_text(encoding="utf-8")

    assert _SEVERITY_FLOOR in tooling
    assert _SEVERITY_FLOOR in local_test
