#!/usr/bin/env python3
"""Block git push when canonical agents/rules move without their install siblings.

Thin adapter over :mod:`push_guard_base`. Reuses the parity logic that lives
in ``build/scripts/validate_install_parity.py`` so the same rules apply in CI
(``scripts/validation/pre_pr.py``) and at push time (this guard). Activates on
any path that could anchor a parity group; the validator decides whether the
diff is actually drifting or whether the touched files form a clean group.

Hook Type: PreToolUse
Exit Codes (Claude Hook Semantics, exempt from ADR-035):
    0 = Allow (no parity drift detected, or the diff did not touch any
        tracked file)
    2 = Block (parity drift detected; the message lists missing siblings)

Fail-open path:
    The validator depends on the build script being importable. If the
    import or the call fails for an environmental reason (the build tree
    is absent on a consumer-repo checkout, the module raises an unexpected
    error), the guard fail-opens with an EVENT line so telemetry can
    flag the degraded state. Real parity violations always block; only
    infrastructure failures fail-open.
"""

from __future__ import annotations

import sys
from pathlib import Path

from _bootstrap import ensure_plugin_paths

ensure_plugin_paths()

from push_guard_base import emit_fail_open, run_guard  # noqa: E402
from hook_utilities import get_project_directory  # noqa: E402

GUARD_NAME = "install-parity"

# Globs that wake this guard. Multi-segment paths are checked by
# push_guard_base via prefix + suffix matching.
_GLOBS = (
    "templates/agents/*.shared.md",
    ".claude/agents/*.md",
    ".github/agents/*.agent.md",
    "src/claude/*.md",
    "src/copilot-cli/agents/*.agent.md",
    "src/vs-code-agents/*.agent.md",
    ".claude/rules/*.md",
    ".github/instructions/*.instructions.md",
    "src/copilot-cli/instructions/*.instructions.md",
)


def _import_validator():
    """Import the validator from the repo's build tree.

    Returns the module on success or ``None`` on failure. Importing is
    isolated so the guard can fail-open cleanly when the script is run in
    a consumer repo that does not vendor ``build/scripts/``.
    """
    project_dir = get_project_directory()
    if not project_dir:
        return None
    candidate = Path(project_dir) / "build" / "scripts"
    if not candidate.is_dir():
        return None
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))
    try:
        import validate_install_parity as vip  # noqa: PLC0415
    except ImportError as exc:
        emit_fail_open(
            GUARD_NAME,
            "import_failed",
            f"validate_install_parity: {type(exc).__name__}: {exc}",
        )
        return None
    return vip


def _validate(_matching: list[str], all_changed: list[str]) -> list[str]:
    vip = _import_validator()
    if vip is None:
        return []

    project_dir = get_project_directory()
    if not project_dir:
        emit_fail_open(GUARD_NAME, "no_project_dir", "get_project_directory returned empty")
        return []

    try:
        violations = vip.find_violations(all_changed, repo_root=Path(project_dir))
    except Exception as exc:  # pragma: no cover - defensive fail-open
        emit_fail_open(
            GUARD_NAME, "validator_raised", f"{type(exc).__name__}: {exc}"
        )
        return []

    if not violations:
        return []

    out: list[str] = ["Install-copy parity drift:"]
    for v in violations:
        out.append("")
        out.append(f"  [{v.kind}] {v.name}")
        out.append("    touched:")
        for p in v.touched:
            out.append(f"      {p}")
        out.append("    missing (required siblings):")
        for p in v.missing:
            out.append(f"      {p}")
    out.append("")
    out.append(
        "Fix: stage the missing files in this push. SHARED_AGENT siblings "
        "are templates/agents/X.shared.md, .claude/agents/X.md, "
        ".github/agents/X.agent.md, src/claude/X.md, "
        "src/copilot-cli/agents/X.agent.md, and src/vs-code-agents/X.agent.md. "
        "RULE siblings are .claude/rules/X.md, .github/instructions/X.instructions.md, "
        "and src/copilot-cli/instructions/X.instructions.md."
    )
    return out


def main() -> int:
    return run_guard(_validate, list(_GLOBS), GUARD_NAME)


if __name__ == "__main__":
    sys.exit(main())
