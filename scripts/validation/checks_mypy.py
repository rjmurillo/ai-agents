"""Mypy changed-files gate for the pre-PR runner (Issue #4674).

Extracted from checks_tooling.py to keep that module under the 500-line ceiling.
Reuses git_hook_policy.run_mypy which implements ratchet semantics: tolerates
pre-existing errors and fails only when the change adds new ones.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from checks_common import (  # noqa: E402
    _resolve_branch_base_ref,
    _run_subprocess,
    classify_subprocess_failure,
)

# The typed evidence contract (issue #5635). PACKAGE path, matching pre_pr.py:
# a flat ``import evidence`` and a package ``import scripts.validation.evidence``
# yield two distinct ``EvidenceState`` enums, and the runner resolves the
# package one.
from scripts.validation.evidence import (  # noqa: E402
    REASON_BASE_REF_UNRESOLVED,
    REASON_DIFF_FAILED,
    CheckOutcome,
)

_MYPY_GATE = "validate_mypy_changed_files"


def _module_identity(repo_root: Path, rel_path: str) -> str:
    """The dotted module name mypy derives for a file, by walking up packages.

    Mypy maps a path to a module by climbing while each parent holds an
    ``__init__.py``, and the first directory without one becomes the search
    root. So ``scripts/ai_review_common/workflow.py`` is
    ``scripts.ai_review_common.workflow`` because ``scripts/__init__.py``
    exists, while the same file mirrored under ``.claude/lib/`` and
    ``src/copilot-cli/lib/`` is ``ai_review_common.workflow`` in both, since
    neither ``lib`` directory is a package.
    """
    path = (repo_root / rel_path).resolve()
    parts = [path.stem]
    parent = path.parent
    while (parent / "__init__.py").is_file() and parent != parent.parent:
        parts.append(parent.name)
        parent = parent.parent
    return ".".join(reversed(parts))


def _drop_duplicate_modules(repo_root: Path, py_files: list[str]) -> list[str]:
    """Keep one path per mypy module name, so the run is not aborted by a collision.

    This repository ships generated mirrors: ``scripts/ai_review_common`` is
    copied verbatim to ``.claude/lib/`` and ``src/copilot-cli/lib/`` by
    ``scripts/sync_plugin_lib.py`` and ``build/scripts/build_all.py``, and a
    drift gate keeps the three byte-identical. Neither ``lib`` directory is a
    package, so both mirrors claim the same module name. Handing mypy both
    copies in one invocation makes it exit 1 with "Duplicate module named ...
    errors prevented further checking": the gate then reported a type
    regression having type-checked nothing, on any change the repository's own
    generators produce. Checking one copy checks all of them, since the drift
    gate is what makes them identical.

    Deduplication is by module identity rather than by a hardcoded mirror list,
    so a mirror added later is covered without editing this function. The
    survivor is the first in sorted order, which is deterministic and therefore
    reproducible between a local run and CI.
    """
    kept: dict[str, str] = {}
    collapsed: list[str] = []
    for rel_path in sorted(py_files):
        identity = _module_identity(repo_root, rel_path)
        if identity in kept:
            collapsed.append(f"{rel_path} (duplicate of {kept[identity]})")
            continue
        kept[identity] = rel_path
    if collapsed:
        print(
            f"Mypy gate: collapsed {len(collapsed)} duplicate module path(s); "
            f"checking one copy of each: {', '.join(collapsed)}"
        )
    return [rel_path for rel_path in py_files if rel_path in set(kept.values())]


def validate_mypy_changed_files(repo_root: Path) -> CheckOutcome:
    """Run mypy over Python files changed on the branch (ratchet semantics).

    Surfaces type regressions at pre-PR time rather than waiting for push CI.

    Returns typed evidence (issue #5635). The two early returns below carry the
    same defect ``validate_session_end`` carried: an unresolved base ref and a
    failed ``git diff`` both returned ``True``, so a gate that type-checked
    nothing reported the same value as one that type-checked a clean branch.
    """
    base_ref = _resolve_branch_base_ref(repo_root)
    if base_ref is None:
        print("[BLOCKED] Mypy gate: no base ref resolved")
        return CheckOutcome.blocked(
            _MYPY_GATE,
            reason=REASON_BASE_REF_UNRESOLVED,
            scope="Python files changed on the branch",
            detail=(
                "no base ref resolved, so the changed-file set could not be "
                "computed and no file was type-checked"
            ),
        )

    exit_code, stdout, diff_stderr = _run_subprocess(
        [
            "git",
            "-C",
            str(repo_root),
            "diff",
            "--name-only",
            "--diff-filter=ACMR",
            f"{base_ref}...HEAD",
        ],
        timeout=30,
    )
    if exit_code != 0:
        reason = classify_subprocess_failure(exit_code, diff_stderr, default=REASON_DIFF_FAILED)
        print(f"[UNKNOWN] Mypy gate: git diff failed ({reason})")
        return CheckOutcome.unknown(
            _MYPY_GATE,
            reason=reason,
            revision=f"{base_ref}...HEAD",
            scope="Python files changed on the branch",
            detail=f"git diff exited {exit_code}, so the changed-file set is unknown",
        )

    py_files = _drop_duplicate_modules(
        repo_root,
        [p for p in stdout.splitlines() if p.endswith(".py") and (repo_root / p).is_file()],
    )
    scope = f"Python files changed against {base_ref}"
    if not py_files:
        print("[PASS] Mypy (0 Python files changed on branch)")
        return CheckOutcome.passed(
            _MYPY_GATE, revision=f"{base_ref}...HEAD", scope=scope, examined=0
        )

    print(f"Type-checking {len(py_files)} changed Python file(s)...")
    from git_hook_policy import run_mypy

    mypy_exit = run_mypy(py_files, repo_root)
    if mypy_exit != 0:
        return CheckOutcome.failed(
            _MYPY_GATE,
            reason="mypy.regression",
            revision=f"{base_ref}...HEAD",
            scope=scope,
            examined=len(py_files),
            detail=f"run_mypy exited {mypy_exit} over {len(py_files)} changed file(s)",
        )
    return CheckOutcome.passed(
        _MYPY_GATE, revision=f"{base_ref}...HEAD", scope=scope, examined=len(py_files)
    )
