#!/usr/bin/env python3
"""Enforce blocking PR validation results."""

from __future__ import annotations

import os
import subprocess
import sys

LOGIC_ERROR = 1
BYPASS_LABEL = "commit-limit-bypass"

# CONTRIBUTING.md, section "Bypassing the Limit", is the canonical authority for
# this label; CONTRIBUTING.md:880 reads, verbatim:
#     1. A human maintainer MUST add the `commit-limit-bypass` label
# So the blocked-PR annotation states the sanctioned action (split) and names the
# label as a maintainer decision rather than as the reader's next step (issue
# #4782). This is CI's own standalone copy rather than an import:
# pr-validation.yml:212 runs this script as
# `python3 scripts/ci/enforce_pr_validation.py` with nothing installed and no
# sys.path setup, and an import failure here takes the required check red on
# every PR. There is no longer a local-hook counterpart to duplicate against:
# the pre-push commit-count gate (scripts/validation/git_hook_policy.py:
# _check_commit_limit) was demoted to a non-blocking report per ADR-100 and
# issue #5232, and dropped its bypass-label wording along with the block.
# tests/validation/test_human_only_label_guidance.py pins this message against
# CONTRIBUTING.md's declared policy directly.
HUMAN_ONLY_NOTICE = (
    f"The '{BYPASS_LABEL}' label lifts the ceiling, but CONTRIBUTING.md "
    '("Bypassing the Limit") requires a human maintainer to add it: ask a '
    "maintainer to decide, and do not apply it yourself."
)


def _fetch_labels(repository: str, pr_number: str) -> tuple[int, list[str]]:
    result = subprocess.run(
        [
            "gh",
            "api",
            f"repos/{repository}/issues/{pr_number}/labels",
            "--jq",
            ".[].name",
        ],
        check=False,
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    labels = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return result.returncode, labels


def main(argv: list[str] | None = None) -> int:
    if argv:
        print("::error::unexpected command line arguments", file=sys.stderr)
        return 2
    overall_status = os.environ.get("OVERALL_STATUS", "")
    commit_status = os.environ.get("COMMIT_STATUS", "")
    commit_count = os.environ.get("COMMIT_COUNT", "")
    commit_limit = os.environ.get("COMMIT_LIMIT", "").strip()
    pr_number = os.environ.get("PR_NUMBER", "")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    if overall_status in {"FAIL", "ERROR"}:
        print(f"::error::PR validation failed: {overall_status}", file=sys.stderr)
        return LOGIC_ERROR
    if commit_status == "BLOCKED":
        exit_code, labels = _fetch_labels(repository, pr_number)
        if exit_code != 0:
            print(
                f"::error::Failed to fetch PR labels (exit code: {exit_code})",
                file=sys.stderr,
            )
            return LOGIC_ERROR
        if BYPASS_LABEL in labels:
            print(f"::warning::Commit limit bypassed via '{BYPASS_LABEL}' label")
        else:
            # The main-merge relief (issue #3596) widens the ceiling to 40, so
            # the applied limit is only knowable from the producer's output. With
            # no value to report, naming none beats naming a wrong one.
            ceiling = f" (limit: {commit_limit})" if commit_limit else ""
            print(
                f"::error::PR has {commit_count} commits{ceiling}. "
                f"Split this PR into smaller ones. {HUMAN_ONLY_NOTICE}",
                file=sys.stderr,
            )
            return LOGIC_ERROR
    print("✓ PR validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
