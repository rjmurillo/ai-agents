#!/usr/bin/env python3
"""Pre-creation validation pipeline for new_pr.py (issue #4764).

Split out of ``new_pr.py``, which had reached 678 lines carrying both the CLI
and the whole validation pipeline. This module owns the checks that run before
``gh pr create``: the session-log scan, the warning log, the em/en-dash guard,
and the escaped-newline guard.

Loaded by absolute path, never by name
--------------------------------------
``new_pr.py`` runs under ``python3 -I``. The push-pr identity guard requires
that flag, and isolated mode removes the script's own directory from
``sys.path``. Measured on CPython 3.14.6:

    $ python3 -I main.py
    ModuleNotFoundError: No module named 'sibling'

So ``import pr_validations`` cannot work here. ``new_pr.py`` loads this file
with ``importlib.util.spec_from_file_location`` against an absolute path
derived from its own ``__file__``. That keeps the isolation ``-I`` exists to
provide: putting the directory on ``sys.path`` instead would let anyone who can
write into the script directory shadow a stdlib module for this process, which
is a strictly worse position than the one before the split.

The identity guard pins this file's SHA-256 alongside ``new_pr.py`` and
``validate_pr_description.py``, so the bundle is verified as a unit and this
module cannot be swapped independently.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path


def _git_env() -> dict[str, str]:
    """Return environment with git hook override variables stripped."""
    return {
        k: v
        for k, v in os.environ.items()
        if k not in {"GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE"}
    }


def validate_no_escaped_newlines(body_content: str) -> None:
    """Reject a body made from literal backslash-n sequences."""
    escaped_count = body_content.count("\\n")
    if not escaped_count or "\n" in body_content.strip():
        return
    print(
        f"ERROR: Body carries {escaped_count} literal backslash-n"
        " sequence(s) and no line break, so GitHub would render it as one"
        " unbroken paragraph and drop every heading, list and table.",
        file=sys.stderr,
    )
    print(
        "  Write the body to a file and pass --body-file, which cannot"
        " express this error.",
        file=sys.stderr,
    )
    raise SystemExit(1)

# Em/en-dash detection regex for Validation 5. Inlined here rather than
# imported from scripts.validation.pr_description because:
#
# 1. This file is one of two copies the project keeps in sync:
#    - .claude/skills/github/scripts/pr/new_pr.py (the source the
#      developer edits)
#    - src/copilot-cli/skills/github/scripts/pr/new_pr.py (the
#      generated copy produced by build/scripts/build_all.py)
#    Both copies live at different depths from the repo root
#    (parents[5] vs parents[6]), so any cross-package import requires
#    path resolution that works at both depths. The complexity (walking
#    up looking for a marker, subprocess git calls, etc.) is not worth
#    it for a 5-line regex.
# 2. The detection logic is small (compile, search). Drift between the
#    two definitions (this one and scripts.validation.pr_description's
#    _DASH_RE) is caught by the test suite (tests/test_new_pr.py and
#    tests/test_validation_pr_description.py) which exercises both with
#    the same fixtures.
# 3. The two layers serve different purposes: this is the pre-creation
#    guard, scripts.validation.pr_description is the CI fallback. Keeping
#    them independent lets each fail open or fail closed differently per
#    its threat model.
#
# Uses Unicode escape sequences so this source file does not contain
# U+2014 or U+2013 itself per `.claude/rules/universal.md` MUST NOT
# entry 5 (Issue #1923).
_DASH_RE = re.compile("[\u2013\u2014]")

# Extensions the skill-violation scanner (scripts/detect_skill_violation.py)
# actually inspects. Filtering changed files to this set before building the
# scan argv keeps the command line short on large diffs and skips the
# subprocess entirely when no changed file is scannable. This mirrors
# detect_skill_violation.VALID_EXTENSIONS; the two are kept in sync by
# test_new_pr.py, which imports both and asserts equality (same drift-guard
# strategy as _DASH_RE above). A local constant avoids the cross-package
# import path resolution the _DASH_RE comment documents rejecting.
_SKILL_SCAN_EXTENSIONS = frozenset({".md", ".py", ".ps1", ".psm1"})


_SESSION_LOG_FILENAME_RE = re.compile(
    # Canonical filename per session-init script:
    # .agents/sessions/YYYY-MM-DD-session-NN[-keyword1-keyword2-...].{md|json}
    # Keywords are kebab-case (lowercase letters/digits + hyphens only).
    r"^\.agents/sessions/"
    r"\d{4}-\d{2}-\d{2}-session-\d+"
    r"(?:-[a-z0-9-]+)?"
    r"\.(md|json)$"
)


def _extract_validatable_session_logs(
    changed_files: list[str],
) -> tuple[list[str], bool]:
    """Return (JSON session logs, legacy_md_present) from changed files.

    Filename pattern requires YYYY-MM-DD-session-NN prefix to exclude
    tally files like STEP-0-METRICS.md and STEP-0.5-METRICS.md.
    validate_session_json.py only accepts JSON. Legacy .md session logs
    are not validated here and are not migrated by any workflow: the
    ai-session-protocol.yml CI check that once migrated them was retired.
    A session log is optional, so warn the author and move on.

    Returns a tuple so callers can distinguish "no session log at all"
    (both empty) from "legacy .md staged, no JSON to validate locally"
    (validatable empty, has_legacy_md True).
    """
    matched = [f for f in changed_files if _SESSION_LOG_FILENAME_RE.match(f)]
    legacy_md = [f for f in matched if f.endswith(".md")]
    if legacy_md:
        print(
            f"  WARNING: legacy .md session log(s) staged ({legacy_md}); "
            "these are not validated. A session log is optional; if you "
            "keep one, use the JSON format that validate_session_json.py checks.",
            file=sys.stderr,
        )
    return [f for f in matched if f.endswith(".json")], bool(legacy_md)


# Issue #4764: /push-pr must not execute repository-controlled Python to decide
# whether to create a pull request. All three detectors named below live under
# scripts/, which any branch can rewrite, so this script never runs them and
# reports them as not run. CI runs them from a trusted checkout.
#
# Issue #4825 review 4894113215 finding 1: this was previously a helper that
# ignored all three of its arguments and always returned False. It printed
# "Skipped ... because scripts/ is changed or dirty" on a clean branch, did not
# record the skip, and still summarized the run as "All pre-creation
# validations passed!". The boundary is a constant policy, not a runtime
# condition, so it is spelled as one.
_UNTRUSTED_REPOSITORY_VALIDATORS = (
    "Session End (scripts/validate_session_json.py)",
    "skill violation (scripts/detect_skill_violation.py)",
    "test coverage (scripts/detect_test_coverage_gaps.py)",
)
_UNTRUSTED_REPOSITORY_REASON = (
    "repository-local Python is outside the trusted push-pr boundary"
)


def _report_not_run(validator: str) -> None:
    """Name a validator this script deliberately does not run."""
    print(f"  Not run: {validator}.")
    print(f"  Reason: {_UNTRUSTED_REPOSITORY_REASON}; CI runs it from a trusted checkout.")


class _WarningLog:
    """Collect warning-level failures so the summary cannot contradict them.

    Issue #4764: Validation 4 runs ``validate_pr_description.py`` in warning
    mode, so a non-zero exit does not block PR creation. That policy is
    unchanged. What was wrong is that the run then printed

        Trusted pre-creation validations passed.

    directly beneath the validator's own ``ERROR: invalid PR description``.
    Measured against a stub validator exiting 1 at commit 5cd72a7dad.

    The summary is the line a reader scans, so announcing a pass while a check
    failed is a silent failure with extra output. Every warning path feeds this
    log and the summary reports "completed with warnings" when it is non-empty.
    Fixing only Validation 4 would leave the failed-``git diff`` and
    missing-session-log paths equally invisible, which is the partial-guard
    failure mode.
    """

    def __init__(self) -> None:
        self._reasons: list[str] = []

    def record(self, reason: str) -> None:
        self._reasons.append(reason)

    def __bool__(self) -> bool:
        return bool(self._reasons)

    def report(self) -> None:
        """Print the closing summary, qualified by whether anything warned."""
        not_run = ", ".join(_UNTRUSTED_REPOSITORY_VALIDATORS)
        headline = (
            "Trusted pre-creation validations completed with warnings."
            if self._reasons
            else "Trusted pre-creation validations passed."
        )
        print(
            f"{headline} {len(_UNTRUSTED_REPOSITORY_VALIDATORS)} repository-local "
            f"check(s) did not run: {not_run}."
        )
        print(f"  Reason: {_UNTRUSTED_REPOSITORY_REASON}.")
        for reason in self._reasons:
            print(f"  Warning: {reason}")


def run_validations(
    repo_root: str,
    base: str,
    head: str,
    *,
    title: str = "",
    body: str = "",
    body_file: str = "",
) -> None:
    """Run pre-creation validations. Raises SystemExit(1) on failure."""
    warnings = _WarningLog()
    try:
        os.makedirs(os.path.join(repo_root, ".agents"), exist_ok=True)
    except PermissionError as exc:
        print(f"Warning: Could not create .agents directory: {exc}", file=sys.stderr)
        warnings.record(f"could not create .agents directory: {exc}")

    print("Running validations...")
    print()

    # Validation 1: Session End (if .agents/ files changed)
    print("[1/6] Checking Session End protocol...")
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...{head}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        env=_git_env(),
    )
    diff_failed = result.returncode != 0
    if diff_failed:
        print(
            f"  WARNING: 'git diff {base}...{head}' failed (exit {result.returncode}); "
            "the changed-file set is unknown. Validations that rely on it are "
            "skipped, not treated as 'no changes'.",
            file=sys.stderr,
        )
        warnings.record(
            f"'git diff {base}...{head}' failed (exit {result.returncode}); "
            "Validations 1 and 2 examined an unknown changed-file set"
        )
    changed_files = result.stdout.strip().splitlines() if not diff_failed else []
    agents_changed = any(f.startswith(".agents/") for f in changed_files)

    if agents_changed:
        session_logs, has_legacy_md = _extract_validatable_session_logs(
            changed_files
        )
        if session_logs:
            _report_not_run(_UNTRUSTED_REPOSITORY_VALIDATORS[0])
        elif has_legacy_md:
            # A legacy .md log leaves nothing for this run to validate, so the
            # summary must say so. Printing the warning without recording it
            # reproduced the exact defect issue #4764 filed against Validation
            # 4: a WARNING line on stderr under an unqualified pass headline.
            warnings.record(
                "only legacy .md session log(s) staged; no JSON session log was validated here"
            )
        else:
            print("  WARNING: No session log found but .agents/ files changed", file=sys.stderr)
            warnings.record("no session log found but .agents/ files changed")
    elif diff_failed:
        print("  Skipped: git diff failed, changed files unknown (see warning above).")
    else:
        print("  No .agents/ changes, skipping")

    # Validation 2: Skill violation detection (WARNING)
    print()
    print("[2/6] Checking for skill violations...")
    scannable_files = [f for f in changed_files if Path(f).suffix in _SKILL_SCAN_EXTENSIONS]
    _report_not_run(_UNTRUSTED_REPOSITORY_VALIDATORS[1])
    if diff_failed:
        print("  Scope: unknown, git diff failed (see warning above).")
    elif not changed_files:
        print("  Scope: no changed files.")
    elif not scannable_files:
        _exts = ", ".join(sorted(_SKILL_SCAN_EXTENSIONS))
        print(f"  Scope: no changed file has a scannable extension ({_exts}).")
    else:
        print(f"  Scope: {len(scannable_files)} changed file(s) would have been scanned.")

    # Validation 3: Test coverage detection (WARNING)
    print()
    print("[3/6] Checking test coverage...")
    _report_not_run(_UNTRUSTED_REPOSITORY_VALIDATORS[2])

    # Validation 4: PR Description validation (WARNING)
    print()
    print("[4/6] Validating PR description...")
    validate_script = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "validate_pr_description.py",
    )
    if os.path.exists(validate_script) and title:
        val_args = [sys.executable, "-I", validate_script, "--title", title]
        if body:
            val_args.extend(["--body", body])
        elif body_file:
            val_args.extend(["--body-file", body_file])
        val_result = subprocess.run(
            val_args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        # Print human-readable output (on stderr from validator)
        if val_result.stderr:
            print(val_result.stderr, end="", file=sys.stderr)
        # Warning mode: a non-zero exit does NOT block creation. It is recorded
        # so the closing summary cannot report an unqualified pass over it
        # (issue #4764). Changing this to a block would be a policy change; the
        # CI-side validator is the blocking layer.
        if val_result.returncode != 0:
            warnings.record(
                f"validate_pr_description.py exited {val_result.returncode} "
                "(warning mode: PR creation continues)"
            )
    else:
        print("  Skipped (no title available or validator not found)")

    # Validation 5: Em/en-dash check (CRITICAL, blocks creation)
    # PR descriptions live in GitHub and never reach Git hook stdin, so the
    # Lefthook jobs declared in lefthook.yml cannot scan them.
    # This is the shift-left guard that prevents dashes from being submitted
    # at all. Closes the gap that allowed PR #1930 to ship with em/en-dashes
    # in the description despite local dash checks.
    # Rule: .claude/rules/universal.md MUST NOT entry 5. Refs Issue #1923.
    print()
    print("[5/6] Em/en-dash check on title and body...")
    body_content = body or ""
    if not body_content and body_file and os.path.exists(body_file):
        try:
            with open(body_file, encoding="utf-8") as f:
                body_content = f.read()
        except OSError as exc:
            print(f"  WARNING: Could not read body file: {exc}", file=sys.stderr)
            warnings.record(f"could not read body file: {exc}")
    dash_violations: list[str] = []
    if _DASH_RE.search(title):
        dash_violations.append("title")
    body_dash_lines = [
        f"line {n}"
        for n, line in enumerate(body_content.splitlines(), start=1)
        if _DASH_RE.search(line)
    ]
    if body_dash_lines:
        sample = ", ".join(body_dash_lines[:5])
        if len(body_dash_lines) > 5:
            sample += f", ... (+{len(body_dash_lines) - 5} more)"
        dash_violations.append(f"body ({sample})")
    if dash_violations:
        print(
            "ERROR: Em-dash (U+2014) or en-dash (U+2013) found in: "
            + "; ".join(dash_violations),
            file=sys.stderr,
        )
        print(
            "  Replace with comma, period, hyphen, or restructure.",
            file=sys.stderr,
        )
        print(
            "  Rule: .claude/rules/universal.md MUST NOT entry 5 (Issue #1923).",
            file=sys.stderr,
        )
        print(
            "  Override (NOT RECOMMENDED): re-run with --skip-validation"
            " --audit-reason \"...\".",
            file=sys.stderr,
        )
        raise SystemExit(1)
    print("  No prohibited characters in title or body.")

    print()
    print("[6/6] Escaped-newline check on body...")
    validate_no_escaped_newlines(body_content)
    print("  Body line breaks are real newlines.")

    print()
    warnings.report()
    print()
