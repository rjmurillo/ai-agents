#!/usr/bin/env python3
"""Gate: generated output is stale relative to its sources.

CI has asked this question since REQ-003-005. The canonical CI source is
``.github/workflows/validate-generated-agents.yml``, step "Build-all staleness
check (REQ-003-005)", which runs verbatim::

    uv run python build/scripts/build_all.py --check

and step "Plugin lib sync check (M7-T1)", which runs verbatim::

    uv run python scripts/sync_plugin_lib.py --check

``scripts/validation/pre_pr.py`` ran neither. Its only ``build_all.py``
reference was ``validate_no_orphaned_build_deferrals``, which reads the
deferral comments inside that file's source and says nothing about whether the
generated tree matches its inputs. Those are different questions, so a
hand-edit to a generated file passed every local gate and failed in CI.

Measured cost on PR #5059: round-cap wiring was hand-edited into
``src/copilot-cli/skills/pr-autofix/SKILL.md``, which is generated from
``.claude/commands/pr-autofix.md``. 26 of 26 skill tests passed,
``build/generate_agents.py --validate`` passed (a different generator pair that
does not cover skills), and ``pre_pr.py`` reported unrelated findings only. CI
then showed the generator stripping all 43 lines of the wiring. The feature
would have merged as a silent no-op. Issue #5079.

Order is the contract, not a call
---------------------------------

``.claude/rules/generated-artifacts.md`` ("Generator order: sync before build")
requires ``scripts/sync_plugin_lib.py`` to run before
``build/scripts/build_all.py``. ``build_all.py`` reads ``.claude/lib/`` and
never populates it, so a change under ``scripts/github_core/`` reaches
``src/copilot-cli/lib/`` only once the sync has run. Run in the other order,
both scripts exit 0 and there is no local signal at all.

This gate honors that order and stops at the first failure. A stale
``.claude/lib/`` makes ``build_all --check`` compare the Copilot mirror against
input that is itself out of date, so its verdict carries no information until
the sync check is clean. Reporting the sync failure alone is the honest result,
and the examined count says so.

The rule also forbids resolving this by having ``build_all.py`` invoke
``sync_plugin_lib.py``: REQ-003-010 bars generators from writing under
``.claude/``, and the sync writes there by design. Both scripts run here in
``--check`` mode, which is read-only. ``build_all.py --check`` snapshots and
restores the trees it owns (issue #2440), and ``sync_plugin_lib.py --check`` is
a dry run.

Stricter/looser/different than canonical: CI runs the two checks as separate
steps and in the opposite order (build_all at line 158, sync at line 209),
which is safe there because each step reports independently. This gate runs
them in one process in the rule's order so the first reported failure is the
one a contributor must fix first.

Exit codes (ADR-035):
    0 - Success (no staleness detected)
    1 - Logic error (a generator check reported drift)
    2 - Config error (invalid repository root, or a checked script is absent)
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Ordered per .claude/rules/generated-artifacts.md "Generator order: sync
# before build". Each row is (label, repo-relative script path). Changing the
# order breaks the contract this module exists to honor.
_CHECKS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("sync_plugin_lib.py --check", ("scripts", "sync_plugin_lib.py")),
    ("build_all.py --check", ("build", "scripts", "build_all.py")),
)

# The gate runs as one lefthook job among two dozen parallel ones, so size the
# cap for a loaded machine rather than the 4.4s a standalone run measures
# (.claude/rules/ci-scripts.md MUST 16).
_CHECK_TIMEOUT_SECONDS = 600

_MAX_OUTPUT_LINES = 40


def _echo_tail(output: str) -> None:
    """Print the tail of a child's combined output, bounded against flooding.

    The tail, not the head. ``build_all.py`` writes several hundred lines of
    per-file generation progress to stdout and its ``STALENESS DETECTED`` block
    to stderr, so a head-bounded echo shows the progress and drops the reason.
    Callers concatenate stdout then stderr, which puts the diagnosis last.
    """
    text = output.strip()
    if not text:
        return
    lines = text.splitlines()
    if len(lines) > _MAX_OUTPUT_LINES:
        print(f"  ... {len(lines) - _MAX_OUTPUT_LINES} earlier line(s) omitted")
    for line in lines[-_MAX_OUTPUT_LINES:]:
        print(line)
    sys.stdout.flush()


def _run_check(script: Path, repo_root: Path) -> tuple[int, str]:
    """Run one generator in ``--check`` mode. Returns (exit code, output).

    A timeout is a failure, not a pass: the caller must not read a killed child
    as a clean tree.
    """
    try:
        result = subprocess.run(
            [sys.executable, str(script), "--check"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_CHECK_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return -1, f"{script.name} --check exceeded {_CHECK_TIMEOUT_SECONDS}s"
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def validate_generated_staleness(repo_root: Path) -> bool:
    """Return True when no generator's output is stale relative to its sources.

    Entry point matching the ``validate_*(repo_root) -> bool`` contract used by
    ``pre_pr_sequence``. Fails closed when a checked script is absent: a silent
    skip would defeat the point of registering the gate.

    Prints the examined count next to the failure count so a caller can tell
    "no drift across two checks" from "nothing was checked"
    (.claude/rules/ci-scripts.md MUST 11 and MUST 12).
    """
    examined = 0
    for label, parts in _CHECKS:
        script = repo_root.joinpath(*parts)
        if not script.is_file():
            print(
                f"[ERROR] {script} is absent; the generated-staleness gate "
                f"cannot run. Examined {examined} of {len(_CHECKS)} checks.",
                file=sys.stderr,
            )
            return False

        exit_code, output = _run_check(script, repo_root)
        examined += 1
        if exit_code != 0:
            # Only on failure. A clean run's several hundred lines of generator
            # progress would bury every other gate's output in pre_pr.py.
            _echo_tail(output)
            remaining = len(_CHECKS) - examined
            unrun = (
                f" The remaining {remaining} check(s) did not run: their input "
                f"is not yet known good."
                if remaining
                else ""
            )
            print(
                f"[FAIL] {label} reported staleness (exit {exit_code}). "
                f"Examined {examined} of {len(_CHECKS)} checks.{unrun}",
                file=sys.stderr,
            )
            print(
                "Fix: run the generators in order, then commit the result:\n"
                "  uv run python scripts/sync_plugin_lib.py\n"
                "  uv run python build/scripts/build_all.py",
                file=sys.stderr,
            )
            return False

    print(f"generated staleness: 0 stale in {examined} generator check(s) examined")
    return True


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns an ADR-035 exit code."""
    args = argv if argv is not None else sys.argv[1:]
    repo_root = Path(args[0]).resolve() if args else Path(__file__).resolve().parents[2]
    if not repo_root.is_dir():
        print(f"[FAIL] Invalid repository root: {repo_root}", file=sys.stderr)
        return 2
    return 0 if validate_generated_staleness(repo_root) else 1


if __name__ == "__main__":
    raise SystemExit(main())
