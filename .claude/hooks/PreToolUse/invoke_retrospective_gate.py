#!/usr/bin/env python3
"""Block git push without retrospective evidence per ADR-033.

Claude Code PreToolUse hook that enforces retrospective before push.
Prevents pushing without capturing session learnings.

Gate triggers on:
- git push commands

Evidence requirements (any one satisfies):
1. Retrospective section in session log (## Retrospective)
2. Retrospective file in .agents/retrospective/ for today
3. Reference to retrospective file in session log

Bypass conditions:
- Documentation-only changes (no code files)
- Trivial sessions (<10 minutes, single file)
- SKIP_RETROSPECTIVE_GATE environment variable set

Hook Type: PreToolUse
Exit Codes (Claude Hook Semantics, exempt from ADR-035):
    0 = Allow (not push, or retrospective evidence exists)
    2 = Block (push without retrospective evidence)
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
if _plugin_root:
    _lib_dir = os.path.join(_plugin_root, "lib")
else:
    _lib_dir = str(Path(__file__).resolve().parents[2] / "lib")
if os.path.isdir(_lib_dir) and _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

try:
    from hook_utilities import get_project_directory, get_today_session_log
except ImportError:
    # Fallback implementations when hook_utilities is not available
    def get_project_directory() -> str:
        """Resolve the project root directory."""
        env_dir = os.environ.get("CLAUDE_PROJECT_DIR", "").strip()
        if env_dir:
            return str(Path(env_dir).resolve())
        return str(Path.cwd())

    def get_today_session_log(sessions_dir: str, date: str | None = None) -> Path | None:
        """Find the most recent session log for the given date."""
        if date is None:
            date = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        sessions_path = Path(sessions_dir)
        if not sessions_path.is_dir():
            return None
        try:
            logs = sorted(
                sessions_path.glob(f"{date}-session-*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            return None
        return logs[0] if logs else None


_GIT_PUSH_PATTERN = re.compile(r"(?:^|\s)git\s+push\b")
_RETROSPECTIVE_SECTION_PATTERN = re.compile(
    r"(?i)(##\s*retrospective|retrospective\s*section|learnings?\s*captured)"
)
_RETROSPECTIVE_FILE_REF_PATTERN = re.compile(
    r"(?i)(\.agents/retrospective/|retrospective[-_]?file|retro[-_]?\d{4})"
)

# Documentation-only file patterns
_DOC_PATTERNS = [
    re.compile(r"\.md$"),
    re.compile(r"\.txt$"),
    re.compile(r"(^|/)README$"),
    re.compile(r"(^|/)LICENSE$"),
    re.compile(r"(^|/)CHANGELOG$"),
    re.compile(r"\.gitignore$"),
    re.compile(r"\.editorconfig$"),
]

# Session start time for trivial session detection
_SESSION_START_TIME = time.time()
_TRIVIAL_SESSION_MINUTES = 10


def is_git_push_command(command: str | None) -> bool:
    """Check if a command string is a git push command."""
    if not command:
        return False
    return _GIT_PUSH_PATTERN.search(command) is not None


def check_retrospective_in_session_log(session_log: Path) -> bool:
    """Check if session log contains retrospective evidence."""
    try:
        content = session_log.read_text(encoding="utf-8")
        if _RETROSPECTIVE_SECTION_PATTERN.search(content):
            return True
        if _RETROSPECTIVE_FILE_REF_PATTERN.search(content):
            return True
    except OSError:
        pass
    return False


def check_retrospective_file_exists(project_dir: str) -> bool:
    """Check if a retrospective file exists for today."""
    retro_dir = Path(project_dir) / ".agents" / "retrospective"
    if not retro_dir.is_dir():
        return False

    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    try:
        # Look for files matching today's date
        today_retros = list(retro_dir.glob(f"{today}*.md"))
        return len(today_retros) > 0
    except OSError:
        return False


def check_documentation_only() -> bool:
    """Check if all changed files are documentation-only."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "origin/main...HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            result = subprocess.run(
                ["git", "diff", "--name-only", "origin/main"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return False

        changed_files = result.stdout.strip()
        if not changed_files:
            return True  # No changes, allow

        for file_path in changed_files.splitlines():
            is_doc = any(pat.search(file_path) for pat in _DOC_PATTERNS)
            if not is_doc:
                return False

        return True
    except (subprocess.TimeoutExpired, OSError):
        return False


def check_trivial_session() -> bool:
    """Check if this is a trivial session (short duration, minimal changes)."""
    # Check session duration
    elapsed_minutes = (time.time() - _SESSION_START_TIME) / 60
    if elapsed_minutes > _TRIVIAL_SESSION_MINUTES:
        return False

    # Check number of changed files
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "origin/main...HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return False

        changed_files = result.stdout.strip().splitlines()
        # Trivial = single file change
        return len(changed_files) <= 1
    except (subprocess.TimeoutExpired, OSError):
        return False


def main() -> int:
    """Main hook entry point. Returns exit code."""
    try:
        if sys.stdin.isatty():
            return 0

        input_json = sys.stdin.read()
        if not input_json.strip():
            return 0

        hook_input = json.loads(input_json)

        tool_input = hook_input.get("tool_input")
        if not isinstance(tool_input, dict):
            return 0
        command = tool_input.get("command")
        if not command:
            return 0

        if not is_git_push_command(command):
            return 0

        project_dir = get_project_directory()
        sessions_dir = os.path.join(project_dir, ".agents", "sessions")

        # Skip if .agents infrastructure is absent (consumer repo)
        if not os.path.isdir(sessions_dir):
            print(
                "[SKIP] .agents/sessions/ not found (consumer repo). "
                "Retrospective enforcement skipped.",
                file=sys.stderr,
            )
            return 0

        # Bypass 1: Environment variable override
        if os.environ.get("SKIP_RETROSPECTIVE_GATE") == "true":
            print(
                "Retrospective gate bypassed via SKIP_RETROSPECTIVE_GATE environment variable",
                file=sys.stderr,
            )
            return 0

        # Bypass 2: Documentation-only changes
        if check_documentation_only():
            return 0

        # Bypass 3: Trivial session
        if check_trivial_session():
            return 0

        # Check for retrospective evidence
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        session_log = get_today_session_log(sessions_dir, date=today)

        has_retrospective = False

        # Check 1: Retrospective file exists for today
        if check_retrospective_file_exists(project_dir):
            has_retrospective = True

        # Check 2: Retrospective section in session log
        if session_log and check_retrospective_in_session_log(session_log):
            has_retrospective = True

        if has_retrospective:
            return 0

        # Block: No retrospective evidence found
        output = f"""
## BLOCKED: Retrospective Required Before Push

**Session retrospective required per ADR-033 enforcement gates.**

### Why Retrospectives Matter
- Capture learnings while context is fresh
- Prevent knowledge loss across sessions
- Enable continuous improvement
- Build institutional memory

### How to Satisfy This Gate

**Option 1: Run retrospective agent**
```
Task(subagent_type='retrospective', prompt='Analyze this session for learnings')
```

**Option 2: Add retrospective section to session log**
Add a `## Retrospective` section to today's session log with:
- What went well
- What could improve
- Key learnings

**Option 3: Create retrospective file**
Create `.agents/retrospective/{today}-*.md` with session analysis.

### Bypass Conditions
- Documentation-only changes (auto-detected)
- Trivial sessions (<10 minutes, single file)
- Set `SKIP_RETROSPECTIVE_GATE=true` (requires justification)

**Current Date**: {today}
**Session Log**: {session_log.name if session_log else "Not found"}
"""
        print(output)
        print("Push blocked: No retrospective evidence found", file=sys.stderr)
        return 2

    except Exception as exc:
        # Fail-open on errors (don't block on infrastructure issues)
        print(
            f"Retrospective gate error: {type(exc).__name__} - {exc}",
            file=sys.stderr,
        )
        return 0


if __name__ == "__main__":
    sys.exit(main())
