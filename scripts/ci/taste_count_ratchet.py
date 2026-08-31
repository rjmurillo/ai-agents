#!/usr/bin/env python3
"""Whole-repo taste-lint error-count ratchet (issue #3779).

``taste_lints.py`` exits 10 when it finds an error-severity violation, and
nothing in the repository has ever read that. ``run_taste_advisory`` in
``scripts/validation/git_hook_policy.py`` captures the exit code, prints
"findings are advisory", and returns 0; no workflow calls the linter at all. So
the ``error`` severity is decorative, and every commit touching a large file
prints an error the author correctly learns to ignore. That is the same training
signal that teaches people to ignore the naming and complexity rules riding in
the same output.

Existing debt is recorded in ``taste_count_baseline.txt``, measured with the
linter itself rather than a reimplementation of it. This freezes the ceiling
and blocks growth, the same shape ``ruff_count_ratchet.py`` uses for lint debt.
Every currently-failing file keeps passing on day one and no contributor's
existing work breaks, but the count cannot rise.

Scope is git-TRACKED files. The linter's own ``--directory`` mode walks the
filesystem with ``os.walk`` and no exclusions, so it would count untracked
scratch, nested worktrees, and vendored caches that happen to be on disk. That
is the phantom-count failure ``ruff_count_ratchet.py`` was written to avoid.

Every tracked path is passed in, not a filtered subset: ``run_lint`` already
skips anything outside its scannable-extension set, so filtering here would
duplicate that list and let the two drift.

Stdlib only: this runs by path in CI and must not depend on the project's
import graph.

Exit codes (AGENTS.md contract):
    0 - ok (count <= baseline, or --update records a decrease)
    1 - regression (count > baseline, or baseline raised vs --base-ref)
    2 - config error (baseline missing or malformed, bad args)
    3 - external error (the linter could not run)
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.ci.count_ratchet import (
    EXIT_CONFIG,
    EXIT_EXTERNAL,
    EXIT_OK,
    EXIT_REGRESSION,
    build_parser,
    chunk,
    run,
    tracked_files,
)

__all__ = [
    "EXIT_CONFIG",
    "EXIT_EXTERNAL",
    "EXIT_OK",
    "EXIT_REGRESSION",
    "MERGE_TREE_BACKED",
    "current_count",
    "main",
]

_BASELINE_PATH = Path(__file__).with_name("taste_count_baseline.txt")

MERGE_TREE_BACKED = True
"""This baseline is registered in ``merge_tree_ratchet_registry.py::RATCHETS``.

Registration is what lets ``count_ratchet.run`` pass a branch that merely holds
a number ``main`` lowered underneath it: the merged result is measured by
``scripts/ci/merge_tree_ratchet_check.py`` instead. Pinned against the registry
by ``tests/ci/test_merge_tree_backing_declarations.py``.
"""

_LINTER = Path(".claude/skills/taste-lints/scripts/taste_lints.py")

# taste_lints.py exit contract: 0 clean, 1 script error, 10 violations found.
# Only 0 and 10 mean the scan produced a trustworthy count.
_EXIT_CLEAN = 0
_EXIT_VIOLATIONS = 10


def current_count(repo_root: Path) -> int | None:
    """Total tracked-file error-severity violations, or None if the scan failed.

    Returning None rather than 0 on any failure is load-bearing. A zero from a
    crashed linter would look like a clean tree, and ``--update`` would write
    that zero into the baseline and permanently disarm the gate.

    "Any failure" includes a report that parsed as JSON but is not a mapping.
    ``format_json`` in ``.claude/skills/taste-lints/scripts/taste_lints.py``
    only ever emits an object, so a list, a string, or a bare null came from
    something else. Reading ``error_count`` off one raised ``AttributeError``,
    and the traceback left the process exiting 1: the ratchet's own code for a
    REGRESSION. An unreadable report is an external error and must exit 3, or a
    broken linter reads as new violations a contributor cannot find.
    """
    files = tracked_files(repo_root, ("*",))
    if files is None:
        return None
    if not files:
        return 0

    total = 0
    for batch in chunk(files):
        try:
            proc = subprocess.run(
                [sys.executable, str(_LINTER), "--format", "json", "--", *batch],
                cwd=repo_root,
                capture_output=True,
                text=True,
                errors="replace",
                encoding="utf-8",
                check=False,
            )
        except (FileNotFoundError, OSError) as exc:
            sys.stderr.write(f"taste-lints could not be launched: {exc}\n")
            return None
        if proc.returncode not in (_EXIT_CLEAN, _EXIT_VIOLATIONS):
            sys.stderr.write(f"taste-lints exited {proc.returncode}, which is not a scan result\n")
            sys.stderr.write(proc.stderr)
            return None
        try:
            report = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            sys.stderr.write(f"taste-lints emitted unparseable JSON: {exc}\n")
            return None
        if not isinstance(report, dict):
            sys.stderr.write("taste-lints report was not a JSON object\n")
            return None
        count = report.get("error_count")
        if not isinstance(count, int):
            sys.stderr.write("taste-lints report has no integer error_count\n")
            return None
        total += count
    return total


_REQUIRED_FIELDS = ("severity", "file", "rule", "message")


def _batch_findings(repo_root: Path, batch: Sequence[str]) -> list[object] | None:
    """The ``violations`` list from one linter batch, or None when unusable.

    Canonical shape, quoted from ``format_json`` in
    ``.claude/skills/taste-lints/scripts/taste_lints.py``::

        data = {
            "files_scanned": result.files_scanned,
            "files_by_category": result.files_by_category,
            "error_count": result.error_count,
            "warning_count": result.warning_count,
            "violations": [ ... for v in result.violations ],
        }

    So the top level is always an object and ``violations`` is always a list.
    A report that is neither did not come from a healthy run of that emitter,
    and reading it as "no violations" would report a clean tree from a broken
    scan: the same silent diagnostic this work exists to remove. Both shapes
    return None and name themselves on stderr instead.

    Reading them as empty was not theoretical. A report keyed ``findings`` (the
    name this lister used before #3902) rendered nothing at all, and a report
    whose ``violations`` value was null or a number raised ``TypeError``
    straight out of the pre-push hook.

    Every ``return None`` leg names its cause. ``run`` prints the list under
    ``if violations:``, so a lister that returns None prints exactly as much as
    a clean tree: nothing.
    """
    try:
        proc = subprocess.run(
            [sys.executable, str(_LINTER), "--format", "json", "--", *batch],
            cwd=repo_root,
            capture_output=True,
            text=True,
            errors="replace",
            encoding="utf-8",
            check=False,
        )
    except (FileNotFoundError, OSError) as exc:
        sys.stderr.write(f"taste-lint diagnostic unavailable: {exc}\n")
        return None
    if proc.returncode not in (_EXIT_CLEAN, _EXIT_VIOLATIONS):
        sys.stderr.write(f"taste-lint diagnostic unavailable: linter exit {proc.returncode}\n")
        sys.stderr.write(proc.stderr)
        return None
    try:
        report = json.loads(proc.stdout)
    except json.JSONDecodeError:
        sys.stderr.write("taste-lint diagnostic unavailable: linter output was not JSON\n")
        return None
    if not isinstance(report, dict):
        sys.stderr.write("taste-lint diagnostic unavailable: report was not a JSON object\n")
        return None
    findings = report.get("violations")
    if not isinstance(findings, list):
        sys.stderr.write("taste-lint diagnostic unavailable: report carried no violations list\n")
        return None
    return findings


def _violation_fields(finding: object) -> dict[str, str] | None:
    """The four fields a rendered line needs, or None when the entry is malformed.

    ``Violation`` in ``.claude/skills/taste-lints/scripts/taste_lints.py``
    declares ``rule: str``, ``severity: str``, ``file: str``, ``line: int``,
    ``message: str``, ``remediation: str``, ``category: str``, and
    ``format_json`` copies each field straight across. Every entry from a
    healthy scan therefore carries all four names this renders, each a string.

    An entry that does not is a broken emitter, not a violation to describe,
    and the old fallbacks hid exactly that: a missing ``file`` rendered
    ``"?: [file-size] ..."`` and a missing ``rule`` and ``message`` rendered
    ``"a.md: [?] "``. Both look like real diagnostic output, so a contributor
    read a line that named no file and went looking for a violation the
    renderer had already lost. Naming the cause once beats printing a screen of
    placeholders.

    Every entry is checked, warnings included. The severity filter runs on the
    caller's side of this, so a malformed warning is still a malformed report
    and still means the list cannot be trusted.
    """
    if not isinstance(finding, dict):
        sys.stderr.write(
            "taste-lint diagnostic unavailable: a violation entry was not a JSON object\n"
        )
        return None
    fields: dict[str, str] = {}
    for name in _REQUIRED_FIELDS:
        value = finding.get(name)
        if not isinstance(value, str):
            sys.stderr.write(
                f"taste-lint diagnostic unavailable: a violation entry has no string {name}\n"
            )
            return None
        fields[name] = value
    return fields


def list_violations(
    repo_root: Path, priority_paths: frozenset[str] = frozenset()
) -> list[str] | None:
    """Return a human-readable line per error-severity violation, or None.

    Used by the ratchet to show WHICH violations are present on regression so
    contributors do not need a separate run to find them (issue #3902).

    Violations in ``priority_paths`` come first. The ratchet caps the printed
    list at 40 lines and this repository carries 601 tracked violations, so
    emission order alone buries the branch's own violation: on issue #3902's PR
    the one added violation was at index 596 and never printed. Ordering is
    stable within each group, so the rest of the list keeps scan order.

    None means the scan could not be read, which is not the same as a clean
    tree and never renders as one. Every leg that returns it says why.
    """
    files = tracked_files(repo_root, ("*",))
    if files is None:
        return None
    if not files:
        return []

    lines: list[str] = []
    deferred: list[str] = []
    for batch in chunk(files):
        findings = _batch_findings(repo_root, batch)
        if findings is None:
            return None
        # Each item carries "file", not "path". Reading "path" here rendered
        # every line as "?" while still looking like a working diagnostic.
        for finding in findings:
            fields = _violation_fields(finding)
            if fields is None:
                return None
            if fields["severity"] != "error":
                continue
            target = lines if fields["file"] in priority_paths else deferred
            target.append(f"{fields['file']}: [{fields['rule']}] {fields['message']}")
    return lines + deferred


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser(
        "Whole-repo taste-lint error-count ratchet (issue #3779).", _BASELINE_PATH
    )
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    return run(
        args,
        label="taste count ratchet",
        counter=current_count,
        scan_error="taste-lints failed to run",
        regression_advice=(
            "New error-severity taste violations cannot merge. Fix them, or add a "
            "reasoned `# taste-lint: ignore <rule>` comment in the first 10 lines "
            "of the file explaining why the rule does not apply (issue #3779)."
        ),
        lister=list_violations,
        merge_tree_backed=MERGE_TREE_BACKED,
    )


if __name__ == "__main__":
    sys.exit(main())
