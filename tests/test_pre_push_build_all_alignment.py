#!/usr/bin/env python3
"""Regression coverage for Issue #2343: pre-push must agree with build_all.py --check.

The pre-push hook used to invoke two PowerShell scripts (``build/Generate-Agents.ps1``
and ``build/scripts/Detect-AgentDrift.ps1``) that were expunged in commit
7b8347da (ADR-042 Python migration). In any worktree where pwsh is not available
or the .ps1 file is absent, the hook printed ``SKIP: Agent generation (script
not found)`` while ``build/scripts/build_all.py --check`` -- which is the
authoritative gate per the issue -- passed cleanly. This disagreement is the
exact symptom Issue #2343 calls out from PR #2340 autofix.

These tests pin the script-content contract so the divergence cannot regress.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PRE_PUSH = REPO_ROOT / ".githooks" / "pre-push"


def _pre_push_text() -> str:
    return PRE_PUSH.read_text(encoding="utf-8")


def test_no_retired_powershell_generator_references() -> None:
    """Section 10's old ``Generate-Agents.ps1 -Validate`` invocation must be gone.

    ADR-042 retired the PowerShell script. ``build_all.py --check`` (Section
    11b) covers agent generation transitively via ``_build_agents`` in
    ``build/scripts/build_all.py``, so a separate Section 10 only created a
    contradictory signal.
    """
    text = _pre_push_text()
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            # Comments may reference the retired script by name for context.
            continue
        assert "Generate-Agents.ps1" not in stripped, (
            f"Retired PowerShell script Generate-Agents.ps1 referenced in "
            f"executable pre-push code: {stripped!r}. ADR-042 expunged it; "
            f"build_all.py --check is authoritative."
        )


def test_no_retired_powershell_drift_references() -> None:
    """Section 11's old ``Detect-AgentDrift.ps1`` invocation must be gone."""
    text = _pre_push_text()
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        assert "Detect-AgentDrift.ps1" not in stripped, (
            f"Retired PowerShell script Detect-AgentDrift.ps1 referenced in "
            f"executable pre-push code: {stripped!r}. Use the Python port "
            f"build/scripts/detect_agent_drift.py."
        )


def test_drift_check_uses_python_port() -> None:
    """The drift gate must invoke the Python port via the uv-aware launcher."""
    text = _pre_push_text()
    assert 'AGENT_DRIFT_SCRIPT="$REPO_ROOT/build/scripts/detect_agent_drift.py"' in text, (
        "Section 11 must point at the Python port at "
        "build/scripts/detect_agent_drift.py (ADR-042)."
    )
    # The launcher must be uv-aware (set_python_cmd) so it matches the
    # Phase-2/4 sites and Section 11b -- bare python3 raises ImportError on
    # PyYAML in uv-managed checkouts.
    drift_block_start = text.index("# 11. Agent drift detection")
    drift_block_end = text.index("# 11b. Build pipeline staleness")
    drift_block = text[drift_block_start:drift_block_end]
    assert "set_python_cmd" in drift_block, (
        "Section 11 must launch the Python drift script via set_python_cmd "
        "(uv-aware), not bare python3 or pwsh."
    )
    assert 'pwsh' not in drift_block, (
        "Section 11 must not shell out to pwsh; ADR-042 retired all "
        "PowerShell scripts in this code path."
    )


def test_drift_check_only_runs_for_agent_paths() -> None:
    """Non-agent src changes must not trigger whole-repo drift checks.

    PR #2335 changed `src/copilot-cli/skills/review/*`; the old broad `src/`
    trigger ran global agent drift and blocked on unrelated baseline drift.
    """
    text = _pre_push_text()
    drift_block_start = text.index("# 11. Agent drift detection")
    drift_block_end = text.index("# 11b. Build pipeline staleness")
    drift_block = text[drift_block_start:drift_block_end]
    assert "src/(claude|vs-code-agents|copilot-cli/agents)/" in drift_block
    assert "'^(src/|templates/" not in drift_block


def test_build_all_check_remains_authoritative() -> None:
    """Section 11b's ``build_all.py --check`` invocation must remain intact.

    Per Issue #2343 the issue body, ``build_all.py --check`` is the
    intended source of truth. Any future refactor that drops this section
    would lose the only gate that actually exercises the Python generators.
    """
    text = _pre_push_text()
    assert 'BUILD_ALL_SCRIPT="$REPO_ROOT/build/scripts/build_all.py"' in text
    assert '"$BUILD_ALL_SCRIPT" --check' in text


def test_drift_missing_message_names_exact_path() -> None:
    """When the drift script is missing, the SKIP message must name the path.

    Acceptance criterion from Issue #2343: "Missing-script messages include
    exact paths and whether the condition is blocking." Generic "script not
    found" messages sent agents chasing phantom dependencies during the
    PR #2340 autofix.
    """
    text = _pre_push_text()
    # The SKIP message for a missing drift script must interpolate the path
    # variable AND explicitly state the condition is non-blocking.
    assert "script not found at $AGENT_DRIFT_SCRIPT" in text, (
        "Missing-script SKIP must name the exact path via $AGENT_DRIFT_SCRIPT."
    )
    assert "non-blocking" in text and "build_all.py --check is authoritative" in text, (
        "Missing-script SKIP must state the condition is non-blocking and "
        "point agents at build_all.py --check as the source of truth."
    )
