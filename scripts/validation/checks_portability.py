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


def _run_portability_validator(
    repo_root: Path, relative: str, module: str = "", *extra_args: str
) -> bool:
    """Run one portability validator and report whether it exited clean.

    The four validators below share a CLI: a single ``--repo-root`` and an exit
    code of 0 for clean, non-zero for drift or a configuration error. One runner
    for all four keeps a fifth from arriving as a fifth near-identical copy.
    ``extra_args`` appends flags after ``--repo-root`` for a wrapped script
    whose validate-only behavior needs one, e.g. ``generate_skills.py
    --validate`` for :func:`validate_skill_template_drift`.

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
        [sys.executable, *target, "--repo-root", str(repo_root), *extra_args],
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
    return _run_portability_validator(repo_root, "scripts/validation/check_skill_contract_tests.py")


def validate_skill_template_drift(repo_root: Path) -> bool:
    """Fail when a template-owned SKILL.md differs from its rendered template.

    Wraps ``build/scripts/generate_skills.py --validate`` (ADR-108). That flag
    renders every ``templates/skills/<name>.SKILL.md.tmpl`` in memory and
    compares the result, byte for byte, against the committed
    ``.claude/skills/<name>/SKILL.md``; it never writes. Exit 0 covers both "no
    template exists yet" (an empty ``templates/skills/`` directory, the state
    this repository is in before the pilot templates land in TASK-026) and
    "every render matches its committed file". Exit 1 or 2 names the drifted or
    malformed file on stdout/stderr, printed by the shared runner below.

    Same shape as :func:`validate_skill_contract_tests` above: a subprocess
    wrapper around a script with its own ``--repo-root``/exit-code CLI, run
    through :func:`_run_portability_validator` so a fifth near-identical copy
    of that plumbing does not accrete here (see the module docstring). The
    ``--validate`` flag is passed as an extra arg, since this is the one
    caller in this module whose wrapped script needs one.

    Unlike the other three validators in this module, the wrapped script is
    ``build/scripts/generate_skills.py``, not a ``scripts/validation/*`` file,
    because the drift predicate DESIGN-024 specifies
    (``.agents/specs/design/DESIGN-024-skill-guidance-excerpt-sync.md``,
    "Wiring": "``scripts/validation/checks_portability.py``:
    ``validate_skill_template_drift(repo_root)`` wrapping
    ``generate_skills.py --validate``") lives in the generator that already
    owns rendering, not in a second copy of the compile logic.
    """
    return _run_portability_validator(
        repo_root, "build/scripts/generate_skills.py", "", "--validate"
    )


def validate_agent_template_drift(repo_root: Path) -> bool:
    """Fail when a rendered src/claude/agents file differs from its template.

    Wraps ``build/scripts/agent_templates.py --validate`` (ADR-109 B1), the
    agents counterpart of :func:`validate_skill_template_drift` above: it
    renders every ``templates/agents/<stem>.claude.md.tmpl`` in memory and
    compares the result, byte for byte, against the committed
    ``src/claude/agents/<stem>.md``; it never writes. Exit 0 covers "no
    template pair exists" and "every render matches". Exit 1 or 2 names the
    drifted or malformed file, printed by the shared runner.
    """
    return _run_portability_validator(
        repo_root, "build/scripts/agent_templates.py", "", "--validate"
    )
