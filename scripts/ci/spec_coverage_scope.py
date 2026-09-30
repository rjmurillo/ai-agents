#!/usr/bin/env python3
"""Decide inside the Validate Spec Coverage job whether spec validation applies.

ADR-101 requirement 1 (`.project-toolkit/architecture/ADR-101-enforcement-planes.md`)
forbids a condition sourced outside a job's own logic from letting that job
report success without running the verification its name claims. Before this
script, `validate-spec` in `.github/workflows/ai-spec-validation.yml` took its
scope from another job:

  - a job-level `if:` read `needs.check-paths.result`, and
  - its first step read `needs.check-paths.outputs.has-code-changes`, computed
    by a path-filter action in that other job.

The verdict on "does this pull request touch code the spec must cover" belonged
to a different job. It now belongs to this one. The job checks out the pull
request, runs this script over the same immutable base and head SHAs the event
carries, and reads only the `skip` value this script emits.

What moved and what did not, so nobody reads more into it than is there:

  - Moved: the source of the scope decision. It is now a checked-in module the
    job itself executes over the checked-out tree, not an output of a sibling
    job.
  - Not moved: the path list is still head-editable, like every file the pull
    request can edit. This narrows the window, it does not close it. What
    closes it is the base-ref publisher in ADR-101 requirement 2, which is
    outside this change.

Decision table. `skip=true` means the job publishes without judging anything;
the workflow prints the reason so a skip is distinguishable from a pass.

  event               condition                                skip
  ------------------  ---------------------------------------  -----
  workflow_dispatch   an operator asked for a validation         false
  anything else       base or head SHA missing, malformed or
                      unreadable                                 false
  anything else       no changed file under a code prefix        true
  anything else       at least one changed file under a prefix   false

The job stays off `merge_group` through its own `if:` on the event name. A queue
run has no pull request body or number to validate, and the job holds an
environment secret. That event condition is not sourced from another job and
this context is not a required one, so it is left in place and named here.

An unreadable diff never skips. A verifier that cannot see the change must run
the validation rather than assume it is uninteresting, which is the opposite
polarity of the path filter this replaces (a filter error there read as "no
code changes").

Uses only the standard library: the workflow runs it with bare `python3`
(`.claude/rules/ci-scripts.md` MUST 18).

ENV:
  EVENT_NAME        - github.event_name
  BASE_SHA          - github.event.pull_request.base.sha (empty off pull_request)
  HEAD_SHA          - github.event.pull_request.head.sha (empty off pull_request)
  GITHUB_OUTPUT     - path to step output file (optional; stdout only when unset)

Outputs:
  skip    - "true" or "false"
  reason  - one line saying why

EXIT CODES (ADR-035):
  0 - decision emitted
  2 - configuration: EVENT_NAME is unset
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

EXIT_OK = 0
EXIT_CONFIG = 2

# The prefixes the previous `dorny/paths-filter` block named under `code:`.
# `**` under each of those roots is a prefix match, so a prefix test is the
# same predicate without an action or a glob library.
CODE_PREFIXES: tuple[str, ...] = (
    "src/",
    "templates/",
    "scripts/",
    "build/",
    ".claude/skills/",
)

_ALL_ZERO_SHA = "0" * 40

# A commit id as GitHub issues it. Anything else, including a value that begins
# with `-`, is refused before it reaches `git diff` argv (CWE-88).
_SHA_PATTERN = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")


@dataclass(frozen=True, slots=True)
class Scope:
    """Whether spec validation is skipped, and why."""

    skip: bool
    reason: str


def changed_files(repo_root: Path, base: str, head: str) -> list[str] | None:
    """Return the files `head` changed against `base` (three-dot), or None.

    None means git could not answer: an unfetched SHA, a shallow checkout, or
    git missing. The caller must not read None as an empty change set.

    `--no-renames` lists both sides of a move. Without it a file moved from
    `src/x.py` to `docs/x.py` shows only `docs/x.py`, and the removal from a
    code prefix goes unseen.
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "--no-renames", "-z", f"{base}...{head}"],
            cwd=repo_root,
            capture_output=True,
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    raw = result.stdout.decode("utf-8", errors="replace")
    return [path for path in raw.split("\0") if path]


def _is_code_path(path: str) -> bool:
    return path.startswith(CODE_PREFIXES)


def _is_usable_sha(value: str) -> bool:
    return value != _ALL_ZERO_SHA and _SHA_PATTERN.fullmatch(value) is not None


def decide(event_name: str, base: str, head: str, repo_root: Path) -> Scope:
    """Apply the decision table in the module docstring."""
    if event_name == "workflow_dispatch":
        return Scope(False, "manual dispatch always validates")
    if not _is_usable_sha(base) or not _is_usable_sha(head):
        return Scope(
            False, f"cannot diff without base and head SHAs (base={base!r}, head={head!r})"
        )
    changed = changed_files(repo_root, base, head)
    if changed is None:
        return Scope(False, f"could not diff {base!r}...{head!r}; validating rather than skipping")
    code = [path for path in changed if _is_code_path(path)]
    if code:
        return Scope(False, f"{len(code)} of {len(changed)} changed files are under a code prefix")
    return Scope(True, f"0 of {len(changed)} changed files are under a code prefix")


def _emit(scope: Scope) -> None:
    skip = "true" if scope.skip else "false"
    print(f"skip={skip}")
    print(f"reason={scope.reason}")
    output = os.environ.get("GITHUB_OUTPUT")
    if not output:
        return
    with open(output, "a", encoding="utf-8") as handle:
        handle.write(f"skip={skip}\n")
        handle.write(f"reason={scope.reason}\n")


def main() -> int:
    event_name = os.environ.get("EVENT_NAME", "").strip()
    if not event_name:
        print("EVENT_NAME is not set; refusing to decide a scope.", file=sys.stderr)
        return EXIT_CONFIG
    base = os.environ.get("BASE_SHA", "").strip()
    head = os.environ.get("HEAD_SHA", "").strip()
    _emit(decide(event_name, base, head, Path.cwd()))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
