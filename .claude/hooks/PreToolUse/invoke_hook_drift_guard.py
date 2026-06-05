#!/usr/bin/env python3
"""Block git push when hook generator output drifts from canonical source.

Alt B (deterministic full-tree regeneration + drift gate) was already
shipped at CI level via build/scripts/build_all.py --check inside
.github/workflows/validate-generated-agents.yml. That gate catches the
"edited a canonical .claude/hooks/<Event>/*.py without regenerating the
matcher shims under src/copilot-cli/hooks/<event>/" class of bug.

This guard adds the same check at git-push time so the feedback loop
moves from CI (minutes) to local terminal (seconds). Activates when
the push touches a canonical hook source, the Claude settings.json, or
a generated shim file. Then runs the generator and compares the
resulting file-system state to detect drift on hook paths.

Why not call build_all.py --check directly?
    build_all.py --check runs all generators (rules, agents, skills,
    commands, lib, hooks). Total: ~0.2s. For a pre-push hook we want
    fast feedback. This guard scopes to hook-related diff only and
    fail-opens on infrastructure errors (build tree absent, generator
    raises) so consumer-repo checkouts are not blocked.

Hook Type: PreToolUse
Exit Codes (Claude Hook Semantics, exempt from ADR-035):
    0 = Allow (no hook-shim drift detected, or diff did not touch hook paths)
    2 = Block (drift detected; the message lists drifted shim paths)

Fail-open path:
    Build tree absent (consumer-repo checkout), generator module
    unimportable, or generator raises unexpectedly: emit a fail-open
    EVENT line for telemetry and allow the push. Real drift always
    blocks; only infrastructure failures fail-open.

Refs: ADR-061 (Withdrawn 2026-05-27); .agents/critique/ADR-061-debate-log.md
"""

from __future__ import annotations

import importlib.util
import io
import shutil
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from _bootstrap import ensure_plugin_paths

ensure_plugin_paths()

from push_guard_base import emit_fail_open, run_guard  # noqa: E402
from hook_utilities import get_project_directory  # noqa: E402

GUARD_NAME = "hook-drift"


def _emit_k1(detail: str) -> None:
    """Record a K1 kill-criteria event for this drift-guard block.

    K1 (REQ-008-09) counts drift-hook blocks so a maintainer can tell
    when the canonical contract is too strict (3+ false positives in 30
    days rolls back the convergence design). The drift-guard block is the
    raw K1 signal; classifying a block as a true vs false positive happens
    later at read time.

    Telemetry must never block a push: any failure to load or call the
    emitter is swallowed and surfaced as a fail-open EVENT line, never
    raised. The emitter lives outside the plugin lib
    (``scripts/metrics/kill_criteria.py``) and is loaded by file path from
    the project root.
    """
    try:
        project_dir = get_project_directory()
        emitter_path = Path(project_dir) / "scripts" / "metrics" / "kill_criteria.py"
        if not emitter_path.is_file():
            emit_fail_open(GUARD_NAME, "k1_emitter_missing", str(emitter_path))
            return
        spec = importlib.util.spec_from_file_location("kill_criteria", emitter_path)
        if spec is None or spec.loader is None:
            emit_fail_open(GUARD_NAME, "k1_emitter_unloadable", str(emitter_path))
            return
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.emit_event("K1", detail)
    except Exception as exc:  # pragma: no cover - defensive fail-open
        emit_fail_open(GUARD_NAME, "k1_emit_failed", f"{type(exc).__name__}: {exc}")

# Globs that wake this guard. A push that touches any of these has a
# non-trivial chance of causing hook-shim drift. The validator itself
# decides whether drift actually exists.
_GLOBS = (
    ".claude/hooks/*.py",
    ".claude/hooks/**/*.py",
    ".claude/settings.json",
    "src/copilot-cli/hooks/*.py",
    "src/copilot-cli/hooks/**/*.py",
)


def _import_generator():
    """Import generate_hooks from the repo's build tree.

    Returns ``(module, config_path, repo_root)`` on success, or
    ``None`` on any infrastructure failure (build tree absent,
    import failure). Every failure path emits a fail-open EVENT so
    telemetry surfaces the degraded state.
    """
    project_dir = get_project_directory()
    if not project_dir:
        emit_fail_open(
            GUARD_NAME,
            "no_project_dir",
            "get_project_directory returned empty; cannot locate build tree",
        )
        return None
    repo_root = Path(project_dir)
    candidate = repo_root / "build" / "scripts"
    if not candidate.is_dir():
        emit_fail_open(
            GUARD_NAME,
            "build_tree_absent",
            f"build/scripts not found under {project_dir}; consumer-repo checkout",
        )
        return None
    config_path = repo_root / "templates" / "platforms" / "copilot-cli.yaml"
    if not config_path.is_file():
        emit_fail_open(
            GUARD_NAME,
            "config_missing",
            f"copilot-cli.yaml not found at {config_path}",
        )
        return None
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))
    try:
        import generate_hooks as gh  # noqa: PLC0415
    except ImportError as exc:
        emit_fail_open(
            GUARD_NAME,
            "import_failed",
            f"generate_hooks: {type(exc).__name__}: {exc}",
        )
        return None
    return gh, config_path, repo_root


def _hook_diff_paths(repo_root: Path) -> list[str]:
    """Return uncommitted paths under src/copilot-cli/hooks/.

    Combines two sources so that both modified tracked files and new
    untracked files (e.g. freshly generated shims) are included:

    1. ``git diff --name-only`` (no HEAD): unstaged working-tree changes
       relative to the index (modified tracked files not yet staged);
       does not mix in committed state.
    2. ``git ls-files --others --exclude-standard src/copilot-cli/hooks/``:
       untracked files that the generator may have created.

    A failure to run git (binary not found, timeout) is treated as
    no-diff and the guard fails open. The calling hook returns 0 so
    that a broken environment does not block every push.
    """
    hook_prefix = "src/copilot-cli/hooks/"
    git_executable = shutil.which("git")
    if not git_executable:
        return []
    try:
        diff_result = subprocess.run(
            [git_executable, "-C", str(repo_root), "diff", "--name-only"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        untracked_result = subprocess.run(
            [
                git_executable,
                "-C",
                str(repo_root),
                "ls-files",
                "--others",
                "--exclude-standard",
                hook_prefix,
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    paths: list[str] = []
    if diff_result.returncode == 0:
        paths.extend(
            line
            for line in diff_result.stdout.splitlines()
            if line.startswith(hook_prefix)
        )
    if untracked_result.returncode == 0:
        paths.extend(
            line
            for line in untracked_result.stdout.splitlines()
            if line.startswith(hook_prefix)
        )
    return paths


def _validate(_matching: list[str], _all_changed: list[str]) -> list[str]:
    """Run the hook generator and report any drift on hook paths.

    Approach: snapshot the hook-path diff before running the generator,
    then run generate_hooks.generate_hooks() and snapshot again. Only
    paths that appear in the post-generator snapshot but not the
    pre-existing snapshot are reported. This isolates generator-introduced
    drift from any pre-existing local modifications and prevents false
    positives from unrelated uncommitted changes under src/copilot-cli/hooks/.

    Captures generator stdout/stderr to suppress its verbose audit
    output from the hook's user-facing message.
    """
    imported = _import_generator()
    if imported is None:
        return []
    gh, config_path, repo_root = imported

    # Snapshot pre-existing hook-path changes so they are not attributed
    # to this generator run (false-positive prevention).
    pre_existing = set(_hook_diff_paths(repo_root))

    # Run the generator. Suppress its stdout/stderr; we only care about
    # the resulting file-system state and the subsequent diff.
    try:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            rc, _run_result = gh.generate_hooks(config_path, repo_root)
    except Exception as exc:  # pragma: no cover - defensive fail-open
        emit_fail_open(
            GUARD_NAME,
            "generator_raised",
            f"{type(exc).__name__}: {exc}",
        )
        return []

    if rc != 0:
        emit_fail_open(
            GUARD_NAME,
            "generator_failed",
            f"generate_hooks returned non-zero: {rc}",
        )
        return []

    post_run = set(_hook_diff_paths(repo_root))
    drifted = sorted(post_run - pre_existing)
    if not drifted:
        return []

    _emit_k1(",".join(drifted))

    out: list[str] = [
        "Hook-shim drift detected (canonical edited without regenerating shims):",
    ]
    for path in drifted:
        out.append(f"  {path}")
    out.append("")
    out.append(
        "Fix: run `python3 build/scripts/build_all.py` to regenerate, then "
        "stage the resulting changes under src/copilot-cli/hooks/ and push "
        "again. The CI staleness gate (validate-generated-agents.yml) "
        "fires on the same condition; this guard catches it locally."
    )
    out.append(
        "Background: ADR-061 (withdrawn 2026-05-27) proposed a structural "
        "fix (delegate-shim). The 6-agent debate concluded that this "
        "drift gate at the procedural layer is sufficient until "
        "multi-matcher hook count exceeds 8 (current: 4). See "
        ".agents/critique/ADR-061-debate-log.md."
    )
    return out


def main() -> int:
    return run_guard(_validate, list(_GLOBS), GUARD_NAME, include_deletions=False)


if __name__ == "__main__":
    sys.exit(main())
