#!/usr/bin/env python3
"""Surface relevant correction memories before Bash command execution.

Implements the 'Apply' step of the Self-Improving Agent pattern (issue #1345).
Scans .serena/memories/ for HIGH confidence corrections and surfaces matches
before the agent repeats a known mistake.

The Detect-Log-Graduate-Apply loop:
1. Detect: reflect skill + Stop hook (invoke_skill_learning.py)
2. Log: Serena observation memories
3. Graduate: skillbook agent promotes patterns
4. Apply: THIS HOOK surfaces corrections at command time

Hook Type: PreToolUse
Exit Codes (Claude Hook Semantics, exempt from ADR-035):
    0 = Allow (always, this is advisory only)
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

# Bootstrap: find lib directory via env var or manifest walk-up.
# CLAUDE_PLUGIN_ROOT honored when set; otherwise walk up from __file__
# looking for .claude-plugin/plugin.json (the plugin marker). Sibling
# lib/ is the plugin's lib dir. Layout-independent: works in source
# tree (.claude/) and in the deeper src/<provider>/hooks/<event>/ copy.
_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
if _plugin_root:
    _lib_dir: str | None = str(Path(_plugin_root).resolve() / "lib")
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
    # Non-blocking hook: exit 0 on bootstrap failure (intentional, not a typo)
    sys.exit(0)
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)  # Fail open when lib not found

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
            print(f"[SKIP] {hook_name}: .agents/ not found", file=sys.stderr)
            return True
        return False


# Section header pattern for HIGH confidence corrections
_HIGH_SECTION_RE = re.compile(
    r"^##\s+Constraints\s+\(HIGH\s+confidence\)",
    re.IGNORECASE,
)
# Any markdown heading (used to detect section boundaries)
_HEADING_RE = re.compile(r"^##\s+")
# Maximum corrections to surface per invocation (avoid context bloat)
MAX_CORRECTIONS = 3
# Minimum keyword length to avoid false positives
MIN_KEYWORD_LENGTH = 4
# Scan bounds (issue: advisory PreToolUse hook must never wedge the session).
# This hook runs on EVERY Bash command with a tight host timeout (3s in
# .claude/settings.json). A host timeout kills the process (SIGKILL), which
# the try/except in main() cannot catch, so the "advisory, never blocks"
# contract silently becomes fail-CLOSED and denies every command once the
# memory corpus grows past the budget. These caps keep the scan best-effort
# and bounded so wall-clock stays well under the host timeout regardless of
# how large .serena/memories/ becomes.
_SCAN_DEADLINE_SECONDS = 1.5
_MAX_FILES_SCANNED = 500
_MAX_TOTAL_BYTES = 5_000_000
# Total wall-clock budget for the whole hook body, anchored at main() start and
# kept under the 3s host timeout (.claude/settings.json). skip_if_consumer_repo()
# may spend up to its git subprocess timeout before the scan runs, so anchoring
# the scan deadline here (not at scan start) makes a slow git shrink the scan
# window instead of pushing total wall-clock past the host timeout and tripping
# a SIGKILL-into-"hook errored" deny.
_HOOK_WALL_BUDGET_SECONDS = 2.5


def parse_command(stdin_data: str) -> str | None:
    """Extract the Bash command from hook stdin JSON."""
    try:
        data = json.loads(stdin_data)
    except (json.JSONDecodeError, TypeError):
        return None
    tool_input = data.get("tool_input", {})
    if isinstance(tool_input, str):
        try:
            tool_input = json.loads(tool_input)
        except (json.JSONDecodeError, TypeError):
            return tool_input if isinstance(tool_input, str) else None
    if isinstance(tool_input, dict):
        command = tool_input.get("command")
        return command if isinstance(command, str) else None
    return None


def extract_high_corrections(content: str) -> list[str]:
    """Extract bullet points from the Constraints (HIGH confidence) section."""
    lines = content.splitlines()
    in_high_section = False
    corrections: list[str] = []
    current_bullet: list[str] = []

    for line in lines:
        if _HIGH_SECTION_RE.match(line):
            in_high_section = True
            continue
        if in_high_section and _HEADING_RE.match(line):
            break
        if in_high_section:
            stripped = line.strip()
            if stripped.startswith("- "):
                if current_bullet:
                    corrections.append(" ".join(current_bullet))
                current_bullet = [stripped[2:]]
            elif stripped and current_bullet:
                current_bullet.append(stripped)

    if current_bullet:
        corrections.append(" ".join(current_bullet))

    return corrections


def extract_keywords(command: str) -> list[str]:
    """Extract meaningful keywords from a Bash command."""
    tokens = re.split(r"[\s|;&]+", command)
    keywords: list[str] = []
    for token in tokens:
        if token.lstrip("'\"").startswith("-"):
            continue
        clean = token.strip("'-\"./\\")
        if len(clean) < MIN_KEYWORD_LENGTH:
            continue
        keywords.append(clean.lower())
    return keywords


def find_matching_corrections(
    corrections: list[tuple[str, str]],
    keywords: list[str],
) -> list[tuple[str, str]]:
    """Find corrections whose text matches any command keyword.

    Returns list of (source_file, correction_text) tuples.
    """
    matches: list[tuple[str, str]] = []
    for source, text in corrections:
        text_lower = text.lower()
        for kw in keywords:
            if kw in text_lower:
                matches.append((source, text))
                break
    return matches


def _collect_memory_files(memories_dir: Path, deadline: float) -> list[Path]:
    """Return up to ``_MAX_FILES_SCANNED`` ``*.md`` paths, bounded by ``deadline``.

    ``Path.rglob`` returns a lazy generator; iterating it drives the directory
    walk. The count and deadline checks run DURING iteration so a huge or slow
    ``.serena/memories/`` tree cannot blow the host hook timeout before the read
    loop is even entered. Sorting the whole ``rglob`` result up front (the prior
    behavior) materialized and ordered the entire tree first, defeating the very
    wedge this hook exists to prevent. The bounded result is sorted afterward so
    ordering is deterministic within the cap; when the corpus fits under the cap
    (the normal case) ordering is fully deterministic.
    """
    collected: list[Path] = []
    for md_file in memories_dir.rglob("*.md"):
        if len(collected) >= _MAX_FILES_SCANNED:
            break
        if time.monotonic() >= deadline:
            break
        collected.append(md_file)
    collected.sort()
    return collected


def scan_memories(project_root: str, deadline: float | None = None) -> list[tuple[str, str]]:
    """Scan .serena/memories/ for HIGH confidence corrections.

    Best-effort and bounded: stops after ``_SCAN_DEADLINE_SECONDS`` wall clock,
    ``_MAX_FILES_SCANNED`` files, or ``_MAX_TOTAL_BYTES`` read, whichever comes
    first. This is advisory context, so surfacing a subset is acceptable; the
    hard requirement is that the scan cannot exceed the host hook timeout and
    wedge every Bash command (fail-closed-on-timeout regression).

    Files are visited in sorted order for determinism. ``deadline`` is an
    absolute ``time.monotonic()`` value. When a caller passes a larger hook-wide
    deadline (``_HOOK_WALL_BUDGET_SECONDS`` from ``main()``), the scan still caps
    itself at ``_SCAN_DEADLINE_SECONDS`` so it never consumes the whole hook
    budget, matching the "stops after ``_SCAN_DEADLINE_SECONDS``" contract above.

    Returns list of (source_file, correction_text) tuples.
    """
    memories_dir = Path(project_root) / ".serena" / "memories"
    if not memories_dir.is_dir():
        return []

    scan_deadline = time.monotonic() + _SCAN_DEADLINE_SECONDS
    deadline = scan_deadline if deadline is None else min(deadline, scan_deadline)

    all_corrections: list[tuple[str, str]] = []
    total_bytes = 0

    for md_file in _collect_memory_files(memories_dir, deadline):
        if total_bytes >= _MAX_TOTAL_BYTES:
            break
        if time.monotonic() >= deadline:
            break
        try:
            content_bytes = md_file.read_bytes()
            content = content_bytes.decode("utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        total_bytes += len(content_bytes)
        corrections = extract_high_corrections(content)
        for c in corrections:
            all_corrections.append((md_file.name, c))

    return all_corrections


def main() -> int:
    """Main entry point. Always returns 0 (advisory, never blocks)."""
    hook_name = "correction-applier"
    deadline = time.monotonic() + _HOOK_WALL_BUDGET_SECONDS
    try:
        if skip_if_consumer_repo(hook_name):
            return 0

        if sys.stdin.isatty():
            return 0

        stdin_data = sys.stdin.read()
        if not stdin_data.strip():
            return 0

        command = parse_command(stdin_data)
        if not command:
            return 0

        keywords = extract_keywords(command)
        if not keywords:
            return 0

        project_root = get_project_directory()
        all_corrections = scan_memories(project_root, deadline=deadline)
        if not all_corrections:
            return 0

        matches = find_matching_corrections(all_corrections, keywords)
        if not matches:
            return 0

        shown = matches[:MAX_CORRECTIONS]
        lines = ["**Self-Improving Agent: Relevant corrections found**"]
        for source, text in shown:
            lines.append(f"- [{source}] {text}")

        # Advisory hook: surface corrections to the model WITHOUT making a
        # permission decision. PreToolUse model-visible context goes in
        # hookSpecificOutput.additionalContext. {"decision": "allow"} is INVALID:
        # the top-level `decision` field accepts only "approve"/"block" (the
        # blocking guards use "block"); "allow"/"deny"/"ask" belong to
        # hookSpecificOutput.permissionDecision, and setting permissionDecision
        # would auto-approve the tool. additionalContext advises and leaves the
        # normal permission flow intact. The old envelope failed schema
        # validation ("(root): Invalid input"), so the advisory was dropped.
        advisory = "\n".join(lines)
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "additionalContext": advisory,
            }
        }
        print(json.dumps(output))
        # Mirror advisory text to stderr for human visibility in logs
        # (stdout must remain valid JSON for the hook protocol).
        print(advisory, file=sys.stderr)
    except Exception as exc:
        print(f"[{hook_name}] Error (fail-open): {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
