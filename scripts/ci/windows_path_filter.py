#!/usr/bin/env python3
"""Decide which Windows path-contract test files a change reaches (issue #5380).

`test-windows-pwsh` ran on nearly every pull request and always ran every
module that names the `windows_path` marker. A change that reaches none of
those modules, or none of what they read, cannot move the job's verdict. Two
subcommands let the workflow act on that.

`emit` writes a `dorny/paths-filter` document with one key per marked module.
Each key's globs are that module's reach: itself, every tracked file it names,
and a fixed list the whole job depends on. The workflow hands the document to
the action it already uses for `scripts/ci/path_policy.yml`, so the changed-file
list comes from the pull request API and no shell parses it.

`select` reads the action's per-key outputs and writes two `GITHUB_OUTPUT`
lines: `windows-affected` (whether the job starts) and `windows-files` (a JSON
array of the modules to run, empty meaning all of them).

Reach is found by three textual signals: an import that resolves to a tracked
module, a string literal naming a tracked path or a file basename, and a run of
`/` joined literals spelling one. Each resolved Python module is followed the
same way. Directory literals are not expanded: a test that walks a whole tree
reads files no literal names, and expanding a directory pulled in nearly the
whole repository when measured.

Over-matching is the safe direction: it runs one Windows file a change did not
need. Under-matching skips a file a change should have run. The `merge_group`
event, `workflow_dispatch` and pushes to the default branch never narrow, so the
complete set runs before a change settles on `main`. Whole-tree readers rely on
that run. A reach that cannot be computed emits the match-everything key, and
`select` runs everything whenever the action's outputs are missing or unreadable.

Exit codes (AGENTS.md contract): 0 ok, 2 config, 3 external.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import subprocess
import sys
from collections import deque
from collections.abc import Iterable, Mapping
from pathlib import Path, PurePosixPath

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

try:
    from scripts.ci import run_pytest_windows
except ModuleNotFoundError:  # pragma: no cover - exercised via direct file execution
    sys.path.insert(0, str(_PROJECT_ROOT))
    from scripts.ci import run_pytest_windows

MATCH_EVERYTHING = "**"
# The key `emit` writes when the reach cannot be computed. It is not a test
# module, so `select` reads it as "run everything".
FALLBACK_KEY = "__all__"
# dorny/paths-filter adds this output beside the per-filter ones.
_ACTION_SUMMARY_KEY = "changes"

OUTPUT_AFFECTED = "windows-affected"
OUTPUT_FILES = "windows-files"

# Events that run the complete set, so the narrowing never decides what lands.
FULL_RUN_EVENTS = frozenset({"merge_group", "workflow_dispatch"})

EXIT_OK = 0
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3

# What every Windows run depends on without a test naming it: the interpreter
# pin, the dependency lock, pytest configuration and fixtures, the workflow that
# builds the job, and the runner and this module themselves.
ALWAYS_AFFECTED = (
    ".python-version",
    "pyproject.toml",
    "uv.lock",
    "pytest.ini",
    "**/conftest.py",
    ".github/workflows/pytest.yml",
    ".github/actions/setup-code-env/**",
    "scripts/ci/run_pytest_windows.py",
    "scripts/ci/windows_path_filter.py",
)

# A literal ending in one of these names a file. The basename rule fires only
# for these, so a literal such as "main" cannot pull in every file called main.
_BASENAME_SUFFIXES = (".py", ".ps1", ".psm1", ".yml", ".yaml", ".json", ".toml", ".sh", ".md")

# Characters picomatch reads as glob syntax, plus line breaks, which a YAML
# single-quoted scalar folds. A path holding one is emitted as its parent
# directory so the document cannot mis-quote it.
_GLOB_META = frozenset("*?[]{}()!@+|\\#\n\r\t")

_MIN_LITERAL = 2
_MAX_LITERAL = 300


class ReachError(Exception):
    """The tracked-file inventory could not be read."""


def tracked_files(repo_root: Path) -> tuple[str, ...]:
    """Tracked paths at HEAD, newline-safe (`ci-scripts.md` MUST-9).

    Raises:
        ReachError: git failed or is missing.
    """
    try:
        result = subprocess.run(
            ["git", "ls-tree", "-r", "-z", "--name-only", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ReachError(f"could not list tracked files: {exc}") from exc
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise ReachError(f"git ls-tree exited {result.returncode}: {detail}")
    names = result.stdout.decode("utf-8", errors="surrogateescape").split("\0")
    return tuple(sorted(name for name in names if name))


class Inventory:
    """Lookup tables over the tracked paths."""

    def __init__(self, files: Iterable[str]) -> None:
        self.files = frozenset(files)
        self.by_basename: dict[str, list[str]] = {}
        self.by_module_tail: dict[str, list[str]] = {}
        for path in self.files:
            posix = PurePosixPath(path)
            self.by_basename.setdefault(posix.name, []).append(path)
            if path.endswith(".py"):
                self._index_module(posix)

    def _index_module(self, posix: PurePosixPath) -> None:
        parts = list(posix.with_suffix("").parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        for start in range(len(parts)):
            self.by_module_tail.setdefault(".".join(parts[start:]), []).append(str(posix))


def _normalise(literal: str) -> str:
    return literal.replace("\\", "/").strip("/")


def _div_chain(node: ast.BinOp) -> list[str]:
    """String constants of a `a / "x" / "y"` chain, left to right.

    Empty when any right operand is not a string constant. The leftmost operand
    contributes only when it is a constant too, since it is usually a computed
    root that names nothing.
    """
    parts: list[str] = []
    cursor: ast.expr = node
    while isinstance(cursor, ast.BinOp) and isinstance(cursor.op, ast.Div):
        right = cursor.right
        if not (isinstance(right, ast.Constant) and isinstance(right.value, str)):
            return []
        parts.append(right.value)
        cursor = cursor.left
    if isinstance(cursor, ast.Constant) and isinstance(cursor.value, str):
        parts.append(cursor.value)
    parts.reverse()
    return parts


def _join_runs(tree: ast.AST) -> Iterable[str]:
    """`root / "scripts" / "eval"` as `scripts/eval`, plus every suffix of the run."""
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            parts = _div_chain(node)
            for start in range(len(parts)):
                yield "/".join(_normalise(part) for part in parts[start:])


def _imports(tree: ast.AST) -> Iterable[str]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            yield node.module
            for alias in node.names:
                yield f"{node.module}.{alias.name}"


def _literals(tree: ast.AST) -> Iterable[str]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value
            if _MIN_LITERAL <= len(value) <= _MAX_LITERAL and "\n" not in value:
                yield _normalise(value)


def _resolve_literal(literal: str, inventory: Inventory) -> list[str]:
    if not literal or literal.startswith(".."):
        return []
    found = [literal] if literal in inventory.files else []
    if "/" not in literal and literal.endswith(_BASENAME_SUFFIXES):
        found.extend(inventory.by_basename.get(literal, []))
    return found


def _references(path: str, repo_root: Path, inventory: Inventory) -> set[str]:
    """Tracked files the Python module at ``path`` names."""
    try:
        source = (repo_root / path).read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source)
    except (OSError, SyntaxError, ValueError):
        return set()
    found: set[str] = set()
    for module in _imports(tree):
        found.update(inventory.by_module_tail.get(module, []))
    for literal in (*_literals(tree), *_join_runs(tree)):
        found.update(_resolve_literal(literal, inventory))
    return found


def reach(
    repo_root: Path,
    root: str,
    inventory: Inventory,
    references: dict[str, set[str]] | None = None,
) -> set[str]:
    """``root`` plus everything it names, transitively through Python files.

    ``references`` caches each file's names across calls. The marked modules
    share most of their reach, so without it every shared file is parsed once
    per module.
    """
    if references is None:
        references = {}
    seen: set[str] = set()
    queue: deque[str] = deque([root])
    while queue:
        path = queue.popleft()
        if path in seen:
            continue
        seen.add(path)
        if path.endswith(".py"):
            if path not in references:
                references[path] = _references(path, repo_root, inventory)
            queue.extend(references[path] - seen)
    return seen


def _glob_for(path: str) -> str:
    if _GLOB_META.intersection(path):
        parent = str(PurePosixPath(path).parent)
        return MATCH_EVERYTHING if parent == "." else f"{parent}/**"
    return path


def filter_patterns(repo_root: Path, files: Iterable[str] | None = None) -> dict[str, list[str]]:
    """Globs per marked module for the tree at ``repo_root``.

    Raises:
        ReachError: the inventory could not be read.
        run_pytest_windows.DiscoveryError: a test module could not be read.
    """
    inventory = Inventory(tracked_files(repo_root) if files is None else files)
    patterns: dict[str, list[str]] = {}
    references: dict[str, set[str]] = {}
    for root in run_pytest_windows.marked_files(repo_root):
        globs = {_glob_for(path) for path in reach(repo_root, root, inventory, references)}
        globs.update(ALWAYS_AFFECTED)
        patterns[root] = sorted(globs)
    return patterns


def _quote(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def render(patterns: Mapping[str, Iterable[str]]) -> str:
    """The filter document. Every key and entry is single-quoted for YAML."""
    lines: list[str] = []
    for key, globs in patterns.items():
        lines.append(f"{_quote(key)}:")
        lines.extend(f"  - {_quote(glob)}" for glob in globs)
    return "\n".join(lines) + "\n"


def parse_outputs(raw: str) -> dict[str, str] | None:
    """The action's outputs as a mapping, or None when they cannot be trusted."""
    if not raw.strip():
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict) or not parsed:
        # An empty object is what a skipped filter step leaves behind. A real
        # run always carries `changes`, so empty means nothing was measured.
        return None
    return {str(key): str(value) for key, value in parsed.items()}


def runs_everything(event_name: str, ref_name: str, default_branch: str) -> bool:
    """Whether this event is one the narrowing must not decide."""
    if event_name in FULL_RUN_EVENTS:
        return True
    return event_name == "push" and bool(ref_name) and ref_name == default_branch


def select(
    outputs: Mapping[str, str] | None,
    marked: Iterable[str],
    event_name: str,
    ref_name: str,
    default_branch: str,
) -> tuple[bool, list[str]]:
    """``(job starts, modules to run)``. No modules with True means all of them."""
    if outputs is None or runs_everything(event_name, ref_name, default_branch):
        return True, []
    matched = {
        key for key, value in outputs.items() if value == "true" and key != _ACTION_SUMMARY_KEY
    }
    if not matched:
        return False, []
    chosen = [path for path in marked if path in matched]
    if matched - set(chosen):
        # A matched key that is not a marked module is the fallback key or a
        # stale name. Neither says which module is safe to drop.
        return True, []
    return True, chosen


def _cmd_emit(args: argparse.Namespace) -> int:
    try:
        patterns = filter_patterns(args.repo_root.resolve())
    except (ReachError, run_pytest_windows.DiscoveryError) as exc:
        print(f"reach is incomplete, every change will run all of it: {exc}", file=sys.stderr)
        patterns = {FALLBACK_KEY: [MATCH_EVERYTHING]}
    try:
        args.output.write_text(render(patterns), encoding="utf-8")
    except OSError as exc:
        print(f"could not write {args.output}: {exc}", file=sys.stderr)
        return EXIT_EXTERNAL
    total = sum(len(globs) for globs in patterns.values())
    print(f"modules={len(patterns)} patterns={total} output={args.output}", file=sys.stderr)
    return EXIT_OK


def _cmd_select(args: argparse.Namespace) -> int:
    env = os.environ
    output_path = env.get("GITHUB_OUTPUT")
    if not output_path:
        print("GITHUB_OUTPUT is required", file=sys.stderr)
        return EXIT_CONFIG
    try:
        marked = run_pytest_windows.marked_files(args.repo_root.resolve())
    except run_pytest_windows.DiscoveryError as exc:
        print(f"discovery is incomplete, running all of it: {exc}", file=sys.stderr)
        marked = []
        outputs = None
    else:
        outputs = parse_outputs(env.get("FILTER_OUTPUTS", ""))
    affected, files = select(
        outputs,
        marked,
        env.get("GH_EVENT_NAME", ""),
        env.get("GH_REF_NAME", ""),
        env.get("GH_DEFAULT_BRANCH", ""),
    )
    lines = f"{OUTPUT_AFFECTED}={str(affected).lower()}\n{OUTPUT_FILES}={json.dumps(files)}\n"
    try:
        with Path(output_path).open("a", encoding="utf-8") as handle:
            handle.write(lines)
    except OSError as exc:
        print(f"could not write {output_path}: {exc}", file=sys.stderr)
        return EXIT_EXTERNAL
    scope = f"{len(files)} of {len(marked)} modules" if files else "all modules"
    print(f"{OUTPUT_AFFECTED}={str(affected).lower()} {scope}", file=sys.stderr)
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-root", type=Path, default=_PROJECT_ROOT)
    commands = parser.add_subparsers(dest="command", required=True)
    emit = commands.add_parser("emit", help="write the paths-filter document")
    emit.add_argument("--output", required=True, type=Path)
    emit.set_defaults(handler=_cmd_emit)
    selecting = commands.add_parser("select", help="write the job's GITHUB_OUTPUT lines")
    selecting.set_defaults(handler=_cmd_select)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
