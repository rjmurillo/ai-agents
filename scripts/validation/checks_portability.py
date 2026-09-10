#!/usr/bin/env python3
"""Skill-portability gates that mirror the Validate Vendor Portability job.

The CI job ``.github/workflows/validate-vendor-portability.yml`` runs six
validators. Two of them, ``check_vendor_portability.py`` and
``check_skill_md_portability.py``, have lived in ``checks_spec.py`` since the
pre-PR runner was split up (issue #2223) and stay there: their wrappers are
imported by name from ``checks_spec`` and from ``pre_pr`` in several tests, and
moving them would be churn in files this change has no other reason to touch.

The other four had no pre-PR gate at all, which is issue #5670: ``pre_pr.py``
reported all 65 gates green on ``fix/4462-squash-merge-audit`` while
``check_skill_portability`` exited 1 for a skill script with no baseline entry.
They live here rather than in ``checks_spec.py`` because adding them there took
that file from 478 to 568 lines, past the 500-line ceiling
``scripts/ci/taste_count_ratchet.py`` enforces.

A seventh validator belongs in this file.
``tests/validation/test_pre_pr_covers_vendor_portability.py`` reads the workflow
and fails until one exists for it, wherever it is defined.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from checks_common import (  # noqa: E402
    MissingScriptSkip,
    _run_subprocess,
)


def _run_portability_validator(repo_root: Path, relative: str, module: str = "") -> bool:
    """Run one portability validator and report whether it exited clean.

    The four validators below share a CLI: a single ``--repo-root`` and an exit
    code of 0 for clean, non-zero for drift or a configuration error. One runner
    for all four keeps a fifth from arriving as a fifth near-identical copy.

    ``cwd`` is the repository root so the ``-m`` form resolves the
    ``scripts.validation`` package the way the CI job does. It is passed for the
    script form too: the CI job runs from the repository root, so a validator
    that ever reads a relative path reads it from the same place locally.

    Existence is checked against the file even when ``module`` is set, because a
    missing module raises inside the child, where it reads as a plain non-zero
    exit rather than as the deliberate skip ``MissingScriptSkip`` encodes.
    """
    script = repo_root / relative
    if not script.exists():
        raise MissingScriptSkip(f"{relative} not present")
    target = ["-m", module] if module else [str(script)]
    exit_code, stdout, stderr = _run_subprocess(
        [sys.executable, *target, "--repo-root", str(repo_root)],
        cwd=repo_root,
    )
    output = (stdout or "") + (stderr or "")
    if output.strip():
        for line in output.strip().splitlines()[:40]:
            print(line)
    return bool(exit_code == 0)


def validate_skill_script_portability(repo_root: Path) -> bool:
    """Fail when a skill script's upstream-only path count exceeds its baseline.

    Wraps ``scripts.validation.check_skill_portability``, the per-script ratchet
    keyed on ``scripts/validation/skill_portability_baseline.json``. A new script
    has no baseline entry, so its allowed count is 0 and any hard-coded upstream
    path fails the gate.

    Invoked as a module, matching the CI job. The script form happens to work
    too, but the two are not interchangeable in general, and a local gate that
    runs a different command from the CI job is how a branch comes to pass
    locally and fail remotely (issue #5670).
    """
    return _run_portability_validator(
        repo_root,
        "scripts/validation/check_skill_portability.py",
        module="scripts.validation.check_skill_portability",
    )


def validate_skill_md_exec_portability(repo_root: Path) -> bool:
    """Fail when a skill .md adds a new bare-exec upstream path (issue #2838).

    Wraps ``scripts/validation/check_skill_md_exec_portability.py``. Distinct
    from ``checks_spec.validate_skill_md_portability``: this ratchet counts the
    paths a reader would execute, where a stale out-of-repo copy runs instead of
    the shipped one, rather than every path a document mentions.
    """
    return _run_portability_validator(
        repo_root, "scripts/validation/check_skill_md_exec_portability.py"
    )


def validate_skill_resolver_anchoring(repo_root: Path) -> bool:
    """Fail when a SKILL.md script-path resolver can select a stale copy.

    Wraps ``scripts/validation/check_skill_resolver_anchoring.py``. A resolver
    that walks candidate roots until one contains the scripts directory picks an
    out-of-repo checkout when the process happens to start next to one, so the
    skill silently runs code the PR did not change.
    """
    return _run_portability_validator(
        repo_root, "scripts/validation/check_skill_resolver_anchoring.py"
    )


def validate_skill_contract_tests(repo_root: Path) -> bool:
    """Fail when a SKILL.md documents an executable contract no test binds.

    Wraps ``scripts/validation/check_skill_contract_tests.py``. A SKILL.md that
    names a script, an exit code, and a meaning is a specification. With nothing
    reading it back, the script drifts away from it and every gate stays green,
    because prose does not go red.
    """
    return _run_portability_validator(
        repo_root, "scripts/validation/check_skill_contract_tests.py"
    )
