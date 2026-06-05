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
parsed stdout-json dict and must return a truthy/falsy value. The
lambda is parsed with ``ast`` and evaluated through a safe subset
(boolean composition, comparisons, constants, and ``d.get(...)``
lookups); arbitrary Python does NOT run. Prefer ``pass_when`` where
possible.

Trust model
-----------

This dispatcher executes ``command`` strings read from the YAML config.
The config path MUST be controlled by the repository, never
user-supplied beyond the validated default. Path traversal protection:
``--config`` is canonicalised and rejected unless it lives under the
repository root via
``scripts.utils.path_validation.validate_safe_path``. The
``pass_when_python`` evaluator no longer calls ``eval``: it parses the
lambda with ``ast`` and walks a whitelisted node set, so a config
expression cannot reach Python's class hierarchy or any builtin. This
closes the arbitrary-code-execution surface the prior ``eval``-based
evaluator carried on PR-branch configs (see below).

PR-branch trust boundary
~~~~~~~~~~~~~~~~~~~~~~~~

When the dispatcher is invoked by ``/pr-review`` after checking out a
PR branch (via ``gh pr checkout``), the config it reads is the PR
branch's copy of ``pr-review-config.yaml`` -- NOT the trusted version
on ``main``. A malicious PR can still edit ``completion_criteria.command``
to execute arbitrary code on the reviewer's machine via the dispatched
subprocess. ``validate_safe_path`` keeps the file inside the repo; it
does NOT make the file trusted. The ``pass_when_python`` path is no
longer part of that surface now that it runs through the AST evaluator
rather than ``eval``.

This is the same trust the reviewer extends by running tests or
linters on a PR branch, but the surface here is more direct: the
dispatcher *will* run whatever command appears in the config.
Reviewers SHOULD inspect any change to ``pr-review-config.yaml`` in
the PR diff before invoking ``/pr-review`` on it. A future hardening
(see CodeRabbit review on PR #1898) is to load the config from a
trusted source (e.g. ``git show main:...``) instead of the working
tree, or to refuse to run if the working-tree config diverges from
``main``. Both options are deferred as follow-up work because they
require restructuring the workflow's config-resolution path.

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
import ast
import json
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

# Resolve the project root by walking up to find the ``scripts/``
# package. A fixed ``parents[N]`` index works for the canonical
# ``.claude/skills/.../pr/`` location but breaks for the
# ``src/copilot-cli/skills/.../pr/`` mirror (one extra ``src/`` level)
# and would break again for any future deployed install. The walk
# resolves the right root regardless of where the script lives.
def _resolve_project_root() -> Path:
    here = Path(__file__).resolve().parent
    for ancestor in (here, *here.parents):
        if (ancestor / "scripts" / "utils" / "path_validation.py").is_file():
            return ancestor
    # Fall back to the original heuristic if the marker is missing
    # (e.g. when the script is bundled without the scripts/ tree).
    return Path(__file__).resolve().parents[4]


_PROJECT_ROOT = _resolve_project_root()
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
        # Per Copilot review: a trailing connective with no atom after
        # it (e.g. ``x == 1 AND``) silently passed before because the
        # outer loop checked ``i < len(tokens)`` only at the top. Catch
        # it explicitly: an AND/OR must be followed by another atom.
        if i >= len(tokens):
            raise ValueError(
                f"pass_when ends with dangling connective {pending_op!r}",
            )

    return bool(result)


# Comparison-operator AST node -> Python operation. Only these
# comparison forms are permitted in a pass_when_python lambda.
_COMPARE_OPS: dict[type[ast.cmpop], Any] = {
    ast.Eq: lambda a, b: a == b,
    ast.NotEq: lambda a, b: a != b,
    ast.Is: lambda a, b: a is b,
    ast.IsNot: lambda a, b: a is not b,
    ast.Lt: lambda a, b: a < b,
    ast.LtE: lambda a, b: a <= b,
    ast.Gt: lambda a, b: a > b,
    ast.GtE: lambda a, b: a >= b,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
}


class _UnsafeExpression(ValueError):
    """A pass_when_python lambda used a construct outside the safe subset."""


def _parse_pass_when_python(expr: str) -> ast.Lambda:
    """Parse and structurally validate a pass_when_python lambda.

    Returns the ``ast.Lambda`` node for a single ``lambda <param>: <body>``
    form. Raises ``ValueError`` on any malformed or non-lambda input so the
    caller fails closed.
    """
    if not isinstance(expr, str):
        raise ValueError("pass_when_python must be a string")
    expr = expr.strip()
    if not expr.startswith("lambda"):
        raise ValueError("pass_when_python must be a lambda expression")
    if "\n" in expr or "\r" in expr:
        raise ValueError("pass_when_python must be a single line")
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"pass_when_python is not valid Python: {exc}") from exc
    node = tree.body
    if not isinstance(node, ast.Lambda):
        raise ValueError("pass_when_python must be a lambda expression")
    args = node.args
    if (
        len(args.args) != 1
        or args.vararg is not None
        or args.kwarg is not None
        or args.kwonlyargs
        or args.posonlyargs
        or args.defaults
    ):
        raise ValueError(
            "pass_when_python lambda must take exactly one positional argument",
        )
    return node


def _eval_node(node: ast.AST, param_name: str, data: dict) -> Any:
    """Evaluate one whitelisted AST node against the bound ``data`` dict.

    Supports the closed set a completion criterion needs: boolean
    composition (``and``/``or``), ``not``, comparisons (including ``is`` and
    ``in``), constants, tuple/list membership operands, the single lambda
    parameter (which resolves to ``data``), and ``<param>.get(key[, default])``
    lookups. Any other node raises ``_UnsafeExpression`` so an unexpected
    construct fails closed instead of executing.
    """
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            result: Any = True
            for value in node.values:
                result = _eval_node(value, param_name, data)
                if not result:
                    return result
            return result
        if isinstance(node.op, ast.Or):
            result: Any = False
            for value in node.values:
                result = _eval_node(value, param_name, data)
                if result:
                    return result
            return result
        raise _UnsafeExpression(f"unsupported boolean op: {type(node.op).__name__}")
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not _eval_node(node.operand, param_name, data)
    if isinstance(node, ast.Compare):
        return _eval_compare(node, param_name, data)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id != param_name:
            raise _UnsafeExpression(f"unknown name: {node.id}")
        return data
    if isinstance(node, (ast.Tuple, ast.List)):
        return [_eval_node(elt, param_name, data) for elt in node.elts]
    if isinstance(node, ast.Call):
        return _eval_call(node, param_name, data)
    raise _UnsafeExpression(f"unsupported expression node: {type(node).__name__}")


def _eval_compare(node: ast.Compare, param_name: str, data: dict) -> bool:
    """Evaluate a (possibly chained) comparison against the safe op table."""
    left = _eval_node(node.left, param_name, data)
    result = True
    for op, comparator in zip(node.ops, node.comparators):
        op_fn = _COMPARE_OPS.get(type(op))
        if op_fn is None:
            raise _UnsafeExpression(
                f"unsupported comparison op: {type(op).__name__}",
            )
        right = _eval_node(comparator, param_name, data)
        if not op_fn(left, right):
            return False
        left = right
    return result


def _eval_call(node: ast.Call, param_name: str, data: dict) -> Any:
    """Evaluate the only permitted call form: ``<param>.get(key[, default])``."""
    func = node.func
    if not (
        isinstance(func, ast.Attribute)
        and func.attr == "get"
        and isinstance(func.value, ast.Name)
        and func.value.id == param_name
    ):
        raise _UnsafeExpression(
            "only <param>.get(...) calls are allowed in pass_when_python",
        )
    if node.keywords or not 1 <= len(node.args) <= 2:
        raise _UnsafeExpression(
            "<param>.get(...) takes one or two positional arguments",
        )
    key = _eval_node(node.args[0], param_name, data)
    default = (
        _eval_node(node.args[1], param_name, data)
        if len(node.args) == 2
        else None
    )
    if not isinstance(data, dict):
        return default
    return data.get(key, default)


def _eval_pass_when_python(data: dict, expr: str) -> bool:
    """Evaluate a pass_when_python expression via a safe AST walk.

    The expression must be a single ``lambda d: ...`` form. The lambda
    receives the parsed stdout-json dict and is evaluated through
    ``_eval_node``, which accepts only a whitelisted node set (boolean
    composition, comparisons, constants, membership operands, the single
    parameter, and ``<param>.get(...)`` lookups). ``eval`` is never called,
    so a config expression cannot reach builtins or the class hierarchy.
    Any out-of-subset construct raises and the caller fails closed.
    """
    node = _parse_pass_when_python(expr)
    param_name = node.args.args[0].arg
    return bool(_eval_node(node.body, param_name, data))


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
      * ``command`` must be a non-empty string. Bot review feedback:
        if YAML parses ``command`` as a list (e.g. due to indentation),
        ``_format_command`` would crash later; catch the type error here.
      * ``fail_open``, when present, must be a real bool. Truthy
        non-bools (``"yes"``, ``1``) silently change gate behavior;
        reject them at schema time.
      * Exactly one of ``pass_when`` / ``pass_when_python`` must be set.
    """
    if not isinstance(criterion, dict):
        raise ConfigError(f"criterion is not a mapping: {criterion!r}")

    # Per Copilot review: presence-with-default lets a missing or
    # wrong-typed ``name``/``verification`` slip through. Require them
    # explicitly and type-check ``name`` so the validator and the
    # dispatcher reject the same configs.
    if "name" not in criterion:
        raise ConfigError("criterion missing required field: name")
    name = criterion["name"]
    if not isinstance(name, str) or not name.strip():
        raise ConfigError(
            f"criterion: name must be a non-empty string "
            f"(got {type(name).__name__})",
        )
    if "verification" not in criterion:
        raise ConfigError(
            f"criterion {name!r}: missing required field: verification",
        )
    verification = criterion["verification"]
    if verification != "command":
        raise ConfigError(
            f"criterion {name!r}: unsupported verification kind "
            f"{verification!r} (expected 'command')",
        )
    cmd_template = criterion.get("command", "")
    if not isinstance(cmd_template, str) or not cmd_template:
        raise ConfigError(
            f"criterion {name!r}: command must be a non-empty string "
            f"(got {type(cmd_template).__name__})",
        )
    if "fail_open" in criterion and not isinstance(criterion["fail_open"], bool):
        raise ConfigError(
            f"criterion {name!r}: fail_open must be a boolean "
            f"(got {type(criterion['fail_open']).__name__})",
        )

    pass_when = criterion.get("pass_when")
    pass_when_python = criterion.get("pass_when_python")
    # Type-check both expression fields when present. The validator
    # already does this; mirror it here so a config that bypasses
    # the standalone validator (direct dispatcher invocation) cannot
    # smuggle a non-string into the eval/DSL paths.
    for field, value in (
        ("pass_when", pass_when),
        ("pass_when_python", pass_when_python),
    ):
        if field in criterion and (
            not isinstance(value, str) or not value.strip()
        ):
            raise ConfigError(
                f"criterion {name!r}: {field} must be a non-empty string "
                f"(got {type(value).__name__})",
            )
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
    # Schema check above already proved this is a real bool (or absent);
    # no permissive truthiness coercion here.
    fail_open = criterion.get("fail_open", False)

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
    except Exception as exc:  # noqa: BLE001
        # A broken pass_when expression is a config bug, not a verifier
        # outage. fail_open does NOT apply: masking a typo with a
        # green gate would defeat the dispatcher's purpose.
        #
        # Catching ``Exception`` (broad) is intentional: a
        # ``pass_when_python`` lambda body can raise anything
        # (``ZeroDivisionError``, ``IndexError``, custom domain
        # exceptions). Per CodeRabbit review, the prior tight-list
        # catch (ValueError, KeyError, ...) let those leak through.
        # ``KeyboardInterrupt`` and ``SystemExit`` are NOT caught
        # because they inherit from ``BaseException``.
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
    """Print a per-criterion result table to stdout.

    For failing rows, also prints the verifier's command and a short
    excerpt of stdout/stderr so the operator can triage without re-running
    the verifier separately. Per CodeRabbit review feedback: an operator
    reading the table should see the same evidence the JSON consumer sees.
    """
    print()
    print("Completion Gate Results")
    print("=" * 60)
    print(f"{'PASS':<6} {'CRITERION':<48}")
    print("-" * 60)
    for row in rows:
        marker = "PASS" if row["passed"] else "FAIL"
        print(f"{marker:<6} {row['name']:<48}")
        if not row["passed"]:
            if row.get("reason"):
                print(f"       reason: {row['reason']}")
            if row.get("command"):
                print(f"       command: {row['command']}")
            stdout_excerpt = (row.get("stdout") or "").strip()
            if stdout_excerpt:
                excerpt = stdout_excerpt.splitlines()[0][:200]
                print(f"       stdout: {excerpt}")
            stderr_excerpt = (row.get("stderr") or "").strip()
            if stderr_excerpt:
                excerpt = stderr_excerpt.splitlines()[0][:200]
                print(f"       stderr: {excerpt}")
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
