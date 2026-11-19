"""Classify changed lines as prose or code, and index the code that changed.

Support module for `same_pr.py`. It reads text the caller already loaded and the
new-side line ranges `doc_accuracy.py` parsed from `git diff --unified=0`; it
runs no git command of its own.

Prose: Markdown and `.tmpl` lines (table rows included, fenced lines excluded),
Python docstrings and comments (found with `ast` and `tokenize`), and JSON or
YAML string values. Code: every other changed line of a source file, tagged with
its innermost enclosing function or class.
"""

from __future__ import annotations

import ast
import io
import json
import re
import tokenize
from dataclasses import dataclass

PROSE_SUFFIXES = {".md", ".tmpl", ".mdx"}
DATA_SUFFIXES = {".json", ".yaml", ".yml"}
CODE_SUFFIXES = {".py", ".cs", ".ts", ".tsx", ".js", ".ps1", ".sh"}
MODULE_SYMBOL = "<module>"
_FENCE = re.compile(r"^\s*(```|~~~)")
_JSON_VALUE = re.compile(r'^\s*"[^"]+"\s*:\s*(".*")\s*,?\s*$')
_YAML_VALUE = re.compile(r"^\s*(?:-\s+)?[\w.-]+:\s+[\"']?(.+?)[\"']?\s*$")
_MIN_DATA_WORDS = 4


@dataclass(frozen=True)
class ProseLine:
    file: str
    line: int
    text: str


@dataclass(frozen=True)
class CodeRegion:
    """The changed lines of one symbol: ``line`` is the first changed line."""

    file: str
    line: int
    symbol: str


def changed_line_numbers(ranges: list[list[int]] | None, total: int) -> set[int]:
    """Expand inclusive ``[start, end]`` ranges; ``None`` means every line changed."""
    if ranges is None:
        return set(range(1, total + 1))
    return {n for start, end in ranges for n in range(start, min(end, total) + 1)}


def _markdown_prose(rel: str, lines: list[str], changed: set[int]) -> list[ProseLine]:
    found: list[ProseLine] = []
    fenced = False
    for number, line in enumerate(lines, start=1):
        if _FENCE.match(line):
            fenced = not fenced
            continue
        if number in changed and not fenced and line.strip():
            found.append(ProseLine(rel, number, line.strip()))
    return found


def _data_prose(rel: str, lines: list[str], changed: set[int]) -> list[ProseLine]:
    pattern = _JSON_VALUE if rel.endswith(".json") else _YAML_VALUE
    found: list[ProseLine] = []
    for number in sorted(changed):
        match = pattern.match(lines[number - 1])
        if not match:
            continue
        value = match.group(1)
        if value.startswith('"'):
            try:
                value = json.loads(value)
            except ValueError:
                continue
        if isinstance(value, str) and len(value.split()) >= _MIN_DATA_WORDS:
            found.append(ProseLine(rel, number, value))
    return found


def _docstring_spans(tree: ast.AST) -> list[tuple[int, int]]:
    spans = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        first = node.body[0] if node.body else None
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
            if isinstance(first.value.value, str) and first.end_lineno:
                spans.append((first.lineno, first.end_lineno))
    return spans


def _comment_lines(source: str) -> dict[int, str]:
    comments: dict[int, str] = {}
    try:
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type == tokenize.COMMENT:
                comments[token.start[0]] = token.string.lstrip("#").strip()
    except (tokenize.TokenError, IndentationError):
        return comments
    return comments


def _symbol_spans(tree: ast.AST) -> list[tuple[int, int, str]]:
    spans = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            spans.append((node.lineno, node.end_lineno or node.lineno, node.name))
    return spans


def _innermost(spans: list[tuple[int, int, str]], line: int) -> str:
    inside = [s for s in spans if s[0] <= line <= s[1]]
    return min(inside, key=lambda s: s[1] - s[0])[2] if inside else MODULE_SYMBOL


def _python_split(
    rel: str, source: str, changed: set[int]
) -> tuple[list[ProseLine], list[CodeRegion], int]:
    lines = source.split("\n")
    doc_spans: list[tuple[int, int]] = []
    spans: list[tuple[int, int, str]] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        pass  # Unparseable source: every changed line stays code with no symbol.
    else:
        doc_spans, spans = _docstring_spans(tree), _symbol_spans(tree)
    comments = _comment_lines(source)
    prose: list[ProseLine] = []
    first_line: dict[str, int] = {}
    code_lines = 0
    for number in sorted(changed):
        text = lines[number - 1].strip()
        if any(start <= number <= end for start, end in doc_spans):
            if text.strip("\"'"):
                prose.append(ProseLine(rel, number, text))
            continue
        if number in comments and comments[number]:
            prose.append(ProseLine(rel, number, comments[number]))
        if text and not text.startswith("#"):
            code_lines += 1
            first_line.setdefault(_innermost(spans, number), number)
    regions = [CodeRegion(rel, line, name) for name, line in first_line.items()]
    return prose, sorted(regions, key=lambda r: r.line), code_lines


def classify_file(
    rel: str, source: str, ranges: list[list[int]] | None
) -> tuple[list[ProseLine], list[CodeRegion], int]:
    """Split one file's changed lines into prose, code regions, and a code-line count."""
    lines = source.split("\n")
    changed = changed_line_numbers(ranges, len(lines))
    suffix = "." + rel.rsplit(".", 1)[-1].lower() if "." in rel else ""
    if suffix in PROSE_SUFFIXES:
        return _markdown_prose(rel, lines, changed), [], 0
    if suffix in DATA_SUFFIXES:
        return _data_prose(rel, lines, changed), [], 0
    if suffix == ".py":
        return _python_split(rel, source, changed)
    if suffix in CODE_SUFFIXES:
        body = [n for n in sorted(changed) if lines[n - 1].strip()]
        regions = [CodeRegion(rel, body[0], MODULE_SYMBOL)] if body else []
        return [], regions, len(body)
    return [], [], 0


# -- code index ---------------------------------------------------------------


def _identifiers(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            names.add(child.id)
        elif isinstance(child, ast.Attribute):
            names.add(child.attr)
    return names


def _is_exit_call(node: ast.Call) -> bool:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "exit"
    return isinstance(func, ast.Attribute) and func.attr == "exit"


class CodeIndex:
    """Lazy AST facts about the changed Python files, keyed by repo-relative path."""

    _MAIN_NAMES = {"main", "_main", "cli", "run_cli"}

    def __init__(self, sources: dict[str, str]) -> None:
        self.sources = {k: v for k, v in sources.items() if k.endswith(".py")}
        self._trees: dict[str, ast.AST | None] = {}

    def tree(self, rel: str) -> ast.AST | None:
        if rel not in self._trees:
            try:
                self._trees[rel] = ast.parse(self.sources[rel])
            except SyntaxError:
                self._trees[rel] = None
        return self._trees[rel]

    def exit_literals(self, rel: str) -> dict[int, int]:
        """Map each literal exit integer to its first line.

        Counts ``sys.exit(N)``, ``exit(N)``, and ``return N`` inside ``main``-like
        functions only: a ``return 1`` in a helper is rarely a process exit code.
        """
        tree = self.tree(rel)
        found: dict[int, int] = {}
        if tree is None:
            return found
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _is_exit_call(node) and node.args:
                self._take(found, node.args[0], node.lineno)
            if isinstance(node, ast.FunctionDef) and node.name in self._MAIN_NAMES:
                for ret in ast.walk(node):
                    if isinstance(ret, ast.Return) and ret.value is not None:
                        self._take(found, ret.value, ret.lineno)
        return found

    @staticmethod
    def _take(found: dict[int, int], value: ast.AST, line: int) -> None:
        if isinstance(value, ast.Constant) and type(value.value) is int:
            found.setdefault(value.value, line)

    def assignments(self, key: str) -> list[tuple[str, int, set[str]]]:
        """Return (file, line, identifiers on the right) for each write to ``key``."""
        found = []
        for rel in self.sources:
            tree = self.tree(rel)
            for node in ast.walk(tree) if tree else []:
                for value in _writes_to(node, key):
                    found.append((rel, getattr(node, "lineno", 1), _identifiers(value)))
        return found


def _writes_to(node: ast.AST, key: str) -> list[ast.AST]:
    """Return the value nodes that ``node`` assigns to attribute, item, or keyword ``key``."""
    if isinstance(node, ast.Assign | ast.AnnAssign) and node.value is not None:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if any(_names_key(t, key) for t in targets):
            return [node.value]
    if isinstance(node, ast.Call):
        return [kw.value for kw in node.keywords if kw.arg == key]
    if isinstance(node, ast.Dict):
        return [v for k, v in zip(node.keys, node.values, strict=True) if const_str(k) == key]
    return []


def const_str(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _names_key(target: ast.AST, key: str) -> bool:
    if isinstance(target, ast.Attribute):
        return target.attr == key
    return isinstance(target, ast.Subscript) and const_str(target.slice) == key
