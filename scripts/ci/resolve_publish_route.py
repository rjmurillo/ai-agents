#!/usr/bin/env python3
"""Decide which publish route a run takes, and check the tag against the package version.

ADR-113 decision 5 and Resolved Question 2, issue #5636. Quoted from
``.project-toolkit/architecture/ADR-113-promotion-gate-evidence-and-exceptions.md``:

    "The publish entry point is a default-branch workflow that takes the
    candidate SHA as input."

    "A pushed tag runs the tagged commit's own copy of the workflow (decision 5),
    so the ancestor and tag-match checks cannot protect that route. Until the
    owner creates the ruleset or drops the tag trigger, the gate is advisory."

Two routes reach ``publish.yml``:

- ``workflow_dispatch`` on the default branch, with an optional candidate SHA
  (default: the run's own commit), ``dry-run``, and an optional release tag. This
  route is live. A real publish (``dry-run`` false) runs the gate in enforcing
  mode, and a dry run runs it advisory.
- A push of a ``v*`` tag. This route is dormant and fails closed: it exits 1 with
  the reason. A tag push runs the tagged commit's own copy of the workflow, so
  nothing on that route can vouch for the gate until the owner creates the ``v*``
  tag ruleset. The owner's command is on issue #5636. No code here creates or
  reads a ruleset.

Any other event or ref exits 2.

``route`` writes ``candidate_sha``, ``release_tag``, ``dry_run`` and ``mode`` to
``--github-output``. ``tag-version`` compares a release tag with the version in
``package.json`` and replaces the inline shell step that did the same.

Stdlib only (``ci-scripts.md`` MUST 18).

Exit codes (ADR-035): 0 ok, 1 the route is refused or the tag does not match the
package version, 2 invalid arguments, 3 a file cannot be read.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

EXIT_OK, EXIT_REFUSED, EXIT_CONFIG, EXIT_EXTERNAL = 0, 1, 2, 3
MODE_ADVISORY, MODE_ENFORCING = "advisory", "enforcing"
_SHA_RE = re.compile(r"[0-9a-f]{40}")
_TAG_RE = re.compile(r"v\d+\.\d+\.\d+(?:-[0-9A-Za-z][0-9A-Za-z.-]*)?")
_BRANCH_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*")
TAG_ROUTE_DORMANT = (
    "the v* tag route is dormant. A tag push runs the tagged commit's own copy of "
    "this workflow, so nothing there can vouch for the promotion gate until the "
    "owner creates the v* tag ruleset (issue 5636). Run this workflow by "
    "workflow_dispatch from the default branch instead."
)


class RouteRefusedError(Exception):
    """The run may not publish. ``code`` is the ADR-035 exit code."""

    def __init__(self, message: str, code: int = EXIT_REFUSED) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class RouteDecision:
    """What the rest of the workflow needs to know."""

    candidate_sha: str
    release_tag: str
    dry_run: bool

    @property
    def mode(self) -> str:
        """Enforcing for a real publish, advisory for a dry run."""
        return MODE_ADVISORY if self.dry_run else MODE_ENFORCING


def _dry_run(value: str) -> bool:
    if value not in ("true", "false"):
        raise RouteRefusedError("dry-run must be 'true' or 'false'", EXIT_CONFIG)
    return value == "true"


def _candidate(value: str, run_sha: str) -> str:
    sha = value or run_sha
    if not _SHA_RE.fullmatch(sha):
        raise RouteRefusedError("the candidate must be a 40-character lowercase SHA", EXIT_CONFIG)
    return sha


def _release_tag(value: str) -> str:
    if value and not _TAG_RE.fullmatch(value):
        raise RouteRefusedError("release-tag must look like v1.2.3", EXIT_CONFIG)
    return value


def decide_route(
    *,
    event: str,
    ref: str,
    run_sha: str,
    default_branch: str,
    candidate_input: str,
    dry_run_input: str,
    release_tag_input: str,
) -> RouteDecision:
    """Return the decision for a dispatch on the default branch, or raise ``RouteRefusedError``."""
    if event == "push" and ref.startswith("refs/tags/v"):
        raise RouteRefusedError(TAG_ROUTE_DORMANT)
    if event != "workflow_dispatch":
        raise RouteRefusedError(f"event {event!r} cannot publish", EXIT_CONFIG)
    if not _BRANCH_RE.fullmatch(default_branch) or ref != f"refs/heads/{default_branch}":
        raise RouteRefusedError("publish runs only from the default branch")
    return RouteDecision(
        candidate_sha=_candidate(candidate_input, run_sha),
        release_tag=_release_tag(release_tag_input),
        dry_run=_dry_run(dry_run_input),
    )


def package_version(package_dir: Path) -> str:
    """Return ``version`` from ``package.json``. Raises ``OSError`` or ``ValueError``."""
    document = json.loads((package_dir / "package.json").read_text(encoding="utf-8"))
    version = document.get("version") if isinstance(document, dict) else None
    if not isinstance(version, str) or not version:
        raise ValueError("package.json has no version")
    return version


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    route = commands.add_parser("route", help="decide the publish route")
    for name in ("event", "ref", "run-sha", "default-branch"):
        route.add_argument(f"--{name}", required=True)
    for name in ("candidate-input", "dry-run-input", "release-tag-input"):
        route.add_argument(f"--{name}", default="")
    route.add_argument("--github-output", type=Path, default=None)
    version = commands.add_parser("tag-version", help="check a tag against package.json")
    version.add_argument("--package-dir", type=Path, required=True)
    version.add_argument("--release-tag", default="")
    return parser


def _run_route(args: argparse.Namespace) -> int:
    try:
        decision = decide_route(
            event=args.event,
            ref=args.ref,
            run_sha=args.run_sha,
            default_branch=args.default_branch,
            candidate_input=args.candidate_input,
            dry_run_input=args.dry_run_input or "true",
            release_tag_input=args.release_tag_input,
        )
    except RouteRefusedError as exc:
        print(f"[FAIL] publish route: {json.dumps(str(exc))}", file=sys.stderr)
        return exc.code
    if args.github_output is not None:
        lines = (
            f"candidate_sha={decision.candidate_sha}",
            f"release_tag={decision.release_tag}",
            f"dry_run={'true' if decision.dry_run else 'false'}",
            f"mode={decision.mode}",
        )
        with args.github_output.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    print(f"publish route: dispatch, mode {decision.mode}, candidate {decision.candidate_sha[:12]}")
    return EXIT_OK


def _run_tag_version(args: argparse.Namespace) -> int:
    if not args.release_tag:
        print("tag version: no release tag given, nothing to compare")
        return EXIT_OK
    if not _TAG_RE.fullmatch(args.release_tag):
        print("[FAIL] tag version: release-tag must look like v1.2.3", file=sys.stderr)
        return EXIT_CONFIG
    try:
        version = package_version(args.package_dir)
    except OSError as exc:
        print(
            f"[BLOCKED] tag version: cannot read package.json, {type(exc).__name__}",
            file=sys.stderr,
        )
        return EXIT_EXTERNAL
    except ValueError as exc:
        print(f"[FAIL] tag version: {json.dumps(str(exc))}", file=sys.stderr)
        return EXIT_CONFIG
    if args.release_tag != f"v{version}":
        print(
            f"[FAIL] tag version: {args.release_tag} does not match package.json version {version}",
            file=sys.stderr,
        )
        return EXIT_REFUSED
    print(f"tag version: {args.release_tag} matches package.json")
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point. Returns an ADR-035 exit code."""
    args = _parser().parse_args(argv)
    return _run_route(args) if args.command == "route" else _run_tag_version(args)


if __name__ == "__main__":
    raise SystemExit(main())
