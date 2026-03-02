#!/usr/bin/env python3
"""Detect ADR file changes and prompt Claude to invoke adr-review skill.

Claude Code hook that checks for ADR file changes at session start.
When changes are detected, outputs a blocking gate message that prompts
Claude to invoke the adr-review skill for multi-agent consensus.

Hook Type: SessionStart
Exit Codes:
    0 = Success, stdout added to Claude's context

Related:
    .claude/skills/adr-review/SKILL.md
    .agents/architecture/ADR-*.md
"""

import json
import os
import subprocess
import sys


def get_project_root(script_dir: str) -> str | None:
    """Determine project root with path traversal protection.

    Uses CLAUDE_PROJECT_DIR if set (with validation), otherwise
    derives from script location.
    """
    env_dir = os.environ.get("CLAUDE_PROJECT_DIR", "")
    if env_dir:
        resolved_script_dir = os.path.realpath(script_dir)
        resolved_project_root = os.path.realpath(env_dir) + os.sep
        if not resolved_script_dir.startswith(resolved_project_root):
            print(
                f"Path traversal attempt detected via CLAUDE_PROJECT_DIR. "
                f"Project: '{env_dir}', Script: '{script_dir}'",
                file=sys.stderr,
            )
            return None
        return env_dir

    # Derive from script location: .claude/hooks/ -> project root
    return os.path.dirname(os.path.dirname(script_dir))


def run_detection_script(detect_script: str, project_root: str) -> dict | None:
    """Run the ADR detection PowerShell script and return parsed result."""
    try:
        result = subprocess.run(
            [
                "pwsh", "-NoProfile", "-File", detect_script,
                "-BasePath", project_root, "-IncludeUntracked",
            ],
            capture_output=True,
            text=True,
            cwd=project_root,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        print(f"ADR detection script error: {exc}", file=sys.stderr)
        return None

    if result.returncode != 0:
        output = result.stderr.strip() or result.stdout.strip()
        print(
            f"ADR detection script exited with code {result.returncode}",
            file=sys.stderr,
        )
        print(f"Output: {output}", file=sys.stderr)
        return None

    try:
        return json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError):
        print(
            f"ADR detection script returned invalid JSON: "
            f"{result.stdout[:200]}",
            file=sys.stderr,
        )
        return None


def build_change_message(detection_result: dict) -> str:
    """Build the ADR change notification message."""
    parts = [
        "",
        "## ADR Changes Detected - Review Required",
        "",
        "**BLOCKING GATE**: ADR changes detected - invoke /adr-review "
        "before commit",
        "",
        "### Changes Found",
        "",
    ]

    created = detection_result.get("Created", [])
    modified = detection_result.get("Modified", [])
    deleted = detection_result.get("Deleted", [])

    if created:
        parts.append(f"**Created**: {', '.join(created)}")
    if modified:
        parts.append(f"**Modified**: {', '.join(modified)}")
    if deleted:
        parts.append(f"**Deleted**: {', '.join(deleted)}")

    parts.extend([
        "",
        "### Required Action",
        "",
        "Invoke the adr-review skill for multi-agent consensus:",
        "",
        "```text",
        "/adr-review [ADR-path]",
        "```",
        "",
        "This ensures 6-agent debate (architect, critic, "
        "independent-thinker, security, analyst, high-level-advisor) "
        "before ADR acceptance.",
        "",
        "**Skill**: `.claude/skills/adr-review/SKILL.md`",
        "",
    ])

    return "\n".join(parts)


def main() -> None:
    """Entry point for the ADR change detection hook."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = get_project_root(script_dir)

    if project_root is None:
        sys.exit(0)

    # Validate git repository
    git_dir = os.path.join(project_root, ".git")
    if not os.path.exists(git_dir):
        print(
            f"ADR detection: ProjectRoot '{project_root}' is not a "
            f"git repository",
            file=sys.stderr,
        )
        sys.exit(0)

    detect_script = os.path.join(
        project_root, ".claude", "skills", "adr-review", "scripts",
        "Detect-ADRChanges.ps1"
    )

    if not os.path.isfile(detect_script):
        sys.exit(0)

    try:
        detection_result = run_detection_script(detect_script, project_root)
        if detection_result is None:
            sys.exit(0)

        if detection_result.get("HasChanges", False):
            message = build_change_message(detection_result)
            print(message)

    except Exception as exc:
        print(f"ADR change detection failed: {exc}", file=sys.stderr)
        print(
            "ADR detection skipped. Run detection manually if needed:",
            file=sys.stderr,
        )
        print(
            "  python3 .claude/skills/adr-review/scripts/"
            "detect_adr_changes.py",
            file=sys.stderr,
        )

    sys.exit(0)


if __name__ == "__main__":
    main()
