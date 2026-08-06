#!/usr/bin/env python3
"""External-tool validations for the pre-PR runner (extracted from
``scripts/validation/pre_pr.py``, issue #2223): session-log, Pester,
markdownlint, actionlint, yamllint, path normalization, planning artifacts,
agent-drift, plus ``_find_latest_session_log``; re-exported by ``pre_pr``.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
from collections.abc import Callable
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

MARKDOWNLINT_CLI2_PACKAGE = "markdownlint-cli2@0.23.1"
# "Linting: N files" prints before any read; Summary's count is files *with
# issues*, so a clean file and an unselected file both read as 0-of-0.
_LINTED_COUNT_PATTERN = re.compile(r"^Linting: (\d+) files?$", re.MULTILINE)


def _require_script(script: Path) -> None:
    """Raise MissingScriptSkip if ``script`` is absent (a SKIP, not a FAIL)."""
    if not script.exists():
        raise MissingScriptSkip(
            f"{script.name} not present (ADR-042 expungement; no Python port yet)"
        )


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
    _require_script(script)

    exit_code, _, _ = _run_subprocess(
        ["pwsh", "-NoProfile", "-File", str(script), "-SessionLogPath", str(session_log)]
    )
    return bool(exit_code == 0)


def validate_pester_tests(repo_root: Path, verbose: bool = False) -> bool:
    """Run Pester unit tests."""
    script = repo_root / "build" / "scripts" / "Invoke-PesterTests.ps1"
    _require_script(script)

    verbosity = "Diagnostic" if verbose else "Normal"
    exit_code, _, _ = _run_subprocess(
        ["pwsh", "-NoProfile", "-File", str(script), "-Verbosity", verbosity]
    )
    return bool(exit_code == 0)


def validate_markdown_lint(repo_root: Path, explicit_targets: list[str] | None = None) -> bool:
    """Validate Markdown and report whether markdownlint selected any files.

    ``explicit_targets`` (Lefthook's staged-file jobs) keeps the hook on the
    same reporting path as the pre-PR validator while still letting
    markdownlint-cli2 apply ``ignores`` from ``.markdownlint-cli2.yaml``.
    """
    if not shutil.which("npx"):
        print("[FAIL] npx not found (Node.js required)")
        print("  Install Node.js: https://nodejs.org/")
        return False

    targets = (
        explicit_targets if explicit_targets is not None else _markdown_lint_targets(repo_root)
    )
    scope_name = "selected" if explicit_targets is not None else "branch"
    if targets == []:
        print(f"[PASS] Markdown linting (no markdown files on {scope_name})")
        return True

    autofix = os.environ.get("SKIP_AUTOFIX") != "1"
    action = "Auto-fixing" if autofix else "Checking"
    target_args = ["**/*.md"] if targets is None else targets
    scope = (
        "markdown files" if targets is None else f"{len(target_args)} {scope_name} markdown file(s)"
    )
    print(f"{action} {scope}...")
    command = ["npx", MARKDOWNLINT_CLI2_PACKAGE]
    if autofix:
        command.append("--fix")
    command.append("--")
    command.extend(target_args)

    exit_code, stdout, stderr = _run_subprocess(command, cwd=repo_root)
    if exit_code == 0:
        _report_selection(target_args, stdout)
        return True

    print("[FAIL] Markdown linting failed")
    print()
    # Prefer stderr (violations); stdout's "Finding:" line restates all 44
    # exclusion globs on one long line, burying the file/line/rule. stdout is
    # the fallback when a failure never reaches the violation reporter (e.g.
    # an unparsable config).
    detail = stderr if stderr.strip() else stdout
    for line in detail.splitlines():
        if line.strip():
            print(f"  {line}")
    print()
    print("Common issues:")
    print("  - MD040: Add language identifier to code blocks")
    print("  - MD033: Wrap generic types like ArrayPool<T> in backticks")
    return False


def _linted_file_count(stdout: str) -> int | None:
    """Return files markdownlint-cli2 selected, or None (unknown, not zero)."""
    match = _LINTED_COUNT_PATTERN.search(stdout)
    return int(match.group(1)) if match else None


def _report_selection(target_args: list[str], stdout: str) -> None:
    """Say whether a green run checked anything (issue #3710).

    ``.markdownlint-cli2.yaml`` excludes 89.7% of tracked markdown; naming an
    excluded file selects nothing and exits 0, so a PASS must say which
    kind of PASS it is.
    """
    selected = _linted_file_count(stdout)
    if selected is None:
        print(
            "[WARNING] Markdown linting: could not read the 'Linting: N files' "
            "banner, so how many files were checked is unknown"
        )
        return
    if selected == 0 and target_args:
        print(
            f"[WARNING] Markdown linting selected 0 of {len(target_args)} target(s): "
            "each is excluded by .markdownlint-cli2.yaml, matched no file, or no "
            "longer exists, so nothing was checked. This PASS means 'not "
            "linted', not 'clean'."
        )
        return
    if selected < len(target_args):
        print(
            f"[WARNING] Markdown linting checked {selected} of {len(target_args)} "
            "target(s); the rest were excluded by .markdownlint-cli2.yaml, "
            "matched no file, or no longer exist"
        )


def _git_paths_z(
    repo_root: Path, args: list[str], warn_label: str, action: str
) -> list[str] | None:
    """Run a git subcommand that lists paths NUL-delimited; None on failure.

    ``args`` is the argv after ``git -C <repo_root>`` (each subcommand's own
    ``-z``/``--name-only`` flags). ``-z`` keeps Unicode/space paths intact:
    verified this session, plain ``git diff --name-only`` C-quotes
    ``日本語.md`` as an octal escape; ``-z`` prints raw UTF-8, NUL-terminated.
    """
    exit_code, stdout, stderr = _run_subprocess(
        ["git", "-C", str(repo_root), *args],
        timeout=30,
    )
    if exit_code != 0:
        print(f"[WARNING] {warn_label} target narrowing skipped: {action} failed: {stderr}")
        return None
    return [path for path in stdout.split("\0") if path]


def _changed_paths_since_base(repo_root: Path, warn_label: str) -> list[str] | None:
    """Return the union of changed paths, or None for full-scan fallback.

    Shared by the markdown/workflow/yaml target helpers. Unions three
    signals so a worktree-only edit (staged, unstaged, or brand new) is
    never invisible to a gate's scope: (1) committed changes since the base
    ref (``<base>...HEAD``); (2) uncommitted changes against HEAD, a
    two-dot ``git diff HEAD`` covering the index AND working tree in one
    call; (3) untracked files (``git ls-files --others --exclude-standard``).
    All three run ``-z``; see :func:`_git_paths_z`.

    Returns None (full-scan fallback) when the base ref cannot be resolved
    or ANY command fails -- a failure is a proof failure, not "no changes".
    Returns ``[]`` for a clean worktree. ACMR filtering (Added, Copied,
    Modified, Renamed; no Deleted) is preserved for the two diffs; untracked
    files are included as-is. Callers still apply the existing per-path
    ``(repo_root / path).is_file()`` check afterward.
    """
    base_ref = _resolve_branch_base_ref(repo_root)
    if base_ref is None:
        print(f"[WARNING] {warn_label} target narrowing skipped: no base ref resolved")
        return None

    diff_filter = ["diff", "--name-only", "-z", "--diff-filter=ACMR"]
    sources = (
        (diff_filter + [f"{base_ref}...HEAD"], "git diff (base ref)"),
        (diff_filter + ["HEAD"], "git diff (worktree)"),
        (["ls-files", "--others", "--exclude-standard", "-z"], "git ls-files (untracked)"),
    )

    seen: set[str] = set()
    changed_paths: list[str] = []
    for args, action in sources:
        group = _git_paths_z(repo_root, args, warn_label, action)
        if group is None:
            return None
        for path in group:
            if path not in seen:
                seen.add(path)
                changed_paths.append(path)
    return changed_paths


def _print_capped(output: str, limit: int, unit: str) -> None:
    """Print at most ``limit`` lines of ``output``, then an omitted-count note."""
    lines = output.strip().split("\n")
    for line in lines[:limit]:
        print(line)
    if len(lines) > limit:
        print(f"... ({len(lines) - limit} more {unit} omitted)")


def _filtered_targets(
    repo_root: Path, warn_label: str, predicate: Callable[[str], bool]
) -> list[str] | None:
    """Return changed paths matching ``predicate`` and still on disk.

    None/[] pass through unchanged from :func:`_changed_paths_since_base`;
    ``(repo_root / path).is_file()`` drops any path no longer on disk.
    """
    changed = _changed_paths_since_base(repo_root, warn_label)
    if changed is None:
        return None
    return [path for path in changed if predicate(path) and (repo_root / path).is_file()]


def _markdown_lint_targets(repo_root: Path) -> list[str] | None:
    """Return changed markdown files, [] for none, or None for full-repo fallback."""
    return _filtered_targets(
        repo_root, "Markdown lint", lambda p: p.endswith(".md") and not _is_vendored(p)
    )


def _workflow_yaml_targets(repo_root: Path) -> list[str] | None:
    """Return changed workflow YAML files, [] for none, or None for full fallback.

    Drops composite ``action.yml`` (same false-error reason as the full scan, #2346).
    """
    return _filtered_targets(
        repo_root,
        "Workflow lint",
        lambda p: p.startswith(".github/workflows/") and p.endswith((".yml", ".yaml")),
    )


def _yaml_style_targets(repo_root: Path) -> list[str] | None:
    """Return changed YAML files, [] for none, or None for full-repo fallback.

    No vendored filter: yamllint applies ``.yamllint.yml``'s ``ignore:`` per
    path already (verified 1.38.0: no-op, exit 0), unlike markdown.
    """
    return _filtered_targets(repo_root, "YAML style", lambda p: p.endswith((".yml", ".yaml")))


def validate_workflow_yaml(repo_root: Path) -> bool:
    """Validate GitHub Actions workflow files with actionlint.

    Scoped to ``.github/workflows/``: a bare ``actionlint`` recursively scans
    every YAML file, including composite actions under
    ``.github/actions/*/action.yml``, misreading each as a workflow (issue
    #2346); never widen the glob.

    actionlint shells to shellcheck for ``run:`` scripts at four severities;
    ``info``/``style`` are advisory and turned this gate red on unrelated
    pre-existing findings (Issue #2374), so ``SHELLCHECK_OPTS`` raises the
    floor to ``warning``, mirroring ``validate_yaml_style``'s precedent. An
    empty ``_workflow_yaml_targets`` change set passes without invoking
    actionlint; an unproven scope falls back to the full glob below.
    """
    if not shutil.which("actionlint"):
        print("[WARNING] actionlint not found (workflow validation skipped)")
        print("  Install actionlint to enable GitHub Actions workflow validation.")
        return True

    workflow_path = repo_root / ".github" / "workflows"
    if not workflow_path.is_dir():
        print("[WARNING] No .github/workflows directory found")
        return True

    targets = _workflow_yaml_targets(repo_root)
    if targets == []:
        print("[PASS] Workflow validation (no changed workflow files)")
        return True

    if targets is None:
        workflow_files = list(workflow_path.glob("*.yml")) + list(workflow_path.glob("*.yaml"))
        if not workflow_files:
            print("[WARNING] No workflow files found in .github/workflows/")
            return True
        file_args = [str(f) for f in workflow_files]
        print(f"Validating {len(file_args)} workflow file(s)...")
    else:
        file_args = [str(repo_root / path) for path in targets]
        print(f"Validating {len(file_args)} changed workflow file(s)...")

    shellcheck_env = dict(os.environ)
    existing_opts = shellcheck_env.get("SHELLCHECK_OPTS", "").strip()
    severity_opt = "--severity=warning"
    shellcheck_env["SHELLCHECK_OPTS"] = (
        f"{existing_opts} {severity_opt}".strip() if existing_opts else severity_opt
    )

    exit_code, stdout, stderr = _run_subprocess(
        ["actionlint"] + file_args,
        env=shellcheck_env,
    )

    if exit_code != 0:
        print("[FAIL] actionlint found issues in workflow files")
        _print_capped(stdout or stderr, 20, "lines")
        return False

    print("All workflow files validated successfully.")
    return True


def validate_yaml_style(repo_root: Path) -> bool:
    """Check YAML style with yamllint (advisory: findings warn, never fail).

    An empty ``_yaml_style_targets`` change set passes without invoking
    yamllint; an unproven scope falls back to the full-repo scan.
    """
    if not shutil.which("yamllint"):
        print("[WARNING] yamllint not found (YAML style validation skipped)")
        return True

    targets = _yaml_style_targets(repo_root)
    if targets == []:
        print("[PASS] YAML style check (no changed YAML files)")
        return True

    if targets is None:
        target_args = [str(repo_root)]
        print("Checking YAML files for style issues...")
    else:
        target_args = [str(repo_root / path) for path in targets]
        print(f"Checking {len(target_args)} changed YAML file(s) for style issues...")

    exit_code, stdout, stderr = _run_subprocess(["yamllint", "-f", "parsable", *target_args])

    if exit_code != 0:
        print("[WARNING] yamllint found style issues (non-blocking)")
        _print_capped(stdout or stderr, 30, "issues")
        print()
        print("Note: These are warnings, not errors. Fix when convenient.")
        return True

    print("All YAML files conform to style guidelines.")
    return True


def validate_path_normalization(repo_root: Path) -> bool:
    """Check for absolute paths."""
    script = repo_root / "build" / "scripts" / "Validate-PathNormalization.ps1"
    _require_script(script)

    exit_code, _, _ = _run_subprocess(
        ["pwsh", "-NoProfile", "-File", str(script), "-FailOnViolation"]
    )
    return bool(exit_code == 0)


def validate_planning_artifacts(repo_root: Path) -> bool:
    """Validate planning consistency."""
    script = repo_root / "build" / "scripts" / "Validate-PlanningArtifacts.ps1"
    _require_script(script)

    exit_code, _, _ = _run_subprocess(["pwsh", "-NoProfile", "-File", str(script), "-FailOnError"])
    return bool(exit_code == 0)


def validate_agent_drift(repo_root: Path) -> bool:
    """Detect agent semantic drift (ADR-042 ported Detect-AgentDrift.ps1 to
    build/scripts/detect_agent_drift.py, invoked directly here).

    Runs two comparisons (Issue #2267): vendored src/claude vs
    src/vs-code-agents (blocking), and .claude/agents vs .github/agents
    (advisory only, large pre-existing diffs). Only vendored drift blocks.
    """
    python_script = repo_root / "build" / "scripts" / "detect_agent_drift.py"
    if python_script.exists():
        exit_code, stdout, stderr = _run_subprocess([sys.executable, str(python_script)])
        output = (stdout or "") + (stderr or "")
        if output.strip():
            _print_capped(output, 100, "lines")
        return bool(exit_code == 0)

    # Neither port nor original PS1 exists: SKIP, not a misleading FAIL.
    legacy = repo_root / "build" / "scripts" / "Detect-AgentDrift.ps1"
    if not legacy.exists():
        raise MissingScriptSkip(
            "detect_agent_drift.py and Detect-AgentDrift.ps1 both absent (ADR-042 expungement)"
        )

    exit_code, _, _ = _run_subprocess(["pwsh", "-NoProfile", "-File", str(legacy)])
    return bool(exit_code == 0)


def validate_copilot_version_pin(repo_root: Path) -> bool:
    """Guard the pinned @github/copilot CLI version (Issue #2630).

    Wraps ``check_copilot_version_pin.check_action``: fails when the pin is
    missing, unparseable, or known-bad; SKIP when the action is absent.
    """
    from check_copilot_version_pin import EXIT_OK, check_action

    action = repo_root / ".github" / "actions" / "ai-review" / "action.yml"
    if not action.exists():
        raise MissingScriptSkip(
            "ai-review/action.yml not present (downstream install); nothing to pin-check"
        )
    return bool(check_action(action) == EXIT_OK)


def validate_ci_dependency_pins(repo_root: Path) -> bool:
    """Assert every hand-written pkg==version pin in .github/ YAML agrees
    with pyproject.toml (Issue #3377); SKIP when ``.github/`` is absent.
    """
    workflows = repo_root / ".github"
    pyproject = repo_root / "pyproject.toml"
    if not workflows.is_dir() or not pyproject.is_file():
        raise MissingScriptSkip(
            ".github/ or pyproject.toml not present (downstream install); no pins to check"
        )
    from check_ci_dependency_pins import EXIT_OK as PIN_OK
    from check_ci_dependency_pins import check as check_pins

    return bool(check_pins(workflows, pyproject) == PIN_OK)


def validate_instruction_budget(repo_root: Path) -> bool:
    """Gate the always-on instruction budget per language (Issue #3419).

    Sums the bytes of ``.github/instructions/*.instructions.md`` files whose
    ``applyTo`` scopes them to every file of a language, failing past the
    non-regression ceiling. SKIP when the instructions tree is absent.
    """
    if not (repo_root / ".github" / "instructions").is_dir():
        raise MissingScriptSkip(
            ".github/instructions not present (downstream install); no budget to gate"
        )
    exit_code, stdout, stderr = _run_subprocess(
        [
            sys.executable,
            "-m",
            "scripts.validation.instruction_budget",
            "--ci",
            "--path",
            str(repo_root),
        ],
        cwd=repo_root,
    )
    if exit_code != 0:
        if stdout:
            print(stdout)
        if stderr:
            print(stderr, file=sys.stderr)
    return bool(exit_code == 0)
