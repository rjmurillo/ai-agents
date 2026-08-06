#!/usr/bin/env python3
# taste-lint: ignore file-size
#
# file-size suppression rationale: this module groups validators that shell out
# to external tools. Its line count tracks how many such gates exist, not
# complexity. The real fix is splitting by area (issue #3073 scope), which is
# out of scope for adding a single gate.
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

MARKDOWNLINT_CLI2_PACKAGE = "markdownlint-cli2@0.23.1"
# markdownlint-cli2 prints "Linting: 3 files" (or "Linting: 1 file") before it
# reads anything. The trailing count in its "Summary" line is files *with
# issues*, so a clean file and a file that was never selected both summarise as
# "0 issues in 0 files". This line is the only one that distinguishes them.
_LINTED_COUNT_PATTERN = re.compile(r"^Linting: (\d+) files?$", re.MULTILINE)


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
    return bool(exit_code == 0)


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
    return bool(exit_code == 0)


def validate_markdown_lint(
    repo_root: Path,
    explicit_targets: list[str] | None = None,
) -> bool:
    """Validate Markdown and report whether markdownlint selected any files.

    ``explicit_targets`` is used by Lefthook's staged-file jobs. It keeps the
    hook on the same reporting path as the pre-PR validator while still letting
    markdownlint-cli2 apply ``ignores`` from ``.markdownlint-cli2.yaml``.
    """
    if not shutil.which("npx"):
        print("[FAIL] npx not found (Node.js required)")
        print("  Install Node.js: https://nodejs.org/")
        return False

    targets = (
        explicit_targets
        if explicit_targets is not None
        else _markdown_lint_targets(repo_root)
    )
    scope_name = "selected" if explicit_targets is not None else "branch"
    if targets == []:
        print(f"[PASS] Markdown linting (no markdown files on {scope_name})")
        return True

    autofix = os.environ.get("SKIP_AUTOFIX") != "1"
    action = "Auto-fixing" if autofix else "Checking"
    target_args = ["**/*.md"] if targets is None else targets
    scope = (
        "markdown files"
        if targets is None
        else f"{len(target_args)} {scope_name} markdown file(s)"
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
    # markdownlint-cli2 writes violations to stderr and a progress banner to
    # stdout, and both were discarded here. A failing run printed the canned
    # list below and nothing else, so an MD041 and an MD032 arrived as advice
    # about MD040 and MD033. Print what the tool actually said.
    #
    # stderr only, when it has anything: stdout's "Finding:" line restates all
    # 44 exclusion globs on one ~1,000-character line and would bury the two
    # lines that name the file, the line and the rule. stdout is the fallback
    # for the failure modes that never reach the violation reporter, such as an
    # unparsable config.
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
    """Return how many files markdownlint-cli2 actually selected, or None.

    None means the banner was absent, which happens if the tool changes its
    output. Callers must not read that as zero or as "all of them"; it is
    "unknown", and saying so beats guessing.
    """
    match = _LINTED_COUNT_PATTERN.search(stdout)
    return int(match.group(1)) if match else None


def _report_selection(target_args: list[str], stdout: str) -> None:
    """Say whether a green run checked anything (issue #3710).

    ``.markdownlint-cli2.yaml`` excludes 89.7% of tracked markdown, including
    ``.claude/skills/**``, ``.agents/**`` and ``**/CLAUDE.md``, which is most of
    what anyone edits here. Naming an excluded file on the command line selects
    nothing and exits 0, so this check reported PASS on a branch where every
    changed file went unread, and the session log recorded "markdownlint passed"
    as evidence. The exclusions are deliberate, so this is not a failure. It is
    a PASS that has to say which kind of PASS it is.
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
    return bool(exit_code == 0)


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
    return bool(exit_code == 0)


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
        return bool(exit_code == 0)

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
    return bool(exit_code == 0)


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
    return bool(check_action(action) == EXIT_OK)


def validate_ci_dependency_pins(repo_root: Path) -> bool:
    """Assert every hand-written pkg==version pin in .github/ YAML agrees with
    pyproject.toml (Issue #3377).

    Thin wrapper over ``check_ci_dependency_pins.check``, whose module docstring
    holds the full scope. In short: workflow and action YAML only, and only for
    packages pyproject declares. The .github tree is absent in downstream
    installs, so SKIP rather than FAIL when it is not present.
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
    ``applyTo`` scopes them to every file of a language (per VS Code applyTo
    matching semantics) and fails when a language exceeds its non-regression
    ceiling. Runs the module via ``-m`` from ``repo_root`` so its
    ``scripts.validation`` package import resolves. The instructions tree is
    absent in downstream installs, so SKIP rather than FAIL when it is missing.
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
