#!/usr/bin/env python3
"""Plugin, install, and hook gates for the pre-PR runner.

Extracted from ``scripts/validation/pre_pr.py`` (issue #2223). Groups the
checks that guard install-copy parity, the plugin.json version bump, hook
anchoring, local git-hooks installation, and the shift-left workflow local-run.

Behavior-preserving move: each function is identical to its previous definition
in ``pre_pr.py``. ``pre_pr`` re-exports these names so existing imports keep
working.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from checks_common import (  # noqa: E402
    MissingScriptSkip,
    _resolve_branch_base_ref,
    _run_build_script_gate,
    _run_subprocess,
)


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
