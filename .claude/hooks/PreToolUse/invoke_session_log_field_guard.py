#!/usr/bin/env python3
"""Block git push when session logs carry placeholder values.

Thin adapter over :mod:`push_guard_base`. Activates on
``.agents/sessions/*.json`` files in the push changeset and validates
four structural fields:

- ``schemaVersion`` present and non-empty
- ``endingCommit`` present and not the literal ``"pending"``
- ``markdownLintRun.Complete`` is ``true``
- ``markdownLintRun.Evidence`` is a non-placeholder string >= 20 chars

Hook Type: PreToolUse
Exit Codes (Claude Hook Semantics, exempt from ADR-035):
    0 = Allow (no session-log files, all fields valid)
    2 = Block (any field placeholder, missing, or malformed JSON)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

def _find_hooks_dir(root: Path) -> str | None:
    """Return hooks dir, trying both PreToolUse (Claude) and preToolUse (copilot-cli)."""
    for variant in ("PreToolUse", "preToolUse"):
        candidate = root / "hooks" / variant
        if candidate.is_dir():
            return str(candidate)
    return None


_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
if _plugin_root:
    _resolved_root = Path(_plugin_root).resolve()
    _hooks_dir = _find_hooks_dir(_resolved_root)
    _lib_dir = str(_resolved_root / "lib")
else:
    _cur = Path(__file__).resolve().parent
    _hooks_dir = None
    _lib_dir = None
    while True:
        if (_cur / ".claude-plugin" / "plugin.json").is_file():
            _hooks_dir = _find_hooks_dir(_cur)
            _lib_dir = str(_cur / "lib")
            break
        if _cur.parent == _cur:
            break
        _cur = _cur.parent
if _hooks_dir is None or not os.path.isdir(_hooks_dir):
    print(
        f"Plugin hooks directory not found: {_hooks_dir} "
        f"(CLAUDE_PLUGIN_ROOT={_plugin_root!r})",
        file=sys.stderr,
    )
    sys.exit(2)
if _lib_dir is None or not os.path.isdir(_lib_dir):
    print(
        f"Plugin lib directory not found: {_lib_dir} "
        f"(CLAUDE_PLUGIN_ROOT={_plugin_root!r})",
        file=sys.stderr,
    )
    sys.exit(2)
if _hooks_dir not in sys.path:
    sys.path.insert(0, _hooks_dir)
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from push_guard_base import run_guard  # noqa: E402
from hook_utilities import get_project_directory  # noqa: E402

GUARD_NAME = "session-log-field"
GLOBS = [".agents/sessions/*.json"]
EVIDENCE_MIN_LENGTH = 20
EVIDENCE_PLACEHOLDERS = frozenset(
    {"", "pending", "tbd", "n/a", "none", "done", "."}
)


def _check_schema_version(path: str, data: dict) -> list[str]:
    value = data.get("schemaVersion")
    if not isinstance(value, str) or not value:
        return [f"{path}:schemaVersion missing or empty"]
    return []


def _check_ending_commit(path: str, data: dict) -> list[str]:
    value = data.get("endingCommit")
    if not isinstance(value, str) or not value or value == "pending":
        return [f"{path}:endingCommit pending or missing"]
    return []


def _check_markdown_lint_complete(path: str, data: dict) -> list[str]:
    run = data.get("markdownLintRun")
    if not isinstance(run, dict):
        return [f"{path}:markdownLintRun.Complete false or missing"]
    if run.get("Complete") is not True:
        return [f"{path}:markdownLintRun.Complete false or missing"]
    return []


def _check_markdown_lint_evidence(path: str, data: dict) -> list[str]:
    run = data.get("markdownLintRun")
    if not isinstance(run, dict):
        return [f"{path}:markdownLintRun.Evidence placeholder or under-20-chars"]
    evidence = run.get("Evidence")
    if not isinstance(evidence, str):
        return [f"{path}:markdownLintRun.Evidence placeholder or under-20-chars"]
    stripped = evidence.strip()
    if stripped.lower() in EVIDENCE_PLACEHOLDERS:
        return [f"{path}:markdownLintRun.Evidence placeholder or under-20-chars"]
    if len(stripped) < EVIDENCE_MIN_LENGTH:
        return [f"{path}:markdownLintRun.Evidence placeholder or under-20-chars"]
    return []


def _validate_one(project_dir: Path, rel_path: str) -> list[str]:
    full = project_dir / rel_path
    try:
        text = full.read_text(encoding="utf-8")
    except (OSError, FileNotFoundError) as exc:
        return [f"{rel_path}: read error - {exc}"]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return [f"{rel_path}: JSON parse error - {exc.msg}"]
    if not isinstance(data, dict):
        return [f"{rel_path}: top-level JSON must be an object"]

    violations: list[str] = []
    violations.extend(_check_schema_version(rel_path, data))
    violations.extend(_check_ending_commit(rel_path, data))
    violations.extend(_check_markdown_lint_complete(rel_path, data))
    violations.extend(_check_markdown_lint_evidence(rel_path, data))
    return violations


def _validate(matching: list[str], _all_changed: list[str]) -> list[str]:
    project_dir = Path(get_project_directory())
    out: list[str] = []
    for rel_path in matching:
        out.extend(_validate_one(project_dir, rel_path))
    return out


def main() -> int:
    return run_guard(_validate, GLOBS, GUARD_NAME)


if __name__ == "__main__":
    sys.exit(main())
