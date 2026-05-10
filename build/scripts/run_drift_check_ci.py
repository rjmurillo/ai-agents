#!/usr/bin/env python3
"""CI wrapper around generate_pr_quality_prompts.py --dry-run (REQ-008-03).

Replaces the inline bash logic in the ``review-axes-drift-check`` job of
``ai-pr-quality-gate.yml`` per ADR-006 (logic in testable modules, not YAML).

The wrapper:
1. Runs the generator in --dry-run mode.
2. Captures stdout (drift diff or "ok" status lines).
3. Writes a structured GitHub Actions Step Summary.
4. Emits a GitHub Actions error annotation on drift.
5. Propagates the generator exit code (0 ok, 1 drift, 2 config error).

EXIT CODES (per ADR-035, mirrors generate_pr_quality_prompts.py):
    0 - clean (no drift)
    1 - drift detected (developer must regenerate and commit)
    2 - config error: wrapper-level (generator script missing) OR underlying
        generator config error (canonical dir missing, invalid filename,
        symlink rejected). Distinguishing 1 from 2 is required for CI to
        report drift vs broken setup. PR #1965 cluster U.

Refs #1934 (REQ-008-03), #1934 /review devops gate finding F1.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GENERATOR = REPO_ROOT / "build" / "scripts" / "generate_pr_quality_prompts.py"


def _write_step_summary(content: str) -> None:
    """Append to GITHUB_STEP_SUMMARY when present; no-op locally."""
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    with open(summary_path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(content)
        if not content.endswith("\n"):
            fh.write("\n")


def _format_summary(exit_code: int, output: str) -> str:
    if exit_code == 0:
        return "## Review-axes drift check\n\nNo drift detected.\n"
    if exit_code == 1:
        return (
            "## Review-axes drift check\n\n"
            "Drift detected between `.claude/review-axes/` (canonical) and "
            "`.github/prompts/pr-quality-gate-*.md` (generated).\n\n"
            "Fix: `python3 build/scripts/generate_pr_quality_prompts.py` and "
            "commit the regenerated CI prompts.\n\n"
            "<details><summary>Diff</summary>\n\n"
            "```diff\n"
            f"{output}\n"
            "```\n\n"
            "</details>\n"
        )
    return (
        f"## Review-axes drift check\n\n"
        f"Generator exited with code {exit_code} (config error).\n\n"
        f"```\n{output}\n```\n"
    )


def run(generator: Path) -> int:
    if not generator.is_file():
        try:
            label = str(generator.relative_to(REPO_ROOT))
        except ValueError:
            label = str(generator)
        print(
            f"::error::generator missing at {label}; "
            f"the drift check cannot run.",
            file=sys.stderr,
        )
        return 2

    result = subprocess.run(
        [sys.executable, str(generator), "--dry-run"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=60,
        check=False,
    )
    output = result.stdout + ("\n" + result.stderr if result.stderr else "")
    print(output)

    _write_step_summary(_format_summary(result.returncode, output))

    # Propagate the generator's exit code distinctly: 1 = drift detected
    # (developer must regenerate), 2 = config error (canonical dir missing,
    # invalid filename, symlink rejected). Collapsing both to 1 makes it
    # impossible to distinguish a fixable drift from a broken setup.
    # PR #1965 cursor + copilot review (cluster D).
    if result.returncode == 1:
        print(
            "::error file=.github/prompts/::"
            "Review-axes drift detected. Run "
            "python3 build/scripts/generate_pr_quality_prompts.py and commit.",
            file=sys.stderr,
        )
        return 1
    if result.returncode != 0:
        print(
            f"::error::generate_pr_quality_prompts.py exited {result.returncode} "
            f"(config error). Investigate the generator output above.",
            file=sys.stderr,
        )
        return result.returncode

    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Wrapper around generate_pr_quality_prompts.py --dry-run for CI. "
            "Emits a GitHub Step Summary and an error annotation on drift."
        )
    )
    parser.add_argument(
        "--generator",
        type=Path,
        default=GENERATOR,
        help="Path to the generator script (default: build/scripts/generate_pr_quality_prompts.py)",
    )
    args = parser.parse_args(argv)
    return run(args.generator)


if __name__ == "__main__":
    sys.exit(main())
