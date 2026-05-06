#!/usr/bin/env python3
"""Block git push when session logs carry placeholder values.

Thin adapter over :mod:`push_guard_base`. Activates on
``.agents/sessions/*.json`` files in the push changeset.

Schema (compatible with scripts/validate_session_json.py):

- ``endingCommit``: tolerated absent (investigation-only sessions); the
  literal placeholder ``"pending"`` is rejected.
- ``protocolCompliance.sessionEnd.markdownLintRun``: required (per the
  canonical session validator). Both ``Complete`` and ``complete`` keys
  are accepted; same for ``Evidence`` and ``evidence``. ``Complete``
  must be ``true``. ``Evidence`` must be a non-empty, non-placeholder
  string; placeholder detection uses the same word-boundary
  CONTRADICTION_PATTERNS regex as the canonical validator. The canonical
  path is the only accepted location: a legacy top-level
  ``markdownLintRun`` block is treated as missing so this guard cannot
  pass logs that ``scripts/validate_session_json.py`` would reject.

Stricter than canonical (intentional, documented here so the divergence
is not silent):

- The canonical validator records a *warning* for "Missing evidence" on
  a complete=true item. This pre-push guard *blocks* on missing or
  non-string evidence so the placeholder problem cannot reach CI in the
  first place.
- This guard does not validate the optional ``schemaVersion`` field.
  The schema at ``.agents/schemas/session-log.schema.json`` declares it
  but the canonical Python validator does not enforce it; this guard
  matches the canonical validator's enforcement, not the schema text.

Hook Type: PreToolUse
Exit Codes (Claude Hook Semantics, exempt from ADR-035):
    0 = Allow (no session-log files in changeset, all fields valid)
    2 = Block (markdownLintRun missing/incomplete, Evidence placeholder,
        endingCommit literal "pending", or malformed JSON)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from _bootstrap import ensure_plugin_paths

ensure_plugin_paths()

from push_guard_base import run_guard  # noqa: E402
from hook_utilities import get_project_directory  # noqa: E402

GUARD_NAME = "session-log-field"
GLOBS = [".agents/sessions/*.json"]
# Placeholder regex is the SAME word-boundary pattern as the canonical
# scripts/validate_session_json.py CONTRADICTION_PATTERNS, so any string
# that would trigger the canonical evidence-contradiction warning will
# trip this guard. Real session logs include short-but-valid evidence
# such as "0 errors" so no minimum-length floor is enforced.
#
# Note on enforcement-strength divergence (kept stricter than canonical
# on purpose): the canonical validator only records a *warning* when a
# complete=true item is missing evidence, while this pre-push guard
# *blocks* missing or non-string evidence. The intent is that placeholder
# evidence in a session log never reaches CI to begin with; the
# pre-push guard is the strictest layer in the chain.
CONTRADICTION_PATTERNS = re.compile(
    r"(?i)\b(not available|skipped|N/A|deferred|will validate|will run|TODO|pending|TBD)\b"
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
    if not stripped or CONTRADICTION_PATTERNS.search(stripped):
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
