#!/usr/bin/env python3
"""Decide whether the AI PR quality gate should run for this event.

Extracted from the inline ``Determine if review should run`` step in
``.github/workflows/ai-pr-quality-gate.yml`` (ADR-006: no logic in YAML).

Decision rules (reproduced verbatim from the original bash block):

1. Bot actors (``dependabot[bot]``, ``github-actions[bot]``) -> skip review.
2. ``workflow_dispatch`` events -> run review (manual trigger, assume intent).
3. Otherwise run only when the paths-filter reported relevant changes
   (``RELEVANT == 'true'``).

The script writes ``should-run-review=true|false`` to ``GITHUB_OUTPUT`` and prints a
human-readable ``Decision:`` line, exactly as the original step did.

Input env vars:
    GH_ACTOR        - the triggering actor (github.actor).
    GH_EVENT_NAME   - the event name (github.event_name).
    RELEVANT        - paths-filter result ('true' when relevant files changed).
    GITHUB_OUTPUT   - path to the GitHub Actions output file.

Exit codes (ADR-035):
    0 - decision written successfully
    2 - GITHUB_OUTPUT is not set (config error)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_BOT_ACTORS = frozenset({"dependabot[bot]", "github-actions[bot]"})


def decide(gh_actor: str, gh_event_name: str, relevant: str) -> tuple[bool, str]:
    """Return ``(should_run, decision_message)`` for the given inputs."""

    if gh_actor in _BOT_ACTORS:
        return False, f"Decision: Skip review (bot actor: {gh_actor})"
    if gh_event_name == "workflow_dispatch":
        return True, "Decision: Run review (manual trigger)"
    if relevant == "true":
        return True, "Decision: Run review (relevant files changed)"
    return False, "Decision: Skip review (no relevant files changed)"


def write_should_run_review(output_path: Path, should_run: bool) -> None:
    """Append ``should-run-review=true|false`` to the GitHub output file."""

    value = "true" if should_run else "false"
    with output_path.open("a", encoding="utf-8") as handle:
        handle.write(f"should-run-review={value}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--gh-actor",
        default=os.environ.get("GH_ACTOR", ""),
        help="Triggering actor (github.actor).",
    )
    parser.add_argument(
        "--gh-event-name",
        default=os.environ.get("GH_EVENT_NAME", ""),
        help="Event name (github.event_name).",
    )
    parser.add_argument(
        "--relevant",
        default=os.environ.get("RELEVANT", ""),
        help="paths-filter result ('true' when relevant files changed).",
    )
    args = parser.parse_args(argv)

    should_run, message = decide(args.gh_actor, args.gh_event_name, args.relevant)

    # Print the same diagnostic line the original bash block emitted (the else
    # branch that echoed "Relevant files changed: $RELEVANT").
    in_relevant_branch = (
        args.gh_actor not in _BOT_ACTORS
        and args.gh_event_name != "workflow_dispatch"
    )
    if in_relevant_branch:
        print(f"Relevant files changed: {args.relevant}")
    print(message)

    github_output = os.environ.get("GITHUB_OUTPUT")
    if not github_output:
        print("error: GITHUB_OUTPUT is not set", file=sys.stderr)
        return 2

    write_should_run_review(Path(github_output), should_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
