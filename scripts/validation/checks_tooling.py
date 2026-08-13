#!/usr/bin/env python3
# taste-lint: ignore file-size
#
# file-size suppression rationale: this module groups validators that shell out
# to external tools. Its line count tracks how many such gates exist, not
# complexity. The real fix is splitting by area (issue #3073 scope), which is
# out of scope for adding a single gate.
"""External-tool validations for the pre-PR runner (extracted from
``scripts/validation/pre_pr.py``, issue #2223): session-log, Pester,
markdownlint, actionlint, yamllint, path normalization, planning artifacts,
agent-drift, plus ``_find_latest_session_log``; re-exported by ``pre_pr``.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import cast

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from checks_changed_paths import _filtered_targets  # noqa: E402
from checks_common import (  # noqa: E402
    MissingScriptSkip,
    _resolve_branch_base_ref,
    _run_subprocess,
)
from checks_dash import _is_vendored  # noqa: E402
from checks_workflow_targets import _workflow_yaml_targets  # noqa: E402

from scripts.validation.session_scope import new_session_logs  # noqa: E402

MARKDOWNLINT_CLI2_PACKAGE = "markdownlint-cli2@0.23.1"
MARKDOWNLINT_TARGET_BATCH_LIMIT = 100
# Keep target arguments below Windows cmd.exe's 8,191-character limit; npx
# resolves through npx.cmd there. The remaining space covers command overhead.
MARKDOWNLINT_COMMAND_LENGTH_LIMIT = 7_500
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


def _prepr_session_command(
    python_script: Path,
    log_path: Path,
    relative_path: str,
    new_logs: set[str],
    validation_head: str,
) -> list[str]:
    """Build the pre-PR validator command for one changed session log."""
    command = [sys.executable, str(python_script), str(log_path)]
    if relative_path in new_logs:
        return [*command, "--validation-head", validation_head]
    return [*command, "--existing-log"]


def _changed_session_paths(output: str, repo_root: Path) -> list[str]:
    """Return JSON session paths from NUL-delimited git output.

    Pre-PR validates the committed branch state. A dirty worktree that removes a
    changed session log must fail closed in validation, not disappear from the
    candidate list because the local file is absent.
    """
    del repo_root
    return [
        path
        for path in output.split("\0")
        if path.startswith(".agents/sessions/")
        and path.endswith(".json")
    ]


def validate_session_end(repo_root: Path) -> bool:
    """Validate session logs changed on the branch.

    Invokes scripts/validate_session_json.py (ADR-042). Scoped to session logs
    changed on the current branch so pre-existing violations do not block
    unrelated work.
    """
    base_ref = _resolve_branch_base_ref(repo_root)
    if base_ref is None:
        print("[WARNING] Session validation skipped: no base ref resolved")
        return True

    exit_code, stdout, _ = _run_subprocess(
        ["git", "-C", str(repo_root), "diff", "--name-only", "-z",
         "--diff-filter=ACMR", f"{base_ref}...HEAD"],
        timeout=30,
    )
    if exit_code != 0:
        print("[WARNING] Session validation skipped: git diff failed")
        return True

    changed_paths = _changed_session_paths(stdout, repo_root)
    if not changed_paths:
        print("[PASS] Session End Validation (no session logs on branch)")
        return True
    new_logs = new_session_logs(changed_paths, repo_root, compare_ref="HEAD")

    _, validation_head, _ = _run_subprocess(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        timeout=30,
    )
    validation_head = validation_head.strip() or "INVALID_HEAD"

    python_script = repo_root / "scripts" / "validate_session_json.py"
    if not python_script.exists():
        raise MissingScriptSkip(
            "validate_session_json.py not present (downstream install)"
        )

    failed = False
    for relative_path in changed_paths:
        log_path = repo_root / relative_path
        print(f"Validating session log: {log_path.name}")
        command = _prepr_session_command(
            python_script,
            log_path,
            relative_path,
            new_logs,
            validation_head,
        )
        exit_code, stdout, stderr = _run_subprocess(
            command
        )
        output = (stdout or "") + (stderr or "")
        if output.strip():
            for line in output.strip().splitlines()[:20]:
                print(line)
        if exit_code != 0:
            failed = True
    return not failed


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
    try:
        target_batches = (
            [target_args]
            if targets is None
            else _markdown_lint_target_batches(target_args, autofix=autofix)
        )
    except ValueError as exc:
        print(f"[FAIL] Markdown linting failed: {exc}")
        return False

    failed = False
    for batch in target_batches:
        command = _markdown_lint_command(batch, autofix=autofix)
        exit_code, stdout, stderr = _run_subprocess(command, cwd=repo_root)
        if exit_code != 0:
            _report_markdown_lint_failure(exit_code, stdout, stderr)
            failed = True
        else:
            _report_selection(batch, stdout)
    return not failed


def _markdown_lint_command(
    target_args: list[str],
    *,
    autofix: bool,
) -> list[str]:
    command = ["npx", MARKDOWNLINT_CLI2_PACKAGE]
    if autofix:
        command.append("--fix")
    return [*command, "--", *target_args]


def _windows_command_length(command: list[str]) -> int:
    """Return rendered command length in UTF-16 code units."""
    rendered = subprocess.list2cmdline(command)
    return len(rendered.encode("utf-16-le")) // 2


def _markdown_lint_target_batches(
    target_args: list[str],
    *,
    autofix: bool,
) -> list[list[str]]:
    """Bound argument count and the rendered Windows command line."""
    batches: list[list[str]] = []
    batch: list[str] = []
    for target in target_args:
        if len(batch) >= MARKDOWNLINT_TARGET_BATCH_LIMIT:
            batches.append(batch)
            batch = []

        candidate = [*batch, target]
        command_length = _windows_command_length(
            _markdown_lint_command(candidate, autofix=autofix)
        )
        if command_length <= MARKDOWNLINT_COMMAND_LENGTH_LIMIT:
            batch = candidate
            continue
        if batch:
            batches.append(batch)
            batch = []
            command_length = _windows_command_length(
                _markdown_lint_command([target], autofix=autofix)
            )
        if command_length > MARKDOWNLINT_COMMAND_LENGTH_LIMIT:
            preview = target if len(target) <= 80 else f"{target[:77]}..."
            raise ValueError(
                f"target {preview!r} renders to {command_length:,} UTF-16 code units "
                "and cannot fit under the Windows command-line limit of "
                f"{MARKDOWNLINT_COMMAND_LENGTH_LIMIT:,}"
            )
        batch = [target]

    if batch:
        batches.append(batch)
    return batches


def _report_markdown_lint_failure(exit_code: int, stdout: str, stderr: str) -> None:
    """Report the tool's real failure signal without guessing a lint rule."""
    print(f"[FAIL] Markdown linting failed (exit code {exit_code})")
    detail = stderr if stderr.strip() else stdout
    if not detail.strip():
        print("  markdownlint-cli2 produced no stdout or stderr.")
        return
    stream = "stderr" if stderr.strip() else "stdout"
    print(f"{stream}:")
    for line in detail.splitlines():
        if line.strip():
            print(f"  {line}")


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


def _print_capped(output: str, limit: int, unit: str) -> None:
    """Print at most ``limit`` lines of ``output``, then an omitted-count note."""
    lines = output.strip().split("\n")
    for line in lines[:limit]:
        print(line)
    if len(lines) > limit:
        print(f"... ({len(lines) - limit} more {unit} omitted)")


def _markdown_lint_targets(repo_root: Path) -> list[str] | None:
    """Return changed markdown files, [] for none, or None for full-repo fallback."""
    return cast(
        list[str] | None,
        _filtered_targets(
            repo_root, "Markdown lint", lambda p: p.endswith(".md") and not _is_vendored(p)
        ),
    )


def _yaml_style_targets(repo_root: Path) -> list[str] | None:
    """Return changed YAML files, [] for none, or None for full-repo fallback.

    No vendored filter: yamllint applies ``.yamllint.yml``'s ``ignore:`` per
    path already (verified 1.38.0: no-op, exit 0), unlike markdown.
    """
    return cast(
        list[str] | None,
        _filtered_targets(repo_root, "YAML style", lambda p: p.endswith((".yml", ".yaml"))),
    )


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


def _run_python_validator(repo_root: Path, script_rel: str, args: list[str]) -> bool:
    """Run a Python validator script and print its output. Returns pass/fail."""
    python_script = repo_root / script_rel
    if not python_script.exists():
        raise MissingScriptSkip(f"{Path(script_rel).name} not present (downstream install)")
    exit_code, stdout, stderr = _run_subprocess(
        [sys.executable, str(python_script)] + args, cwd=repo_root
    )
    output = (stdout or "") + (stderr or "")
    if output.strip():
        for line in output.strip().splitlines()[:40]:
            print(line)
    return bool(exit_code == 0)


def validate_path_normalization(repo_root: Path) -> bool:
    """Check for absolute paths (ADR-042 Python port). CI: validate-paths.yml."""
    return _run_python_validator(
        repo_root, "build/scripts/validate_path_normalization.py", ["--fail-on-violation"]
    )


def validate_planning_artifacts(repo_root: Path) -> bool:
    """Validate planning consistency (ADR-042 Python port). CI: validate-planning-artifacts.yml."""
    return _run_python_validator(
        repo_root, "build/scripts/validate_planning_artifacts.py", ["--fail-on-error"]
    )


def validate_agent_drift(repo_root: Path) -> bool:
    """Detect agent semantic drift (ADR-042 ported Detect-AgentDrift.ps1 to
    build/scripts/detect_agent_drift.py, invoked directly here).

    Runs two comparisons (Issue #2267): vendored src/claude vs
    src/vs-code-agents (blocking), and .claude/agents vs .github/agents
    (advisory only, large pre-existing diffs). Only vendored drift blocks.
    """
    python_script = repo_root / "build" / "scripts" / "detect_agent_drift.py"
    if not python_script.exists():
        raise MissingScriptSkip(
            "detect_agent_drift.py not present (downstream install)"
        )

    exit_code, stdout, stderr = _run_subprocess(
        [sys.executable, str(python_script)]
    )
    output = (stdout or "") + (stderr or "")
    if output.strip():
        for line in output.strip().splitlines()[:100]:
            print(line)
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


def validate_always_on_corpus_claims(repo_root: Path) -> bool:
    """Pin the numeric claims in model-context-doctrine.md to live measurements.

    Runs ``tests/validation/test_always_on_corpus_claims.py`` via pytest so the
    byte counts, file counts, and multipliers stated in the doctrine doc never
    drift silently from the actual always-on instruction corpus. The test file
    itself runs in under 0.5 seconds. The instructions tree is absent in
    downstream installs, so SKIP rather than FAIL when it is missing.
    """
    if not (repo_root / ".github" / "instructions").is_dir():
        raise MissingScriptSkip(
            ".github/instructions not present (downstream install); no corpus to check"
        )
    test_path = repo_root / "tests" / "validation" / "test_always_on_corpus_claims.py"
    if not test_path.is_file():
        raise MissingScriptSkip(
            "tests/validation/test_always_on_corpus_claims.py not present; "
            "no corpus claim test to run"
        )
    exit_code, stdout, stderr = _run_subprocess(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/validation/test_always_on_corpus_claims.py",
            "-q",
        ],
        cwd=repo_root,
    )
    if exit_code != 0:
        if stdout:
            print(stdout)
        if stderr:
            print(stderr, file=sys.stderr)
    return bool(exit_code == 0)
