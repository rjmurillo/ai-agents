#!/usr/bin/env python3
"""Unified shift-left validation runner for pre-PR checks.

Runs all local validations before creating a pull request.
Executes validations in optimized order (fast checks first).

Validation sequence:
    1. Session End (for latest session log)
    2. Pester Tests (all unit tests)
    3. Markdown Lint (auto-fix and validate)
    4. Workflow YAML (validate GitHub Actions workflows)
    5. Design Review Frontmatter (validate DESIGN-REVIEW YAML frontmatter)
    6. Build Command Exit Gates (PR #1887 retrospective Layer 2)
    7. Canonical Citation Check (heuristic mirror-claim citation; soft warn)
    7b. Spec Contradiction Check (PR/issue vs committed frontmatter; advisory)
    8. YAML Style (check YAML style with yamllint) [skip if --quick]
    9. Path Normalization (check for absolute paths) [skip if --quick, requires PS1]
   10. Planning Artifacts (validate planning consistency) [skip if --quick, requires PS1]
   11. Agent Drift (detect semantic drift) [skip if --quick, requires PS1]

Exit codes follow ADR-035:
    0 - Success (all validations passed)
    1 - Logic error (one or more validations failed)
    2 - Config error (environment or configuration issue)
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

# Frontmatter parsing and DESIGN-REVIEW validation live in sibling modules
# (issue #2223). Re-exported here so ``_parse_yaml_frontmatter`` and
# ``validate_design_review_frontmatter`` stay importable from ``pre_pr``.
from validate_design_review import (  # noqa: E402, F401
    _BLOCKING_STATUSES,
    _REQUIRED_FRONTMATTER_FIELDS,
    _VALID_PRIORITIES,
    _VALID_STATUSES,
    validate_design_review_frontmatter,
)
from yaml_utils import _parse_yaml_frontmatter  # noqa: E402, F401


class MissingScriptSkip(Exception):  # noqa: N818 - control-flow signal, not an error condition
    """Raised by a validation when a referenced script is absent on disk.

    Per ADR-042 (Python migration), several legacy PowerShell validators were
    expunged. Their absence should not produce a misleading [FAIL]; instead the
    validation is reported as SKIP and does not affect the overall exit code.
    """


@dataclass
class ValidationRecord:
    """Result of a single validation step."""

    name: str
    status: str  # PASS, FAIL, SKIP
    duration: float = 0.0
    message: str = ""


@dataclass
class ValidationState:
    """Tracks overall validation results."""

    results: list[ValidationRecord] = field(default_factory=list)
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0


def _find_latest_session_log(repo_root: Path) -> Path | None:
    """Find the most recent session log in .agents/sessions/."""
    sessions_path = repo_root / ".agents" / "sessions"
    if not sessions_path.is_dir():
        return None

    pattern = re.compile(r"^\d{4}-\d{2}-\d{2}-session-\d+.*\.(?:md|json)$")
    candidates = sorted(
        (f for f in sessions_path.iterdir() if f.is_file() and pattern.match(f.name)),
        key=lambda f: f.name,
        reverse=True,
    )

    return candidates[0] if candidates else None


def _run_subprocess(
    args: list[str], timeout: int = 300, cwd: Path | str | None = None
) -> tuple[int, str, str]:
    """Run a subprocess and return (exit_code, stdout, stderr)."""
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError:
        return -1, "", f"Command not found: {args[0]}"
    except subprocess.TimeoutExpired:
        return -1, "", f"Command timed out after {timeout}s"


def run_validation(
    name: str,
    state: ValidationState,
    callback: Callable[[], bool],
    skip: bool = False,
) -> bool:
    """Run a validation and track results. Returns True on pass/skip."""
    state.total += 1

    if skip:
        print(f"[SKIP] {name} (skipped due to --quick flag)")
        state.skipped += 1
        state.results.append(ValidationRecord(name=name, status="SKIP", message="Skipped"))
        return True

    print()
    print(f"=== {name} ===")
    print("[RUNNING] Starting validation...")

    start = time.monotonic()
    success = False
    skipped = False
    message = ""

    try:
        success = callback()
        message = "Validation passed" if success else "Validation failed"
    except MissingScriptSkip as exc:
        skipped = True
        success = True  # SKIP does not count as failure for the gate
        message = f"Skipped: {exc}"
    except Exception as exc:
        success = False
        message = f"Validation error: {exc}"

    duration = time.monotonic() - start

    if skipped:
        state.skipped += 1
        status_label = "SKIP"
    elif success:
        state.passed += 1
        status_label = "PASS"
    else:
        state.failed += 1
        status_label = "FAIL"

    state.results.append(
        ValidationRecord(
            name=name,
            status=status_label,
            duration=duration,
            message=message,
        )
    )

    print()
    print(f"[{status_label}] {name} completed in {duration:.2f}s")
    if status_label == "FAIL":
        print(f"Error: {message}")
    elif status_label == "SKIP":
        print(f"Note: {message}")

    return success


# ---------------------------------------------------------------------------
# Individual validations
# ---------------------------------------------------------------------------


def validate_session_end(repo_root: Path) -> bool:
    """Validate the latest session log."""
    session_log = _find_latest_session_log(repo_root)
    if session_log is None:
        print("[WARNING] No session log found in .agents/sessions/")
        print("  If this is an agent session, create a session log.")
        print("  If this is a manual commit, this check can be skipped.")
        return True

    print(f"Latest session log: {session_log.name}")

    script = repo_root / "scripts" / "Validate-Session.ps1"
    if not script.exists():
        # Per ADR-042 the PowerShell validator was expunged and no Python port
        # exists yet. Treat as SKIP rather than a misleading FAIL.
        raise MissingScriptSkip(
            "Validate-Session.ps1 not present (ADR-042 expungement; no Python port yet)"
        )

    exit_code, _, _ = _run_subprocess(
        ["pwsh", "-NoProfile", "-File", str(script), "-SessionLogPath", str(session_log)]
    )
    return exit_code == 0


def validate_pester_tests(repo_root: Path, verbose: bool = False) -> bool:
    """Run Pester unit tests."""
    script = repo_root / "build" / "scripts" / "Invoke-PesterTests.ps1"
    if not script.exists():
        raise MissingScriptSkip(
            "Invoke-PesterTests.ps1 not present (ADR-042 expungement; no Python port yet)"
        )

    verbosity = "Diagnostic" if verbose else "Normal"
    exit_code, _, _ = _run_subprocess(
        ["pwsh", "-NoProfile", "-File", str(script), "-Verbosity", verbosity]
    )
    return exit_code == 0


def validate_markdown_lint(repo_root: Path) -> bool:
    """Run markdownlint auto-fix and validate."""
    if not shutil.which("npx"):
        print("[FAIL] npx not found (Node.js required)")
        print("  Install Node.js: https://nodejs.org/")
        return False

    print("Auto-fixing markdown files...")
    exit_code, _, _ = _run_subprocess(["npx", "markdownlint-cli2", "--fix", "**/*.md"])

    if exit_code != 0:
        print("[FAIL] Markdown linting failed (some issues cannot be auto-fixed)")
        print()
        print("Common unfixable issues:")
        print("  - MD040: Add language identifier to code blocks")
        print("  - MD033: Wrap generic types like ArrayPool<T> in backticks")
        return False

    return True


def _gh_base_ref(repo_root: Path) -> str | None:
    """Return ``origin/<baseRefName>`` for the open PR, or None.

    Asks the gh CLI for the PR's base branch name, then prefixes
    ``origin/`` so callers can pass the result to ``git diff`` directly.

    Behavior:
    - If gh is not on PATH, return None.
    - If gh succeeds but no PR exists for the current branch (empty
      output), return None.
    - If gh exits non-zero (auth, network, unknown error), return None.

    A related helper (``_gh_base_ref``) lives in
    ``.claude/hooks/PreToolUse/push_guard_base.py`` for use inside the
    pre-push framework. Find it via
    ``grep -n '^def _gh_base_ref' .claude/hooks/PreToolUse/push_guard_base.py``.
    The two functions evolved separately and intentionally cover
    different runtime contexts (CI vs developer machine). Test coverage
    in this codebase locks in the public contract above; the canonical
    file does the same in its own test suite.
    """
    if not shutil.which("gh"):
        return None
    exit_code, stdout, _ = _run_subprocess(
        ["gh", "pr", "view", "--json", "baseRefName", "-q", ".baseRefName"],
        timeout=5,
        cwd=repo_root,
    )
    if exit_code != 0:
        return None
    base = stdout.strip()
    if not base:
        return None
    return f"origin/{base}"


def _resolve_branch_base_ref(repo_root: Path) -> str | None:
    """Resolve the branch base ref by trying signals in priority order.

    Tries each candidate in order and returns the first one that
    resolves to a real ref locally:

        1. The PR's actual baseRefName via ``gh pr view`` (validated
           further with ``git rev-parse --verify`` so an unfetched ref
           falls through to the next step).
        2. The current branch's configured upstream via ``@{u}``.
        3. The remote's default branch via ``refs/remotes/origin/HEAD``.
        4. ``origin/main`` as a last-resort literal.

    Returns None when none resolve.

    A related helper (``_detect_default_base_ref``) lives in
    ``.claude/hooks/PreToolUse/push_guard_base.py`` and follows the same
    priority order; locate it via
    ``grep -n '^def _detect_default_base_ref' .claude/hooks/PreToolUse/push_guard_base.py``
    if you want the pre-push framework's perspective. The two functions
    have separate test suites that lock in their respective contracts.
    """
    pr_base = _gh_base_ref(repo_root)
    if pr_base:
        exit_code, _, _ = _run_subprocess(
            ["git", "-C", str(repo_root), "rev-parse", "--verify", "--quiet", pr_base],
            timeout=10,
        )
        if exit_code == 0:
            return pr_base

    candidates = ("@{u}", "refs/remotes/origin/HEAD", "origin/main")
    for ref in candidates:
        exit_code, _, _ = _run_subprocess(
            ["git", "-C", str(repo_root), "rev-parse", "--verify", "--quiet", ref],
            timeout=10,
        )
        if exit_code == 0:
            return ref
    return None


# Compiled detection regex. Uses Unicode escape sequences so this source
# file does not contain U+2014 or U+2013 itself (Issue #1923, REQ-006).
_DASH_RE = re.compile("[\u2013\u2014]")


# Paths skipped by the branch-wide dash scan:
# - node_modules/, .venv/, .serena/cache/: vendored content (REQ-006-AC5)
# - tests/hooks/fixtures/: test fixtures intentionally contain U+2014/U+2013
#   to exercise the detection logic; flagging them would fail every PR that
#   touches the dash-guard test suite
_VENDORED_PREFIXES = (
    "node_modules/",
    ".venv/",
    ".serena/cache/",
    "tests/hooks/fixtures/",
)


def _is_vendored(path: str) -> bool:
    """True when ``path`` starts with any vendored prefix."""
    return any(path.startswith(prefix) for prefix in _VENDORED_PREFIXES)


def _branch_markdown_files(repo_root: Path) -> list[str] | None:
    """Resolve branch base and return non-vendored markdown paths to scan.

    Returns None when the scan cannot run (no base ref or git diff failure);
    callers treat None as fail-open (pass without scanning).
    """
    base_ref = _resolve_branch_base_ref(repo_root)
    if base_ref is None:
        print("[WARNING] Em/en-dash branch scan skipped: no base ref resolved")
        return None

    exit_code, stdout, stderr = _run_subprocess(
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
        print(
            f"[WARNING] Em/en-dash branch scan skipped: git diff failed: {stderr}",
        )
        return None

    return [
        p for p in stdout.splitlines() if p.endswith(".md") and not _is_vendored(p)
    ]


def _find_dash_violations(
    repo_root: Path, paths: list[str],
) -> list[tuple[str, int]]:
    """Read each committed path and return (path, line_num) hits.

    Reads file content from the HEAD commit via ``git show HEAD:<path>``
    rather than the working tree. The list of paths comes from
    ``git diff <base>...HEAD --name-only``, so the scan target must be
    the HEAD blob to match the diff scope. Reading the working tree
    instead would give wrong answers when the working tree differs from
    HEAD (uncommitted edits, partial staging, or a fresh checkout that
    has not yet pulled the branch).
    """
    violations: list[tuple[str, int]] = []
    for relpath in paths:
        exit_code, stdout, _ = _run_subprocess(
            ["git", "-C", str(repo_root), "show", f"HEAD:{relpath}"],
            timeout=10,
        )
        if exit_code != 0:
            # `_branch_markdown_files` already filters out deletions via
            # ``--diff-filter=ACMR``, so a non-zero ``git show`` here
            # signals an unexpected condition (missing object in the
            # local clone, a path that resolves to a directory, an I/O
            # error). Skip silently rather than fail the whole scan;
            # `git diff`-listed paths that cannot be read are not
            # actionable for the dash check.
            continue
        violations.extend(
            (relpath, line_num)
            for line_num, line in enumerate(stdout.splitlines(), start=1)
            if _DASH_RE.search(line)
        )
    return violations


def _print_dash_violations(violations: list[tuple[str, int]]) -> None:
    """Emit the structured failure block for branch-wide dash violations."""
    print("[FAIL] Em/en-dash prohibition violated")
    print("  Files containing U+2014 (em-dash) or U+2013 (en-dash):")
    for path, line_num in violations:
        print(f"    {path}:{line_num}")
    print("  Fix: replace U+2014 with comma, period, or colon;")
    print("       U+2013 with hyphen in numeric ranges;")
    print("       or restructure the sentence.")
    print(
        "  Rule: .claude/rules/universal.md MUST NOT entry 5 (Refs #1923).",
    )


def validate_dash_prohibition(repo_root: Path) -> bool:
    """Branch-wide em/en-dash check (Issue #1923, REQ-006-AC7).

    Catches U+2014 (em-dash) and U+2013 (en-dash) in any *.md file
    changed on this branch since divergence from the base ref. Complements
    the pre-commit and commit-msg hooks (which only block at commit time)
    by catching dashes that landed before the hooks were installed.

    Vendored paths (node_modules/, .venv/, .serena/cache/) are skipped.
    Test fixtures (tests/hooks/fixtures/) are skipped because they
    intentionally contain dashes to exercise the detection logic.
    .github/instructions/ is NOT skipped (REQ-006-AC4).

    Returns True (pass) when no violations are found OR when the scan
    cannot run (fail open). Returns False on any violation.
    """
    candidate_paths = _branch_markdown_files(repo_root)
    if candidate_paths is None:
        return True
    if not candidate_paths:
        print("[PASS] Em/en-dash prohibition (no markdown files on branch)")
        return True

    violations = _find_dash_violations(repo_root, candidate_paths)
    if violations:
        _print_dash_violations(violations)
        return False

    print(
        f"[PASS] Em/en-dash prohibition ({len(candidate_paths)} markdown file(s) checked)",
    )
    return True


def validate_workflow_yaml(repo_root: Path) -> bool:
    """Validate GitHub Actions workflow files with actionlint."""
    if not shutil.which("actionlint"):
        print("[WARNING] actionlint not found (workflow validation skipped)")
        print("  Install actionlint to enable GitHub Actions workflow validation.")
        return True

    workflow_path = repo_root / ".github" / "workflows"
    if not workflow_path.is_dir():
        print("[WARNING] No .github/workflows directory found")
        return True

    workflow_files = list(workflow_path.glob("*.yml")) + list(
        workflow_path.glob("*.yaml")
    )
    if not workflow_files:
        print("[WARNING] No workflow files found in .github/workflows/")
        return True

    print(f"Validating {len(workflow_files)} workflow file(s)...")

    exit_code, stdout, stderr = _run_subprocess(
        ["actionlint"] + [str(f) for f in workflow_files]
    )

    if exit_code != 0:
        print("[FAIL] actionlint found issues in workflow files")
        output = stdout or stderr
        lines = output.strip().split("\n")
        for line in lines[:20]:
            print(line)
        if len(lines) > 20:
            print(f"... ({len(lines) - 20} more lines omitted)")
        return False

    print("All workflow files validated successfully.")
    return True


def validate_yaml_style(repo_root: Path) -> bool:
    """Check YAML style with yamllint."""
    if not shutil.which("yamllint"):
        print("[WARNING] yamllint not found (YAML style validation skipped)")
        return True

    print("Checking YAML files for style issues...")
    exit_code, stdout, stderr = _run_subprocess(
        ["yamllint", "-f", "parsable", str(repo_root)]
    )

    if exit_code != 0:
        print("[WARNING] yamllint found style issues (non-blocking)")
        output = stdout or stderr
        lines = output.strip().split("\n")
        for line in lines[:30]:
            print(line)
        if len(lines) > 30:
            print(f"... ({len(lines) - 30} more issues omitted)")
        print()
        print("Note: These are warnings, not errors. Fix when convenient.")
        return True

    print("All YAML files conform to style guidelines.")
    return True


def validate_path_normalization(repo_root: Path) -> bool:
    """Check for absolute paths."""
    script = repo_root / "build" / "scripts" / "Validate-PathNormalization.ps1"
    if not script.exists():
        raise MissingScriptSkip(
            "Validate-PathNormalization.ps1 not present (ADR-042 expungement; no Python port yet)"
        )

    exit_code, _, _ = _run_subprocess(
        ["pwsh", "-NoProfile", "-File", str(script), "-FailOnViolation"]
    )
    return exit_code == 0


def validate_planning_artifacts(repo_root: Path) -> bool:
    """Validate planning consistency."""
    script = repo_root / "build" / "scripts" / "Validate-PlanningArtifacts.ps1"
    if not script.exists():
        raise MissingScriptSkip(
            "Validate-PlanningArtifacts.ps1 not present (ADR-042 expungement; no Python port yet)"
        )

    exit_code, _, _ = _run_subprocess(
        ["pwsh", "-NoProfile", "-File", str(script), "-FailOnError"]
    )
    return exit_code == 0


def validate_hook_anchoring(repo_root: Path) -> bool:
    """Plugin hook files must anchor every script to the plugin root (#2205).

    Covers both shipped plugin hook files: ``.claude/hooks/hooks.json`` (Claude,
    ``${CLAUDE_PLUGIN_ROOT}``) and ``src/copilot-cli/hooks/hooks.json`` (Copilot).
    Bare ``./hooks/...`` paths fail under either CLI because hooks run with
    ``cwd`` set to the user's working directory, not the plugin install dir.
    The Copilot shape is enforced against the generator, so this gate keeps the
    anchored form the default and blocks a silent regression on either side.
    """
    script = repo_root / "scripts" / "validation" / "validate_hook_anchoring.py"
    if not script.exists():
        raise MissingScriptSkip("validate_hook_anchoring.py not present")

    exit_code, stdout, stderr = _run_subprocess(
        ["python3", str(script), "--repo-root", str(repo_root)]
    )
    if exit_code != 0:
        # Surface the anchoring detail so the fix is actionable inline.
        detail = stdout.rstrip() or stderr.rstrip()
        if detail:
            print(detail)
    return exit_code == 0


def validate_build_gates(repo_root: Path) -> bool:
    """Verify ``.claude/commands/build.md`` still wires the required exit gates.

    The /build command is the implementer's exit path. If a future edit
    removes the code-qualities-assessment / taste-lints / doc-accuracy
    invocations, the iteration paradox documented in PR #1887 returns.
    Lock the contract here. See ``check_build_gates.py`` for the rules.
    """
    script = repo_root / "scripts" / "validation" / "check_build_gates.py"
    if not script.exists():
        raise MissingScriptSkip(
            "scripts/validation/check_build_gates.py not present"
        )
    exit_code, stdout, stderr = _run_subprocess(
        [sys.executable, str(script), "--repo-root", str(repo_root)]
    )
    output = (stdout or "") + (stderr or "")
    if output.strip():
        for line in output.strip().splitlines()[:40]:
            print(line)
    return exit_code == 0


def validate_spec_id_uniqueness(repo_root: Path) -> bool:
    """Enforce unique `id:` frontmatter across spec catalog (Issue #2068).

    Duplicate REQ/DESIGN/TASK IDs break traceability and any spec-graph
    tooling that joins by ID. The README under each category already
    documents uniqueness; this gate enforces it.
    """
    script = repo_root / "scripts" / "validation" / "check_spec_id_uniqueness.py"
    if not script.exists():
        raise MissingScriptSkip(
            "scripts/validation/check_spec_id_uniqueness.py not present"
        )
    exit_code, stdout, stderr = _run_subprocess(
        [sys.executable, str(script), "--repo-root", str(repo_root)]
    )
    output = (stdout or "") + (stderr or "")
    if output.strip():
        for line in output.strip().splitlines()[:40]:
            print(line)
    return exit_code == 0


def validate_vendor_portability(repo_root: Path) -> bool:
    """Fail when a new skill script hard-codes an upstream-only path (Issue #2050).

    Wraps ``scripts/validation/check_vendor_portability.py``. The script exits 0
    when there are no NEW offenders (baseline-listed debt is allowed) or no scan
    roots are present, 1 when a NEW offender is found, and 2 on a configuration
    error. Exit 1 and 2 are both hard failures here.
    """
    script = repo_root / "scripts" / "validation" / "check_vendor_portability.py"
    if not script.exists():
        raise MissingScriptSkip(
            "scripts/validation/check_vendor_portability.py not present"
        )
    exit_code, stdout, stderr = _run_subprocess(
        [sys.executable, str(script), "--repo-root", str(repo_root)]
    )
    output = (stdout or "") + (stderr or "")
    if output.strip():
        for line in output.strip().splitlines()[:40]:
            print(line)
    return exit_code == 0


def validate_sync_registry(repo_root: Path) -> bool:
    """Enforce that every shared lib package is registered for sync (Issue #1909).

    `scripts/sync_plugin_lib.py:SYNC_PAIRS` lists the shared packages copied
    into `.claude/lib/` for plugin distribution. A new lib package added
    without a SYNC_PAIRS entry silently misses the sync and crashes a shimmed
    hook at install time. This gate fails when a package under the source roots
    or under `.claude/lib/` is unregistered.
    """
    script = repo_root / "scripts" / "validation" / "validate_sync_registry.py"
    if not script.exists():
        raise MissingScriptSkip(
            "scripts/validation/validate_sync_registry.py not present"
        )
    exit_code, stdout, stderr = _run_subprocess(
        [sys.executable, str(script), "--repo-root", str(repo_root)]
    )
    output = (stdout or "") + (stderr or "")
    if output.strip():
        for line in output.strip().splitlines()[:40]:
            print(line)
    return exit_code == 0


def validate_agent_catalog(repo_root: Path) -> bool:
    """Detect drift between docs/agent-catalog.md and templates/agents/.

    Wraps ``scripts/validation/validate_agent_catalog.py``. The wrapped script
    regenerates the catalog to a buffer and exits 0 when the committed file
    matches, 1 on drift or a missing catalog, 2 on config error, and 3 on a bad
    template. Any non-zero exit is a hard failure: a stale catalog is the exact
    thing this gate exists to catch (Issue #1904).

    Fails closed when the validator is absent rather than raising
    MissingScriptSkip; a silent skip would defeat the gate.
    """
    script = repo_root / "scripts" / "validation" / "validate_agent_catalog.py"
    if not script.exists():
        print(
            "[ERROR] validate_agent_catalog.py absent; the agent-catalog gate "
            "cannot run. Hard failure: the gate is the point of registering "
            "this validator.",
            file=sys.stderr,
        )
        return False
    exit_code, stdout, stderr = _run_subprocess([sys.executable, str(script)])
    output = (stdout or "") + (stderr or "")
    if output.strip():
        for line in output.strip().splitlines()[:40]:
            print(line)
    return exit_code == 0


def validate_canonical_citations(repo_root: Path) -> bool:
    """Heuristic check for uncited mirror-claims.

    Soft-warn by default. Set STRICT_CANONICAL_CHECK=1 in the environment
    to upgrade to a hard failure. Always returns True in soft-warn mode
    so a single uncited claim does not block the PR pipeline.

    See: `.claude/rules/canonical-source-mirror.md` and PR #1887
    retrospective Layer 4.
    """
    script = repo_root / "scripts" / "validation" / "check_canonical_citations.py"
    if not script.exists():
        print("[WARNING] check_canonical_citations.py not found (skipping)")
        return True

    exit_code, stdout, stderr = _run_subprocess(
        [sys.executable, str(script), "--repo-root", str(repo_root)]
    )

    output = stdout.strip()
    if output:
        print(output)
    if stderr.strip():
        print(stderr.strip(), file=sys.stderr)

    # Default mode is soft-warn; the script already exits 0 unless
    # STRICT_CANONICAL_CHECK=1 is set. Treat any non-zero exit as a fail
    # so CI can opt into strict mode by setting the env var.
    return exit_code == 0


def validate_orchestrator_citations(repo_root: Path) -> bool:
    """Verify orchestrator prose path citations resolve to real files.

    Wraps ``scripts/validation/check_orchestrator_citations.py``, which fails
    when a backtick path citation in ``.claude/commands/pr-quality/all.md``
    points to a file that no longer exists. A stale citation (e.g. the removed
    ``AIReviewCommon.psm1`` reference fixed in PR #1934) sends the next reader
    to a dead pointer. See Issue #1966.
    """
    script = repo_root / "scripts" / "validation" / "check_orchestrator_citations.py"
    if not script.exists():
        print("[WARNING] check_orchestrator_citations.py not found (skipping)")
        return True

    exit_code, stdout, stderr = _run_subprocess(
        [sys.executable, str(script), "--repo-root", str(repo_root)]
    )
    if stdout.strip():
        print(stdout.strip())
    if stderr.strip():
        print(stderr.strip(), file=sys.stderr)
    return exit_code == 0


def validate_spec_contradiction(repo_root: Path) -> bool:
    """Advisory check for PR-description vs linked-issue vs code contradictions.

    Wraps ``scripts/validation/spec_contradiction.py`` in ``--advisory`` mode,
    so a heuristic false positive never blocks the local pre-PR cycle. The
    script catches the PR #1897 round-7 loop locally (Issue #1894 claimed
    ``model_tier: sonnet`` while the committed agent frontmatter shipped
    ``model: opus``), which CI's "Validate Spec Coverage" gate surfaced only
    after each push. Always returns True; the WARN output is the signal.

    See Issue #1920 and the retrospective at
    ``.agents/retrospective/2026-05-08-pr-1897-confident-incorrectness-recurrence.md``.
    """
    script = repo_root / "scripts" / "validation" / "spec_contradiction.py"
    if not script.exists():
        print("[WARNING] spec_contradiction.py not found (skipping)")
        return True

    base_ref = _resolve_branch_base_ref(repo_root)
    cmd = [
        sys.executable,
        str(script),
        "--repo-root",
        str(repo_root),
        "--advisory",
    ]
    if base_ref:
        cmd.extend(["--base", base_ref])
    exit_code, stdout, stderr = _run_subprocess(cmd)
    if stdout.strip():
        print(stdout.strip())
    if stderr.strip():
        print(stderr.strip(), file=sys.stderr)
    # Advisory: the wrapped script already exits 0 under --advisory, so any
    # non-zero exit here is a config error (e.g. could not resolve repo). Do
    # not block the pre-PR cycle on it; surface the output and pass.
    return True


def validate_agent_drift(repo_root: Path) -> bool:
    """Detect agent semantic drift.

    Per ADR-042 the legacy Detect-AgentDrift.ps1 was expunged in favor of the
    Python port at build/scripts/detect_agent_drift.py. Invoke the Python
    version directly so the drift gate continues to run after migration.

    The detector runs two comparisons (Issue #2267): the vendored
    src/claude vs src/vs-code-agents pair (blocking) and the hand-maintained
    .claude/agents vs .github/agents install pair for shared-template agents
    (advisory; reported but does not flip the exit code, because the two
    self-host copies carry large pre-existing structural differences). Only
    vendored drift blocks this gate.
    """
    python_script = repo_root / "build" / "scripts" / "detect_agent_drift.py"
    if python_script.exists():
        exit_code, stdout, stderr = _run_subprocess(
            [sys.executable, str(python_script)]
        )
        # Surface drift output for visibility (mirrors other Python validators).
        # Cap at 100 lines: the detector now reports two comparisons (vendored
        # and install), so 40 truncated the install-pass results (Issue #2267).
        output = (stdout or "") + (stderr or "")
        if output.strip():
            for line in output.strip().splitlines()[:100]:
                print(line)
        return exit_code == 0

    # Legacy fallback: if neither port nor original PS1 exist, SKIP rather than
    # report a misleading FAIL (ADR-042 expungement tolerance).
    legacy = repo_root / "build" / "scripts" / "Detect-AgentDrift.ps1"
    if not legacy.exists():
        raise MissingScriptSkip(
            "detect_agent_drift.py and Detect-AgentDrift.ps1 both absent "
            "(ADR-042 expungement)"
        )

    exit_code, _, _ = _run_subprocess(
        ["pwsh", "-NoProfile", "-File", str(legacy)]
    )
    return exit_code == 0


def _run_build_script_gate(
    repo_root: Path,
    script_name: str,
    gate_label: str,
) -> bool:
    """Run a build script gate with standard error handling.

    Shared helper for gates that wrap a ``build/scripts/`` Python validator
    with the same pattern: check existence, resolve base ref, invoke with
    ``--base``, print output, and return success/failure.

    Args:
        repo_root: Repository root path.
        script_name: Filename under ``build/scripts/`` (e.g.,
            ``validate_install_parity.py``).
        gate_label: Human-readable name for error messages (e.g.,
            ``install-parity``).

    Returns:
        True if the script exits 0, False otherwise. Fails closed when
        the script is absent or when the base ref cannot be resolved.
    """
    script = repo_root / "build" / "scripts" / script_name
    if not script.exists():
        print(
            f"[ERROR] {script_name} absent; the {gate_label} gate cannot "
            f"run. Hard failure: the gate is the point of registering "
            f"this validator.",
            file=sys.stderr,
        )
        return False
    base_ref = _resolve_branch_base_ref(repo_root)
    if not base_ref:
        print(
            f"[ERROR] {gate_label} gate: base ref could not be resolved; "
            f"refusing to invoke validator without an explicit --base.",
            file=sys.stderr,
        )
        return False
    cmd = [sys.executable, str(script), "--base", base_ref]
    exit_code, stdout, stderr = _run_subprocess(cmd)
    output = (stdout or "") + (stderr or "")
    if output.strip():
        for line in output.strip().splitlines()[:80]:
            print(line)
    return exit_code == 0


def validate_install_parity(repo_root: Path) -> bool:
    """Detect install-copy drift across SHARED_AGENT and RULE parity groups.

    Wraps ``build/scripts/validate_install_parity.py``. The script exits 0
    when the diff is clean, 1 when one or more parity groups have missing
    siblings, and 2 on configuration errors. We treat exit 1 as a hard
    failure; exit 2 is also a failure because the validator could not run.

    This is the new gate being wired in, not a legacy script. If the
    validator is missing from build/scripts/, fail closed (return False)
    instead of raising MissingScriptSkip; a silent skip would defeat the
    point of registering the gate.

    Passes an explicit ``--base`` resolved by ``_resolve_branch_base_ref``.
    Fails closed when the base cannot be resolved, so the validator never
    falls back to its own @{push} default (which is not reliably set in CI
    or fresh local checkouts) and never validates against an unknown base.
    """
    return _run_build_script_gate(
        repo_root, "validate_install_parity.py", "install-parity"
    )


def validate_plugin_version_bump(repo_root: Path) -> bool:
    """Fail when a plugin source dir changed without a plugin.json bump.

    Wraps ``build/scripts/validate_plugin_version_bump.py``. The script exits
    0 when every touched plugin was version-bumped (or nothing relevant
    changed), 1 when a touched plugin's version did not increase, and 2 on a
    configuration error (unparseable version, git unavailable). Exit 1 and 2
    are both hard failures here.

    Like the install-parity gate, this fails closed when the validator is
    absent (a silent skip would defeat the gate) and when the branch base ref
    cannot be resolved (so the validator never diffs against an unknown base).
    """
    return _run_build_script_gate(
        repo_root, "validate_plugin_version_bump.py", "plugin version-bump"
    )


def validate_git_hooks_installed(repo_root: Path) -> bool:
    """Fail when the local clone is not wired to run the canonical githooks.

    Delegates to ``scripts/install_git_hooks.py --check``, which verifies that
    ``core.hooksPath`` resolves to ``.githooks`` and the hook scripts exist and
    are executable. A clone left on the default ``.git/hooks`` (or pointed at an
    absolute path) silently bypasses every pre-push guard, including the plugin
    version-bump gate, so drift here is a hard local failure.

    Skipped under CI: a CI checkout neither has nor should have
    ``core.hooksPath`` set to ``.githooks`` (the guards run as workflow steps,
    not local hooks), so the check is irrelevant there.

    Worktree-aware: ``scripts/install_git_hooks.py --check`` reads the effective
    hook configuration while resolving the canonical relative ``.githooks`` path
    against the current worktree. This keeps the gate active in linked worktrees
    so shared-config drift still fails before push (Issue #2220).
    """
    if (
        os.environ.get("GITHUB_ACTIONS", "").lower() in ("true", "1")
        or os.environ.get("CI", "").lower() in ("true", "1")
    ):
        raise MissingScriptSkip("git hooks check skipped under CI")
    script = repo_root / "scripts" / "install_git_hooks.py"
    if not script.exists():
        print(
            "[ERROR] install_git_hooks.py absent; the git-hooks gate cannot "
            "run. Hard failure: the gate is the point of registering "
            "this validator.",
            file=sys.stderr,
        )
        return False
    exit_code, stdout, stderr = _run_subprocess(
        [sys.executable, str(script), "--check", "--repo-root", str(repo_root)]
    )
    if stdout.strip():
        print(stdout.strip())
    if stderr.strip():
        print(stderr.strip(), file=sys.stderr)
    if exit_code != 0:
        print(
            "[FAIL] Local git hooks are not installed. "
            "Run: python3 scripts/install_git_hooks.py"
        )
    return exit_code == 0


def validate_workflow_local_run(repo_root: Path) -> bool:
    """Shift-left tier of the workflow local-run gate (actionlint + act -n).

    Runs the fast stages of ``scripts/validation/run_workflow_local_test.py``
    (``--no-full``) over the changed ``.github/workflows`` files. The full
    ``gh act`` execution stage is reserved for the pre-push hook so pre_pr stays
    fast and does not require a running Docker daemon.

    Contract: pass when no workflow changed or all run stages pass. A stage
    failure (exit 1) blocks. A configuration error (exit 2: a path that escapes
    the repo root, or a missing repo root) also blocks, because the inputs are
    wrong and a clean run cannot be trusted. A missing local tool (exit 3) does
    NOT block here, because the pre-push gate is the authoritative enforcer;
    pre_pr only warns so a contributor without actionlint installed is not
    stopped pre-PR.
    """
    script = repo_root / "scripts" / "validation" / "run_workflow_local_test.py"
    if not script.exists():
        raise MissingScriptSkip("run_workflow_local_test.py not present")

    base_ref = _resolve_branch_base_ref(repo_root)
    if not base_ref:
        print("[WARN] workflow local-run: base ref unresolved; skipping.")
        return True

    diff_code, diff_out, _ = _run_subprocess(
        ["git", "-C", str(repo_root), "diff", "--name-only", f"{base_ref}...HEAD"]
    )
    if diff_code != 0:
        print("[WARN] workflow local-run: git diff failed; skipping.")
        return True
    changed = [
        line
        for line in diff_out.splitlines()
        if line.startswith(".github/workflows/")
        and line.endswith((".yml", ".yaml"))
        and (repo_root / line).is_file()
    ]
    if not changed:
        print("No changed workflow files; nothing to run locally.")
        return True

    # Pass the known repo_root explicitly so containment and path resolution
    # validate against this checkout, not the script's path-derived default
    # (robust to symlinked checkouts).
    cmd = [
        sys.executable,
        str(script),
        "--repo-root",
        str(repo_root),
        "--no-full",
        "--files",
        *changed,
    ]
    exit_code, stdout, stderr = _run_subprocess(cmd)
    output = (stdout or "") + (stderr or "")
    if output.strip():
        for line in output.strip().splitlines()[:80]:
            print(line)
    if exit_code == 3:
        print(
            "[WARN] workflow local-run tools unavailable locally; the pre-push "
            "hook enforces the full gate (actionlint + gh act)."
        )
        return True
    return exit_code == 0


def validate_review_marker(repo_root: Path) -> bool:
    """Advisory check for a SHA-bound ``Reviewed-By: /review@...`` marker on HEAD.

    Wraps ``scripts/validation/validate_review_marker.py`` (Issue #1938). The
    marker is the ``/ship`` precondition: it proves ``/review`` passed on the
    exact code being shipped. ``/ship`` itself blocks on a missing marker (AC1);
    here the check is **advisory** by default, because most pre-PR pushes are
    mid-development and have not run ``/review`` yet. Blocking every such push
    would break normal iteration.

    Set ``REVIEW_MARKER_ENFORCED=1`` to escalate to BLOCKING (returns False when
    HEAD has no binding marker). Mirrors the advisory/enforced pattern used by
    ``validate_command_bundle_coverage`` (``BUNDLE_CHECK_ENFORCED``).
    """
    enforced = os.environ.get("REVIEW_MARKER_ENFORCED", "").lower() in ("1", "true")

    script = repo_root / "scripts" / "validation" / "validate_review_marker.py"
    if not script.exists():
        if enforced:
            print("[FAIL] validate_review_marker.py not present")
            return False
        print("[WARN] validate_review_marker.py not found (advisory skip)")
        return True

    exit_code, stdout, stderr = _run_subprocess(
        [sys.executable, str(script), "--repo-root", str(repo_root)]
    )
    output = (stdout or "") + (stderr or "")
    if output.strip():
        for line in output.strip().splitlines()[:20]:
            print(line)

    if exit_code == 0:
        return True

    if enforced:
        # exit 1 (no/stale marker) and exit 2 (config) both block in enforced mode.
        return False
    print(
        "  Note: advisory only (default). /ship blocks on this; pre_pr does not. "
        "Set REVIEW_MARKER_ENFORCED=1 to make it BLOCKING here. See Issue #1938."
    )
    return True


def validate_command_bundle_coverage(repo_root: Path) -> bool:
    """SPEC-005 advisory check: each lifecycle command invokes its bundled skills.

    Reads the canonical BUNDLE_REGISTRY from
    ``scripts/validation/bundle_registry.py`` and verifies that each
    ``.claude/commands/<file>`` contains the expected
    ``Skill(skill="...")`` invocation.

    Default behavior is **advisory** (returns True regardless of missing
    invocations; emits WARN findings). Set
    ``BUNDLE_CHECK_ENFORCED=1`` to escalate to BLOCKING (returns False
    on any missing invocation). Per SPEC-005 AC-14 and Q3 resolution.
    """
    enforced = os.environ.get("BUNDLE_CHECK_ENFORCED", "").lower() in ("1", "true")

    # Lazy import; sibling module under scripts/validation/.
    sys.path.insert(0, str(repo_root / "scripts" / "validation"))
    try:
        from bundle_registry import BUNDLE_REGISTRY, expected_skill_invocation
    except ImportError as exc:
        # Per SPEC-005 Q3: default is advisory. An import failure in advisory
        # mode must not block pre_pr; in enforced mode it is a hard fail.
        if enforced:
            print(f"[FAIL] Could not import bundle_registry: {exc}")
            return False
        print(f"[WARN] Could not import bundle_registry (advisory skip): {exc}")
        return True

    commands_dir = repo_root / ".claude" / "commands"

    missing: list[tuple[str, str]] = []
    for command_file, skill in BUNDLE_REGISTRY:
        path = commands_dir / command_file
        if not path.exists():
            missing.append((command_file, skill))
            continue
        text = path.read_text(encoding="utf-8")
        if expected_skill_invocation(skill) not in text:
            missing.append((command_file, skill))

    if not missing:
        print(f"[PASS] All {len(BUNDLE_REGISTRY)} bundle invocations present")
        return True

    label = "FAIL" if enforced else "WARN"
    mode = "blocking" if enforced else "advisory"
    print(f"[{label}] {len(missing)} bundle invocation(s) missing ({mode}):")
    for cmd, skill in missing:
        print(f"  - {cmd}: missing Skill(skill=\"{skill}\")")
    if not enforced:
        print(
            "  Note: advisory only (default). Set BUNDLE_CHECK_ENFORCED=1 "
            "to make this BLOCKING. See SPEC-005 AC-14."
        )
    return not enforced


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with env var defaults."""
    parser = argparse.ArgumentParser(
        description="Unified shift-left validation runner for pre-PR checks.",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        default=os.environ.get("QUICK_MODE", "").lower() in ("true", "1"),
        help="Skip slow validations (path normalization, planning, drift)",
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        default=os.environ.get("SKIP_TESTS", "").lower() in ("true", "1"),
        help="Skip Pester unit tests (use sparingly)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Run with verbose output",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns ADR-035 exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    # Determine repo root (parent of scripts/)
    repo_root = Path(__file__).resolve().parent.parent.parent
    if not repo_root.is_dir():
        print(f"[FAIL] Invalid repository root: {repo_root}", file=sys.stderr)
        return 2

    quick = args.quick
    mode = "Quick (fast checks only)" if quick else "Full"
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

    print()
    print("=== Pre-PR Validation Runner ===")
    print(f"Repository: {repo_root}")
    print(f"Mode: {mode}")
    print(f"Started: {now}")
    print()

    state = ValidationState()
    start_time = time.monotonic()

    # 1. Session End
    run_validation(
        "Session End Validation",
        state,
        lambda: validate_session_end(repo_root),
    )

    # 2. Pester Tests
    if not args.skip_tests:
        run_validation(
            "Pester Unit Tests",
            state,
            lambda: validate_pester_tests(repo_root, args.verbose),
        )
    else:
        print("[SKIP] Pester Unit Tests (skipped via --skip-tests)")
        state.total += 1
        state.skipped += 1

    # 3. Markdown Lint
    run_validation(
        "Markdown Linting",
        state,
        lambda: validate_markdown_lint(repo_root),
    )

    # 3.5 Workflow YAML
    run_validation(
        "Workflow YAML Validation",
        state,
        lambda: validate_workflow_yaml(repo_root),
    )

    # 3.6 Design Review Frontmatter
    run_validation(
        "Design Review Frontmatter",
        state,
        lambda: validate_design_review_frontmatter(repo_root),
    )

    # 3.7 Build Command Exit Gates (PR #1887 retrospective Layer 2)
    run_validation(
        "Build Command Exit Gates",
        state,
        lambda: validate_build_gates(repo_root),
    )

    # 3.75 Spec ID Uniqueness (Issue #2068)
    run_validation(
        "Spec ID Uniqueness",
        state,
        lambda: validate_spec_id_uniqueness(repo_root),
    )

    # 3.76 Vendor Portability (no new hard-coded upstream-only paths; Issue #2050)
    run_validation(
        "Vendor Portability",
        state,
        lambda: validate_vendor_portability(repo_root),
    )

    # 3.77 Sync Registry Provenance (Issue #1909)
    run_validation(
        "Sync Registry Provenance",
        state,
        lambda: validate_sync_registry(repo_root),
    )

    # 3.78 Agent Catalog Drift (docs/agent-catalog.md vs templates/agents/; #1904)
    run_validation(
        "Agent Catalog Drift",
        state,
        lambda: validate_agent_catalog(repo_root),
    )

    # 3.8 Canonical Citation Check (heuristic; soft warn unless
    # STRICT_CANONICAL_CHECK=1; PR #1887 retrospective Layer 4)
    run_validation(
        "Canonical Citation Check",
        state,
        lambda: validate_canonical_citations(repo_root),
    )

    # 3.82 Orchestrator Citation Check (Issue #1966). Fails when a backtick
    # path citation in .claude/commands/pr-quality/all.md points to a file
    # that no longer exists.
    run_validation(
        "Orchestrator Citation Check",
        state,
        lambda: validate_orchestrator_citations(repo_root),
    )

    # 3.85 Em/en-dash branch-wide check (Issue #1923, REQ-006-AC7)
    run_validation(
        "Em/en-dash Prohibition",
        state,
        lambda: validate_dash_prohibition(repo_root),
    )

    # 3.87 Spec Contradiction Check (advisory; Issue #1920). Catches the
    # PR #1897 round-7 loop (linked issue claims one model tier, committed
    # agent frontmatter ships another) locally instead of after each push.
    run_validation(
        "Spec Contradiction Check",
        state,
        lambda: validate_spec_contradiction(repo_root),
    )

    # 3.9 YAML Style (skip if quick)
    run_validation(
        "YAML Style Validation",
        state,
        lambda: validate_yaml_style(repo_root),
        skip=quick,
    )

    # 4. Path Normalization (skip if quick)
    run_validation(
        "Path Normalization",
        state,
        lambda: validate_path_normalization(repo_root),
        skip=quick,
    )

    # 5. Planning Artifacts (skip if quick)
    run_validation(
        "Planning Artifacts",
        state,
        lambda: validate_planning_artifacts(repo_root),
        skip=quick,
    )

    # 6. Agent Drift (skip if quick)
    run_validation(
        "Agent Drift Detection",
        state,
        lambda: validate_agent_drift(repo_root),
        skip=quick,
    )

    # 6b. Install Parity (changed-together sibling check; cheap, always on)
    run_validation(
        "Install Parity (agents and rules)",
        state,
        lambda: validate_install_parity(repo_root),
    )

    # 6c. Plugin Version Bump (source change requires a plugin.json bump; #2118)
    run_validation(
        "Plugin Version Bump",
        state,
        lambda: validate_plugin_version_bump(repo_root),
    )

    # 6c2. Hook Anchoring (Claude + Copilot plugin hooks.json must anchor to the
    # plugin root; bare paths regressed Copilot CLI in #2205, same trap on Claude)
    run_validation(
        "Hook Anchoring (Claude + Copilot)",
        state,
        lambda: validate_hook_anchoring(repo_root),
    )

    # 6d. Git Hooks Installed (local clone must run the canonical .githooks;
    # a desynced hooksPath bypasses the pre-push guards). Skipped under CI.
    run_validation(
        "Git Hooks Installed",
        state,
        lambda: validate_git_hooks_installed(repo_root),
    )

    # 6d. Workflow Local Run (actionlint + gh act dry-run for changed workflows)
    run_validation(
        "Workflow Local Run",
        state,
        lambda: validate_workflow_local_run(repo_root),
    )

    # 7. Command-Skill Bundle Coverage (advisory by default; SPEC-005 AC-14)
    run_validation(
        "Command-Skill Bundle Coverage",
        state,
        lambda: validate_command_bundle_coverage(repo_root),
    )

    # 7b. Review Marker (advisory by default; /ship blocks, Issue #1938).
    # Reports whether HEAD carries a SHA-bound Reviewed-By: /review@... marker.
    run_validation(
        "Review Marker (SHA-bound /review)",
        state,
        lambda: validate_review_marker(repo_root),
    )

    total_duration = time.monotonic() - start_time

    # Summary
    print()
    print("=== Validation Summary ===")
    print(f"Duration: {total_duration:.2f}s")
    print(f"Total Validations: {state.total}")
    print(f"Passed: {state.passed}")
    print(f"Failed: {state.failed}")
    print(f"Skipped: {state.skipped}")
    print()

    print("=== Detailed Results ===")
    print()
    for record in state.results:
        duration_str = f" ({record.duration:.2f}s)" if record.duration > 0 else ""
        print(f"[{record.status}] {record.name}{duration_str}")

    print()

    if state.failed > 0:
        print(f"RESULT: {state.failed} validation(s) failed")
        print()
        print("Fix suggestions:")
        print("  1. Review error messages above for specific issues")
        print("  2. Run individual validation scripts for more details")
        print("  3. See .agents/SHIFT-LEFT.md for workflow documentation")
        print()
        return 1

    print("RESULT: All validations passed")
    print()
    print("Ready to create pull request!")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
