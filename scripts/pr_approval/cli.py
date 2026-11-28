"""Offline CLI: evaluate a local evidence snapshot against local policy files.

Usage:
    python -m scripts.pr_approval.cli --snapshot pr.json \\
        [--policy .github/pr-approval-policy.toml] \\
        [--registry .github/pr-approval-registry.toml] \\
        [--codeowners .github/CODEOWNERS] [--comment]

Reads files only. Makes no network call and writes nothing.
Exit codes: 0 decision printed, 2 a policy, registry, or snapshot input is
invalid (a HOLD decision is still printed when a snapshot was readable).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts.pr_approval.codeowners import parse_codeowners
from scripts.pr_approval.comment import render_comment
from scripts.pr_approval.engine import evaluate, evidence_fingerprint
from scripts.pr_approval.policy import PolicyError, parse_policy
from scripts.pr_approval.registry import RegistryError, parse_registry
from scripts.pr_approval.snapshot import parse_snapshot

EXIT_OK = 0
EXIT_CONFIG = 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate a PR evidence snapshot in observe mode (offline)."
    )
    parser.add_argument("--snapshot", required=True, type=Path, help="JSON evidence snapshot")
    parser.add_argument("--policy", type=Path, default=Path(".github/pr-approval-policy.toml"))
    parser.add_argument("--registry", type=Path, default=Path(".github/pr-approval-registry.toml"))
    parser.add_argument("--codeowners", type=Path, default=Path(".github/CODEOWNERS"))
    parser.add_argument(
        "--comment", action="store_true", help="print the rendered comment, not JSON"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        raw = json.loads(args.snapshot.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"error: cannot read snapshot {args.snapshot}: {exc}", file=sys.stderr)
        return EXIT_CONFIG

    exit_code = EXIT_OK
    policy = registry = codeowners = None
    try:
        policy = parse_policy(args.policy.read_bytes())
    except (OSError, PolicyError) as exc:
        print(f"error: policy {args.policy}: {exc}", file=sys.stderr)
        exit_code = EXIT_CONFIG
    try:
        registry = parse_registry(args.registry.read_bytes())
    except (OSError, RegistryError) as exc:
        print(f"error: registry {args.registry}: {exc}", file=sys.stderr)
        exit_code = EXIT_CONFIG
    try:
        codeowners = parse_codeowners(args.codeowners.read_text(encoding="utf-8"))
    except OSError as exc:
        print(f"error: codeowners {args.codeowners}: {exc}", file=sys.stderr)
        exit_code = EXIT_CONFIG

    decision = evaluate(
        parse_snapshot(raw), policy, registry, codeowners, evidence_fingerprint(raw)
    )
    if args.comment:
        print(render_comment(decision))
    else:
        print(json.dumps(decision.to_dict(), indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
