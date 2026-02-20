#!/usr/bin/env python3
"""
One-time cleanup: post spec-generator evaluation as a comment on issue #617,
then close issue #617, PR #1220, and PR #1221.

Context:
  PR #1220 added `.agents/planning/eval-617-spec-generator-skill.md` concluding
  "No Action Needed" for issue #617. Per project feedback, the evaluation result
  belongs as an issue comment, not a PR. This script performs that transition.

Exit codes follow ADR-035: 0=success, 1=logic error, 3=external failure.
"""
from __future__ import annotations

import base64
import json
import subprocess
import sys

REPO = "rjmurillo/ai-agents"
ISSUE = 617
PR_EVAL = 1220   # PR with the eval document (to be closed)
PR_THIS = 1221   # This working Copilot PR (to be closed)
EVAL_FILE = ".agents/planning/eval-617-spec-generator-skill.md"
EVAL_BRANCH = "feat/617-autonomous"
MARKER = "<!-- eval-617-spec-generator-no-action -->"
CLOSE_REASON = "completed"


def gh(*args: str) -> str:
    """Run a gh CLI command and return stdout; exit on failure."""
    result = subprocess.run(["gh", *args], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR: gh {' '.join(args)}\n{result.stderr}", file=sys.stderr)
        sys.exit(3)
    return result.stdout.strip()


def gh_try(*args: str) -> tuple[int, str]:
    """Run a gh CLI command; return (exit_code, stderr)."""
    result = subprocess.run(["gh", *args], capture_output=True, text=True)
    return result.returncode, result.stderr.strip()


def get_eval_content() -> str:
    """Return the evaluation file content from the PR #1220 branch."""
    raw = gh("api", f"repos/{REPO}/contents/{EVAL_FILE}?ref={EVAL_BRANCH}")
    data = json.loads(raw)
    return base64.b64decode(data["content"]).decode("utf-8")


def comment_already_posted() -> bool:
    """Return True if the idempotency marker is already in issue comments."""
    raw = gh("api", f"repos/{REPO}/issues/{ISSUE}/comments")
    comments = json.loads(raw)
    return any(MARKER in c.get("body", "") for c in comments)


def issue_is_open() -> bool:
    """Return True if issue #617 is still open."""
    raw = gh("api", f"repos/{REPO}/issues/{ISSUE}", "-q", ".state")
    return raw == "open"


def pr_is_open(number: int) -> bool:
    """Return True if the given PR is still open."""
    raw = gh("api", f"repos/{REPO}/pulls/{number}", "-q", ".state")
    return raw == "open"


def main() -> int:
    print(f"=== close_eval_617: closing issue #{ISSUE} and PRs #{PR_EVAL}, #{PR_THIS} ===")

    # Pre-flight: ensure gh CLI is available
    code, _ = gh_try("version")
    if code != 0:
        print("ERROR: 'gh' CLI not found or not authenticated.", file=sys.stderr)
        return 1

    # Step 1: Fetch eval file content from PR branch
    print(f"Fetching eval content from branch '{EVAL_BRANCH}'...")
    eval_content = get_eval_content()
    print("Content fetched.")

    # Step 2: Post eval content as comment on issue #617 (idempotent)
    if comment_already_posted():
        print(f"Idempotency marker found; comment already posted on issue #{ISSUE}. Skipping.")
    else:
        comment_body = f"{MARKER}\n\n{eval_content}"
        print(f"Posting evaluation comment on issue #{ISSUE}...")
        gh("issue", "comment", str(ISSUE), "--repo", REPO, "--body", comment_body)
        print("Comment posted.")

    # Step 3: Close issue #617
    if issue_is_open():
        print(f"Closing issue #{ISSUE}...")
        gh("issue", "close", str(ISSUE), "--repo", REPO, "--reason", CLOSE_REASON)
        print(f"Issue #{ISSUE} closed.")
    else:
        print(f"Issue #{ISSUE} already closed. Skipping.")

    # Step 4: Close PR #1220 (the eval PR)
    if pr_is_open(PR_EVAL):
        print(f"Closing PR #{PR_EVAL}...")
        gh(
            "pr", "close", str(PR_EVAL), "--repo", REPO,
            "--comment",
            "Closing: evaluation result posted as a comment on issue #617. "
            "No code changes needed. See #617 for the decision.",
        )
        print(f"PR #{PR_EVAL} closed.")
    else:
        print(f"PR #{PR_EVAL} already closed. Skipping.")

    # Step 5: Close PR #1221 (this working Copilot PR)
    if pr_is_open(PR_THIS):
        print(f"Closing PR #{PR_THIS}...")
        gh(
            "pr", "close", str(PR_THIS), "--repo", REPO,
            "--comment",
            "Task complete: evaluation comment posted on issue #617, "
            "issue closed, and PR #1220 closed. No code changes required.",
        )
        print(f"PR #{PR_THIS} closed.")
    else:
        print(f"PR #{PR_THIS} already closed. Skipping.")

    print("=== Done. ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
