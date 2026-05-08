#!/usr/bin/env python3
"""Run the /pr-review completion gate against a pull request.

Reads completion_criteria from a config YAML, dispatches each criterion's
verification command, parses the resulting JSON, and evaluates the
``pass_when`` expression. Prints a per-criterion result table. Exits 0 if
every criterion passes, 1 if any criterion fails.

This replaces the prior narrative completion gate where the agent claimed
verdicts like "0 unresolved threads". Each verdict is now produced by an
external command whose JSON output IS the source of truth. The script
dispatches; it does not narrate.

The ``pass_when`` mini-DSL supports:

  * dotted path access:        ``stdout-json.unresolved_count``
  * literals:                  integers, ``true``, ``false``, ``null``,
                               and double-quoted strings
  * comparison operators:      ``==``, ``!=``
  * boolean composition:       ``AND``, ``OR`` (left-to-right; no parens)

The ``stdout-json`` prefix denotes the parsed JSON object on the
command's stdout. Any other dotted prefix is treated as a literal lookup
into the same object (so ``stdout-json.x`` and ``x`` are equivalent).

Each criterion may set ``fail_open: true`` to treat dispatch errors
(non-zero exit, non-JSON stdout) as a pass. Default is ``fail_open:
false``: if the command misbehaves, the criterion fails closed. This
matches the retrospective's "Reporting-Without-Acting Anti-Pattern"
guidance: a verifier that cannot verify must not be silently treated as
having verified.

If the DSL is insufficient, a criterion may instead specify
``pass_when_python: "lambda d: <expr>"``. The expression receives the
parsed stdout-json dict and must return a truthy/falsy value. This is
provided as an escape hatch when a criterion's logic does not fit the
DSL; prefer ``pass_when`` where possible.

Exit codes follow ADR-035:
    0 - All criteria passed
    1 - At least one criterion failed (or had an evaluation error)
    2 - Config/usage error (config missing, malformed, or no criteria)
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

# stdlib YAML loader is not available; we use a tiny inline loader for the
# narrow shape we need. PyYAML is preferred when present (matches the rest
# of the codebase), but standard library only is the contract for this
# script. The loader handles enough of YAML to parse pr-review-config.yaml.
try:
    import yaml  # type: ignore[import-untyped]
    _HAVE_YAML = True
except ImportError:  # pragma: no cover - exercised when PyYAML missing
    yaml = None  # type: ignore[assignment]
    _HAVE_YAML = False


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------


_DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parents[4] / "commands" / "pr-review-config.yaml"
)


def _load_config(path: Path) -> dict:
    """Load a YAML config file. Raises on parse failure or missing file."""
    if not path.is_file():
        raise FileNotFoundError(f"Config file not found: {path}")

    text = path.read_text(encoding="utf-8")

    if _HAVE_YAML:
        data = yaml.safe_load(text)  # type: ignore[union-attr]
        if not isinstance(data, dict):
            raise ValueError(
                f"Config root must be a mapping, got {type(data).__name__}"
            )
        return data

    raise RuntimeError(
        "PyYAML is required to parse the completion-gate config; "
        "install it via `pip install pyyaml`."
    )


# ---------------------------------------------------------------------------
# pass_when DSL
# ---------------------------------------------------------------------------


def _resolve_path(data: dict, path: str) -> Any:
    """Resolve a dotted path against a parsed-stdout dict.

    The leading segment may be ``stdout-json`` (or absent); both refer to
    the dict itself. Returns ``None`` if any segment is missing, so the
    caller can compare against ``null`` literals.
    """
    segments = path.split(".")
    if segments and segments[0] == "stdout-json":
        segments = segments[1:]

    cur: Any = data
    for seg in segments:
        if isinstance(cur, dict) and seg in cur:
            cur = cur[seg]
        else:
            return None
    return cur


def _parse_literal(token: str) -> Any:
    """Parse a single DSL literal: int, bool, null, or quoted string."""
    if token == "true":
        return True
    if token == "false":
        return False
    if token == "null":
        return None
    if (
        len(token) >= 2
        and token[0] == '"'
        and token[-1] == '"'
    ):
        return token[1:-1]
    try:
        return int(token)
    except ValueError as exc:
        raise ValueError(f"Unrecognized literal in pass_when: {token!r}") from exc


def _eval_atom(data: dict, atom: list[str]) -> bool:
    """Evaluate a 3-token atom: ``<path> <op> <literal>``."""
    if len(atom) != 3:
        raise ValueError(
            f"pass_when atom must have 3 tokens, got {atom!r}"
        )
    path, op, literal_tok = atom
    actual = _resolve_path(data, path)
    expected = _parse_literal(literal_tok)
    if op == "==":
        return actual == expected
    if op == "!=":
        return actual != expected
    raise ValueError(f"Unsupported pass_when operator: {op!r}")


def _eval_pass_when(data: dict, expr: str) -> bool:
    """Evaluate a pass_when expression against parsed stdout-json data.

    Tokens are split on whitespace (literals must not contain spaces).
    Atoms are joined left-to-right with ``AND`` / ``OR`` connectives;
    AND and OR have equal precedence and evaluate strictly in order
    (no parentheses). Short-circuiting follows the connective.
    """
    tokens = expr.split()
    if not tokens:
        raise ValueError("pass_when expression is empty")

    result: bool | None = None
    pending_op: str | None = None
    i = 0
    while i < len(tokens):
        atom = tokens[i:i + 3]
        i += 3
        atom_value = _eval_atom(data, atom)

        if result is None:
            result = atom_value
        elif pending_op == "AND":
            result = result and atom_value
        elif pending_op == "OR":
            result = result or atom_value
        else:
            raise ValueError(
                f"Missing AND/OR connective before atom {atom!r}"
            )

        if i >= len(tokens):
            break

        pending_op = tokens[i]
        if pending_op not in ("AND", "OR"):
            raise ValueError(
                f"Expected AND/OR, got {pending_op!r}"
            )
        i += 1

    return bool(result)


def _eval_pass_when_python(data: dict, expr: str) -> bool:
    """Evaluate a pass_when_python expression. Escape hatch only.

    The expression must be a single ``lambda d: ...`` form. The lambda
    receives the parsed stdout-json dict.
    """
    expr = expr.strip()
    if not expr.startswith("lambda"):
        raise ValueError(
            "pass_when_python must be a lambda expression"
        )
    func = eval(expr, {"__builtins__": {}}, {})  # noqa: S307
    if not callable(func):
        raise ValueError("pass_when_python did not yield a callable")
    return bool(func(data))


# ---------------------------------------------------------------------------
# Criterion dispatch
# ---------------------------------------------------------------------------


def _format_command(template: str, pr_number: int) -> list[str]:
    """Render a command template with ``{pr}`` substitution and split it."""
    rendered = template.replace("{pr}", str(pr_number))
    return shlex.split(rendered)


def _parse_stdout_json(stdout: str) -> dict | None:
    """Return parsed JSON dict from stdout or None if unparseable."""
    text = stdout.strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict):
        return parsed
    return None


def _evaluate_criterion(criterion: dict, pr_number: int) -> dict:
    """Run one criterion's command and evaluate its pass_when expression.

    Returns a dict with: name, passed (bool), reason (str), command (str),
    exit_code (int|None), parsed (bool).
    """
    name = criterion.get("name", "<unnamed>")
    verification = criterion.get("verification", "command")
    fail_open = bool(criterion.get("fail_open", False))

    result: dict = {
        "name": name,
        "passed": False,
        "reason": "",
        "command": "",
        "exit_code": None,
        "parsed": False,
    }

    if verification != "command":
        result["reason"] = (
            f"unsupported verification kind: {verification!r}"
        )
        return result

    cmd_template = criterion.get("command", "")
    if not cmd_template:
        result["reason"] = "criterion has no command"
        return result

    argv = _format_command(cmd_template, pr_number)
    result["command"] = " ".join(argv)

    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        result["reason"] = f"command failed to run: {exc}"
        result["passed"] = fail_open
        return result

    result["exit_code"] = proc.returncode
    parsed = _parse_stdout_json(proc.stdout)
    if parsed is None:
        result["reason"] = (
            f"command stdout is not a JSON object "
            f"(exit={proc.returncode}); fail_open={fail_open}"
        )
        result["passed"] = fail_open
        return result

    result["parsed"] = True

    pass_when = criterion.get("pass_when")
    pass_when_python = criterion.get("pass_when_python")
    try:
        if pass_when_python:
            verdict = _eval_pass_when_python(parsed, pass_when_python)
        elif pass_when:
            verdict = _eval_pass_when(parsed, pass_when)
        else:
            result["reason"] = "criterion has no pass_when expression"
            return result
    except (ValueError, SyntaxError, TypeError, KeyError, NameError, AttributeError) as exc:
        result["reason"] = f"pass_when error: {exc}; fail_open={fail_open}"
        result["passed"] = fail_open
        return result

    result["passed"] = verdict
    if not verdict:
        result["reason"] = (
            f"pass_when evaluated false; stdout-json keys: "
            f"{sorted(parsed.keys())}"
        )
    return result


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _print_table(rows: list[dict]) -> None:
    """Print a per-criterion result table to stdout."""
    print()
    print("Completion Gate Results")
    print("=" * 60)
    print(f"{'PASS':<6} {'CRITERION':<48}")
    print("-" * 60)
    for row in rows:
        marker = "PASS" if row["passed"] else "FAIL"
        print(f"{marker:<6} {row['name']:<48}")
        if not row["passed"] and row["reason"]:
            print(f"       reason: {row['reason']}")
    print("-" * 60)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the /pr-review completion gate.",
    )
    parser.add_argument(
        "--config",
        default=str(_DEFAULT_CONFIG_PATH),
        help="Path to pr-review-config.yaml",
    )
    parser.add_argument(
        "--pull-request",
        type=int,
        required=True,
        help="Pull request number",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a single JSON object rather than the human table",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.pull_request <= 0:
        print("Pull request number must be positive.", file=sys.stderr)
        return 2

    config_path = Path(args.config)
    try:
        config = _load_config(config_path)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"Failed to load config {config_path}: {exc}", file=sys.stderr)
        return 2

    criteria = config.get("completion_criteria")
    if not criteria:
        print("No completion_criteria in config", file=sys.stderr)
        return 2

    rows: list[dict] = []
    for criterion in criteria:
        if not isinstance(criterion, dict):
            rows.append(
                {
                    "name": "<malformed>",
                    "passed": False,
                    "reason": f"criterion is not a mapping: {criterion!r}",
                    "command": "",
                    "exit_code": None,
                    "parsed": False,
                }
            )
            continue
        rows.append(_evaluate_criterion(criterion, args.pull_request))

    if args.json:
        print(
            json.dumps(
                {
                    "pull_request": args.pull_request,
                    "all_passed": all(r["passed"] for r in rows),
                    "criteria": rows,
                },
                indent=2,
            )
        )
    else:
        _print_table(rows)

    return 0 if all(r["passed"] for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
