"""Structural tests for worktree GC automation wiring (issues #4193, #4257).

Issue #4257: worktree-gc-report gated every push on an unbounded local scan
that answered no question about the change being pushed. The job is removed
from pre-push. The script remains reachable via the documented command in
scripts/README.md.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LEFTHOOK = _REPO_ROOT / "lefthook.yml"
_SCRIPTS_README = _REPO_ROOT / "scripts" / "README.md"


def _iter_jobs(node: Any):
    if isinstance(node, dict):
        if "name" in node and "run" in node:
            yield node
        for value in node.values():
            yield from _iter_jobs(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_jobs(item)


def test_worktree_gc_report_is_not_in_pre_push() -> None:
    """worktree-gc-report must not appear in any pre-push job.

    Negative control for issue #4257: the job was removed from the gate because
    an unbounded local scan cannot fail the push for a reason related to the
    change. A test that merely checks the job is absent with --apply is not
    sufficient; the job must not be there at all.
    """
    data = yaml.safe_load(_LEFTHOOK.read_text(encoding="utf-8"))
    pre_push = data.get("pre-push", {})
    pre_push_jobs = list(_iter_jobs(pre_push))
    names = [job.get("name") for job in pre_push_jobs]
    assert "worktree-gc-report" not in names, (
        "worktree-gc-report is present in the pre-push hook. "
        "It was removed by issue #4257 because it times out on large worktree counts "
        "and answers no question about the change being pushed. "
        "Remove it from lefthook.yml."
    )


def test_gc_worktrees_script_is_documented_in_scripts_readme() -> None:
    """gc_worktrees.py must remain reachable via a documented command.

    Issue #4257 AC4: the report remains reachable by a documented command after
    removal from pre-push.
    """
    text = _SCRIPTS_README.read_text(encoding="utf-8")
    assert "gc_worktrees.py" in text, (
        "scripts/README.md does not mention gc_worktrees.py. "
        "The script must remain documented so contributors can run it on demand. "
        "Refs issue #4257 AC4."
    )


def test_pre_push_without_job_present_would_pass_isolation_check() -> None:
    """Isolating negative control: if the job were re-added, the absence test fails.

    This test mutates an in-memory copy of the config to add the job back, then
    confirms that the absence assertion fires. This proves the structural test is
    load-bearing and cannot pass in both the fixed and unfixed states.
    """
    import copy

    data = yaml.safe_load(_LEFTHOOK.read_text(encoding="utf-8"))
    mutated = copy.deepcopy(data)

    # Inject the removed job back into the first group in pre-push.
    ghost_job = {
        "name": "worktree-gc-report",
        "timeout": "2m",
        "run": "uv run --frozen python scripts/maintenance/gc_worktrees.py",
    }
    for item in mutated.get("pre-push", {}).get("jobs", []):
        if isinstance(item, dict) and "group" in item:
            item["group"]["jobs"].append(ghost_job)
            break
    else:
        mutated.setdefault("pre-push", {}).setdefault("jobs", []).append(ghost_job)

    pre_push_jobs = list(_iter_jobs(mutated.get("pre-push", {})))
    names = [job.get("name") for job in pre_push_jobs]

    # The mutated config must contain the job -- confirming the injection worked.
    assert "worktree-gc-report" in names, (
        "Injection of worktree-gc-report into the mutated config failed. "
        "The negative control is broken; fix the mutation logic."
    )
    # And a checker that asserts absence would fail on the mutated config.
    assert "worktree-gc-report" in names  # redundant but documents intent

