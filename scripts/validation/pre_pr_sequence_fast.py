#!/usr/bin/env python3
"""Fast structural gates that open the pre-PR sequence (issue #4251).

Six sub-second, repo-wide checks that run before anything slower. They share a
property the rest of the sequence does not: each one scans the whole tracked
tree, costs well under a second, and blocks the push on its own. Running them
first means the cheapest push-blocking signal arrives before a contributor
spends minutes on the full suite.

Extracted from ``pre_pr_sequence`` when that module crossed the 500-line taste
ceiling. The grouping is by cost and blast radius, not by convenience: adding a
seventh whole-tree sub-second gate belongs here, and a slow or narrowly scoped
check does not.

Validators are imported from the ``check*`` sibling modules rather than from
``pre_pr``, which runs as ``__main__`` when invoked as a script; importing it by
name would load a second copy of that module. ``run_validation`` and ``state``
are injected by the caller for the same reason.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from check_duplicate_test_helpers import validate_duplicate_test_helpers  # noqa: E402
from check_nested_tests import validate_no_nested_tests  # noqa: E402
from check_test_tree_writes import validate_test_tree_writes  # noqa: E402
from check_unreachable_code import validate_unreachable_code  # noqa: E402
from checks_ratchet import validate_count_ratchets  # noqa: E402
from validate_python_syntax import validate_python_syntax  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = ["ValidationStateLike", "run_fast_gates"]


class ValidationStateLike(Protocol):
    """Structural view of ``pre_pr.ValidationState`` the sequence writes to.

    Typed structurally rather than imported from ``pre_pr`` so neither this
    module nor ``pre_pr_sequence`` references ``pre_pr``. ``pre_pr`` imports the
    sequence; a back-reference would make mypy resolve ``pre_pr`` under two
    module names (Issue #3073).
    """

    total: int
    skipped: int


def run_fast_gates(
    repo_root: Path,
    state: ValidationStateLike,
    run_validation: Callable[..., bool],
) -> None:
    """Run the six whole-tree sub-second gates, recording into ``state``.

    Takes no ``args``: none of these gates is skippable. A gate cheap enough to
    always run has no reason to read ``--quick`` or ``--skip-tests``, and
    threading the namespace through would invite one to start.
    """
    # Blocking parse gate over every tracked .py file (issue #2655). A
    # SyntaxError in a hook module wedges the CLI, because the PreToolUse
    # dispatcher fails closed on import. Ruff and pytest never caught PR #2640:
    # ruff is advisory and nothing imports those modules. Runs first because it
    # is both the cheapest and the highest-impact defect in the set.
    run_validation(
        "Python Syntax (compile gate)",
        state,
        lambda: validate_python_syntax(repo_root),
    )

    # Count ratchets (issue #4251). Before these ran here, a contributor saw
    # pre_pr.py pass, pushed, and learned 674 seconds later that a 0.21 second
    # ratchet had failed, because the ratchets ran only in the pre-push group
    # alongside the full suite.
    run_validation(
        "Count Ratchets",
        state,
        lambda: validate_count_ratchets(repo_root),
    )

    run_validation(
        "Nested Test Detection",
        state,
        lambda: validate_no_nested_tests(repo_root),
    )

    run_validation(
        "Duplicate Test Helper Detection",
        state,
        lambda: validate_duplicate_test_helpers(repo_root),
    )

    run_validation(
        "Unreachable Code Detection",
        state,
        lambda: validate_unreachable_code(repo_root),
    )

    run_validation(
        "Test Working Tree Writes",
        state,
        lambda: validate_test_tree_writes(repo_root),
    )
