#!/usr/bin/env python3
"""Persist plan/TODO state after Write/Edit operations.

Claude Code PostToolUse hook that saves lightweight checkpoints when
session logs or plan/TODO files are written. This provides compaction-resume
context without duplicating full file content.

Addresses continuation reset after context compaction where plan position
and TODO status are lost.

Triggers on:
- Session log writes (.agents/sessions/*.json)
- Plan/TODO file writes (TODO.md, PLAN.md, .agents/plan*.md)

Hook Type: PostToolUse (non-blocking, fail-open)
Exit Codes:
    0 = Always (never blocks tool use)

References:
    - Issue #1703 (lifecycle hook infrastructure)
    - Issue #1691 (anti-drift protocol)
    - ADR-008 (protocol automation)
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

# --- Standard hook boilerplate ---
_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
if _plugin_root:
    _lib_dir = os.path.join(_plugin_root, "lib")
else:
    _lib_dir = str(Path(__file__).resolve().parents[2] / "lib")
if os.path.isdir(_lib_dir) and _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

try:
    from hook_utilities import get_project_directory
    from hook_utilities.guards import skip_if_consumer_repo
except ImportError:

    def get_project_directory() -> str:
        env_dir = os.environ.get("CLAUDE_PROJECT_DIR", "").strip()
        if env_dir:
            return str(Path(env_dir).resolve())
        return str(Path.cwd())

    def skip_if_consumer_repo(hook_name: str) -> bool:
        agents_path = Path(get_project_directory()) / ".agents"
        if not agents_path.is_dir():
            print(f"[SKIP] {hook_name}: .agents/ not found (consumer repo)", file=sys.stderr)
            return True
        return False


HOOK_NAME = "plan-state-sync"

# Patterns for files we want to checkpoint
# All patterns use (?:^|/) anchors to ensure we match only project-relative
# paths starting with .agents/, not arbitrary paths containing that substring
# (e.g., "mock.agents/sessions/log.json" should not match).
SESSION_LOG_PATTERN = re.compile(r"(?:^|/)\.agents/sessions/.*\.json$")
PLAN_FILE_PATTERNS = [
    re.compile(r"(?:^|/)TODO\.md$", re.IGNORECASE),
    re.compile(r"(?:^|/)PLAN\.md$", re.IGNORECASE),
    # Match `.agents/plan*.md` at the .agents/ root only. Earlier pattern
    # `\.agents/plan.*\.md$` also matched `.agents/planning/.../*.md` and
    # other nested files, triggering checkpoints for unrelated planning
    # docs. `[^/]*` keeps the match scoped to a single path segment.
    re.compile(r"(?:^|/)\.agents/plan[^/]*\.md$", re.IGNORECASE),
    re.compile(r"(?:^|/)PROJECT-PLAN\.md$", re.IGNORECASE),
]

SUMMARY_MAX_CHARS = 500


def _read_stdin_json() -> dict[str, object] | None:
    """Read and parse JSON from stdin (Claude hook input)."""
    if sys.stdin.isatty():
        return None
    try:
        data = sys.stdin.read().strip()
        if not data:
            return None
        parsed: object = json.loads(data)
        if not isinstance(parsed, dict):
            return None
        # json.loads object keys are always str, so the cast below is sound.
        return parsed
    except (json.JSONDecodeError, OSError):
        return None


def _extract_file_path(hook_input: dict[str, object]) -> str | None:
    """Extract the file path from hook input.

    Defends against malformed hook input where ``hook_input`` or
    ``tool_input`` is not a mapping, and against non-string ``file_path``
    values that would later break string ops in ``_is_checkpointable_file``.
    Returning ``None`` lets the caller skip checkpointing without
    disabling the hook silently.
    """
    if not isinstance(hook_input, dict):
        return None
    tool_input = hook_input.get("tool_input", {})
    if not isinstance(tool_input, dict):
        return None
    # Write tool uses 'file_path', Edit tool may use 'file_path' or 'path'.
    # Require a non-empty string; ignore other types so downstream code
    # never operates on, e.g., a dict or None.
    for key in ("file_path", "path"):
        value = tool_input.get(key)
        if isinstance(value, str):
            stripped = value.strip()
            if stripped:
                return stripped
    return None


def _is_checkpointable_file(file_path: str) -> bool:
    """Check if the written file should trigger a checkpoint."""
    # Normalize path separators
    normalized = file_path.replace("\\", "/")

    if SESSION_LOG_PATTERN.search(normalized):
        return True

    for pattern in PLAN_FILE_PATTERNS:
        if pattern.search(normalized):
            return True

    return False


def _read_file_summary(file_path: str) -> str:
    """Read first SUMMARY_MAX_CHARS of a file as a summary.

    Streams only the bytes needed instead of loading the whole file, so
    large session logs do not balloon hook memory.
    """
    try:
        path = Path(file_path)
        if not path.exists():
            return "(file not found)"
        with path.open(encoding="utf-8", errors="replace") as handle:
            content = handle.read(SUMMARY_MAX_CHARS + 1)
        if len(content) > SUMMARY_MAX_CHARS:
            return content[:SUMMARY_MAX_CHARS] + "..."
        return content
    except OSError:
        return "(read error)"


# Issue #2523: msvcrt.locking() locks a byte RANGE from the current file
# position, unlike fcntl.flock() which locks the whole file. The previous
# 1-byte lock at an arbitrary position was decorative: concurrent sessions
# could still interleave writes. Lock a fixed region anchored at offset 0
# instead; both lock and unlock must use the same anchor and length.
_NT_LOCK_BYTES = 0x7FFFFFFF


def _acquire_lock(handle) -> None:
    """Acquire an advisory exclusive lock on an open file handle."""
    if sys.platform == "win32":  # pragma: no cover - platform branch
        import msvcrt

        pos = handle.tell()
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, _NT_LOCK_BYTES)
        finally:
            handle.seek(pos)
        return
    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)


def _release_lock(handle) -> None:
    """Release the advisory lock held on an open file handle."""
    if sys.platform == "win32":  # pragma: no cover - platform branch
        import msvcrt

        pos = handle.tell()
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, _NT_LOCK_BYTES)
        except OSError:
            pass
        finally:
            handle.seek(pos)
        return
    import fcntl

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass


def _write_checkpoint(project_dir: str, file_path: str, summary: str) -> None:
    """Write a lightweight checkpoint for plan/state recovery.

    Concurrent PostToolUse hooks can race on the per-day checkpoint file, so
    the read-modify-write sequence is wrapped in an advisory exclusive lock
    (fcntl.flock on POSIX, msvcrt.locking on Windows). Without the lock,
    interleaved writes drop entries or produce invalid JSON.
    """
    checkpoint_dir = Path(project_dir) / ".agents" / ".hook-state"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    timestamp = datetime.now(tz=UTC).isoformat()

    checkpoint_file = checkpoint_dir / f"plan-checkpoint-{today}.json"

    # Open r+ when present, w+ to create; serialize via OS advisory lock.
    mode = "r+" if checkpoint_file.exists() else "w+"
    with checkpoint_file.open(mode, encoding="utf-8") as handle:
        _acquire_lock(handle)
        try:
            checkpoints: list[dict[str, object]] = []
            handle.seek(0)
            raw = handle.read()
            if raw:
                try:
                    existing = json.loads(raw)
                    if isinstance(existing, list):
                        checkpoints = existing
                except json.JSONDecodeError:
                    # Preserve the corrupt file under .corrupt so prior
                    # checkpoints are not silently wiped when the daily
                    # JSON cannot be parsed. The new write proceeds with
                    # an empty list so the hook still records progress.
                    corrupt_path = checkpoint_file.with_suffix(
                        checkpoint_file.suffix + ".corrupt"
                    )
                    try:
                        corrupt_path.write_text(raw, encoding="utf-8")
                    except OSError:
                        pass

            checkpoints.append({
                "file": file_path,
                "timestamp": timestamp,
                "summary": summary,
            })

            # Keep only last 20 checkpoints to avoid unbounded growth
            if len(checkpoints) > 20:
                checkpoints = checkpoints[-20:]

            handle.seek(0)
            handle.truncate()
            handle.write(
                json.dumps(checkpoints, indent=2, ensure_ascii=False)
            )
            handle.flush()
        finally:
            _release_lock(handle)


def main() -> None:
    """Checkpoint plan/TODO state after relevant file writes."""
    # Read stdin first to ensure it's drained before any early exit,
    # maintaining the fail-open drain contract with the harness.
    hook_input = _read_stdin_json()

    if skip_if_consumer_repo(HOOK_NAME):
        sys.exit(0)

    if hook_input is None:
        sys.exit(0)

    file_path = _extract_file_path(hook_input)
    if not file_path:
        sys.exit(0)

    if not _is_checkpointable_file(file_path):
        sys.exit(0)

    project_dir = get_project_directory()
    project_root = Path(project_dir).resolve()

    # Anchor relative paths to the project root so a hook process whose
    # CWD is a subdirectory still resolves to the file Claude wrote, and
    # reject paths that escape the repo (CWE-22 path traversal).
    candidate = Path(file_path)
    resolved = (
        candidate.resolve()
        if candidate.is_absolute()
        else (project_root / candidate).resolve()
    )
    try:
        resolved.relative_to(project_root)
    except ValueError:
        print(
            f"[WARNING] {HOOK_NAME}: ignoring out-of-root path: {file_path}",
            file=sys.stderr,
        )
        sys.exit(0)

    summary = _read_file_summary(str(resolved))

    # Persist a project-relative path so checkpoints stay portable across
    # machines and CWDs, instead of leaking absolute paths from whoever
    # invoked Claude.
    try:
        recorded_path = str(resolved.relative_to(project_root))
    except ValueError:
        recorded_path = file_path

    _write_checkpoint(project_dir, recorded_path, summary)

    print(f"[INFO] {HOOK_NAME}: Checkpointed state for {recorded_path}", file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[WARNING] {HOOK_NAME} error: {exc}", file=sys.stderr)
        sys.exit(0)
