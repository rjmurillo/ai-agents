#!/usr/bin/env python3
"""Create a validated PR with all guardrails enforced.

Wrapper around the New-PR skill that provides a convenient interface for
creating PRs with validation. Delegates to the skill for better cohesion.

EXIT CODES:
  0  - Success
  1  - Validation failure
  2  - Usage/environment error

See: ADR-035 Exit Code Standardization
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def get_repo_root() -> Path | None:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return Path(result.stdout.strip())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a validated PR with guardrails")
    parser.add_argument("--title", default="", help="PR title in conventional commit format")
    parser.add_argument("--body", default="", help="PR description body")
    parser.add_argument("--body-file", default="", help="Path to file containing PR body")
    parser.add_argument("--base", default="main", help="Target branch (default: main)")
    parser.add_argument("--head", default="", help="Source branch (default: current)")
    parser.add_argument("--draft", action="store_true", help="Create as draft PR")
    parser.add_argument("--web", action="store_true", help="Open browser to create PR interactively")
    parser.add_argument("--skip-validation", action="store_true", help="Skip validation checks")
    parser.add_argument("--audit-reason", default="", help="Reason for skipping validation")
    args = parser.parse_args(argv)

    repo_root = get_repo_root()
    if not repo_root:
        print("ERROR: Not in a git repository", file=sys.stderr)
        return 2

    if not shutil.which("gh"):
        print("ERROR: gh CLI not found. Install: https://cli.github.com/", file=sys.stderr)
        return 2

    if args.web:
        if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS") or not os.environ.get("DISPLAY"):
            print("ERROR: Web mode not available in CI or headless environments", file=sys.stderr)
            return 2
        gh_args = ["gh", "pr", "create", "--web"]
        if args.base:
            gh_args.extend(["--base", args.base])
        result = subprocess.run(gh_args)
        return result.returncode

    if not args.title:
        print("ERROR: Title required (use --title or --web)", file=sys.stderr)
        return 2

    skill_script = repo_root / ".claude" / "skills" / "github" / "scripts" / "pr" / "New-PR.ps1"
    if not skill_script.exists():
        print(f"ERROR: PR creation skill not found: {skill_script}", file=sys.stderr)
        return 2

    skill_args = ["pwsh", "-NoProfile", "-File", str(skill_script), "-Title", args.title, "-Base", args.base]

    if args.head:
        skill_args.extend(["-Head", args.head])
    if args.body:
        skill_args.extend(["-Body", args.body])
    if args.body_file:
        skill_args.extend(["-BodyFile", args.body_file])
    if args.draft:
        skill_args.append("-Draft")
    if args.skip_validation:
        skill_args.append("-SkipValidation")
        if args.audit_reason:
            skill_args.extend(["-AuditReason", args.audit_reason])

    result = subprocess.run(skill_args)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
