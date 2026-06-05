#!/usr/bin/env python3
"""External-tool validations for the pre-PR runner.

Extracted from ``scripts/validation/pre_pr.py`` (issue #2223). Groups the
checks that shell out to an external tool or a legacy PowerShell validator:
session-log validation, Pester tests, markdownlint, actionlint, yamllint,
path normalization, planning artifacts, and agent-drift detection. Also holds
``_find_latest_session_log``, the session-log discovery helper.

Behavior-preserving move: each function is identical to its previous definition
in ``pre_pr.py``. ``pre_pr`` re-exports these names so existing imports keep
working.
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from checks_common import MissingScriptSkip, _run_subprocess  # noqa: E402


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
