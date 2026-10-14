#!/usr/bin/env python3
"""Deterministic engine for the requirements-interview ambiguity-audit mode.

Subcommands:
    check   validate a coverage ledger against the source specification, record
            answers the document or codebase already holds, and plan the next
            batch of source-anchored decision questions. A ledger with no
            question to ask returns the verdict NO MATERIAL GAPS.
    verify  prove a rebuilt specification integrates every accepted decision
            exactly once, keeps unresolved decisions in an 'Open decisions'
            section, and deletes no unaffected source line.

Question bounds come from the decision-question engine (#5408): this module
composes that engine and does not copy its option, recommendation, hold, or
dependency rules.

Exit codes: 0 = ok, 1 = logic failure (invalid ledger, incomplete question,
failed verification), 2 = configuration error (unreadable file, missing
decision-question engine).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from audit_check import ledger_problems, load_decision_question, plan_questions
from audit_verify import verify_rebuild

EXIT_OK = 0
EXIT_LOGIC = 1
EXIT_CONFIG = 2


def _read_json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def run_check(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    dq = load_decision_question()
    source_lines = Path(args.source).read_text(encoding="utf-8").splitlines()
    ledger = _read_json(args.ledger)
    root = Path(args.repo_root).resolve()
    candidates, problems = ledger_problems(ledger, source_lines, root)
    if problems:
        return {"status": "invalid", "problems": problems}, EXIT_LOGIC
    max_options = args.max_options or dq.MAX_PRESENTED_OPTIONS
    max_questions = args.max_questions or dq.MAX_QUESTIONS_PER_CALL
    result = plan_questions(candidates, ledger, max_options, max_questions)
    return result, EXIT_LOGIC if result["status"] in (
        "incomplete",
        "revise_recommendation",
    ) else EXIT_OK


def run_verify(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    source = Path(args.source).read_text(encoding="utf-8")
    rebuilt = Path(args.rebuilt).read_text(encoding="utf-8")
    ledger = _read_json(args.ledger)
    candidates, problems = ledger_problems(
        ledger, source.splitlines(), Path(args.repo_root).resolve()
    )
    if problems:
        return {"status": "invalid", "problems": problems}, EXIT_LOGIC
    result = verify_rebuild(candidates, _read_json(args.log), source, rebuilt)
    return result, EXIT_OK if result["status"] == "verified" else EXIT_LOGIC


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("check", "verify"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--source", required=True, help="Path to the specification.")
        cmd.add_argument("--ledger", required=True, help="Path to the coverage ledger JSON.")
        cmd.add_argument("--repo-root", default=".", help="Root for codebase evidence paths.")
    check = sub.choices["check"]
    check.add_argument(
        "--max-options", type=int, default=0, help="Options per prompt (default: engine)."
    )
    check.add_argument(
        "--max-questions", type=int, default=0, help="Questions per call (default: engine)."
    )
    verify = sub.choices["verify"]
    verify.add_argument("--log", required=True, help="Decision log JSON keyed by question ID.")
    verify.add_argument("--rebuilt", required=True, help="Path to the rebuilt specification.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result, code = (run_check if args.command == "check" else run_verify)(args)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    except (OSError, KeyError, TypeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONFIG if isinstance(exc, OSError) else EXIT_LOGIC
    print(json.dumps(result, indent=2))
    return code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
