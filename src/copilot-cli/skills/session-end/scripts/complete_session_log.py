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
from datetime import UTC
from pathlib import Path
from types import ModuleType


def _resolve_paths_lib_dir() -> str:
    """Resolve the vendor-portable path-helper lib directory (Issue #2050)."""
    plugin_root = os.environ.get("COPILOT_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT")
    if plugin_root:
        lib_dir = Path(plugin_root).expanduser().resolve() / "lib"
    else:
        workspace = os.environ.get("GITHUB_WORKSPACE")
        if workspace:
            lib_dir = Path(workspace).expanduser().resolve() / ".claude" / "lib"
        else:
            lib_dir = Path(__file__).resolve().parents[3] / "lib"
    if not lib_dir.is_dir():
        print(f"Plugin lib directory not found: {lib_dir}", file=sys.stderr)
        sys.exit(2)
    return str(lib_dir)


_LIB_DIR = _resolve_paths_lib_dir()
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from paths import resolve_artifact_root  # noqa: E402

# Sibling-module loader for rework_warning (REQ-010).
# Loaded lazily inside main() to keep import-time failures from breaking
# session-end entirely if the sibling is missing or has a syntax error.
# Pattern documented in implementation-007-pr1989-recursive-failure-learnings.


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Complete and validate a session log.",
    )
    parser.add_argument(
        "--session-path", default="",
        help="Path to session log JSON. Auto-detects most recent if not provided.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would change without writing to the file.",
    )
    return parser


def _get_repo_root() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],
        capture_output=True, text=True, timeout=10, check=False,
    )
    if result.returncode != 0:
        return os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".."),
        )
    git_common = Path(result.stdout.strip())
    if not git_common.is_absolute():
        git_common = (Path.cwd() / git_common).resolve()
    else:
        git_common = git_common.resolve()
    return str(git_common.parent)


def _find_current_session_log(sessions_dir: str) -> str | None:
    """Find the most recent session log, preferring today's sessions."""
    from datetime import datetime
    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")

    if not os.path.isdir(sessions_dir):
        return None

    candidates = []
    for name in os.listdir(sessions_dir):
        if name.endswith(".json") and re.match(r"\d{4}-\d{2}-\d{2}-session-\d+", name):
            full = os.path.join(sessions_dir, name)
            candidates.append((os.path.getmtime(full), full, name))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0], reverse=True)

    # Prefer today's sessions
    for _, full, name in candidates:
        if name.startswith(today):
            return full

    return candidates[0][1]


def _get_ending_commit() -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        capture_output=True, text=True, timeout=10, check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _test_handoff_modified() -> bool:
    for cmd in [["git", "diff", "--cached", "--name-only"], ["git", "diff", "--name-only"]]:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10, check=False,
        )
        if result.returncode == 0 and "HANDOFF.md" in result.stdout:
            return True
    return False


def _test_serena_memory_updated() -> bool:
    for cmd in [
        ["git", "diff", "--cached", "--name-only"],
        ["git", "diff", "--name-only"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ]:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10, check=False,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if line.startswith(".serena/memories"):
                    return True
    return False


def _run_markdown_lint() -> tuple[bool, str]:
    """Run markdownlint on changed markdown files. Returns (success, message)."""
    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        capture_output=True, text=True, timeout=10, check=False,
    )
    unstaged = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMR"],
        capture_output=True, text=True, timeout=10, check=False,
    )

    md_files = set()
    for output in [staged.stdout, unstaged.stdout]:
        for line in output.splitlines():
            if line.strip().endswith(".md"):
                md_files.add(line.strip())

    if not md_files:
        return True, "No markdown files changed"

    all_success = True
    errors = []
    for f in md_files:
        result = subprocess.run(
            ["npx", "markdownlint-cli2", "--fix", "--", f],
            capture_output=True, text=True, timeout=30, check=False,
        )
        if result.returncode != 0:
            all_success = False
            errors.append(result.stdout.strip() or result.stderr.strip())

    if all_success:
        return True, f"{len(md_files)} files linted"
    return False, "\n".join(errors)


def _test_uncommitted_changes() -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True, text=True, timeout=10, check=False,
    )
    if result.returncode != 0:
        return True
    return bool(result.stdout.strip())


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
    except Exception:  # noqa: BLE001 - informational; must never block
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
    except Exception as exc:  # noqa: BLE001 - informational; must never block
        notice = f"rework-warning: skipped (runtime error: {type(exc).__name__})"
        print(notice)
        return "Rework warning: skipped (runtime error)", [notice]
    if rework_items:
        summary = (
            f"[WARN] rework warning: {len(rework_items)} file(s) "
            f"at {_threshold}+ edits"
        )
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
            print("[FAIL] No session log found in .agents/sessions/", file=sys.stderr)
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
    if ending_commit and not session.get("endingCommit"):
        session["endingCommit"] = ending_commit
        changes.append(f"Set endingCommit: {ending_commit}")

    # 2. handoffPreserved (MUST) - replaces legacy handoffNotUpdated (issue #868)
    handoff_modified = _test_handoff_modified()
    # Support both new "handoffPreserved" and legacy "handoffNotUpdated" field names
    handoff_key = (
        "handoffPreserved" if "handoffPreserved" in session_end
        else "handoffNotUpdated" if "handoffNotUpdated" in session_end
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
    memory_updated = _test_serena_memory_updated()
    if "serenaMemoryUpdated" in session_end:
        check = session_end["serenaMemoryUpdated"]
        if memory_updated:
            check["Complete"] = True
            check["Evidence"] = ".serena/memories/ has changes"
            changes.append("Confirmed Serena memory updated")
        elif not check.get("Complete"):
            changes.append(
                "[TODO] Serena memory not updated"
                " - update .serena/memories/ before completing"
            )

    # 4. markdownLintRun
    print("Running markdown lint...", file=sys.stderr)
    lint_success, lint_output = _run_markdown_lint()
    if "markdownLintRun" in session_end:
        check = session_end["markdownLintRun"]
        check["Complete"] = lint_success
        check["Evidence"] = lint_output
        changes.append(f"Markdown lint: {lint_output}")

    # 4b. Rework warning (REQ-012-07, REQ-012-08). Emitted as informational
    # stdout lines after lint; never blocks completion.
    # ADR-060: evidence lines are also persisted in the session log JSON under
    # protocolCompliance.sessionEnd.reworkWarning.Evidence. Pre-existing
    # reworkWarning keys (set by other tooling) are preserved.
    rework_summary, rework_evidence = _run_rework_warning_step()
    changes.append(rework_summary)
    if "reworkWarning" not in session_end:
        session_end["reworkWarning"] = {}
    session_end["reworkWarning"]["Evidence"] = rework_evidence

    # 5. changesCommitted
    has_uncommitted = _test_uncommitted_changes()
    if "changesCommitted" in session_end:
        check = session_end["changesCommitted"]
        if not has_uncommitted:
            check["Complete"] = True
            check["Evidence"] = f"All changes committed (HEAD: {ending_commit})"
            changes.append("All changes committed")
        else:
            changes.append("[TODO] Uncommitted changes exist - commit before completing")

    # 6. checklistComplete - evaluate after all others
    must_items = ["handoffPreserved", "handoffNotUpdated", "serenaMemoryUpdated",
                  "markdownLintRun", "changesCommitted", "validationPassed"]
    all_must_complete = True
    for item in must_items:
        if item in session_end:
            check = session_end[item]
            level = check.get("level", "")
            complete = check.get("Complete", False)
            if level == "MUST" and not complete:
                all_must_complete = False
            if level == "MUST NOT" and complete:
                all_must_complete = False

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
        result = subprocess.run(
            [sys.executable, validate_script, session_path],
            capture_output=False, timeout=60, check=False,
        )
        validation_exit_code = result.returncode

        if not args.dry_run and "validationPassed" in session_end:
            check = session_end["validationPassed"]
            check["Complete"] = validation_exit_code == 0
            check["Evidence"] = (
                "validate_session_json.py passed" if validation_exit_code == 0
                else "validate_session_json.py failed"
            )

            if validation_exit_code == 0 and all_must_complete:
                session_end["checklistComplete"]["Complete"] = True
                session_end["checklistComplete"]["Evidence"] = (
                    "All MUST items verified and validation passed"
                )

            with open(session_path, "w", encoding="utf-8") as f:
                json.dump(session, f, indent=2)

        if validation_exit_code != 0:
            print("", file=sys.stderr)
            print("[FAIL] Session validation failed. Fix issues above and re-run.", file=sys.stderr)
            return 1
    else:
        print(f"WARNING: Validation script not found: {validate_script}", file=sys.stderr)

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
