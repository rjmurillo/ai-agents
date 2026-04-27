#!/usr/bin/env python3
"""CLI entrypoint for the panning-for-gold skill.

Subcommands:
    init      - Create the workspace directory layout.
    validate  - Validate an inventory file against the schema.
    merge     - Merge pass1 and final inventories, write the result.
    synth     - Build the gold-found file from inventory + evaluations.

EXIT CODES (ADR-035):
    0 - Success
    1 - Logic error
    2 - Config error
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

from inventory import (  # noqa: E402
    InventoryError,
    Thread,
    merge,
    read_inventory,
    render_inventory,
)
from synthesis import (  # noqa: E402
    SynthesisError,
    build_gold_found,
)

WORKSPACE_ENV: str = "PANNING_WORKSPACE"
DEFAULT_WORKSPACE: str = "./.panning"
SUBDIRS: tuple[str, ...] = ("transcripts", "inventories", "evaluations", "gold-found")


def resolve_workspace(arg_value: str | None) -> Path:
    """Pick the workspace root from CLI arg, env var, or default."""
    if arg_value:
        return Path(arg_value).resolve()
    env_value = os.environ.get(WORKSPACE_ENV)
    if env_value:
        return Path(env_value).resolve()
    return Path(DEFAULT_WORKSPACE).resolve()


def cmd_init(args: argparse.Namespace) -> int:
    """Create workspace subdirectories. Idempotent."""
    workspace = resolve_workspace(args.workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    for sub in SUBDIRS:
        (workspace / sub).mkdir(exist_ok=True)
    print(f"Initialized workspace: {workspace}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate an inventory file."""
    try:
        threads = read_inventory(Path(args.inventory))
    except InventoryError as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1
    print(f"VALID: {len(threads)} thread(s) in {args.inventory}")
    return 0


def cmd_merge(args: argparse.Namespace) -> int:
    """Merge two inventories and write the result."""
    try:
        pass1 = read_inventory(Path(args.pass1))
        final = read_inventory(Path(args.final))
    except InventoryError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    merged: list[Thread] = merge(pass1, final)
    output_path = Path(args.output)
    if output_path.exists() and not args.force:
        print(f"ERROR: refusing to overwrite {output_path} (pass --force)", file=sys.stderr)
        return 2
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_inventory(merged, source=str(args.final)), encoding="utf-8")
    print(f"Merged {len(merged)} thread(s) -> {output_path}")
    return 0


def cmd_synth(args: argparse.Namespace) -> int:
    """Build the gold-found markdown file."""
    try:
        threads = read_inventory(Path(args.inventory))
    except InventoryError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    evaluations_dir = Path(args.evaluations)
    if not evaluations_dir.is_dir():
        print(f"ERROR: evaluations dir not found: {evaluations_dir}", file=sys.stderr)
        return 2
    try:
        text = build_gold_found(
            threads=threads,
            evaluations_dir=evaluations_dir,
            source=args.source or str(args.inventory),
        )
    except SynthesisError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    output_path = Path(args.output)
    if output_path.exists() and not args.force:
        print(f"ERROR: refusing to overwrite {output_path} (pass --force)", file=sys.stderr)
        return 2
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")
    print(f"Wrote gold-found -> {output_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Construct the top-level parser."""
    parser = argparse.ArgumentParser(
        prog="pan.py",
        description="Triage raw input into evaluated thread inventories.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Create the workspace directory layout.")
    p_init.add_argument("--workspace", help="Workspace root (default: ./.panning).")
    p_init.set_defaults(func=cmd_init)

    p_val = sub.add_parser("validate", help="Validate an inventory file.")
    p_val.add_argument("--inventory", required=True, help="Path to inventory markdown.")
    p_val.set_defaults(func=cmd_validate)

    p_merge = sub.add_parser("merge", help="Merge pass1 and final inventories.")
    p_merge.add_argument("--pass1", required=True, help="Path to pass1 inventory.")
    p_merge.add_argument("--final", required=True, help="Path to final inventory.")
    p_merge.add_argument("--output", required=True, help="Path to write the merged inventory.")
    p_merge.add_argument("--force", action="store_true", help="Overwrite output if present.")
    p_merge.set_defaults(func=cmd_merge)

    p_synth = sub.add_parser("synth", help="Build the gold-found markdown file.")
    p_synth.add_argument("--inventory", required=True, help="Final inventory path.")
    p_synth.add_argument("--evaluations", required=True, help="Evaluations directory path.")
    p_synth.add_argument("--output", required=True, help="Path to write the gold-found file.")
    p_synth.add_argument("--source", help="Source label for the metadata block.")
    p_synth.add_argument("--force", action="store_true", help="Overwrite output if present.")
    p_synth.set_defaults(func=cmd_synth)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    func = args.func
    return int(func(args))


if __name__ == "__main__":
    raise SystemExit(main())
