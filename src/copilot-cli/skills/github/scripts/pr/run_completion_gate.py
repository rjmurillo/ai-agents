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

Trust model
-----------

This dispatcher executes ``command`` strings and ``pass_when_python``
lambdas read from the YAML config. The config path MUST be controlled
by the repository, never user-supplied beyond the validated default.
Path traversal protection: ``--config`` is canonicalised and rejected
unless it lives under the repository root via
``scripts.utils.path_validation.validate_safe_path``. The
``pass_when_python`` evaluator runs ``eval`` with an empty
``__builtins__`` dict; this is NOT a sandbox (Python's class hierarchy
remains reachable) and is only acceptable because the config is
in-repo, in-tree, and reviewed alongside this script. Do not extend
this dispatcher to load config from network input or user-supplied
absolute paths.

Substitution
------------

Only ``{pr}`` is substituted into ``command`` templates, and the
substituted value is the integer ``--pull-request`` argument validated
by argparse (``type=int``) plus a positivity check. Other ``{...}``
slots present in the surrounding ``pr-review-config.yaml`` (for
example ``{thread_id}`` or ``{body}`` in the thread-resolution scripts)
belong to other consumers and are not handled here. Future maintainers
extending this dispatcher must re-validate every new slot they add.

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

# Resolve the project root so ``scripts.utils.path_validation`` is
# importable. The dispatcher lives at
# ``<repo>/src/copilot-cli/skills/github/scripts/pr/run_completion_gate.py``,
# so ``parents[5]`` (i.e. six levels up from the file) is the repo
# root. The same lookup pattern is used by other Python scripts in the
# repo (e.g. validate_pr_review_config.py at scripts/, which uses
# ``parent.parent``).
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parents[5]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.utils.path_validation import validate_safe_path  # noqa: E402

# PyYAML is a hard dependency for this script. The rest of the codebase
# already requires PyYAML; matching that is simpler than maintaining a
# stdlib-only loader and avoids the schema-drift risk of a partial parser.
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
    _PROJECT_ROOT / ".claude" / "commands" / "pr-review-config.yaml"
)


class ConfigError(Exception):
    """Schema or load error in the completion-gate config.

    Raised by :func:`_load_config` and :func:`_evaluate_criterion` to
    distinguish a config bug (which the dispatcher exits 2 for, per
    ADR-035) from a criterion that legitimately failed (exit 1).
    """


def _load_config(path: Path) -> dict:
    """Load a YAML config file. Raises ConfigError on any failure mode."""
    if not path.is_file():
        raise ConfigError(f"Config file not found: {path}")
    if not _HAVE_YAML:
        raise ConfigError(
            "PyYAML is required to parse the completion-gate config; "
            "install it via `pip install pyyaml`.",
        )
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"Cannot read config {path}: {exc}") from exc
    try:
        data = yaml.safe_load(text)  # type: ignore[union-attr]
    except yaml.YAMLError as exc:  # type: ignore[union-attr]
        raise ConfigError(f"Cannot parse config {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(
            f"Config root must be a mapping, got {type(data).__name__}",
        )
    return data


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

    Tokens are split with ``shlex.split(posix=False)`` so double-quoted
    string literals stay intact (``"PR merged"`` remains one token, not
    two). Atoms are joined left-to-right with ``AND`` / ``OR``
    connectives; AND and OR have equal precedence and evaluate strictly
    in order (no parentheses). Atoms are pure dict lookups, so the
    evaluation order does not affect correctness.
    """
    try:
        tokens = shlex.split(expr, posix=False)
    except ValueError as exc:
        raise ValueError(f"pass_when tokenization failed: {exc}") from exc
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

    Security: this function calls ``eval``. The empty ``__builtins__``
    dict does NOT sandbox the expression (Python's class hierarchy is
    still reachable). The trust model lives in the module docstring:
    the config that supplies ``expr`` MUST be repo-controlled. Reject
    obviously malformed expressions before eval to keep the surface
    visible to maintainers.
    """
    if not isinstance(expr, str):
        raise ValueError("pass_when_python must be a string")
    expr = expr.strip()
    if not expr.startswith("lambda"):
        raise ValueError(
            "pass_when_python must be a lambda expression"
        )
    if "\n" in expr or "\r" in expr:
        raise ValueError("pass_when_python must be a single line")
    func = eval(expr, {"__builtins__": {}}, {})  # noqa: S307
    if not callable(func):
        raise ValueError("pass_when_python did not yield a callable")
    return bool(func(data))


# ---------------------------------------------------------------------------
# Criterion dispatch
# ---------------------------------------------------------------------------


def _format_command(template: str, pr_number: int) -> list[str]:
    """Render a command template with ``{pr}`` substitution and split it.

    ``pr_number`` MUST be an int. The CLI is the only validated entry
    point: argparse coerces ``--pull-request`` to int and ``main``
    rejects non-positive values before this function is reached. This
    assertion documents that contract for any future caller and
    forecloses CWE-78 via stringly-typed PR identifiers.
    """
    if not isinstance(pr_number, int) or isinstance(pr_number, bool):
        raise TypeError(f"pr_number must be int, got {type(pr_number).__name__}")
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


def _validate_criterion_schema(criterion: dict) -> tuple[str, str, str | None, str | None]:
    """Schema-check one criterion. Raises ConfigError on any violation.

    Returns ``(name, command, pass_when, pass_when_python)``.

    Schema rules (mirror scripts/validate_pr_review_config.py):
      * ``verification`` must be ``"command"`` (only kind supported).
      * ``command`` must be a non-empty string.
      * Exactly one of ``pass_when`` / ``pass_when_python`` must be set
        (Copilot review feedback: both-set is ambiguous).
    """
    if not isinstance(criterion, dict):
        raise ConfigError(f"criterion is not a mapping: {criterion!r}")

    name = criterion.get("name", "<unnamed>")
    verification = criterion.get("verification", "command")
    if verification != "command":
        raise ConfigError(
            f"criterion {name!r}: unsupported verification kind "
            f"{verification!r} (expected 'command')",
        )
    cmd_template = criterion.get("command", "")
    if not cmd_template:
        raise ConfigError(f"criterion {name!r}: missing command")

    pass_when = criterion.get("pass_when")
    pass_when_python = criterion.get("pass_when_python")
    if pass_when and pass_when_python:
        raise ConfigError(
            f"criterion {name!r}: pass_when and pass_when_python are "
            f"mutually exclusive; specify exactly one",
        )
    if not pass_when and not pass_when_python:
        raise ConfigError(
            f"criterion {name!r}: missing pass_when or pass_when_python",
        )
    return name, cmd_template, pass_when, pass_when_python


def _evaluate_criterion(criterion: dict, pr_number: int) -> dict:
    """Run one criterion's command and evaluate its pass_when expression.

    Returns a dict with: name, passed (bool), reason (str), command (str),
    exit_code (int|None), parsed (bool), stdout (str), stderr (str).

    Raises :class:`ConfigError` on any schema violation; the caller
    (``main``) translates that to exit 2 per ADR-035. Once the schema
    check passes, the function never raises: command failures, malformed
    output, and broken pass_when expressions are all reported as a
    failed criterion (with ``fail_open`` honored where applicable).

    Failure semantics:
      * Command not found / timeout / non-zero exit -> dispatch error;
        ``passed = fail_open``.
      * Stdout is not a JSON object -> dispatch error;
        ``passed = fail_open``.
      * pass_when raises (DSL syntax error, bad literal, broken lambda)
        -> evaluator failure; ``passed = False`` regardless of
        ``fail_open``. A verifier that ran successfully but whose
        contract cannot be evaluated is a config bug, not a verifier
        outage; masking it with ``fail_open`` would let a typo silently
        green the gate.
    """
    name, cmd_template, pass_when, pass_when_python = _validate_criterion_schema(criterion)
    fail_open = bool(criterion.get("fail_open", False))

    result: dict = {
        "name": name,
        "passed": False,
        "reason": "",
        "command": "",
        "exit_code": None,
        "parsed": False,
        "stdout": "",
        "stderr": "",
    }

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
    result["stdout"] = proc.stdout
    result["stderr"] = proc.stderr

    if proc.returncode != 0:
        result["reason"] = (
            f"command exited non-zero ({proc.returncode}); "
            f"fail_open={fail_open}; stderr={proc.stderr.strip()[:200]!r}"
        )
        result["passed"] = fail_open
        return result

    parsed = _parse_stdout_json(proc.stdout)
    if parsed is None:
        result["reason"] = (
            f"command stdout is not a JSON object; fail_open={fail_open}"
        )
        result["passed"] = fail_open
        return result

    result["parsed"] = True

    try:
        if pass_when_python:
            verdict = _eval_pass_when_python(parsed, pass_when_python)
        else:
            verdict = _eval_pass_when(parsed, pass_when)
    except (ValueError, SyntaxError, TypeError, KeyError, NameError, AttributeError) as exc:
        # A broken pass_when expression is a config bug, not a verifier
        # outage. fail_open does NOT apply: masking a typo with a
        # green gate would defeat the dispatcher's purpose.
        result["reason"] = f"pass_when error (fails closed): {exc}"
        result["passed"] = False
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

    try:
        config_path = validate_safe_path(args.config, _PROJECT_ROOT)
    except (FileNotFoundError, ValueError) as exc:
        print(
            f"Refusing to load config from unsafe path {args.config!r}: {exc}",
            file=sys.stderr,
        )
        return 2

    try:
        config = _load_config(config_path)
    except ConfigError as exc:
        print(f"Failed to load config {config_path}: {exc}", file=sys.stderr)
        return 2

    criteria = config.get("completion_criteria")
    # Reject anything other than a list. The previous ``if not criteria``
    # accepted a dict that is non-empty, which would silently iterate the
    # dict's keys (CodeRabbit review feedback).
    if not isinstance(criteria, list):
        print(
            f"completion_criteria must be a list, got "
            f"{type(criteria).__name__}",
            file=sys.stderr,
        )
        return 2
    if not criteria:
        print("No completion_criteria in config", file=sys.stderr)
        return 2

    rows: list[dict] = []
    try:
        for criterion in criteria:
            rows.append(_evaluate_criterion(criterion, args.pull_request))
    except ConfigError as exc:
        # Schema bug in a criterion: exit 2 per ADR-035, do not pretend
        # the gate ran. Distinguishes a malformed config from a verifier
        # legitimately reporting failure.
        print(f"Config error in completion_criteria: {exc}", file=sys.stderr)
        return 2

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
