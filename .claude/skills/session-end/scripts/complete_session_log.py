#!/usr/bin/env python3
"""Complete a session log by auto-populating session end evidence and validating.

Finds the current session log, auto-populates session end checklist items
with evidence gathered from git state and file changes, runs validation,
and reports status.

Exit codes follow ADR-035:
    0 - Success
    1 - Error: Validation failed or missing required items
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import warnings
from collections.abc import Iterable
from pathlib import Path
from types import ModuleType
from typing import cast


def _resolve_paths_lib_dir() -> Path:
    """Resolve the vendor-portable path-helper lib directory (Issue #2050)."""
    # ADR-047 keeps this bootstrap inline because imports need sys.path first.
    plugin_root = os.environ.get("COPILOT_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT")
    if plugin_root:
        lib_dir = Path(plugin_root).expanduser().resolve() / "lib"
        if not os.path.isdir(lib_dir):
            print(f"Plugin lib directory not found: {lib_dir}", file=sys.stderr)
            sys.exit(2)
        return lib_dir
    candidates: list[Path] = []
    workspace = os.environ.get("GITHUB_WORKSPACE")
    if workspace:
        candidates.append(Path(workspace).expanduser().resolve() / ".claude" / "lib")
    candidates.append(Path(__file__).resolve().parents[3] / "lib")
    for lib_dir in candidates:
        if os.path.isdir(lib_dir):
            return lib_dir.resolve()
    checked = ", ".join(str(candidate) for candidate in candidates)
    print(f"Plugin lib directory not found. Checked: {checked}", file=sys.stderr)
    sys.exit(2)


_LIB_DIR = _resolve_paths_lib_dir()
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from paths import artifact_dir, resolve_artifact_root  # noqa: E402
from qa_report import (  # noqa: E402
    QaBinding,
    session_log_identity,
    validate_qa_report,
)

# Sibling-module loader for rework_warning (REQ-010).
# Loaded lazily inside main() to keep import-time failures from breaking
# session-end entirely if the sibling is missing or has a syntax error.
# Pattern documented in implementation-007-pr1989-recursive-failure-learnings.

# .agents/SESSION-PROTOCOL.md defines this exact QA exemption value:
# "SKIPPED: investigation-only".
_QA_SKIP_REASONS = ("investigation-only",)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Complete and validate a session log.",
    )
    parser.add_argument(
        "--session-path",
        default="",
        help="Path to session log JSON. Auto-detects most recent if not provided.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without writing to the file.",
    )
    parser.add_argument(
        "--refresh-ending-commit",
        action="store_true",
        help=(
            "Replace a non-empty endingCommit with the current HEAD. "
            "Use after the final work commit."
        ),
    )
    parser.add_argument(
        "--markdown-files",
        nargs="+",
        default=None,
        metavar="FILE",
        help=(
            "Lint these Markdown files instead of discovering staged and "
            "unstaged files."
        ),
    )
    qa_group = parser.add_mutually_exclusive_group()
    qa_group.add_argument(
        "--qa-report",
        default="",
        metavar="FILE",
        help="Record a completed report under the configured QA artifact root.",
    )
    qa_group.add_argument(
        "--qa-skip-reason",
        choices=_QA_SKIP_REASONS,
        help="Verify and record a policy-approved investigation-only QA exemption.",
    )
    return parser


def _get_repo_root() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
        check=False,
    )
    if result.returncode != 0:
        return os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".."),
        )
    return result.stdout.strip()


def _get_current_branch() -> str | None:
    """Return the current git branch, or None when it cannot be determined."""
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
        check=False,
    )
    if result.returncode != 0:
        return None
    branch = result.stdout.strip()
    return branch or None


def _read_log_branch(full: str) -> str | None:
    """Return the branch field from a session log file, or None on error."""
    try:
        data = json.loads(Path(full).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    session = data.get("session")
    if isinstance(session, dict):
        branch = session.get("branch")
        if isinstance(branch, str):
            return branch
    branch = data.get("branch")
    return branch if isinstance(branch, str) else None


def _match_log_for_branch(
    candidates: list[tuple[float, str, str]], branch: str
) -> str | None:
    """Return the newest candidate whose branch field matches."""
    for _, full, _ in sorted(candidates, key=lambda x: (x[0], x[2]), reverse=True):
        if _read_log_branch(full) == branch:
            return full
    return None


def _find_current_session_log(sessions_dir: str) -> str | None:
    """Find the session log for the current branch, or None.

    Scans session logs and returns the newest whose ``session.branch`` (or
    legacy top-level ``branch``) field matches the current git branch.
    Returns ``None`` when the branch cannot be determined (detached HEAD) or
    when no log carries a matching branch field.

    Returning ``None`` rather than the mtime winner prevents session-end from
    writing into a different session's log when concurrent agents on other
    branches own a newer mtime (issue #4161). The caller detects ``None`` and
    asks the operator to supply ``--session-path`` explicitly.
    """
    if not os.path.isdir(sessions_dir):
        return None

    candidates = []
    for name in os.listdir(sessions_dir):
        if name.endswith(".json") and re.match(r"\d{4}-\d{2}-\d{2}-session-\d+", name):
            full = os.path.join(sessions_dir, name)
            try:
                mtime = os.path.getmtime(full)
            except OSError:
                warnings.warn(
                    f"Skipping unreadable session log: {name}",
                    UserWarning,
                    stacklevel=2,
                )
                continue
            candidates.append((mtime, full, name))

    if not candidates:
        return None

    branch = _get_current_branch()
    if branch is None:
        return None

    return _match_log_for_branch(candidates, branch)


def _get_ending_commit() -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _set_ending_commit(
    session: dict[str, object],
    ending_commit: str | None,
    *,
    refresh: bool,
) -> str | None:
    """Set or explicitly refresh endingCommit, returning a change summary."""
    if not ending_commit:
        return None

    short_commit = ending_commit[:10]
    existing_commit = session.get("endingCommit")
    if existing_commit and not refresh:
        return None

    ending_commit_changed = existing_commit != short_commit
    if ending_commit_changed:
        session["endingCommit"] = short_commit

    comparison_changed = False
    episode_metrics = session.get("episodeMetrics")
    if refresh and isinstance(episode_metrics, dict):
        comparison = episode_metrics.get("comparison")
        if (
            isinstance(comparison, dict)
            and comparison.get("kind") == "gitCommitRange"
            and comparison.get("head") != ending_commit
        ):
            comparison["head"] = ending_commit
            comparison_changed = True

    if ending_commit_changed:
        action = "Refreshed" if existing_commit else "Set"
        return f"{action} endingCommit: {short_commit}"
    if comparison_changed:
        return f"Refreshed episode comparison head: {ending_commit}"
    return None


def _test_handoff_modified() -> bool:
    for cmd in [["git", "diff", "--cached", "--name-only"], ["git", "diff", "--name-only"]]:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
        if result.returncode == 0 and "HANDOFF.md" in result.stdout:
            return True
    return False


def _test_serena_memory_updated(starting_commit: str | None = None) -> bool:
    for cmd in [
        ["git", "diff", "--cached", "--name-only"],
        ["git", "diff", "--name-only"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ]:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if line.startswith(".serena/memories/"):
                    return True
    if starting_commit:
        result = subprocess.run(
            [
                "git",
                "log",
                "--name-only",
                "--format=",
                f"{starting_commit}..HEAD",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if line.startswith(".serena/memories/"):
                    return True
    return False


def _changed_markdown_files() -> set[str]:
    """Return staged and unstaged Markdown paths."""
    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
        check=False,
    )
    unstaged = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMR"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
        check=False,
    )

    markdown_files: set[str] = set()
    for output in [staged.stdout, unstaged.stdout]:
        for line in output.splitlines():
            if line.strip().endswith(".md"):
                markdown_files.add(line.strip())
    return markdown_files


def _markdown_lint_selection(
    output: str,
    target_count: int,
    *,
    used_pre_pr: bool,
) -> int | None:
    """Return the measured selected-file count from lint output."""
    selection_match = re.search(
        r"Markdown linting (?:checked|selected) "
        r"(\d+) of \d+ target\(s\)",
        output,
    )
    if selection_match:
        return int(selection_match.group(1))
    if "could not read the 'Linting: N files' banner" in output:
        return None

    raw_match = re.search(r"Linting:\s+(\d+)\s+file", output)
    if raw_match:
        return int(raw_match.group(1))
    if used_pre_pr:
        return target_count
    return None


def _run_markdown_lint(
    markdown_files: list[str] | None = None,
) -> tuple[bool, str]:
    """Run measured markdownlint. Returns (success, evidence)."""
    selected_files = (
        _changed_markdown_files()
        if markdown_files is None
        else markdown_files
    )
    targets = sorted(set(selected_files))
    if not targets:
        if markdown_files is not None:
            return False, "NOT LINTED: explicit markdown scope is empty"
        return True, "NOT LINTED: no changed markdown files"

    repo_root = Path(_get_repo_root())
    pre_pr = repo_root / "scripts" / "validation" / "pre_pr.py"
    used_pre_pr = pre_pr.is_file()
    if used_pre_pr:
        command = [
            sys.executable,
            str(pre_pr),
            "--markdown-lint-only",
            "--",
            *targets,
        ]
        source = "pre_pr.py --markdown-lint-only"
    else:
        command = [
            "npx",
            "markdownlint-cli2",
            "--fix",
            "--",
            *targets,
        ]
        source = "markdownlint-cli2"

    result = subprocess.run(
        command,
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )
    output = "\n".join(
        part.strip()
        for part in (result.stdout, result.stderr)
        if part.strip()
    )
    if result.returncode != 0:
        return False, output or f"{source} failed"

    selected = _markdown_lint_selection(
        output,
        len(targets),
        used_pre_pr=used_pre_pr,
    )
    if selected is None:
        return False, f"{source}: selected file count unknown"
    if selected == 0:
        return markdown_files is None, (
            f"NOT LINTED: {source} selected 0 of {len(targets)} files"
        )
    return True, f"{source}: {selected} of {len(targets)} files linted"


def _test_uncommitted_changes(
    exclude_path: str | None = None,
    *,
    exclude_paths: Iterable[str] = (),
) -> bool:
    """Return True when uncommitted changes exist outside owned evidence.

    Excluded paths are repository-relative session artifacts owned by this
    command. They appear in ``git status`` while the evidence commit is being
    assembled, so counting them would make ``changesCommitted`` impossible to
    satisfy (issue #4425).
    """
    result = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
        check=False,
    )
    if result.returncode != 0:
        return True
    excluded = {Path(path).as_posix() for path in exclude_paths}
    if exclude_path:
        excluded.add(Path(exclude_path).as_posix())
    records = result.stdout.split("\0")
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if not record:
            continue
        if len(record) < 4:
            return True
        status = record[:2]
        paths = [record[3:].rstrip("\n")]
        if "R" in status or "C" in status:
            if index >= len(records) or not records[index]:
                return True
            paths.append(records[index].rstrip("\n"))
            index += 1
        if any(Path(path).as_posix() not in excluded for path in paths):
            return True
    return False


def _repo_relative_owned_path(path: str | Path, repo_root: str) -> str | None:
    """Return a repo-relative path unless the value escapes the repo."""
    try:
        relative_path = os.path.relpath(path, repo_root)
    except ValueError:
        return None
    if relative_path == os.pardir or relative_path.startswith((os.pardir + os.sep, "../", "..\\")):
        return None
    return relative_path


def _validate_path_containment(session_path: str, sessions_dir: str) -> str | None:
    """Validate session path is inside sessions directory. Returns resolved path or None."""
    try:
        resolved = os.path.realpath(session_path)
        base = os.path.realpath(sessions_dir) + os.sep
        if not resolved.startswith(base):
            return None
        return resolved
    except (OSError, ValueError):
        return None


def _qa_report_evidence(
    repo_root: Path,
    report_path: str,
    binding: QaBinding,
) -> str:
    """Return a passing QA report path bound to this session and commit."""
    candidate = Path(report_path)
    if not candidate.is_absolute():
        candidate = repo_root / candidate

    resolved_root = repo_root.resolve()
    resolved_report = candidate.resolve()
    qa_root = artifact_dir("qa", base=resolved_root).resolve()
    try:
        resolved_report.relative_to(qa_root)
    except ValueError as exc:
        raise ValueError(
            "QA report must be under the configured QA artifact root"
        ) from exc
    if not resolved_report.is_file():
        raise ValueError(f"QA report not found: {resolved_report}")
    # ADR-096: `head` is required. `binding.commit` is the session's own
    # resolved ending commit (already computed by the caller before this
    # function runs), so no additional git call is needed here.
    validate_qa_report(resolved_report, binding, head=binding.commit, repo_root=resolved_root)
    try:
        return resolved_report.relative_to(resolved_root).as_posix()
    except ValueError:
        return str(resolved_report)


def _qa_session_log_identity(session_path: str, repo_root: str) -> str:
    """Return a stable session identity across artifact-root overrides."""
    return cast(
        str,
        session_log_identity(
            Path(session_path),
            sessions_root=artifact_dir("sessions", base=Path(repo_root)),
        ),
    )


def _investigation_skip_evidence(repo_root: Path, starting_commit: object) -> str:
    """Validate investigation-only scope and return its evidence value."""
    if not isinstance(starting_commit, str) or not starting_commit:
        raise ValueError("Investigation-only QA requires a session starting commit")
    eligibility_script = (
        Path(__file__).resolve().parents[2]
        / "session"
        / "scripts"
        / "test_investigation_eligibility.py"
    )
    if not eligibility_script.is_file():
        raise ValueError(f"Investigation eligibility checker not found: {eligibility_script}")
    result = subprocess.run(
        [sys.executable, str(eligibility_script), "--base-ref", starting_commit],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError("Investigation eligibility checker failed")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("Investigation eligibility checker returned invalid JSON") from exc
    if payload.get("Error"):
        raise ValueError(str(payload["Error"]))
    if payload.get("Eligible") is not True:
        violations = payload.get("Violations", [])
        detail = ", ".join(str(path) for path in violations) or "unknown changed path"
        raise ValueError(f"Investigation-only QA is not eligible: {detail}")
    return "SKIPPED: investigation-only"


def _owned_evidence_paths(
    session_path: str,
    repo_root: str,
    qa_owned_path: str | None,
) -> list[str]:
    """Return session artifacts allowed in the final evidence commit."""
    session_rel = _repo_relative_owned_path(session_path, repo_root)
    episode_path = (
        artifact_dir("memory", base=Path(repo_root))
        / "episodes"
        / f"episode-{Path(session_path).stem}.json"
    )
    episode_rel = _repo_relative_owned_path(episode_path, repo_root)
    return [path for path in (session_rel, qa_owned_path, episode_rel) if path]


def _must_items_complete(
    session_end: dict[str, object],
    *,
    include_validation: bool = True,
) -> bool:
    """Return whether every required session-end item is complete."""
    handoff_key = (
        "handoffPreserved"
        if "handoffPreserved" in session_end
        else "handoffNotUpdated"
        if "handoffNotUpdated" in session_end
        else None
    )
    if handoff_key is None:
        return False

    required_items = [
        handoff_key,
        "serenaMemoryUpdated",
        "markdownLintRun",
        "qaValidation",
        "changesCommitted",
    ]
    if include_validation:
        required_items.append("validationPassed")
    for item in required_items:
        check = session_end.get(item)
        if not isinstance(check, dict):
            return False
        level = check.get("level", "")
        complete = check.get("Complete", False)
        if item == handoff_key and level == "MUST NOT":
            if complete:
                return False
            continue
        if level != "MUST" or not complete:
            return False
    return True


# Rework warning (REQ-012-07, REQ-012-08, REQ-012-09 / M4) is extracted
# to a sibling module so this file stays under the 500-line taste-lint
# threshold. See rework_warning.py for the implementation. The sibling
# import is loaded via importlib so it works whether the script is run
# directly (sys.path[0] is the script dir) or imported by tests via
# importlib.util.spec_from_file_location (which does NOT add the dir).
def _load_rework_module() -> ModuleType:
    """Load the rework_warning sibling module without depending on sys.path."""
    import importlib.util as _il

    _path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rework_warning.py")
    _spec = _il.spec_from_file_location("rework_warning", _path)
    if _spec is None or _spec.loader is None:
        raise ImportError(f"cannot load rework_warning from {_path}")
    _mod = _il.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    return _mod


# PR #1989 coderabbit: load lazily and tolerate failure. The rework-warning
# step is informational, not a gate; a missing or broken sibling module
# must not crash module import (which would block session-end entirely).
# Issue #2069 Finding B: use PEP 562 __getattr__ for true lazy loading so
# compute_rework_warning, emit_rework_warning_lines, and REWORK_THRESHOLD
# are not bound in module __dict__ until first access.
_rework_cache: dict[str, object] = {}
_LAZY_NAMES = frozenset({"compute_rework_warning", "emit_rework_warning_lines", "REWORK_THRESHOLD"})


def _ensure_rework_loaded() -> None:
    """Lazy-load the rework_warning sibling module on first access."""
    if _rework_cache:
        return
    try:
        _mod = _load_rework_module()
        _rework_cache["REWORK_THRESHOLD"] = _mod.REWORK_THRESHOLD
        _rework_cache["compute_rework_warning"] = _mod.compute_rework_warning
        _rework_cache["emit_rework_warning_lines"] = _mod.emit_rework_warning_lines
    except Exception:
        _rework_cache["REWORK_THRESHOLD"] = 6
        _rework_cache["compute_rework_warning"] = None
        _rework_cache["emit_rework_warning_lines"] = None
    globals().update(_rework_cache)


def __getattr__(name: str) -> object:
    """PEP 562 lazy attribute access for rework_warning sibling exports."""
    if name in _LAZY_NAMES:
        _ensure_rework_loaded()
        return _rework_cache[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _run_rework_warning_step() -> tuple[str, list[str]]:
    """Run the rework-warning check and emit lines to stdout.

    Returns a tuple of:
    - summary: one-line string suitable for the session-end ``changes`` log.
    - evidence_lines: list of strings emitted to stdout (REQ-012-08).
      Persisted under ``protocolCompliance.sessionEnd.reworkWarning.Evidence``
      in the session log JSON (ADR-060).

    Output to stdout is at least one line, never silent (REQ-012-08). The
    function is extracted so the main() driver does not absorb its branching
    into its own cyclomatic complexity.

    Degrades gracefully when the sibling rework_warning module is missing or
    broken (PR #1989 coderabbit): emits a single notice line and returns the
    same shape as a clean no-warning run, so callers do not have to
    special-case the import failure.
    """
    _ensure_rework_loaded()
    _g = globals()
    _compute = _g.get("compute_rework_warning")
    _emit = _g.get("emit_rework_warning_lines")
    _threshold = _g.get("REWORK_THRESHOLD", 6)
    if _compute is None or _emit is None:
        notice = "rework-warning: skipped (sibling module unavailable)"
        print(notice)
        return "Rework warning: skipped (sibling unavailable)", [notice]
    # PR #1989 cursor follow-up: the rework-warning step is informational
    # and MUST NOT block session-end under any circumstances (REQ-012-08).
    # Wrap runtime calls so an unexpected git or subprocess failure inside
    # compute_rework_warning or emit_rework_warning_lines degrades to a
    # single notice line instead of crashing the driver. Step 4b runs
    # before validation; a crash here would also prevent the validation
    # step from running. Exception excludes KeyboardInterrupt and
    # SystemExit so Ctrl+C still works.
    try:
        rework_items = _compute()
        lines = list(_emit(rework_items))
        for line in lines:
            print(line)
    except Exception as exc:
        notice = f"rework-warning: skipped (runtime error: {type(exc).__name__})"
        print(notice)
        return "Rework warning: skipped (runtime error)", [notice]
    if rework_items:
        summary = f"[WARN] rework warning: {len(rework_items)} file(s) at {_threshold}+ edits"
    else:
        summary = "Rework warning: none"
    return summary, lines


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = _get_repo_root()

    sessions_dir = str(resolve_artifact_root("sessions", base=repo_root))

    # Find session log
    session_path = args.session_path
    if not session_path:
        session_path = _find_current_session_log(sessions_dir)
        if not session_path:
            branch = _get_current_branch()
            where = f"branch '{branch}'" if branch else "detached HEAD (no current branch)"
            print(
                f"[FAIL] No session log found for {where} in {sessions_dir}. "
                "Use --session-path to specify the log explicitly.",
                file=sys.stderr,
            )
            return 1
        print(f"Auto-detected session log: {session_path}", file=sys.stderr)
    else:
        if not os.path.isfile(session_path):
            print(f"[FAIL] Session file not found: {session_path}", file=sys.stderr)
            return 1
        resolved = _validate_path_containment(session_path, sessions_dir)
        if resolved is None:
            print(f"[FAIL] Session path must be inside '{sessions_dir}'.", file=sys.stderr)
            return 1
        session_path = resolved

    # Read session log
    try:
        with open(session_path, encoding="utf-8") as f:
            session = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[FAIL] Invalid JSON in session file: {session_path}", file=sys.stderr)
        print(f"  Error: {exc}", file=sys.stderr)
        return 1

    # Verify structure
    pc = session.get("protocolCompliance", {})
    session_end = pc.get("sessionEnd")
    if session_end is None:
        print("[FAIL] Session log missing protocolCompliance.sessionEnd section", file=sys.stderr)
        return 1

    changes: list[str] = []
    print("", file=sys.stderr)
    print("=== Session End Completion ===", file=sys.stderr)
    print(f"File: {session_path}", file=sys.stderr)
    print("", file=sys.stderr)

    # 1. Ending commit
    ending_commit = _get_ending_commit()
    if not ending_commit:
        print(
            "[FAIL] Could not resolve current HEAD for endingCommit.",
            file=sys.stderr,
        )
        return 1
    ending_commit_change = _set_ending_commit(
        session,
        ending_commit,
        refresh=args.refresh_ending_commit,
    )
    if ending_commit_change:
        changes.append(ending_commit_change)

    # 2. handoffPreserved (MUST) - replaces legacy handoffNotUpdated (issue #868)
    handoff_modified = _test_handoff_modified()
    # Support both new "handoffPreserved" and legacy "handoffNotUpdated" field names
    handoff_key = (
        "handoffPreserved"
        if "handoffPreserved" in session_end
        else "handoffNotUpdated"
        if "handoffNotUpdated" in session_end
        else None
    )
    if handoff_key == "handoffPreserved":
        check = session_end[handoff_key]
        if handoff_modified:
            check["Complete"] = False
            check["Evidence"] = "WARNING: HANDOFF.md was modified (should be read-only)"
            changes.append("[WARN] HANDOFF.md was modified (violation)")
        else:
            check["Complete"] = True
            check["Evidence"] = "HANDOFF.md not modified (read-only respected)"
            changes.append("Confirmed HANDOFF.md preserved (not modified)")
    elif handoff_key == "handoffNotUpdated":
        check = session_end[handoff_key]
        if handoff_modified:
            check["Complete"] = True
            check["Evidence"] = "WARNING: HANDOFF.md was modified - this violates MUST NOT"
            changes.append("[WARN] HANDOFF.md was modified (MUST NOT violation)")
        else:
            check["Complete"] = False
            check["Evidence"] = "HANDOFF.md not modified (read-only respected)"
            changes.append("Confirmed HANDOFF.md not modified")

    # 3. serenaMemoryUpdated
    starting_commit = session.get("session", {}).get("startingCommit")
    memory_updated = _test_serena_memory_updated(starting_commit)
    if "serenaMemoryUpdated" in session_end:
        check = session_end["serenaMemoryUpdated"]
        if memory_updated:
            check["Complete"] = True
            check["Evidence"] = ".serena/memories/ has changes"
            changes.append("Confirmed Serena memory updated")
        elif not check.get("Complete"):
            changes.append(
                "[TODO] Serena memory not updated - update .serena/memories/ before completing"
            )

    # 4. markdownLintRun
    print("Running markdown lint...", file=sys.stderr)
    lint_success, lint_output = _run_markdown_lint(args.markdown_files)
    if "markdownLintRun" in session_end:
        check = session_end["markdownLintRun"]
        check["Complete"] = lint_success
        check["Evidence"] = lint_output
        changes.append(f"Markdown lint: {lint_output}")

    qa_evidence = ""
    qa_owned_path = ""
    if args.qa_report:
        try:
            session_log = _qa_session_log_identity(session_path, repo_root)
            binding = QaBinding(
                session_log=session_log,
                commit=ending_commit,
            )
            qa_owned_path = _qa_report_evidence(
                Path(repo_root),
                args.qa_report,
                binding,
            )
        except ValueError as exc:
            print(f"[FAIL] {exc}", file=sys.stderr)
            return 1
        qa_evidence = qa_owned_path
    elif args.qa_skip_reason:
        try:
            qa_evidence = _investigation_skip_evidence(
                Path(repo_root),
                session.get("session", {}).get("startingCommit"),
            )
        except ValueError as exc:
            print(f"[FAIL] {exc}", file=sys.stderr)
            return 1

    if qa_evidence:
        session_end["qaValidation"] = {
            "level": "MUST",
            "Complete": True,
            "Evidence": qa_evidence,
        }
        changes.append(f"QA validation: {qa_evidence}")

    # 4b. Rework warning (REQ-012-07, REQ-012-08). Emitted as informational
    # stdout lines after lint; never blocks completion.
    # ADR-060: evidence lines are also persisted in the session log JSON under
    # protocolCompliance.sessionEnd.reworkWarning.Evidence. Pre-existing
    # reworkWarning keys (set by other tooling) are preserved.
    rework_summary, rework_evidence = _run_rework_warning_step()
    changes.append(rework_summary)
    if "reworkWarning" not in session_end:
        session_end["reworkWarning"] = {}
    # Schema requires Evidence as a string (checklistItem shape). Join list entries
    # with newline so the full rework output is preserved (issue #3929, #3954).
    # Complete derives from whether the step actually ran: a "skipped" summary
    # means the sibling module was absent or threw a runtime error (post-#4001).
    rework_ran = "skipped" not in rework_summary.lower()
    session_end["reworkWarning"]["level"] = "SHOULD"
    session_end["reworkWarning"]["Complete"] = rework_ran
    session_end["reworkWarning"]["Evidence"] = (
        "\n".join(rework_evidence) if isinstance(rework_evidence, list) else str(rework_evidence)
    )

    # 5. changesCommitted
    # Exclude the session log itself: it is staged or modified while this
    # check runs and would always appear in porcelain output, making
    # changesCommitted impossible to satisfy (issue #4425).
    owned_evidence = _owned_evidence_paths(
        session_path,
        repo_root,
        qa_owned_path,
    )
    has_uncommitted = _test_uncommitted_changes(
        exclude_paths=owned_evidence
    )
    if "changesCommitted" in session_end:
        check = session_end["changesCommitted"]
        if not has_uncommitted:
            ending_commit_label = str(session.get("endingCommit", ending_commit))
            check["Complete"] = True
            check["Evidence"] = f"All changes committed (HEAD: {ending_commit_label})"
            changes.append("All changes committed")
        else:
            check["Complete"] = False
            check["Evidence"] = "Uncommitted changes remain"
            changes.append("[TODO] Uncommitted changes exist - commit before completing")

    # 6. Prepare the self-referential validation fields before validation.
    # The validator requires both fields to be complete, so a prior failed run
    # otherwise cannot recover after its underlying evidence is fixed.
    validation_ready = _must_items_complete(session_end, include_validation=False)
    validation_check = session_end.get("validationPassed")
    if isinstance(validation_check, dict):
        validation_check["Complete"] = validation_ready
        validation_check["Evidence"] = (
            "Validation preconditions satisfied"
            if validation_ready
            else "Validation blocked by incomplete MUST items"
        )

    # 7. checklistComplete - evaluate after all others
    all_must_complete = _must_items_complete(session_end)

    if "checklistComplete" in session_end:
        check = session_end["checklistComplete"]
        check["Complete"] = all_must_complete
        if all_must_complete:
            check["Evidence"] = "All MUST items verified"
        else:
            check["Evidence"] = "Some MUST items still incomplete"

    # Report changes
    print("", file=sys.stderr)
    print("--- Changes ---", file=sys.stderr)
    for change in changes:
        print(f"  {change}", file=sys.stderr)

    # Write updated session log
    if not args.dry_run:
        with open(session_path, "w", encoding="utf-8") as f:
            json.dump(session, f, indent=2)
        print("", file=sys.stderr)
        print(f"Updated: {session_path}", file=sys.stderr)
    else:
        print("", file=sys.stderr)
        print("[DRY RUN] No changes written", file=sys.stderr)

    # Run validation
    print("", file=sys.stderr)
    print("Running validation...", file=sys.stderr)
    validate_script = os.path.join(repo_root, "scripts", "validate_session_json.py")

    if os.path.isfile(validate_script):
        sys.stdout.flush()
        result = subprocess.run(
            [
                sys.executable,
                validate_script,
                session_path,
                "--validation-head",
                ending_commit,
            ],
            capture_output=False,
            timeout=60,
            check=False,
        )
        validation_exit_code = result.returncode

        if not args.dry_run and "validationPassed" in session_end:
            check = session_end["validationPassed"]
            check["Complete"] = validation_exit_code == 0
            check["Evidence"] = (
                "validate_session_json.py passed"
                if validation_exit_code == 0
                else "validate_session_json.py failed"
            )

            all_must_complete = _must_items_complete(session_end)
            if validation_exit_code == 0 and all_must_complete:
                session_end["checklistComplete"]["Complete"] = True
                session_end["checklistComplete"]["Evidence"] = (
                    "All MUST items verified and validation passed"
                )
            else:
                session_end["checklistComplete"]["Complete"] = False
                session_end["checklistComplete"]["Evidence"] = (
                    "Some MUST items still incomplete"
                )

            with open(session_path, "w", encoding="utf-8") as f:
                json.dump(session, f, indent=2)

        if validation_exit_code != 0:
            print("", file=sys.stderr)
            print("[FAIL] Session validation failed. Fix issues above and re-run.", file=sys.stderr)
            return 1
    else:
        if not args.dry_run and "validationPassed" in session_end:
            session_end["validationPassed"]["Complete"] = False
            session_end["validationPassed"]["Evidence"] = (
                "validate_session_json.py not found"
            )
            session_end["checklistComplete"]["Complete"] = False
            session_end["checklistComplete"]["Evidence"] = (
                "Validation script unavailable"
            )
            with open(session_path, "w", encoding="utf-8") as f:
                json.dump(session, f, indent=2)
        print(f"ERROR: Validation script not found: {validate_script}", file=sys.stderr)
        return 1

    if not all_must_complete:
        print("", file=sys.stderr)
        print("[FAIL] Required session-end evidence is incomplete.", file=sys.stderr)
        return 1

    # Rework warning (REQ-010-01..04) is emitted earlier via
    # `_run_rework_warning_step()` at the lint/changes step; do not
    # duplicate the emission here. PR #1989 copilot review caught the
    # double-emit. The single emission point keeps session-end output
    # predictable and avoids running `git log` twice per run.

    print("", file=sys.stderr)
    print("[PASS] Session log completed and validated", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
