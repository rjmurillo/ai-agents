#!/usr/bin/env python3
"""Surface topical Serena memories before a Write/Edit (issue #2005).

PreToolUse hook on Write|Edit. Derives a topic from the target file path,
finds matching memories under .serena/memories/, and surfaces up to three as
advisory context so the writing path includes a memory-read step (PR #2004
showed memory-as-passive-reference fails when the writing path skips it).

Advisory only. Per .claude/rules/release-it.md (lifecycle hooks MUST be fast,
bound their one integration point, and degrade to a no-op): the only
integration point is the local filesystem (no MCP, no subprocess); a hard
internal deadline abandons the scan rather than slowing the agent, and every
failure path exits 0 with no output.

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

# Bootstrap: find lib directory via env var or manifest walk-up (mirrors
# invoke_correction_applier.py so the hook works in both the source tree and
# the deeper src/<provider>/hooks/<event>/ copy).
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
    # Non-blocking hook: exit 0 on bootstrap failure (intentional).
    sys.exit(0)
if _lib_dir not in sys.path:
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
            return True
        return False


# Max memories to surface (avoid context bloat).
MAX_MEMORIES = 3
# Hard cap on injected advisory text (2KB per the issue AC).
MAX_INJECT_BYTES = 2048
# Soft internal deadline for the whole scan (seconds). The harness timeout is
# the backstop; this keeps the hook from ever slowing a Write/Edit.
SCAN_DEADLINE_SECONDS = 0.08

# Table-driven topic keying: first match wins. Each rule maps a path prefix to
# a topic; a callable receives the regex match so per-skill names can be
# extracted. Order matters (most specific first).
_TOPIC_RULES: list[tuple[re.Pattern[str], object]] = [
    (re.compile(r"^\.claude/skills/([^/]+)/"), lambda m: m.group(1)),
    (re.compile(r"^\.claude/hooks/"), lambda m: "hooks"),
    (re.compile(r"^\.claude/commands/"), lambda m: "commands"),
    (re.compile(r"^\.claude/agents/"), lambda m: "agents"),
    (re.compile(r"^\.claude/rules/"), lambda m: "rules"),
    (re.compile(r"^scripts/validation/"), lambda m: "validation"),
    (re.compile(r"^scripts/"), lambda m: "scripts"),
    (re.compile(r"^build/"), lambda m: "build"),
    (re.compile(r"^templates/"), lambda m: "templates"),
    (re.compile(r"^tests/"), lambda m: "tests"),
    (re.compile(r"^\.github/workflows/"), lambda m: "workflow"),
]
# Constrain the derived topic to a safe charset before it is used as a
# substring match against memory paths (no traversal, no glob metacharacters).
_SAFE_TOPIC_RE = re.compile(r"[^a-z0-9_-]")


def parse_file_path(stdin_data: str) -> str | None:
    """Extract tool_input.file_path from the hook stdin JSON."""
    try:
        data = json.loads(stdin_data)
    except (json.JSONDecodeError, TypeError):
        return None
    tool_input = data.get("tool_input")
    if tool_input is None:
        tool_input = {}
    if isinstance(tool_input, str):
        try:
            tool_input = json.loads(tool_input)
        except (json.JSONDecodeError, TypeError):
            return None
    if not isinstance(tool_input, dict):
        return None
    path = tool_input.get("file_path")
    return path if isinstance(path, str) and path else None


def relativize(file_path: str, project_root: str) -> str:
    """Return file_path relative to project_root (POSIX slashes).

    Absolute paths under the root are made relative; an already-relative path
    is returned as-is (only a leading ``./`` prefix is stripped). A leading
    dot in a real segment (``.claude``, ``.github``) is preserved.
    """
    if os.path.isabs(file_path):
        try:
            rel = os.path.relpath(file_path, project_root)
        except ValueError:
            rel = file_path
    else:
        rel = file_path
    # Normalize to collapse .. segments before topic matching.
    rel = os.path.normpath(rel)
    rel = rel.replace(os.sep, "/")
    if rel.startswith("./"):
        rel = rel[2:]
    return rel


def derive_topic(rel_path: str) -> str | None:
    """Map a repo-relative path to a topic key (table-driven)."""
    for pattern, resolver in _TOPIC_RULES:
        match = pattern.match(rel_path)
        if match:
            topic = resolver(match)  # type: ignore[operator]
            return _SAFE_TOPIC_RE.sub("", topic.lower()) or None
    # Fallback: first non-dot path segment.
    for segment in rel_path.split("/"):
        if segment and not segment.startswith("."):
            return _SAFE_TOPIC_RE.sub("", segment.lower()) or None
    return None


def _summary_line_from_file(path: Path) -> str:
    """Return a one-line summary by reading only until the first heading/prose line.

    Opens the file and reads line-by-line to avoid loading large files entirely.
    A leading YAML frontmatter block (delimited by ``---``) is skipped so its
    keys are never mistaken for the summary. Leading blank lines before the
    frontmatter opener are also skipped.
    """
    try:
        with path.open("r", encoding="utf-8") as f:
            in_frontmatter = False
            seen_first_nonblank = False
            for raw in f:
                line = raw.strip()
                if not seen_first_nonblank:
                    if not line:
                        continue
                    seen_first_nonblank = True
                    if line == "---":
                        in_frontmatter = True
                        continue
                if in_frontmatter:
                    if line == "---":
                        in_frontmatter = False
                    continue
                if not line or line == "---":
                    continue
                if line.startswith("#"):
                    return line.lstrip("# ").strip()[:160]
                return line[:160]
    except (OSError, UnicodeDecodeError):
        pass
    return ""


def find_topical_memories(
    project_root: str, topic: str, deadline: float,
) -> list[tuple[str, str]]:
    """Return up to MAX_MEMORIES (relative_path, summary) for the topic.

    Matches a memory when the topic (or its singular form) appears in the
    memory's relative path. Ranks by mtime descending. Abandons the scan if
    the deadline passes, returning whatever was collected.
    """
    memories_dir = Path(project_root) / ".serena" / "memories"
    if not memories_dir.is_dir():
        return []
    singular = topic.removesuffix("s")
    needles = {topic, singular} if len(singular) >= 2 else {topic}
    candidates: list[tuple[float, Path, str]] = []
    for md_file in memories_dir.rglob("*.md"):
        if time.monotonic() > deadline:
            break
        try:
            rel = md_file.relative_to(memories_dir).as_posix().lower()
        except ValueError:
            continue
        if not any(n and n in rel for n in needles):
            continue
        try:
            mtime = md_file.stat().st_mtime
        except OSError:
            continue
        candidates.append((mtime, md_file, md_file.relative_to(memories_dir).as_posix()))
    candidates.sort(key=lambda c: c[0], reverse=True)

    results: list[tuple[str, str]] = []
    for _mtime, path, rel in candidates[:MAX_MEMORIES]:
        if time.monotonic() > deadline:
            break
        results.append((rel, _summary_line_from_file(path)))
    return results


def render_advisory(topic: str, memories: list[tuple[str, str]]) -> str:
    """Render the advisory block, capped at MAX_INJECT_BYTES."""
    lines = [f"**Topical memory ({topic})**: read before writing if relevant."]
    for rel, summary in memories:
        suffix = f" - {summary}" if summary else ""
        lines.append(f"- .serena/memories/{rel}{suffix}")
    text = "\n".join(lines)
    if len(text.encode("utf-8")) > MAX_INJECT_BYTES:
        text = text.encode("utf-8")[:MAX_INJECT_BYTES].decode("utf-8", "ignore")
        text += "\n- ... (truncated)"
    return text


def main() -> int:
    """Always returns 0 (advisory, never blocks)."""
    hook_name = "topical-memory-injection"
    try:
        if skip_if_consumer_repo(hook_name):
            return 0
        if sys.stdin.isatty():
            return 0
        stdin_data = sys.stdin.read()
        if not stdin_data.strip():
            return 0

        file_path = parse_file_path(stdin_data)
        if not file_path:
            return 0
        project_root = get_project_directory()
        rel_path = relativize(file_path, project_root)
        topic = derive_topic(rel_path)
        if not topic:
            return 0

        deadline = time.monotonic() + SCAN_DEADLINE_SECONDS
        memories = find_topical_memories(project_root, topic, deadline)
        if not memories:
            return 0

        advisory = render_advisory(topic, memories)
        # Advisory only: inject as model-visible context via
        # hookSpecificOutput.additionalContext. {"decision": "allow"} is invalid
        # (top-level `decision` accepts only "approve"/"block"); see
        # invoke_correction_applier.py for the full rationale.
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "additionalContext": advisory,
                    }
                }
            )
        )
        print(advisory, file=sys.stderr)
    except Exception as exc:  # noqa: BLE001 - advisory hook fails open
        print(f"[{hook_name}] Error (fail-open): {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
