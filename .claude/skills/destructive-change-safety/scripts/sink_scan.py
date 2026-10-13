#!/usr/bin/env python3
"""Find destructive sinks and trace call paths to them (destructive-change-safety).

Scans Python files with ``ast`` and SQL or shell files line by line. A sink is
a call or statement that deletes, overwrites, or irreversibly mutates state.
For every sink the scan reports the enclosing function, the call chains from
entry points down to it (callers), and the CLI flags declared on the functions
along each chain or on a function they call directly. Given ``--changed``
names, it also reports which sinks a changed function can reach (forward trace).

The call graph is name based: every definition that shares a simple name is
one node, and ``obj.purge()`` resolves to any ``purge`` in the scanned set.
That over-approximates reachability on purpose. A false path costs a reviewer
one look; a missed path costs the data.

A sink whose function has no caller inside the scanned set reports
``callers_unknown``: the entry point lives outside the scan, so the scan
cannot call the path traced. A file that cannot be parsed makes the decision
``unknown``, never ``skip``. So is a source file in a language the scan
cannot read (PowerShell, JavaScript, C#, Go, and the like): the report lists it
under ``unscanned`` and the decision is ``unknown``. A scope that holds no file
the scan could read or name raises ``EmptyScopeError``.

EXIT CODES (ADR-035):
    0 - Scan finished; ``decision`` is ``skip`` (no sink) or ``activate``
    1 - Logic error: ``decision`` is ``unknown`` (a file failed to parse, or
        a source file in an unsupported language went unscanned)
    2 - Config error: a path does not exist or holds no scannable file
"""

from __future__ import annotations

import ast
import re
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path

MODULE_SCOPE = "<module>"
MAX_CHAINS = 20
MAX_DEPTH = 12
SCANNED_SUFFIXES = {".py", ".sql", ".sh"}
SKIPPED_DIRS = {".git", "__pycache__", ".venv", "node_modules", ".mypy_cache"}
# Code or script suffixes the scan cannot read. A match in a scanned tree makes
# the decision ``unknown``; prose and data suffixes stay ignored.
UNSUPPORTED_SUFFIXES = {
    ".ps1", ".psm1", ".psd1", ".bat", ".cmd", ".bash", ".zsh", ".fish",
    ".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx",
    ".cs", ".go", ".java", ".kt", ".rs", ".rb", ".php", ".pl", ".lua",
    ".c", ".cc", ".cpp", ".h", ".hpp", ".swift", ".scala",
}  # fmt: skip

# Dotted calls that delete or overwrite. Attribute-only names are limited to
# ones that are not also common non-destructive methods (no bare ``.remove``
# or ``.replace``: list.remove and str.replace would drown the signal).
DOTTED_SINKS: dict[str, str] = {
    "os.remove": "delete",
    "os.unlink": "delete",
    "os.rmdir": "delete",
    "os.removedirs": "delete",
    "os.replace": "overwrite",
    "os.rename": "overwrite",
    "os.truncate": "overwrite",
    "shutil.rmtree": "delete",
    "shutil.move": "overwrite",
    "shutil.copyfile": "overwrite",
}
ATTRIBUTE_SINKS: dict[str, str] = {
    "unlink": "delete",
    "rmdir": "delete",
    "rmtree": "delete",
    "write_text": "overwrite",
    "write_bytes": "overwrite",
    "truncate": "overwrite",
}
SUBPROCESS_CALLS = {"run", "call", "check_call", "check_output", "Popen", "system"}

SQL_PATTERN = re.compile(
    r"\b(DELETE\s+FROM|TRUNCATE\s+TABLE|DROP\s+(?:TABLE|DATABASE|INDEX|SCHEMA|VIEW)"
    r"|UPDATE\s+\w+\s+SET)\b",
    re.IGNORECASE,
)
SHELL_PATTERN = re.compile(
    r"(?:^|[\s;&|(])(rm|rmdir|shred|truncate)\s"
    r"|git\s+(?:clean|reset\s+--hard|branch\s+-D|push\s+(?:\S+\s+)*--force)"
    r"|kubectl\s+delete|terraform\s+destroy|docker\s+(?:rm|rmi|system\s+prune)"
    r"|gh\s+\w+\s+delete",
)


# Destructive git subcommands passed as an argv list to a wrapper such as
# ``_run_git(["worktree", "remove", path])``. The wrapper hides ``subprocess``
# and the ``git`` word, so the list head is matched on its own.
GIT_ARGV_PATTERN = re.compile(
    r"^(?:git\s+)?(?:worktree\s+(?:remove|prune)|clean\s+-|reset\s+--hard|branch\s+-D"
    r"|update-ref\s+-d|stash\s+(?:drop|clear)|gc\s+--prune|push\b.*--force)"
)


class EmptyScopeError(Exception):
    """The roots hold no file the scan can read and no unsupported source file."""


@dataclass(frozen=True)
class Sink:
    """One destructive operation at one source location."""

    file: str
    line: int
    function: str
    kind: str
    label: str

    @property
    def location(self) -> str:
        return f"{self.file}:{self.line}"


@dataclass
class Graph:
    """Name-based call graph plus the flags declared per function."""

    calls: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    flags: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    sinks: list[Sink] = field(default_factory=list)
    unparsed: list[str] = field(default_factory=list)

    def callers(self) -> dict[str, set[str]]:
        reverse: dict[str, set[str]] = defaultdict(set)
        for caller, callees in self.calls.items():
            for callee in callees:
                reverse[callee].add(caller)
        return reverse


def dotted_name(node: ast.AST) -> str:
    """Return ``a.b.c`` for a Name or Attribute chain, else an empty string."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return ""


def callee_name(node: ast.Call) -> str:
    """Return the simple name a call resolves to in the name-based graph."""
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def string_parts(node: ast.AST) -> list[str]:
    """Return the string constants under a call argument, in source order."""
    return [
        n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)
    ]


def open_write_mode(node: ast.Call) -> bool:
    """True for ``open(path, "w...")`` and its ``mode=`` keyword form."""
    if callee_name(node) != "open":
        return False
    modes = [a for a in node.args[1:2]] + [k.value for k in node.keywords if k.arg == "mode"]
    return any(
        isinstance(m, ast.Constant) and isinstance(m.value, str) and m.value.startswith("w")
        for m in modes
    )


def subprocess_sink(node: ast.Call) -> str:
    """Return the shell command text when a subprocess call runs a destructive one."""
    dotted = dotted_name(node.func)
    if dotted.split(".")[-1] not in SUBPROCESS_CALLS or not node.args:
        return ""
    text = " ".join(string_parts(node.args[0]))
    return text if SHELL_PATTERN.search(f" {text}") else ""


def git_argv_sink(node: ast.Call) -> str:
    """Return the git argv text when the first argument is a destructive git list."""
    if not node.args or not isinstance(node.args[0], ast.List | ast.Tuple):
        return ""
    text = " ".join(string_parts(node.args[0]))
    return text if GIT_ARGV_PATTERN.search(text) else ""


def call_sink(node: ast.Call) -> tuple[str, str] | None:
    """Classify a call as a ``(kind, label)`` sink, or None."""
    dotted = dotted_name(node.func)
    if dotted in DOTTED_SINKS:
        return DOTTED_SINKS[dotted], dotted
    command = subprocess_sink(node)
    if command:
        return "command", command.strip()
    argv = git_argv_sink(node)
    if argv:
        return "command", argv
    if open_write_mode(node):
        return "overwrite", "open(..., 'w')"
    name = callee_name(node)
    if isinstance(node.func, ast.Attribute) and name in ATTRIBUTE_SINKS:
        return ATTRIBUTE_SINKS[name], f".{name}()"
    return None


class Collector(ast.NodeVisitor):
    """Walk one module, attributing calls, flags, and sinks to the innermost function."""

    def __init__(self, rel: str, graph: Graph) -> None:
        self.rel = rel
        self.graph = graph
        self.scope = [MODULE_SCOPE]

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    visit_AsyncFunctionDef = visit_FunctionDef  # noqa: N815

    def visit_Call(self, node: ast.Call) -> None:
        here = self.scope[-1]
        name = callee_name(node)
        if name:
            self.graph.calls[here].add(name)
        self.record_flag(node, here)
        sink = call_sink(node)
        if sink:
            self.graph.sinks.append(Sink(self.rel, node.lineno, here, sink[0], sink[1]))
        self.generic_visit(node)

    def visit_Expr(self, node: ast.Expr) -> None:
        """Skip bare string statements: docstrings quote SQL without running it."""
        if not (isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):
            self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str) and SQL_PATTERN.search(node.value):
            label = " ".join(node.value.split())[:60]
            self.graph.sinks.append(Sink(self.rel, node.lineno, self.scope[-1], "sql", label))

    def record_flag(self, node: ast.Call, here: str) -> None:
        if callee_name(node) != "add_argument":
            return
        for arg in node.args:
            if isinstance(arg, ast.Constant) and str(arg.value).startswith("-"):
                self.graph.flags[here].add(str(arg.value))


def scan_python(path: Path, rel: str, graph: Graph) -> None:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
    except (SyntaxError, UnicodeDecodeError, ValueError):
        graph.unparsed.append(rel)
        return
    Collector(rel, graph).visit(tree)


def scan_text(path: Path, rel: str, graph: Graph) -> None:
    """Line-scan a SQL or shell file; the file itself is the entry point."""
    pattern = SQL_PATTERN if path.suffix == ".sql" else SHELL_PATTERN
    kind = "sql" if path.suffix == ".sql" else "command"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (UnicodeDecodeError, OSError):
        graph.unparsed.append(rel)
        return
    for number, line in enumerate(lines, start=1):
        if not line.lstrip().startswith(("#", "--")) and pattern.search(f" {line}"):
            graph.sinks.append(Sink(rel, number, f"<file:{rel}>", kind, line.strip()[:60]))


def iter_files(roots: list[Path]) -> tuple[list[Path], list[Path]]:
    """Return ``(scannable, unscanned)`` files under the roots, sorted.

    A file named as a root is unscanned when its suffix is not scannable. Inside
    a directory only source suffixes in ``UNSUPPORTED_SUFFIXES`` count, so notes
    and data files do not make a scan ``unknown``.
    """
    scannable: set[Path] = set()
    unscanned: set[Path] = set()
    for root in roots:
        candidates = [root] if root.is_file() else sorted(root.rglob("*"))
        for item in candidates:
            if not item.is_file() or SKIPPED_DIRS.intersection(item.parts):
                continue
            if item.suffix in SCANNED_SUFFIXES:
                scannable.add(item)
            elif item.suffix in UNSUPPORTED_SUFFIXES or item == root:
                unscanned.add(item)
    return sorted(scannable), sorted(unscanned)


def relative_name(path: Path, base: Path) -> str:
    """Return the path relative to ``base`` when it lies under it, else as given."""
    return path.relative_to(base).as_posix() if path.is_relative_to(base) else path.as_posix()


def build_graph(files: list[Path], base: Path) -> Graph:
    graph = Graph()
    for path in files:
        rel = relative_name(path, base)
        (scan_python if path.suffix == ".py" else scan_text)(path, rel, graph)
    return graph


def caller_chains(graph: Graph, function: str) -> list[list[str]]:
    """Return call chains ``entry -> ... -> function``, shortest first, capped."""
    reverse = graph.callers()
    queue: deque[list[str]] = deque([[function]])
    chains: list[list[str]] = []
    while queue and len(chains) < MAX_CHAINS:
        chain = queue.popleft()
        parents = sorted(reverse.get(chain[0], set()) - set(chain))
        if not parents or len(chain) >= MAX_DEPTH:
            chains.append(chain)
            continue
        queue.extend([parent, *chain] for parent in parents)
    return chains


def chain_flags(graph: Graph, chain: list[str]) -> list[str]:
    """Flags declared on a chain function or on a function it calls directly.

    A ``main`` that calls ``parse_args`` consumes that parser's flags, so the
    one-hop callees count; without them the common ``parse_args`` split hides
    every flag that gates the sink.
    """
    names = set(chain)
    for name in chain:
        names |= graph.calls.get(name, set())
    return sorted({flag for name in names for flag in graph.flags.get(name, set())})


def forward_reach(graph: Graph, changed: list[str]) -> dict[str, list[str]]:
    """Map each function reachable from ``changed`` to one shortest path."""
    paths: dict[str, list[str]] = {name: [name] for name in changed}
    queue = deque(changed)
    while queue:
        current = queue.popleft()
        for callee in sorted(graph.calls.get(current, set())):
            if callee not in paths:
                paths[callee] = [*paths[current], callee]
                queue.append(callee)
    return paths


def report_sink(graph: Graph, sink: Sink, reach: dict[str, list[str]]) -> dict[str, object]:
    reverse = graph.callers()
    chains = caller_chains(graph, sink.function)
    has_callers = bool(reverse.get(sink.function)) and sink.function != MODULE_SCOPE
    return {
        "location": sink.location,
        "kind": sink.kind,
        "label": sink.label,
        "function": sink.function,
        "callers_unknown": not has_callers,
        "chains": [" -> ".join(chain) for chain in chains],
        "flags": sorted({flag for chain in chains for flag in chain_flags(graph, chain)}),
        "reached_from_changed": " -> ".join(reach[sink.function]) if sink.function in reach else "",
    }


def scan(roots: list[Path], base: Path, changed: list[str]) -> dict[str, object]:
    """Scan the roots and return the JSON-ready report."""
    scannable, unscanned = iter_files(roots)
    if not scannable and not unscanned:
        names = ", ".join(str(root) for root in roots)
        raise EmptyScopeError(f"no scannable file under: {names}")
    graph = build_graph(scannable, base)
    reach = forward_reach(graph, changed)
    unscanned_names = sorted(relative_name(path, base) for path in unscanned)
    if graph.unparsed or unscanned_names:
        decision = "unknown"
    else:
        decision = "activate" if graph.sinks else "skip"
    return {
        "decision": decision,
        "unparsed": sorted(graph.unparsed),
        "unscanned": unscanned_names,
        "sinks": [report_sink(graph, sink, reach) for sink in graph.sinks],
    }
