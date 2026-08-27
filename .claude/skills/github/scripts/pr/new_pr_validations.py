"""Pre-creation validation helpers for ``new_pr.py``."""

from __future__ import annotations

import contextlib
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

from validate_pr_description import validate_no_escaped_newlines

# Uses Unicode escapes so this source does not contain the prohibited
# characters it detects.
_DASH_RE = re.compile("[\u2013\u2014]")

# Keep in sync with scripts/detect_skill_violation.py::VALID_EXTENSIONS.
_SKILL_SCAN_EXTENSIONS = frozenset({".md", ".py", ".ps1", ".psm1"})

_SESSION_LOG_FILENAME_RE = re.compile(
    r"^\.agents/sessions/"
    r"\d{4}-\d{2}-\d{2}-session-\d+"
    r"(?:-[a-z0-9-]+)?"
    r"\.(md|json)$"
)


def _git_env() -> dict[str, str]:
    """Return environment with git hook override variables stripped."""
    return {
        key: value
        for key, value in os.environ.items()
        if key not in {"GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE"}
    }


def _resolve_validation_base(pr_base: str, explicit: str = "") -> str:
    """Return the git ref to use for local validation diffs.

    The ``--base`` value names a branch on GitHub. In a linked worktree the
    local ref may be stale, so prefer the corresponding remote-tracking ref.
    The returned ref is used only for local validation; GitHub still receives
    the bare ``pr_base`` value.
    """
    if explicit:
        return explicit

    remote_ref = f"origin/{pr_base}"
    result = subprocess.run(
        ["git", "rev-parse", "--verify", remote_ref],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
        env=_git_env(),
    )
    if result.returncode == 0:
        return remote_ref
    return pr_base


def _resolve_head_commit(head: str) -> str | None:
    """Return the full commit SHA ``head`` names, or None when it will not resolve.

    The log is read out of ``head``, a branch that may not be checked out, so
    the QA staleness check has to be anchored on the same ref. Left to itself
    the validator anchors on local HEAD instead;
    ``scripts/validate_session_json.py`` reads, verbatim:

        validation_head = args.validation_head
        if not existing_log and not args.creation_mode and validation_head is None:
            validation_head = _resolve_full_commit("HEAD")
    """
    result = subprocess.run(
        ["git", "rev-parse", "--verify", f"{head}^{{commit}}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
        env=_git_env(),
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _run_warning_validator(argv: list[str], *, timeout: int) -> str | None:
    """Run a warning-only validator and name it when it failed to run."""
    name = os.path.basename(argv[1]) if len(argv) > 1 else argv[0]
    try:
        result = subprocess.run(
            argv,
            timeout=timeout,
            env=_git_env(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"  ERROR: {name} could not be run: {exc}", file=sys.stderr)
        return name
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    if result.returncode != 0:
        print(
            f"  ERROR: {name} exited {result.returncode}, so its findings are"
            " unknown. This is a validator failure, not a clean scan.",
            file=sys.stderr,
        )
        return name
    return None


def _extract_validatable_session_logs(
    changed_files: list[str],
) -> tuple[list[str], bool]:
    """Return JSON session logs and whether legacy Markdown logs are present."""
    matched = [path for path in changed_files if _SESSION_LOG_FILENAME_RE.match(path)]
    legacy_md = [path for path in matched if path.endswith(".md")]
    if legacy_md:
        print(
            f"  WARNING: legacy .md session log(s) staged ({legacy_md}); "
            "these are not validated. Session log creation is discontinued; "
            "an existing one must use the JSON format that "
            "validate_session_json.py checks.",
            file=sys.stderr,
        )
    return [path for path in matched if path.endswith(".json")], bool(legacy_md)


@contextlib.contextmanager
def _session_log_for_validation(
    repo_root: str, head: str, session_log: str
) -> Iterator[str | None]:
    """Yield a temporary filesystem copy of a session log from ``head``."""
    show = subprocess.run(
        ["git", "show", f"{head}:{session_log}"],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        env=_git_env(),
    )
    if show.returncode == 0:
        scratch_dir = os.path.join(
            repo_root, ".agents", "scratch", "session-log-validation"
        )
        os.makedirs(scratch_dir, exist_ok=True)
        tmp_name = ""
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                suffix=".json",
                prefix=".session-log-",
                dir=scratch_dir,
                delete=False,
            ) as tmp:
                tmp.write(show.stdout)
                tmp_name = tmp.name
            yield tmp_name
        finally:
            with contextlib.suppress(OSError):
                os.unlink(tmp_name)
        return

    print(
        f"  WARNING: session log {session_log} not found at {head}; "
        "skipping Session End validation.",
        file=sys.stderr,
    )
    yield None


def _session_sort_key(path: str) -> tuple[str, int]:
    """Sort session paths by date and numeric session number."""
    match = re.match(
        r"^\.agents/sessions/"
        r"(\d{4}-\d{2}-\d{2})-session-(\d+)",
        path,
    )
    if match is None:
        return ("", 0)
    return (match.group(1), int(match.group(2)))


def _validate_session_end(
    repo_root: str,
    head: str,
    changed_files: list[str],
    *,
    diff_failed: bool,
) -> None:
    """Run the Session End validation when the changed-file set permits it."""
    agents_changed = any(path.startswith(".agents/") for path in changed_files)
    if not agents_changed:
        if diff_failed:
            print("  Skipped: git diff failed, changed files unknown (see warning above).")
        else:
            print("  No .agents/ changes, skipping")
        return

    session_logs, has_legacy_md = _extract_validatable_session_logs(changed_files)
    if not session_logs:
        # No session log at all is the expected case: session log creation
        # is discontinued, so absence is not warning-worthy.
        return

    session_log = sorted(session_logs, key=_session_sort_key)[-1]
    validate_script = os.path.join(repo_root, "scripts/validate_session_json.py")
    if not os.path.exists(validate_script):
        return

    validation_head = _resolve_head_commit(head)
    if validation_head is None:
        print(
            f"  WARNING: could not resolve {head} to a commit; skipping Session End "
            "validation rather than binding QA staleness to local HEAD.",
            file=sys.stderr,
        )
        return

    with _session_log_for_validation(repo_root, head, session_log) as scratch_path:
        if scratch_path is None:
            return
        _run_session_validator(
            validate_script, session_log, validation_head, scratch_path
        )


def _run_session_validator(
    validate_script: str, session_log: str, validation_head: str, scratch_path: str
) -> None:
    """Run the canonical session validator over one ref-backed scratch copy."""
    # The scratch copy carries no logical identity, so without the flag the QA
    # binding compares the report's recorded session against a temp filename
    # and rejects every QA-linked log (issue #4783).
    # scripts/validate_session_json.py help text, verbatim:
    #     "Use this repository-relative logical session path for QA binding
    #      when validating a ref-backed temporary copy."
    #     "Validate investigation-only scope through this commit instead of
    #      stopping at the recorded endingCommit."
    # Wider than that second line reads: main() also passes --validation-head
    # to validate_qa_report_evidence, so it sets the head QA staleness is
    # measured against, not only investigation-only scope.
    # env=_git_env() matches every other git-touching call here: the validator
    # shells out to git for commit resolution and QA ancestry, so an inherited
    # GIT_DIR would aim those reads at another repository.
    # The scratch path stays last so it remains argv[-1].
    result = subprocess.run(
        [
            sys.executable,
            validate_script,
            "--session-log-identity",
            session_log,
            "--validation-head",
            validation_head,
            scratch_path,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        env=_git_env(),
    )
    # Print on every outcome, matching _run_warning_validator above. Printing
    # only on failure swallowed a COMPLIANT-with-warnings log's warnings.
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    if result.returncode != 0:
        print("Session End validation failed", file=sys.stderr)
        raise SystemExit(1)


def _validate_skill_violations(
    repo_root: str,
    changed_files: list[str],
    *,
    diff_failed: bool,
) -> str | None:
    """Run the changed-file skill scanner when its inputs are known."""
    skill_script = os.path.join(repo_root, "scripts/detect_skill_violation.py")
    scannable_files = [
        path for path in changed_files if Path(path).suffix in _SKILL_SCAN_EXTENSIONS
    ]
    if os.path.exists(skill_script) and scannable_files:
        skill_args = [sys.executable, skill_script]
        for changed_file in scannable_files:
            skill_args.extend(["--file", changed_file])
        return _run_warning_validator(skill_args, timeout=30)

    if os.path.exists(skill_script):
        if diff_failed:
            print("  Skipped: git diff failed, changed files unknown (see warning above).")
        elif not changed_files:
            print("  No changed files to check.")
        else:
            extensions = ", ".join(sorted(_SKILL_SCAN_EXTENSIONS))
            print(f"  No changed files with a scannable extension ({extensions}).")
    return None


def _validate_test_coverage(repo_root: str) -> str | None:
    """Run the warning-only test coverage detector when installed."""
    test_script = os.path.join(repo_root, "scripts/detect_test_coverage_gaps.py")
    if not os.path.exists(test_script):
        return None
    return _run_warning_validator(
        [sys.executable, test_script, "--staged-only"],
        timeout=30,
    )


def _validate_pr_description(
    *,
    title: str,
    body: str,
    body_file: str,
) -> None:
    """Run the warning-only PR description validator."""
    validate_script = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "validate_pr_description.py",
    )
    if not os.path.exists(validate_script) or not title:
        print("  Skipped (no title available or validator not found)")
        return

    arguments = [sys.executable, validate_script, "--title", title]
    body_stdin: str | None = None
    if body:
        arguments.extend(["--body-file", "-"])
        body_stdin = body
    elif body_file:
        arguments.extend(["--body-file", body_file])
    result = subprocess.run(
        arguments,
        input=body_stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)


def _read_body_content(body: str, body_file: str) -> str:
    """Return body text, warning and preserving empty content on read failure."""
    body_content = body or ""
    if body_content or not body_file or not os.path.exists(body_file):
        return body_content
    try:
        with open(body_file, encoding="utf-8") as file:
            return file.read()
    except OSError as exc:
        print(f"  WARNING: Could not read body file: {exc}", file=sys.stderr)
        return body_content


def _validate_dashes(title: str, body_content: str) -> None:
    """Block em/en dashes in the PR title or body."""
    dash_violations: list[str] = []
    if _DASH_RE.search(title):
        dash_violations.append("title")
    body_dash_lines = [
        f"line {number}"
        for number, line in enumerate(body_content.splitlines(), start=1)
        if _DASH_RE.search(line)
    ]
    if body_dash_lines:
        sample = ", ".join(body_dash_lines[:5])
        if len(body_dash_lines) > 5:
            sample += f", ... (+{len(body_dash_lines) - 5} more)"
        dash_violations.append(f"body ({sample})")
    if not dash_violations:
        print("  No prohibited characters in title or body.")
        return

    print(
        "ERROR: Em-dash (U+2014) or en-dash (U+2013) found in: "
        + "; ".join(dash_violations),
        file=sys.stderr,
    )
    print(
        "  Replace with comma, period, hyphen, or restructure.",
        file=sys.stderr,
    )
    print(
        "  Rule: .claude/rules/universal.md MUST NOT entry 5 (Issue #1923).",
        file=sys.stderr,
    )
    print(
        "  Override (NOT RECOMMENDED): re-run with --skip-validation"
        ' --audit-reason "...".',
        file=sys.stderr,
    )
    raise SystemExit(1)


def run_validations(
    repo_root: str,
    base: str,
    head: str,
    *,
    title: str = "",
    body: str = "",
    body_file: str = "",
) -> None:
    """Run pre-creation validations. Raises SystemExit(1) on failure."""
    unrun_validators: list[str] = []
    try:
        os.makedirs(os.path.join(repo_root, ".agents"), exist_ok=True)
    except PermissionError as exc:
        print(f"Warning: Could not create .agents directory: {exc}", file=sys.stderr)

    print("Running validations...")
    print()

    print("[1/6] Checking Session End protocol...")
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...{head}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        env=_git_env(),
    )
    diff_failed = result.returncode != 0
    if diff_failed:
        print(
            f"  WARNING: 'git diff {base}...{head}' failed (exit {result.returncode}); "
            "the changed-file set is unknown. Validations that rely on it are "
            "skipped, not treated as 'no changes'.",
            file=sys.stderr,
        )
    changed_files = result.stdout.strip().splitlines() if not diff_failed else []
    _validate_session_end(
        repo_root,
        head,
        changed_files,
        diff_failed=diff_failed,
    )

    print()
    print("[2/6] Checking for skill violations...")
    failed = _validate_skill_violations(
        repo_root,
        changed_files,
        diff_failed=diff_failed,
    )
    if failed:
        unrun_validators.append(failed)

    print()
    print("[3/6] Checking test coverage...")
    failed = _validate_test_coverage(repo_root)
    if failed:
        unrun_validators.append(failed)

    print()
    print("[4/6] Validating PR description...")
    _validate_pr_description(title=title, body=body, body_file=body_file)

    print()
    print("[5/6] Em/en-dash check on title and body...")
    body_content = _read_body_content(body, body_file)
    _validate_dashes(title, body_content)

    print()
    print("[6/6] Escaped-newline check on body...")
    validate_no_escaped_newlines(body_content)
    print("  Body line breaks are real newlines.")

    print()
    if unrun_validators:
        print(
            "Validation incomplete: "
            + ", ".join(sorted(set(unrun_validators)))
            + " did not run. Fix the validator or re-run with"
            ' --skip-validation --audit-reason "...".',
            file=sys.stderr,
        )
        raise SystemExit(1)
    print("All pre-creation validations passed!")
    print()
