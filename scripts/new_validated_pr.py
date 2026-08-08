#!/usr/bin/env python3
"""Create a validated PR with all guardrails enforced.

Wrapper around the `new_pr` skill script that provides a convenient interface
for creating PRs with validation. Delegates to the skill for better cohesion.

EXIT CODES:
  0  - Success
  1  - Validation failure
  2  - Usage/environment error

See: ADR-035 Exit Code Standardization
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.github_core.repo import get_repo_root  # noqa: E402

SKILL_RELPATH = Path(".claude/skills/github/scripts/pr/new_pr.py")
"""Dispatch target, relative to the repo root.

Exported so tests can assert the wrapper points at a script that exists rather
than restating the path and drifting from it.
"""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create a validated PR with guardrails")
    parser.add_argument("--title", default="", help="PR title in conventional commit format")
    parser.add_argument("--body", default="", help="PR description body")
    parser.add_argument("--body-file", default="", help="Path to file containing PR body")
    parser.add_argument("--base", default="main", help="Target branch (default: main)")
    parser.add_argument("--head", default="", help="Source branch (default: current)")
    parser.add_argument("--draft", action="store_true", help="Create as draft PR")
    parser.add_argument(
        "--web", action="store_true", help="Open browser to create PR interactively",
    )
    parser.add_argument("--skip-validation", action="store_true", help="Skip validation checks")
    parser.add_argument("--audit-reason", default="", help="Reason for skipping validation")
    return parser


def _run_web_mode(base: str) -> int:
    """Hand off to `gh pr create --web`, which needs a browser and so refuses in CI."""
    is_ci = os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS")
    if is_ci or not os.environ.get("DISPLAY"):
        print("ERROR: Web mode not available in CI or headless environments", file=sys.stderr)
        return 2

    gh_args = ["gh", "pr", "create", "--web"]
    if base:
        gh_args.extend(["--base", base])

    sys.stdout.flush()
    return subprocess.run(gh_args).returncode


def _build_skill_args(skill_script: Path, args: argparse.Namespace) -> list[str]:
    """Translate this wrapper's flags into the target script's command line."""
    skill_args = [
        sys.executable, str(skill_script),
        "--title", args.title, "--base", args.base,
    ]

    if args.head:
        skill_args.extend(["--head", args.head])
    if args.body:
        skill_args.extend(["--body", args.body])
    if args.body_file:
        skill_args.extend(["--body-file", args.body_file])
    if args.draft:
        skill_args.append("--draft")
    if args.skip_validation:
        skill_args.append("--skip-validation")
        if args.audit_reason:
            skill_args.extend(["--audit-reason", args.audit_reason])

    return skill_args


def _copy_body_to_prepared_path(
    repo_root: Path, skill_script: Path, source_path: str
) -> str:
    """Preserve the wrapper body-file API through the secure allocator."""
    content = Path(source_path).read_text(encoding="utf-8")
    module_path = skill_script.with_name("prepare_pr_body.py")
    spec = importlib.util.spec_from_file_location("prepare_pr_body", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load PR body allocator: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    relative_path = Path(module.prepare_pr_body(repo_root))
    module.write_prepared_pr_body(repo_root, relative_path.as_posix(), content)
    return str(relative_path.as_posix())


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    repo_root = get_repo_root()
    if not repo_root:
        print("ERROR: Not in a git repository", file=sys.stderr)
        return 2

    if not shutil.which("gh"):
        print("ERROR: gh CLI not found. Install: https://cli.github.com/", file=sys.stderr)
        return 2

    if args.web:
        return _run_web_mode(args.base)

    if not args.title:
        print("ERROR: Title required (use --title or --web)", file=sys.stderr)
        return 2

    skill_script = repo_root / SKILL_RELPATH
    if not skill_script.exists():
        print(f"ERROR: PR creation skill not found: {skill_script}", file=sys.stderr)
        return 2

    if args.body_file:
        try:
            args.body_file = _copy_body_to_prepared_path(
                repo_root, skill_script, args.body_file
            )
        except (OSError, RuntimeError, UnicodeError) as exc:
            print(f"ERROR: Could not prepare PR body: {exc}", file=sys.stderr)
            return 2

    sys.stdout.flush()
    return subprocess.run(_build_skill_args(skill_script, args)).returncode


if __name__ == "__main__":
    sys.exit(main())
