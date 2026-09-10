"""Contract between `pr-autofix.md`'s script calls and its producers' parsers.

Refs #5551. `tests/commands/pr_autofix_field_contract.py` guards the read side:
every `jq` path in the command body has to name a field its producer emits. The
write side had no such guard, and it drifted the same way. The auto-merge disarm
gate passed `--output-format json` to `set_pr_auto_merge.py`, which registers no
such option, so `argparse` exited 2 with `unrecognized arguments` before the
mutation ran.

An unrecognized flag is worse than a missing field, because it fails the call
outright rather than returning a sentinel. The disarm gate's failure branch then
skipped the pull request and printed "skipping to avoid unguarded merge" while
auto-merge stayed armed, which is the state the gate exists to remove.

The extractor binds each long option to the script it was passed to, then checks
it against the options that script's `add_argument` calls register. Deriving the
accepted set statically keeps the check honest without importing a producer,
which would run its `sys.path` bootstrap and its authentication preflight.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from tests.commands.pr_autofix_field_parser import (
    COMMAND_PATH,
    MIRROR_PATH,
    logical_lines,
)

__all__ = [
    "COMMAND_PATH",
    "MIRROR_PATH",
    "FlagUse",
    "derive_accepted_flags",
    "extract_flag_uses",
    "extract_invocations",
    "flag_violations",
    "script_reference_lines",
]

REPO_ROOT = Path(__file__).resolve().parents[2]
# `SCRIPTS_DIR` is rebound inside the command body: line 62 points it at the
# shared `utils` directory for the transport preflight, and every later block
# re-resolves it to the `pr` directory. Both are searched, in that resolution
# order, so a script name is looked up where the body would find it.
SCRIPT_DIRS = (
    REPO_ROOT / ".claude" / "skills" / "github" / "scripts" / "pr",
    REPO_ROOT / ".claude" / "skills" / "github" / "scripts" / "utils",
)
# Shared library the producers import. `add_output_format_arg` lives here and
# registers `--output-format` on nine of the thirteen producers the command body
# calls, so a derivation that read only `add_argument` calls in the script would
# report every one of those nine as a violation.
SHARED_LIB_DIR = REPO_ROOT / ".claude" / "lib" / "github_core"

_INVOKE = re.compile(r"\$SCRIPTS_DIR/([A-Za-z0-9_]+)\.py")
# Pipeline and list separators. `||` is listed before `|` so the two-character
# operator wins at a position where both could match.
_SEGMENT = re.compile(r"\|\||&&|[|;)]")
# A long option. The lookbehind rejects the `--` inside a word or a path, and
# requiring an alphanumeric after the dashes rejects the bare `--` terminator.
_LONG_FLAG = re.compile(r"(?<![A-Za-z0-9_./-])--([A-Za-z0-9][A-Za-z0-9-]*)")


@dataclass(frozen=True)
class FlagUse:
    """One long option passed to a producer script in the command body.

    Attributes:
        line: 1-indexed line where the use's logical line starts.
        script: Producer the option was passed to, without the `.py` suffix.
        flag: The option as written, including its leading dashes.
    """

    line: int
    script: str
    flag: str


def extract_invocations(text: str) -> list[tuple[int, str]]:
    """Every `$SCRIPTS_DIR/<script>.py` call in `text`, as (line, script).

    Comment lines are skipped: the body documents alternatives it does not run,
    and a commented call cannot fail at runtime.
    """
    found: list[tuple[int, str]] = []
    for lineno, line in logical_lines(text):
        if line.lstrip().startswith("#"):
            continue
        for segment in _SEGMENT.split(line):
            match = _INVOKE.search(segment)
            if match is not None:
                found.append((lineno, match.group(1)))
    return found


def extract_flag_uses(text: str) -> list[FlagUse]:
    """Extract every long option in `text`, bound to the script it was given to.

    The logical line is split on shell separators first so a `jq` or a second
    producer downstream of a pipe does not donate its options to the producer
    upstream of it. Within a segment only the text after the script token is
    scanned, which keeps an interpreter option such as `python3 -X dev` from
    being read as a producer option.
    """
    uses: list[FlagUse] = []
    for lineno, line in logical_lines(text):
        if line.lstrip().startswith("#"):
            continue
        for segment in _SEGMENT.split(line):
            match = _INVOKE.search(segment)
            if match is None:
                continue
            for flag in _LONG_FLAG.findall(segment[match.end() :]):
                uses.append(FlagUse(line=lineno, script=match.group(1), flag=f"--{flag}"))
    return uses


def _script_path(script: str) -> Path | None:
    for directory in SCRIPT_DIRS:
        candidate = directory / f"{script}.py"
        if candidate.is_file():
            return candidate
    return None


def _literal_flags(node: ast.Call) -> set[str]:
    """Long options registered by one `add_argument` call."""
    return {
        arg.value
        for arg in node.args
        if isinstance(arg, ast.Constant)
        and isinstance(arg.value, str)
        and arg.value.startswith("--")
    }


def _is_add_argument(node: ast.Call) -> bool:
    return isinstance(node.func, ast.Attribute) and node.func.attr == "add_argument"


def _helper_flags(tree: ast.Module) -> dict[str, frozenset[str]]:
    """Map each function in `tree` to the long options its body registers.

    A producer does not always call `add_argument` itself. `get_pr_context.py`
    and eight of its siblings register `--output-format` by handing their parser
    to `add_output_format_arg`, so a derivation that stopped at direct calls
    would judge those options unregistered and report every use of them.
    """
    helpers: dict[str, frozenset[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        flags: set[str] = set()
        for inner in ast.walk(node):
            if isinstance(inner, ast.Call) and _is_add_argument(inner):
                flags |= _literal_flags(inner)
        if flags:
            helpers[node.name] = frozenset(flags)
    return helpers


@cache
def _shared_helper_flags() -> dict[str, frozenset[str]]:
    """Argument-adding helpers exported by the shared `github_core` library."""
    helpers: dict[str, frozenset[str]] = {}
    for module in sorted(SHARED_LIB_DIR.glob("*.py")):
        helpers.update(_helper_flags(ast.parse(module.read_text(encoding="utf-8"))))
    return helpers


@cache
def derive_accepted_flags(script: str) -> frozenset[str] | None:
    """Statically derive the long options `script` registers.

    Returns None when the script is not on disk, which is itself a finding. An
    empty set means the source parsed but registered no long option, so there is
    nothing to compare against and the caller reports nothing.

    Three shapes contribute. A literal `add_argument` call anywhere in the
    module, including one on a mutually exclusive group, which is how
    `set_pr_auto_merge.py` registers `--enable` and `--disable`. A call to a
    helper the script defines itself. A call to a helper the shared library
    defines, which is where `--output-format` comes from.
    """
    path = _script_path(script)
    if path is None:
        return None
    tree = ast.parse(path.read_text(encoding="utf-8"))
    helpers = dict(_shared_helper_flags())
    helpers.update(_helper_flags(tree))
    flags: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _is_add_argument(node):
            flags |= _literal_flags(node)
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if name is not None and name in helpers:
            flags |= helpers[name]
    return frozenset(flags)


def script_reference_lines(text: str) -> list[tuple[int, str]]:
    """Logical lines that name a script under `SCRIPTS_DIR`.

    Exists so a test can assert the extractor reached every one of them. It
    deliberately does not reuse `_INVOKE`: a guard built on the regex it guards
    goes blind in lockstep with it, passes vacuously, and certifies the
    blindness it exists to catch. Matching the two substrings `SCRIPTS_DIR` and
    `.py` is a much weaker claim than parsing the invocation, and that
    independence is the point.

    The five `SCRIPTS_DIR=` assignments in the body carry no `.py`, so they do
    not appear here.
    """
    return [
        (lineno, line)
        for lineno, line in logical_lines(text)
        if not line.lstrip().startswith("#") and "SCRIPTS_DIR" in line and ".py" in line
    ]


def flag_violations(text: str) -> list[str]:
    """Every long option in `text` that its producer's parser would reject."""
    problems: list[str] = []
    for use in extract_flag_uses(text):
        accepted = derive_accepted_flags(use.script)
        if accepted is None:
            problems.append(
                f"line {use.line}: invokes {use.script}.py, which is not in "
                f"{' or '.join(str(d.relative_to(REPO_ROOT)) for d in SCRIPT_DIRS)}. "
                "The call cannot run and its options cannot be checked."
            )
            continue
        if not accepted:
            continue
        if use.flag not in accepted:
            problems.append(
                f"line {use.line}: passes `{use.flag}` to {use.script}.py, which "
                "registers no such option. argparse exits 2 with `unrecognized "
                "arguments`, so the call fails before doing any work. Registered "
                f"options: {', '.join(sorted(accepted))}."
            )
    return problems
