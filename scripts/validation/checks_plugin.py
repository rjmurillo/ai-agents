#!/usr/bin/env python3
"""Plugin, install, and hook gates for the pre-PR runner.

Extracted from ``scripts/validation/pre_pr.py`` (issue #2223). Groups the
checks that guard install-copy parity, the plugin.json version bump, hook
anchoring, local git-hooks installation, and the shift-left workflow local-run.

This began as a behavior-preserving move from ``pre_pr.py``. Later fixes can
land in this extracted module directly while ``pre_pr`` re-exports these names
so existing imports keep working.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from checks_common import (  # noqa: E402
    MissingScriptSkip,
    _resolve_default_base_ref,
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
    return bool(exit_code == 0)


def validate_copilot_agent_frontmatter(repo_root: Path) -> bool:
    """Every .github/agents/*.agent.md must have parseable YAML frontmatter (#2491-#2496).

    An unquoted description that embeds colon-bearing example text makes Copilot
    fail to load the agent ("mapping values are not allowed in this context").
    This gate parses each file's frontmatter exactly as a YAML loader would and
    blocks a regression of that class.
    """
    script = (
        repo_root / "scripts" / "validation" / "validate_copilot_agent_frontmatter.py"
    )
    if not script.exists():
        raise MissingScriptSkip("validate_copilot_agent_frontmatter.py not present")

    exit_code, stdout, stderr = _run_subprocess(
        [
            sys.executable,
            str(script),
            "--agents-dir",
            str(repo_root / ".github" / "agents"),
        ]
    )
    if exit_code != 0:
        detail = stdout.rstrip() or stderr.rstrip()
        if detail:
            print(detail)
    return bool(exit_code == 0)


def validate_shipped_skill_routes(repo_root: Path) -> bool:
    """Every ``Skill: <name>`` route in a plugin root must resolve in that root.

    Wraps ``scripts/validation/check_shipped_skill_routes.py``. Catches the
    coordination-drift class where a skill is deliberately dropped from a
    shipping set (``templates/platforms/copilot-cli.yaml``) but a routing table
    keeps pointing at it. Issue #2026 dropped ``merge-resolver`` from the
    Copilot toolkit as repo-specific; ``autoplan`` kept routing to it, so a
    consumer with a merge conflict was sent to a skill the plugin does not
    contain. Every gate passed because each control plane was self-consistent.

    The check carries no allowlist, so it also fails a route naming a skill
    that exists nowhere. Exit 2 (a vacuous scan, an unreadable file, no plugin
    root) is treated as failure alongside exit 1: a gate that could not run has
    not passed.

    Fails closed when the validator is absent rather than raising
    MissingScriptSkip; a silent skip would defeat the gate.
    """
    script = repo_root / "scripts" / "validation" / "check_shipped_skill_routes.py"
    if not script.exists():
        print(
            "[ERROR] check_shipped_skill_routes.py absent; the shipped-route "
            "gate cannot run. Hard failure: the gate is the point of "
            "registering this validator.",
            file=sys.stderr,
        )
        return False

    exit_code, stdout, stderr = _run_subprocess(
        [sys.executable, str(script), "--root", str(repo_root)]
    )
    output = (stdout or "") + (stderr or "")
    if output.strip():
        for line in output.strip().splitlines()[:40]:
            print(line)
    return bool(exit_code == 0)


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
    return bool(_run_build_script_gate(
        repo_root, "validate_install_parity.py", "install-parity"
    ))


def validate_agent_content_parity(repo_root: Path) -> bool:
    """Fail when .claude/agents/ and src/claude/ have differing file content.

    validate_install_parity checks co-change in a diff (did both siblings move
    together). It does NOT compare file contents on disk. This gate fills that
    gap: it reads both trees and byte-compares every shared file.

    Wraps ``build/scripts/check_agent_content_parity.py``. Exit 0 = clean,
    exit 1 = drift found, exit 2 = configuration error. All non-zero exits are
    hard failures; a configuration error means the gate could not run, so we
    fail closed.
    """
    script = repo_root / "build" / "scripts" / "check_agent_content_parity.py"
    if not script.is_file():
        print(
            f"[ERROR] check_agent_content_parity.py not found at {script}",
            file=sys.stderr,
        )
        return False

    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = (result.stdout + result.stderr).strip()
    if output:
        for line in output.splitlines()[:40]:
            print(line)
    return result.returncode == 0


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
    return bool(_run_build_script_gate(
        repo_root, "validate_plugin_version_bump.py", "plugin version-bump"
    ))


def _lefthook_check_command() -> list[str] | None:
    uv = shutil.which("uv")
    if uv:
        return [uv, "run", "--frozen", "lefthook", "version"]

    return None


def validate_lefthook_installed(repo_root: Path) -> bool:
    """Fail when the configured Lefthook runtime cannot start.

    CI skips this local-clone check because workflows invoke validation directly.

    This gate must not call ``lefthook check-install``: that command compares
    the shared checksum written by the last installing branch, so a sibling
    branch with different hook config makes another worktree fail even though
    the native shim resolves Lefthook from the active worktree. Issue #4789.

    What each of the two adjacent gates proves, so neither is read as covering
    the other. This one proves the configured runtime starts. ``Git Hook
    Health`` proves git will run the shim and that the shim dispatches Lefthook,
    by requiring Lefthook's own dispatch line as the installed ``pre-push``
    file's final command (``check_git_hook_health.DISPATCH_MARKER``), because an
    executable ``#!/bin/sh`` plus ``exit 0`` satisfies both a runtime-start check
    and an executability check while running no job at all.

    Neither gate proves the shim resolves the same binary this one starts, and
    on Windows they demonstrably differ.
    ``tests/test_lefthook_integration.py::test_install_resets_legacy_hooks_path``
    records that Lefthook 2.1.10 generates the default Windows template, which
    omits the configured ``uv run --frozen lefthook`` runner and resolves
    Lefthook through ``PATH``. So on Windows ``lefthook version`` through uv can
    pass while the shim resolves a different binary, or none. Closing that needs
    a Windows probe with the uv runtime present and the ``PATH`` binary absent,
    which is not covered here. Issue #4789, PR #5358 review.
    """
    if (
        os.environ.get("GITHUB_ACTIONS", "").lower() in ("true", "1")
        or os.environ.get("CI", "").lower() in ("true", "1")
    ):
        raise MissingScriptSkip("lefthook installation check skipped under CI")

    config = repo_root / "lefthook.yml"
    if not config.is_file():
        print("[ERROR] lefthook.yml is absent; installation cannot be verified.", file=sys.stderr)
        return False

    command = _lefthook_check_command()
    if command is None:
        print(
            "[ERROR] uv is unavailable. Lefthook jobs run through uv. "
            "Install uv, then run: uv sync --frozen --extra dev",
            file=sys.stderr,
        )
        return False

    exit_code, stdout, stderr = _run_subprocess(
        command,
        cwd=repo_root,
    )
    if stdout.strip():
        print(stdout.strip())
    if stderr.strip():
        print(stderr.strip(), file=sys.stderr)
    if exit_code != 0:
        print(
            "[FAIL] Lefthook runtime is unavailable. Run: "
            "uv sync --frozen --extra dev"
        )
        return False
    return True


def _add_workflow_paths(repo_root: Path, diff_out: str, changed: list[str]) -> None:
    """Append new ``.github/workflows`` YAML paths from ``diff_out`` to ``changed``.

    Filters to workflow YAML files that still exist on disk (the ``is_file``
    check drops deleted paths) and skips duplicates already collected.
    """
    for line in diff_out.splitlines():
        if not line.startswith(".github/workflows/"):
            continue
        if not line.endswith((".yml", ".yaml")):
            continue
        if not (repo_root / line).is_file():
            continue
        if line not in changed:
            changed.append(line)


def _collect_changed_workflows(repo_root: Path, base_ref: str) -> list[str] | None:
    """Union of changed workflow files across every local git state (issue #3134).

    Combines four sources so a workflow edit is detected before it is committed:
    committed range ``<base>...HEAD``, staged (``--cached``), unstaged, and
    untracked (``ls-files --others --exclude-standard``). Deleted paths are
    dropped by the ``is_file`` check in :func:`_add_workflow_paths`; duplicates
    across sources collapse to the first occurrence.

    Returns None when the committed-range diff itself fails (unresolved base
    ref, git error), signalling the caller to warn and skip. The local sources
    are best-effort: a non-zero exit contributes no paths but does not abort.
    """
    committed_code, committed_out, _ = _run_subprocess(
        ["git", "-C", str(repo_root), "diff", "--name-only", f"{base_ref}...HEAD"]
    )
    if committed_code != 0:
        return None
    changed: list[str] = []
    _add_workflow_paths(repo_root, committed_out, changed)
    local_sources = [
        ["git", "-C", str(repo_root), "diff", "--cached", "--name-only"],
        ["git", "-C", str(repo_root), "diff", "--name-only"],
        ["git", "-C", str(repo_root), "ls-files", "--others", "--exclude-standard"],
    ]
    for cmd in local_sources:
        code, out, _ = _run_subprocess(cmd)
        if code == 0:
            _add_workflow_paths(repo_root, out, changed)
    return changed


def validate_workflow_local_run(repo_root: Path) -> bool:
    """Shift-left tier of the workflow local-run gate (actionlint + act -n).

    Runs the fast stages of ``scripts/validation/run_workflow_local_test.py``
    (``--no-full``) over the changed ``.github/workflows`` files. The full
    ``gh act`` execution stage is reserved for the pre-push hook so pre_pr stays
    fast and does not require a running Docker daemon.

    Contract: pass when no workflow changed or all run stages pass. A stage
    failure (exit 1) blocks. A configuration error (exit 2: a path that escapes
    the repo root, or a missing repo root) also blocks, because the inputs are
    wrong and a clean run cannot be trusted. Missing local tools (exit 3) and
    missing local auth material (exit 4) do NOT block here, because the pre-push
    gate is the authoritative enforcer; pre_pr only warns so a contributor
    without local workflow dependencies is not stopped pre-PR.

    Change detection uses :func:`_resolve_default_base_ref` to choose a default
    branch ref for the diff. The branch's own upstream is deliberately not used:
    once the branch is pushed it yields an empty diff, which is how pre_pr
    previously missed changed workflows that pre-push detected (issue #2571).

    :func:`_collect_changed_workflows` unions the committed range with staged,
    unstaged, and untracked git states (issue #3134) so a workflow edit is
    validated before it is committed, not only after.
    """
    script = repo_root / "scripts" / "validation" / "run_workflow_local_test.py"
    if not script.exists():
        raise MissingScriptSkip("run_workflow_local_test.py not present")

    base_ref = _resolve_default_base_ref(repo_root)
    if not base_ref:
        print("[WARN] workflow local-run: base ref unresolved; skipping.")
        return True

    changed = _collect_changed_workflows(repo_root, base_ref)
    if changed is None:
        print("[WARN] workflow local-run: git diff failed; skipping.")
        return True
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
    if exit_code == 4:
        print(
            "[WARN] workflow local-run auth material unavailable locally; "
            "actionlint passed and CI runs with repository secrets."
        )
        return True
    return bool(exit_code == 0)


def validate_colocated_skill_tests(repo_root: Path) -> bool:
    """Block newly added test files in customer-shipped skill directories.

    Wraps ``scripts/validation/check_colocated_skill_tests.py``. Returns True
    when no new colocated tests are detected. Issue #4838.
    """
    script = repo_root / "scripts" / "validation" / "check_colocated_skill_tests.py"
    if not script.is_file():
        print("[ERROR] check_colocated_skill_tests.py not found")
        return False
    cmd = [sys.executable, str(script), "--repo-root", str(repo_root)]
    exit_code, stdout, stderr = _run_subprocess(cmd)
    output = (stdout or "") + (stderr or "")
    if output.strip():
        for line in output.strip().splitlines()[:40]:
            print(line)
    return bool(exit_code == 0)
