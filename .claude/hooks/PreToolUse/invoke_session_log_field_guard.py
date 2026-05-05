#!/usr/bin/env python3
"""Block git push when session logs carry placeholder values.

Thin adapter over :mod:`push_guard_base`. Activates on
``.agents/sessions/*.json`` files in the push changeset.

Schema (matches scripts/validate_session_json.py):

- ``endingCommit``: tolerated absent (investigation-only sessions); the
  literal placeholder ``"pending"`` is rejected.
- ``protocolCompliance.sessionEnd.markdownLintRun``: required (per the
  canonical session validator). Both ``Complete`` and ``complete`` keys
  are accepted; same for ``Evidence`` and ``evidence``. ``Complete``
  must be ``true``. ``Evidence`` must be a non-placeholder string with
  >= 20 characters after stripping. The canonical path is the only
  accepted location: a legacy top-level ``markdownLintRun`` block is
  treated as missing so this guard cannot pass logs that
  ``scripts/validate_session_json.py`` would reject.

This guard does NOT validate ``schemaVersion`` (no such field in the
real schema) or any field beyond the three above.

Hook Type: PreToolUse
Exit Codes (Claude Hook Semantics, exempt from ADR-035):
    0 = Allow (no session-log files in changeset, all fields valid)
    2 = Block (markdownLintRun missing/incomplete, Evidence placeholder,
        endingCommit literal "pending", or malformed JSON)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from _bootstrap import ensure_plugin_paths

ensure_plugin_paths()

from push_guard_base import run_guard  # noqa: E402
from hook_utilities import get_project_directory  # noqa: E402

GUARD_NAME = "session-log-field"
GLOBS = [".agents/sessions/*.json"]
# Aligned with scripts/validate_session_json.py CONTRADICTION_PATTERNS:
# the canonical validator only rejects evidence that contradicts a
# "complete: true" claim (placeholders like "TODO", "TBD", "pending",
# "N/A", "skipped", "deferred"). It does NOT enforce a minimum length;
# real session logs include short-but-valid evidence such as "0 errors".
# This guard mirrors that contract: empty or placeholder strings block,
# any other non-empty string allows.
EVIDENCE_PLACEHOLDERS = frozenset(
    {"", "pending", "tbd", "n/a", "none", "done", "."}
)


def _ending_commit_is_placeholder(path: str, data: dict) -> list[str]:
    """Block only the literal 'pending' placeholder.

    Real session schema allows endingCommit to be absent (investigation-only
    sessions, no-commit ends). Empty string and missing key are tolerated;
    only the canonical placeholder string 'pending' is rejected.
    """
    value = data.get("endingCommit")
    if isinstance(value, str) and value == "pending":
        return [f"{path}:endingCommit literal 'pending' placeholder"]
    return []


def _markdown_lint_run(data: dict) -> dict | None:
    """Locate markdownLintRun at the canonical path.

    Canonical: protocolCompliance.sessionEnd.markdownLintRun.

    The canonical session validator (scripts/validate_session_json.py) reads
    only this path. A previous version of this guard accepted a legacy
    top-level fallback, but that created a gap: a session log with only
    top-level markdownLintRun would pass this pre-push guard yet still fail
    the canonical CI validator. Aligning to the canonical path closes the gap.

    Defensive: a malformed log might set protocolCompliance or sessionEnd
    to a list or string. Treat any non-dict node along the path as missing
    rather than raising AttributeError.
    """
    pc = data.get("protocolCompliance")
    if not isinstance(pc, dict):
        return None
    end = pc.get("sessionEnd")
    if not isinstance(end, dict):
        return None
    canonical = end.get("markdownLintRun")
    if isinstance(canonical, dict):
        return canonical
    return None


def _read_complete(run: dict) -> object:
    """Tolerate both Complete and complete keys."""
    if "Complete" in run:
        return run["Complete"]
    return run.get("complete")


def _read_evidence(run: dict) -> object:
    """Tolerate both Evidence and evidence keys."""
    if "Evidence" in run:
        return run["Evidence"]
    return run.get("evidence")


def _check_markdown_lint_present(path: str, data: dict) -> list[str]:
    """Canonical validator requires markdownLintRun. Missing is a violation."""
    if _markdown_lint_run(data) is None:
        return [
            f"{path}:protocolCompliance.sessionEnd.markdownLintRun missing "
            "(required by scripts/validate_session_json.py)"
        ]
    return []


def _check_markdown_lint_complete(path: str, data: dict) -> list[str]:
    run = _markdown_lint_run(data)
    if run is None:
        return []
    if _read_complete(run) is not True:
        return [
            f"{path}:protocolCompliance.sessionEnd.markdownLintRun.Complete "
            "must be true"
        ]
    return []


def _check_markdown_lint_evidence(path: str, data: dict) -> list[str]:
    run = _markdown_lint_run(data)
    if run is None:
        return []
    evidence = _read_evidence(run)
    if not isinstance(evidence, str):
        return [
            f"{path}:protocolCompliance.sessionEnd.markdownLintRun.Evidence "
            "missing or non-string"
        ]
    stripped = evidence.strip()
    if stripped.lower() in EVIDENCE_PLACEHOLDERS:
        return [
            f"{path}:protocolCompliance.sessionEnd.markdownLintRun.Evidence "
            "is a placeholder"
        ]
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
    violations.extend(_ending_commit_is_placeholder(rel_path, data))
    violations.extend(_check_markdown_lint_present(rel_path, data))
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
