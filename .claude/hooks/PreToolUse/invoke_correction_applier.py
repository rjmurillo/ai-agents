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
from pathlib import Path

# Bootstrap: find lib directory via env var or manifest walk-up.
# CLAUDE_PLUGIN_ROOT honored when set; otherwise walk up from __file__
# looking for .claude-plugin/plugin.json (the plugin marker). Sibling
# lib/ is the plugin's lib dir. Layout-independent: works in source
# tree (.claude/) and in the deeper src/<provider>/hooks/<event>/ copy.
_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
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
    print(f"Plugin lib directory not found: {_lib_dir} (CLAUDE_PLUGIN_ROOT={_plugin_root!r})", file=sys.stderr)
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
            return tool_input
    return tool_input.get("command") if isinstance(tool_input, dict) else None


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


def scan_memories(project_root: str) -> list[tuple[str, str]]:
    """Scan .serena/memories/ for HIGH confidence corrections.

    Returns list of (source_file, correction_text) tuples.
    """
    memories_dir = Path(project_root) / ".serena" / "memories"
    if not memories_dir.is_dir():
        return []

    all_corrections: list[tuple[str, str]] = []

    for md_file in memories_dir.rglob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        corrections = extract_high_corrections(content)
        for c in corrections:
            all_corrections.append((md_file.name, c))

    return all_corrections


def main() -> int:
    """Main entry point. Always returns 0 (advisory, never blocks)."""
    hook_name = "correction-applier"
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
        all_corrections = scan_memories(project_root)
        if not all_corrections:
            return 0

        matches = find_matching_corrections(all_corrections, keywords)
        if not matches:
            return 0

        shown = matches[:MAX_CORRECTIONS]
        lines = ["**Self-Improving Agent: Relevant corrections found**"]
        for source, text in shown:
            lines.append(f"- [{source}] {text}")

        # PreToolUse ADVISORY output: inject context through
        # hookSpecificOutput.additionalContext. The top-level `decision` field
        # accepts only "approve"/"block" (the blocking guards correctly use
        # "block"); "allow" is invalid there, so Claude Code rejected the whole
        # envelope and silently dropped the advisory (Issue #2468). The
        # allow/deny/ask values belong under
        # hookSpecificOutput.permissionDecision, which is a permission verdict,
        # not the context-injection an advisory needs.
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
