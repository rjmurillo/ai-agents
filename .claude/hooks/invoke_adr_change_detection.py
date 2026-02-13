#!/usr/bin/env python3
"""Detect ADR file changes and prompt Claude to invoke adr-review skill.

Claude Code hook that checks for ADR file changes at session start.
When changes are detected, outputs a blocking gate message that prompts
Claude to invoke the adr-review skill for multi-agent consensus.

Hook Type: SessionStart
Exit Codes:
    0 = Success, stdout added to Claude's context
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def get_project_root() -> str | None:
    """Get the project root directory with path traversal validation.

    Uses CLAUDE_PROJECT_DIR if set and validates that this script lives
    within the specified project root (CWE-22 protection).
    Falls back to deriving from script location.
    """
    script_dir = str(Path(__file__).resolve().parent)
    env_dir = os.environ.get("CLAUDE_PROJECT_DIR", "").strip()

    if env_dir:
        resolved_script = os.path.realpath(script_dir)
        resolved_root = os.path.realpath(env_dir)
        # Ensure script is within the specified project root
        if not resolved_script.startswith(resolved_root + os.sep):
            print(
                f"Path traversal attempt detected via CLAUDE_PROJECT_DIR. "
                f"Project: '{env_dir}', Script: '{script_dir}'",
                file=sys.stderr,
            )
            return None
        return env_dir

    # Derive from script location: hooks dir is 2 levels up from project root
    return str(Path(__file__).resolve().parents[2])


def main() -> int:
    """Main hook entry point. Returns exit code."""
    project_root = get_project_root()
    if project_root is None:
        return 0  # Fail-open

    # Validate the resolved path is a git repository
    if not (Path(project_root) / ".git").exists():
        print(
            f"ADR detection: ProjectRoot '{project_root}' is not a git repository",
            file=sys.stderr,
        )
        return 0

    detect_script = str(
        Path(project_root)
        / ".claude"
        / "skills"
        / "adr-review"
        / "scripts"
        / "detect_adr_changes.py"
    )

    if not Path(detect_script).exists():
        return 0

    try:
        result = subprocess.run(
            [sys.executable, detect_script, "--base-path", project_root, "--include-untracked"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            print(f"ADR detection script exited with code {result.returncode}", file=sys.stderr)
            if result.stderr:
                print(f"Output: {result.stderr.strip()}", file=sys.stderr)
            return 0  # Non-blocking

        detection = json.loads(result.stdout)

        if not detection.get("HasChanges"):
            return 0  # No output if no changes

        lines: list[str] = [
            "",
            "## ADR Changes Detected - Review Required",
            "",
            "**BLOCKING GATE**: ADR changes detected - invoke /adr-review before commit",
            "",
            "### Changes Found",
            "",
        ]

        created = detection.get("Created", [])
        modified = detection.get("Modified", [])
        deleted = detection.get("Deleted", [])

        if created:
            lines.append(f"**Created**: {', '.join(created)}")
        if modified:
            lines.append(f"**Modified**: {', '.join(modified)}")
        if deleted:
            lines.append(f"**Deleted**: {', '.join(deleted)}")

        lines.extend(
            [
                "",
                "### Required Action",
                "",
                "Invoke the adr-review skill for multi-agent consensus:",
                "",
                "```text",
                "/adr-review [ADR-path]",
                "```",
                "",
                "This ensures 6-agent debate (architect, critic, independent-thinker, "
                "security, analyst, high-level-advisor) before ADR acceptance.",
                "",
                "**Skill**: `.claude/skills/adr-review/SKILL.md`",
                "",
            ]
        )

        print("\n".join(lines))
        return 0

    except (json.JSONDecodeError, OSError) as exc:
        print(f"ADR change detection failed: {exc}", file=sys.stderr)
        print(
            "ADR detection skipped. Run detection manually if needed:",
            file=sys.stderr,
        )
        print(
            f"  python3 {detect_script}",
            file=sys.stderr,
        )
        return 0


if __name__ == "__main__":
    sys.exit(main())
