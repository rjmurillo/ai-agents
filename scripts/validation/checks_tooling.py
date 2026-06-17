#!/usr/bin/env python3
"""External-tool validations for the pre-PR runner.

Extracted from ``scripts/validation/pre_pr.py`` (issue #2223). Groups the
checks that shell out to an external tool or a legacy PowerShell validator:
session-log validation, Pester tests, markdownlint, actionlint, yamllint,
path normalization, planning artifacts, and agent-drift detection. Also holds
``_find_latest_session_log``, the session-log discovery helper.

This began as a behavior-preserving move from ``pre_pr.py``. Later fixes can
land in this extracted module directly while ``pre_pr`` re-exports these names
so existing imports keep working.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from checks_common import (  # noqa: E402
    MissingScriptSkip,
    _resolve_branch_base_ref,
    _run_subprocess,
)
from checks_dash import _is_vendored  # noqa: E402


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
    """Run markdownlint auto-fix and validate branch markdown changes."""
    if not shutil.which("npx"):
        print("[FAIL] npx not found (Node.js required)")
        print("  Install Node.js: https://nodejs.org/")
        return False

    targets = _markdown_lint_targets(repo_root)
    if targets == []:
        print("[PASS] Markdown linting (no markdown files on branch)")
        return True
    if targets is None:
        print("Auto-fixing markdown files...")
        command = ["npx", "markdownlint-cli2", "--fix", "**/*.md"]
    else:
        print(f"Auto-fixing {len(targets)} changed markdown file(s)...")
        command = ["npx", "markdownlint-cli2", "--fix", *targets]

    exit_code, _, _ = _run_subprocess(command, cwd=repo_root)

    if exit_code != 0:
        print("[FAIL] Markdown linting failed (some issues cannot be auto-fixed)")
        print()
        print("Common unfixable issues:")
        print("  - MD040: Add language identifier to code blocks")
        print("  - MD033: Wrap generic types like ArrayPool<T> in backticks")
        return False

    return True


def _markdown_lint_targets(repo_root: Path) -> list[str] | None:
    """Return changed markdown files, [] for none, or None for full-repo fallback."""
    base_ref = _resolve_branch_base_ref(repo_root)
    if base_ref is None:
        print("[WARNING] Markdown lint target narrowing skipped: no base ref resolved")
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
            f"[WARNING] Markdown lint target narrowing skipped: git diff failed: {stderr}",
        )
        return None

    return [
        path
        for path in stdout.splitlines()
        if path.endswith(".md") and not _is_vendored(path) and (repo_root / path).is_file()
    ]


def validate_workflow_yaml(repo_root: Path) -> bool:
    """Validate GitHub Actions workflow files with actionlint.

    Scope is restricted to ``.github/workflows/`` by globbing that directory
    and passing the explicit file list to actionlint. This is deliberate:
    actionlint validates workflow files only. A bare ``actionlint`` with no
    path argument recursively scans every ``.yml``/``.yaml`` file, including
    composite action definitions under ``.github/actions/*/action.yml``, and
    misreads each composite ``action.yml`` as a workflow, emitting false
    errors (issue #2346). Composite actions cannot be validated with
    actionlint, so they are never passed to it here. Do not widen the glob
    to the repo root or to ``.github/``.

    actionlint shells out to shellcheck for ``run:`` scripts. shellcheck
    emits findings at four severities: ``error``, ``warning``, ``info``,
    ``style``. The ``info`` and ``style`` tiers are advisory. On a clean
    checkout the existing workflows carry advisory findings unrelated to any
    given PR, which turned this gate red on baseline and blocked merge work
    that touched no workflow (Issue #2374).

    Fix: raise the shellcheck severity floor to ``warning`` via
    ``SHELLCHECK_OPTS`` so only ``warning`` and ``error`` findings block.
    This mirrors the existing precedent that ``validate_yaml_style``
    (yamllint) treats style findings as non-blocking warnings.
    """
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

    shellcheck_env = dict(os.environ)
    existing_opts = shellcheck_env.get("SHELLCHECK_OPTS", "").strip()
    severity_opt = "--severity=warning"
    shellcheck_env["SHELLCHECK_OPTS"] = (
        f"{existing_opts} {severity_opt}".strip() if existing_opts else severity_opt
    )

    exit_code, stdout, stderr = _run_subprocess(
        ["actionlint"] + [str(f) for f in workflow_files],
        env=shellcheck_env,
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


def validate_copilot_version_pin(repo_root: Path) -> bool:
    """Guard the pinned @github/copilot CLI version (Issue #2630).

    Thin wrapper over ``check_copilot_version_pin.check_action``: fails the gate
    when the pin in ``.github/actions/ai-review/action.yml`` is missing,
    unparseable, or on the known-bad list (seed: 0.0.397). The action is absent
    in downstream installs, so SKIP rather than FAIL when it is not present.
    """
    from check_copilot_version_pin import EXIT_OK, check_action

    action = repo_root / ".github" / "actions" / "ai-review" / "action.yml"
    if not action.exists():
        raise MissingScriptSkip(
            "ai-review/action.yml not present (downstream install); nothing to pin-check"
        )
    return check_action(action) == EXIT_OK
