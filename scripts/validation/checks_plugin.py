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


def validate_lefthook_installed(repo_root: Path) -> bool:
    """Fail when Lefthook is unavailable, unconfigured, or not installed locally.

    CI skips this local-clone check because workflows invoke validation directly.
    A linked worktree keeps the existing warning policy because its hook storage
    is shared with the primary clone and may be outside the current change scope.
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

    lefthook = shutil.which("lefthook")
    if not lefthook:
        print(
            "[ERROR] Lefthook is unavailable. Run: uv sync --frozen --extra dev",
            file=sys.stderr,
        )
        return False

    exit_code, stdout, stderr = _run_subprocess(
        [lefthook, "check-install"],
        cwd=repo_root,
    )
    if stdout.strip():
        print(stdout.strip())
    if stderr.strip():
        print(stderr.strip(), file=sys.stderr)
    if exit_code == 0:
        return True
    if _is_linked_worktree(repo_root):
        print(
            "[WARNING] Lefthook is not installed in this linked worktree. "
            "Install it from the primary clone with: "
            "uv run --frozen lefthook install "
            "(non-blocking here, Issue #2374)."
        )
        return True
    print(
        "[FAIL] Lefthook is not installed. Run: "
        "uv run --frozen lefthook install"
    )
    return False


def _is_linked_worktree(repo_root: Path) -> bool:
    """True when ``repo_root`` is a linked git worktree, not the primary clone.

    A linked worktree has a ``--git-dir`` that differs from its
    ``--git-common-dir``; the primary clone has the two equal. Returns False
    when git is unavailable or the paths cannot be resolved, so the caller
    keeps its default hard-fail behavior rather than silently downgrading.
    """
    if not shutil.which("git"):
        return False
    exit_code, stdout, _ = _run_subprocess(
        [
            "git",
            "-C",
            str(repo_root),
            "rev-parse",
            "--git-dir",
            "--git-common-dir",
        ],
        timeout=10,
    )
    if exit_code != 0:
        return False
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    if len(lines) != 2:
        return False
    git_dir, git_common_dir = lines
    git_dir_path = Path(git_dir)
    git_common_dir_path = Path(git_common_dir)
    if not git_dir_path.is_absolute():
        git_dir_path = repo_root / git_dir_path
    if not git_common_dir_path.is_absolute():
        git_common_dir_path = repo_root / git_common_dir_path
    return git_dir_path.resolve() != git_common_dir_path.resolve()


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
