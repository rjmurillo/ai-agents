"""CLI parser for check_agent_skill_discriminator.py."""

from __future__ import annotations

import argparse
import os
from pathlib import Path


def build_parser(default_baseline_name: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Detect new agents added in skill shape (Issue #2008).",
    )
    parser.add_argument(
        "--repo-root",
        default=os.environ.get("REPO_ROOT", "."),
        help="Repository root (env: REPO_ROOT, default: .)",
    )
    parser.add_argument(
        "--changed-files",
        nargs="*",
        default=None,
        help="Changed agent file paths to score (space-separated).",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        default=False,
        help="Score every agent in the repo, not just changed files. "
        "Used by the scheduled full-corpus audit (Issue #4087).",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=None,
        help=(
            "Candidate baseline JSON "
            f"(default: scripts/validation/{default_baseline_name})."
        ),
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Rewrite the full-corpus candidate baseline and exit 0.",
    )
    parser.add_argument(
        "--allow-baseline-shrink",
        action="store_true",
        help="Permit a baseline rewrite that drops recorded candidates.",
    )
    parser.add_argument(
        "--pr-body",
        default=os.environ.get("PR_BODY", ""),
        help="PR description text; scanned for the override token (env: PR_BODY).",
    )
    return parser
