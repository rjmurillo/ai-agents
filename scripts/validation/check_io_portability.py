#!/usr/bin/env python3
"""Flag added Python lines that depend on the platform's text encoding or symlink privilege.

Three rules, each an AST check with no guesswork about intent:

``subprocess-text-encoding``
    A ``subprocess`` call in text mode (``text=True`` or
    ``universal_newlines=True``) that passes no ``encoding``. Python then decodes
    with the locale encoding, which is cp1252 on many Windows hosts.
``file-text-encoding``
    ``Path.read_text()``, ``Path.write_text(data)`` or builtin ``open()`` in
    text mode with no ``encoding``. Same locale dependency. An attribute
    ``.open()`` is not checked: its receiver may be a zip member, an image, or a
    browser, and the AST cannot tell which.
``unguarded-symlink``
    A test file calls ``symlink_to`` or ``os.symlink`` outside a ``try`` that
    catches ``OSError`` or ``NotImplementedError``, in a function with no
    ``skip`` in its name, no ``skipif`` marker on the function or its class, and
    no module ``pytestmark``. Windows without Developer Mode raises ``OSError``,
    so the test errors instead of skipping.

These are the three mechanical rules behind 80 of the 166 Cursor Bugbot
"learned rule" findings on pull requests #6110 to #7380 (evals/third-party-review-gap).

Scope: with ``--base-ref``, only lines added since the merge base with that ref
are reported, so existing code does not block. Generated mirror trees
(``MIRROR_PREFIXES``) are skipped in that mode: ``build_all.py`` copies them from
``src/claude/`` and ``scripts/``, so a violation is reported once, at its
source. With file arguments, every line in those files is reported. A call
carrying ``**kwargs`` is skipped: its encoding cannot be read statically.

Suppress one line with ``# io-portability: ignore <reason>``.

Exit codes (ADR-035): 0 clean, 1 violations, 2 configuration error.
"""

from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

SUPPRESS = "# io-portability: ignore"
_SUBPROCESS_CALLS = frozenset({"run", "Popen", "check_output", "check_call", "call"})
_TEXT_FLAGS = ("text", "universal_newlines")
_SYMLINK_CATCHES = frozenset({"OSError", "NotImplementedError", "Exception", "BaseException"})
# Generated copies of src/claude/skills and the scripts/ lib packages, rendered by
# build/scripts/build_all.py (see templates/AGENTS.md, "Skip"). Editing them is
# overwritten, so a finding there belongs to the source file.
MIRROR_PREFIXES: tuple[str, ...] = (
    "src/copilot-cli/skills/",
    "src/copilot-cli/lib/",
    "src/codex/skills/",
    "src/codex/lib/",
    "src/cursor/skills/",
    "src/cursor/lib/",
    "src/muse/skills/",
    "src/muse/lib/",
    "src/hermes/",
)
_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(?P<start>\d+)(?:,(?P<count>\d+))? @@")


@dataclass(frozen=True, slots=True, order=True)
class Violation:
    path: str
    line: int
    rule: str
    message: str
    end_line: int = 0

    def spans(self, line: int) -> bool:
        """True when ``line`` falls inside the flagged call, first to last line."""
        return self.line <= line <= max(self.line, self.end_line)

    def render(self) -> str:
        return f"{self.path}:{self.line}: [{self.rule}] {self.message}"


def is_test_path(path: str) -> bool:
    name = Path(path).name
    parts = Path(path).parts
    return "tests" in parts or name.startswith("test_") or name == "conftest.py"


def _kwarg(call: ast.Call, name: str) -> ast.expr | None:
    for keyword in call.keywords:
        if keyword.arg == name:
            return keyword.value
    return None


def _has_star_kwargs(call: ast.Call) -> bool:
    return any(keyword.arg is None for keyword in call.keywords)


def _is_true(node: ast.expr | None) -> bool:
    return isinstance(node, ast.Constant) and node.value is True


def _callee(call: ast.Call) -> tuple[str | None, str | None]:
    """``(receiver name, attribute or function name)`` for a call."""
    func = call.func
    if isinstance(func, ast.Attribute):
        receiver = func.value.id if isinstance(func.value, ast.Name) else None
        return receiver, func.attr
    if isinstance(func, ast.Name):
        return None, func.id
    return None, None


def _subprocess_names(tree: ast.Module) -> tuple[set[str], set[str]]:
    """Names bound to the subprocess module, and bare names imported from it."""
    modules: set[str] = set()
    functions: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "subprocess":
                    modules.add(alias.asname or "subprocess")
        elif isinstance(node, ast.ImportFrom) and node.module == "subprocess":
            for alias in node.names:
                if alias.name in _SUBPROCESS_CALLS:
                    functions.add(alias.asname or alias.name)
    return modules, functions


def _text_mode_without_encoding(call: ast.Call) -> bool:
    if _has_star_kwargs(call) or _kwarg(call, "encoding") is not None:
        return False
    return any(_is_true(_kwarg(call, flag)) for flag in _TEXT_FLAGS)


def _mode_is_text(mode: ast.expr | None) -> bool:
    if mode is None:
        return True
    if isinstance(mode, ast.Constant) and isinstance(mode.value, str):
        return "b" not in mode.value
    return False  # a computed mode cannot be judged statically


def _file_io_without_encoding(call: ast.Call) -> str | None:
    if _has_star_kwargs(call) or _kwarg(call, "encoding") is not None:
        return None
    _, name = _callee(call)
    is_attr = isinstance(call.func, ast.Attribute)
    if is_attr and name == "read_text" and not call.args:
        return "read_text() without encoding"
    if is_attr and name == "write_text" and len(call.args) < 2:
        return "write_text() without encoding"
    if not is_attr and name == "open" and call.args:
        if len(call.args) >= 4:
            return None
        mode = call.args[1] if len(call.args) > 1 else _kwarg(call, "mode")
        return "open() in text mode without encoding" if _mode_is_text(mode) else None
    return None


def _catches_symlink_failure(handler: ast.ExceptHandler) -> bool:
    if handler.type is None:
        return True
    names = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
    return any(isinstance(n, ast.Name) and n.id in _SYMLINK_CATCHES for n in names)


def _has_skipif(decorators: Iterable[ast.expr]) -> bool:
    return any("skip" in ast.unparse(d) for d in decorators)


class _Visitor(ast.NodeVisitor):
    def __init__(self, path: str, tree: ast.Module) -> None:
        self.path = path
        self.test_file = is_test_path(path)
        self.modules, self.functions = _subprocess_names(tree)
        self.module_skip = any(
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets)
            for node in tree.body
        )
        self.guards: list[bool] = []  # one entry per enclosing scope or try that guards
        self.found: list[Violation] = []

    def _add(self, node: ast.AST, rule: str, message: str) -> None:
        line = getattr(node, "lineno", 0)
        end = getattr(node, "end_lineno", None) or line
        self.found.append(Violation(self.path, line, rule, message, end))

    def _scope(self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> None:
        guarded = "skip" in node.name.lower() or _has_skipif(node.decorator_list)
        self.guards.append(guarded)
        self.generic_visit(node)
        self.guards.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._scope(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._scope(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._scope(node)

    def _try(self, node: ast.Try | ast.TryStar) -> None:
        """Only the ``try`` body is guarded; handlers, ``else`` and ``finally`` are not."""
        self.guards.append(any(_catches_symlink_failure(h) for h in node.handlers))
        for statement in node.body:
            self.visit(statement)
        self.guards.pop()
        for handler in node.handlers:
            self.visit(handler)
        for tail in (*node.orelse, *node.finalbody):
            self.visit(tail)

    def visit_Try(self, node: ast.Try) -> None:
        self._try(node)

    def visit_TryStar(self, node: ast.TryStar) -> None:
        self._try(node)

    def visit_Call(self, node: ast.Call) -> None:
        receiver, name = _callee(node)
        is_subprocess = (receiver in self.modules and name in _SUBPROCESS_CALLS) or (
            receiver is None and name in self.functions
        )
        if is_subprocess and _text_mode_without_encoding(node):
            self._add(
                node, "subprocess-text-encoding", f"subprocess.{name} text mode without encoding"
            )
        message = _file_io_without_encoding(node)
        if message:
            self._add(node, "file-text-encoding", message)
        if self.test_file and self._is_symlink_call(receiver, name, node):
            if not (self.module_skip or any(self.guards)):
                self._add(node, "unguarded-symlink", "symlink created without a platform skip")
        self.generic_visit(node)

    @staticmethod
    def _is_symlink_call(receiver: str | None, name: str | None, node: ast.Call) -> bool:
        if name == "symlink_to" and isinstance(node.func, ast.Attribute):
            return True
        return receiver == "os" and name == "symlink"


def scan_source(path: str, source: str) -> list[Violation]:
    """Every violation in one file's source. A file that does not parse yields none."""
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError:
        return []
    visitor = _Visitor(path, tree)
    visitor.visit(tree)
    lines = source.splitlines()
    return sorted(
        v for v in visitor.found if not (0 < v.line <= len(lines) and SUPPRESS in lines[v.line - 1])
    )


def added_lines(diff: str) -> dict[str, set[int]]:
    """New-file line numbers added per path in a unified diff with zero context."""
    out: dict[str, set[int]] = {}
    current: str | None = None
    for line in diff.splitlines():
        if line.startswith("+++ "):
            target = line[4:]
            current = target[2:] if target.startswith("b/") else None
            continue
        hunk = _HUNK.match(line)
        if hunk and current is not None:
            start = int(hunk.group("start"))
            count = int(hunk.group("count") or "1")
            out.setdefault(current, set()).update(range(start, start + count))
    return out


def _git(args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=60,
    )


def scan_diff(base_ref: str) -> tuple[list[Violation], int]:
    """Violations on lines added since the merge base with ``base_ref``, and files examined."""
    merge_base = _git(["merge-base", base_ref, "HEAD"])
    if merge_base.returncode != 0:
        raise ValueError(f"cannot find merge base with {base_ref}: {merge_base.stderr.strip()}")
    diff = _git(["diff", "-U0", "--diff-filter=AM", merge_base.stdout.strip(), "--", "*.py"])
    if diff.returncode != 0:
        raise ValueError(f"git diff failed: {diff.stderr.strip()}")
    found: list[Violation] = []
    changed = added_lines(diff.stdout)
    for path, lines in sorted(changed.items()):
        if path.startswith(MIRROR_PREFIXES):
            continue
        try:
            source = Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise ValueError(f"cannot read {path}: {exc}") from exc
        found.extend(v for v in scan_source(path, source) if any(v.spans(line) for line in lines))
    return found, len(changed)


def scan_files(paths: Sequence[str]) -> tuple[list[Violation], int]:
    found: list[Violation] = []
    for path in paths:
        try:
            source = Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise ValueError(f"cannot read {path}: {exc}") from exc
        found.extend(scan_source(path, source))
    return found, len(paths)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="*", help="scan these files in full")
    parser.add_argument("--base-ref", help="scan only lines added since the merge base")
    args = parser.parse_args(argv)
    if bool(args.files) == bool(args.base_ref):
        print("error: pass either files or --base-ref", file=sys.stderr)
        return 2
    try:
        found, examined = scan_diff(args.base_ref) if args.base_ref else scan_files(args.files)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for violation in found:
        print(violation.render())
    print(f"{len(found)} io-portability violation(s) in {examined} file(s) examined")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
