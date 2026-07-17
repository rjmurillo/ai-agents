#!/usr/bin/env python3
"""Block Edit/Write on auth-related files without security review evidence.

Claude Code PreToolUse hook that enforces the "Do Router" gate per ADR-033
Phase 4. Blocks modifications to authentication and authorization files
unless security review evidence exists in the current session.

Hook Type: PreToolUse
Matcher: Edit, Write
Exit Codes (Claude Hook Semantics, exempt from ADR-035):
    0 = Allow (not an auth file, or security review exists)
    2 = Block (auth file modification without security review)
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

# Bootstrap: find lib directory via env var or manifest walk-up.
# CLAUDE_PLUGIN_ROOT honored when set; otherwise walk up from __file__
# looking for .claude-plugin/plugin.json (the plugin marker). Sibling
# lib/ is the plugin's lib dir. Layout-independent: works in source
# tree (.claude/) and in the deeper src/<provider>/hooks/<event>/ copy.
_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
_lib_dir: str | None
if _plugin_root:
    _lib_dir = str(Path(_plugin_root).resolve() / "lib")
else:
    _cur = Path(__file__).resolve().parent
    _lib_dir = None
    while True:
        if (_cur / ".claude-plugin" / "plugin.json").is_file():
            _lib_dir = str(_cur / "lib")
            break
        if _cur.parent == _cur:
            break
        _cur = _cur.parent
if _lib_dir is None or not os.path.isdir(_lib_dir):
    print(
        f"Plugin lib directory not found: {_lib_dir} "
        f"(CLAUDE_PLUGIN_ROOT={_plugin_root!r})",
        file=sys.stderr,
    )
    sys.exit(2)
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from hook_utilities import get_project_directory  # noqa: E402

# File path patterns that indicate auth-related code
_AUTH_PATH_PATTERNS = [
    re.compile(r"(^|[/\\])[Aa]uth[/\\]"),
    re.compile(r"(^|[/\\])[Aa]uthentication[/\\]"),
    re.compile(r"(^|[/\\])[Aa]uthorization[/\\]"),
    re.compile(r"\.auth\.(ts|js|py|cs|java|go|rb)$"),
    re.compile(r"(^|[/\\])middleware[/\\]auth", re.IGNORECASE),
]

# Freeform patch (Codex/Copilot ``apply_patch``, V4A format) file headers.
# GitHub Copilot CLI delivers apply_patch operations to the Write/Edit gate as a
# raw patch STRING rather than an object (issue #3203). Every file the patch
# touches is named by one of these headers:
#   *** Add File: path
#   *** Update File: path
#   *** Delete File: path
#   *** Move to: path      (rename destination inside an Update hunk)
# Matching all four is a superset of what the patch executor applies, so no
# touched path can slip past the auth check. The keyword is matched
# case-insensitively and tolerates surrounding whitespace.
_PATCH_FILE_HEADER = re.compile(
    r"^\*\*\*\s+(?:(?:Add|Update|Delete)\s+File|Move\s+to)\s*:\s*(?P<path>.+?)\s*$",
    re.IGNORECASE,
)

# A V4A structural marker sits at column 0 with no content prefix. The only
# well-formed markers are ``*** Begin Patch``, ``*** End Patch``, and the four
# file headers above. A column-0 ``***`` line that matches none of those is
# malformed: the parser cannot attribute a path to it, so it cannot be gated.
# The anchor is column 0 (``^\*\*\*``), not ``^\s*\*\*\*``, on purpose: a context
# or added line whose *content* begins with ``***`` (e.g. a Markdown horizontal
# rule inside an Update hunk) carries a one-character diff prefix (space, ``+``,
# or ``-``), so it never sits at column 0 and is not mistaken for a marker.
# Fail-closed hardening from the issue #3203 adversarial review.
_PATCH_STRUCTURAL_PREFIX = re.compile(r"^\*\*\*")
_PATCH_BEGIN_END = re.compile(r"^\*\*\*\s+(?:Begin|End)\s+Patch\s*$", re.IGNORECASE)

# Session log patterns indicating security review was performed
_SECURITY_REVIEW_PATTERNS = [
    re.compile(r"security.*review", re.IGNORECASE),
    re.compile(r"security.*agent", re.IGNORECASE),
    re.compile(r"threat.*model", re.IGNORECASE),
    re.compile(r"OWASP", re.IGNORECASE),
    re.compile(r"/security-scan"),
    re.compile(r"security-scan skill"),
    re.compile(r"subagent_type.*security", re.IGNORECASE),
]

_BLOCK_TEMPLATE = """\

## BLOCKED: Security Review Required for Auth Files

**DO ROUTER GATE: Security review required before modifying authentication/authorization files.**

### File

```
{file_path}
```

### Required Action

Run the security agent before editing auth-related files:

```
Task(subagent_type='security', prompt='Review auth-related changes for {file_path}')
```

The security agent will assess:
- Authentication flow security
- Authorization model correctness
- OWASP Top 10 considerations
- Threat model updates

### Alternative: Create Security Report

Place a security review report in `.agents/security/` with today's date:

```
.agents/security/YYYY-MM-DD-security-review.md
```

**Reference**: ADR-033 Phase 4 "Do Router" Integration
"""


def is_auth_path(file_path: str) -> bool:
    """Check if a file path matches auth-related patterns."""
    if not file_path:
        return False
    for pattern in _AUTH_PATH_PATTERNS:
        if pattern.search(file_path):
            return True
    return False


def extract_patch_paths(patch_text: str) -> list[str]:
    """Extract every file path named in a freeform ``apply_patch`` string.

    Parses the ``*** Add File:``/``*** Update File:``/``*** Delete File:`` and
    ``*** Move to:`` headers of a Codex/Copilot V4A patch. Returns the paths in
    the order they appear (duplicates preserved). An empty list signals a string
    that carries no recognizable patch headers, i.e. a malformed patch.
    """
    paths: list[str] = []
    for line in patch_text.splitlines():
        match = _PATCH_FILE_HEADER.match(line)
        if match:
            path = match.group("path").strip()
            if path:
                paths.append(path)
    return paths


def malformed_structural_lines(patch_text: str) -> list[str]:
    """Return every column-0 ``***`` line that is not a well-formed V4A marker.

    A patch that carries an unrecognized structural header cannot be gated
    reliably: no file path can be attributed to it. ``gate_freeform_patch`` fails
    closed when this list is non-empty, so a malformed header cannot smuggle an
    ungated auth-file edit past the gate by sitting next to a benign one (issue
    #3203 adversarial review).
    """
    suspicious: list[str] = []
    for line in patch_text.splitlines():
        if not _PATCH_STRUCTURAL_PREFIX.match(line):
            continue
        if _PATCH_FILE_HEADER.match(line) or _PATCH_BEGIN_END.match(line):
            continue
        suspicious.append(line.strip())
    return suspicious


def gate_paths(file_paths: list[str]) -> int:
    """Gate a set of target paths against the auth-review requirement.

    Returns 0 (allow) when no path is auth-related or when security review
    evidence exists for the session. Returns 2 (block) for an auth-file edit
    without evidence.
    """
    auth_paths = [path for path in file_paths if is_auth_path(path)]
    if not auth_paths:
        return 0

    project_dir = get_project_directory()
    if find_security_evidence(project_dir):
        return 0

    # Auth file edit without security review: block. Report the first auth path
    # in the guidance template; list them all on stderr for diagnostics.
    print(_BLOCK_TEMPLATE.format(file_path=auth_paths[0]))
    print(
        "Blocked: Auth file edit without security review: " + ", ".join(auth_paths),
        file=sys.stderr,
    )
    return 2


def gate_freeform_patch(patch_text: str) -> int:
    """Gate a raw V4A ``apply_patch`` string (Copilot CLI delivery, issue #3203).

    Parses the patch headers, then gates every touched path. A string with no
    recognizable headers, or one carrying a malformed structural header the gate
    cannot attribute to a path, fails closed (exit 2): an unparseable or
    partially parseable patch could hide an auth-file edit the executor would
    still apply.
    """
    malformed = malformed_structural_lines(patch_text)
    if malformed:
        block_security_gate_error(
            "tool_input carries malformed patch header(s) the gate cannot "
            "attribute to a file path (fail-closed): " + "; ".join(malformed[:3])
        )
        return 2

    patch_paths = extract_patch_paths(patch_text)
    if not patch_paths:
        block_security_gate_error(
            "tool_input is a string but not a recognizable patch "
            "(no '*** Add/Update/Delete File:' or '*** Move to:' headers)"
        )
        return 2
    return gate_paths(patch_paths)


def find_security_evidence(project_dir: str) -> bool:
    """Check for security review evidence in the current session.

    Looks for:
    1. Security report files in .agents/security/ dated today
    2. Security review markers in today's session log
    """
    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")

    # Check 1: Security report exists for today
    security_dir = Path(project_dir) / ".agents" / "security"
    if security_dir.is_dir():
        try:
            reports = list(security_dir.glob(f"*{today}*"))
            if reports:
                return True
        except OSError:
            pass

    # Check 2: Session log contains security review evidence
    sessions_dir = Path(project_dir) / ".agents" / "sessions"
    if sessions_dir.is_dir():
        try:
            session_logs = sorted(
                sessions_dir.glob(f"{today}-session-*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            session_logs = []
        # Issue #2523: stream line-by-line instead of read_text(). A
        # multi-MB session log pushed the whole-file read past the hook
        # timeout budget (fail-open). Line streaming follows the
        # established pattern in invoke_false_completion_gate.py.
        # OSError is handled per log file so one unreadable log cannot
        # mask evidence in the others (false block on auth-file edits).
        for log_path in session_logs:
            try:
                with log_path.open(encoding="utf-8", errors="replace") as handle:
                    for line in handle:
                        for pattern in _SECURITY_REVIEW_PATTERNS:
                            if pattern.search(line):
                                return True
            except OSError:
                continue

    return False


def block_security_gate_error(reason: str) -> None:
    """Emit a loud PreToolUse block for malformed input or hook errors."""
    print(
        "\n## BLOCKED: Security Gate Error\n\n"
        "Security gate could not verify whether this auth-related operation "
        "is safe. The hook failed closed.\n\n"
        f"**Reason**: {reason}\n"
    )


def main() -> int:
    """Main hook entry point. Returns exit code."""
    try:
        if sys.stdin.isatty():
            return 0

        input_json = sys.stdin.read()
        if not input_json.strip():
            return 0

        hook_input = json.loads(input_json)
        if not isinstance(hook_input, dict):
            block_security_gate_error("hook input JSON must be an object")
            return 2

        tool_input = hook_input.get("tool_input")

        # GitHub Copilot CLI delivers apply_patch / freeform-edit operations as
        # a raw patch STRING rather than an object (issue #3203). The prior code
        # failed closed on any non-dict tool_input, which denied EVERY
        # apply_patch in Copilot CLI. Parse the patch headers instead and gate
        # each touched path individually.
        if isinstance(tool_input, str):
            return gate_freeform_patch(tool_input)

        if not isinstance(tool_input, dict):
            block_security_gate_error("tool_input is missing or not an object")
            return 2

        # Resolve the target path across harness key spellings. Claude Code's
        # Write/Edit tools use "file_path"; GitHub Copilot CLI's native
        # create/edit tools use "path" (same mapping documented in
        # invoke_plan_state_sync.py). Reading only "file_path" made this gate
        # fail closed on every Copilot create/edit, denying all writes (#2610).
        file_path = ""
        for _path_key in ("file_path", "path"):
            _path_value = tool_input.get(_path_key)
            if isinstance(_path_value, str) and _path_value.strip():
                file_path = _path_value.strip()
                break
        if not file_path:
            # No resolvable target path. This gate classifies auth files by
            # their path; with no path it cannot, and blocking every pathless
            # Write/Edit is a denial of service far worse than the gate's narrow
            # purpose. Allow (fail open); identified auth-file edits without a
            # review are still blocked below.
            print(
                "security-gate: no file path in tool_input; allowing (fail open)",
                file=sys.stderr,
            )
            return 0

        return gate_paths([file_path])

    except Exception as exc:
        print(f"Security gate error: {type(exc).__name__} - {exc}", file=sys.stderr)
        block_security_gate_error(f"{type(exc).__name__}: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
