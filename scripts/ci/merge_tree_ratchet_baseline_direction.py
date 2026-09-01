"""The one-directional baseline guard for merge-tree-backed ratchets.

Issue #5441 remediation. ``merge_tree_ratchet_check.py``'s ``_check_one``
compares the measured count against ``min(base baseline, merged baseline)``,
so a branch that raises its own baseline without adding a violation still
measures under that lower ceiling and passes. That is by design for the
merge-tree gate (see that module's ``_effective_baseline``), but it means the
merge-tree gate alone never blocks a baseline someone raised for no reason.

``count_ratchet._base_ref_verdict`` is the guard that used to catch this: it
ran once per ratchet in ``scripts/validation/checks_ratchet.py``'s
``RATCHETS`` before this module's five entries were removed from that
registry to stop double-counting (the double-count this issue fixed). Its own
docstring says the two checks are complementary, not redundant: "this check
reads the fork point, which the merge-tree gate never does ... Neither
subsumes the other." ``raised_baseline`` below calls it with a count the
caller already measured, restoring that guard without a second counter run:
only two small ``git show``/``merge-base`` reads per ratchet, not the scan
``current_count`` performs.

Split out of ``merge_tree_ratchet_check.py`` to keep that file under the
taste-lints 500-line ceiling (see ``test_checks_ratchet_merge_tree_backstop.
py``'s docstring for the same reasoning applied to a test file).
"""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

from scripts.ci import count_ratchet

if TYPE_CHECKING:
    from pathlib import Path

    from scripts.ci.merge_tree_ratchet_registry import MergeTreeRatchet


def raised_baseline(
    repo_root: Path,
    base_ref: str,
    ratchet: MergeTreeRatchet,
    count: int | None,
) -> bool:
    """True when this branch itself raised ``ratchet``'s baseline."""
    baseline_path = repo_root / ratchet.baseline_path
    recorded = count_ratchet.read_baseline(baseline_path)
    if recorded is None:
        return False  # _check_one already reported the missing/malformed file
    args = argparse.Namespace(repo_root=repo_root, base_ref=base_ref, baseline=baseline_path)
    verdict = count_ratchet._base_ref_verdict(
        args,
        label=ratchet.label,
        baseline=recorded,
        count=count if count is not None else recorded,
        merge_tree_backed=True,
    )
    return verdict is not None
