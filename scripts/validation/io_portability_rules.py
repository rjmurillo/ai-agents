"""AST rules behind check_io_portability.py: what counts as a violation and a guard.

Split from the gate so each file stays under the size ratchet. The gate owns
scope (added lines, mirror trees) and the CLI; this module owns the rules.
"""

from __future__ import annotations

import ast
import io
import re
import tokenize
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

SUPPRESS = "# io-portability: ignore"
# A suppression must say why: the marker followed by at least one word.
_SUPPRESSION = re.compile(re.escape(SUPPRESS) + r"\s+\S")
_SUBPROCESS_CALLS = frozenset({"run", "Popen", "check_output", "check_call", "call"})
_TEXT_FLAGS = ("text", "universal_newlines")
_SYMLINK_CATCHES = frozenset({"OSError", "NotImplementedError", "Exception", "BaseException"})


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


def _given(node: ast.expr | None) -> bool:
    """An argument that sets a value. A literal ``None`` keeps the locale default."""
    return node is not None and not (isinstance(node, ast.Constant) and node.value is None)


def _positional(call: ast.Call, index: int) -> ast.expr | None:
    return call.args[index] if len(call.args) > index else None


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
    if _has_star_kwargs(call) or _given(_kwarg(call, "encoding")):
        return False
    return any(_is_true(_kwarg(call, flag)) for flag in _TEXT_FLAGS)


def _mode_is_text(mode: ast.expr | None) -> bool:
    if mode is None:
        return True
    if isinstance(mode, ast.Constant) and isinstance(mode.value, str):
        return "b" not in mode.value
    return False  # a computed mode cannot be judged statically


def _file_io_without_encoding(call: ast.Call) -> str | None:
    # Unpacked arguments can carry the encoding or a binary mode; judge only what is visible.
    starred = any(isinstance(arg, ast.Starred) for arg in call.args)
    if starred or _has_star_kwargs(call) or _given(_kwarg(call, "encoding")):
        return None
    _, name = _callee(call)
    is_attr = isinstance(call.func, ast.Attribute)
    # Each check names the positional slot that holds the encoding.
    if is_attr and name == "read_text" and not _given(_positional(call, 0)):
        return "read_text() without encoding"
    if is_attr and name == "write_text" and not _given(_positional(call, 1)):
        return "write_text() without encoding"
    if not is_attr and name == "open" and (call.args or _kwarg(call, "file") is not None):
        if _given(_positional(call, 3)):
            return None
        mode = call.args[1] if len(call.args) > 1 else _kwarg(call, "mode")
        return "open() in text mode without encoding" if _mode_is_text(mode) else None
    return None


def _catches_symlink_failure(handler: ast.ExceptHandler) -> bool:
    if handler.type is None:
        return True
    names = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
    return any(isinstance(n, ast.Name) and n.id in _SYMLINK_CATCHES for n in names)


_PYTEST_SKIP_MARKS = frozenset({"skip", "skipif"})
_CONDITIONAL_SKIPS = frozenset({"skipif", "skipIf"})


def _is_skip_mark(expr: ast.expr, skip_marks: frozenset[str]) -> bool:
    """A mark whose callable is a skip, or a module alias of one.

    Only the callable's own name counts (``pytest.mark.skipif``, ``unittest.skipIf``,
    ``skip_on_windows``). Arguments do not: ``usefixtures('skip_cache')`` does not
    skip. A list or tuple, as ``pytestmark`` allows, guards when any element does.
    """
    if isinstance(expr, ast.List | ast.Tuple):
        return any(_is_skip_mark(e, skip_marks) for e in expr.elts)
    if isinstance(expr, ast.Call) and _never_skips(expr):
        return False
    target = expr.func if isinstance(expr, ast.Call) else expr
    if isinstance(target, ast.Name):
        return target.id in skip_marks or "skip" in target.id.lower()
    if not isinstance(target, ast.Attribute):
        return False
    # A pytest mark skips only when it is pytest's own skip or skipif; a custom
    # mark such as ``pytest.mark.skip_cache`` only labels the test.
    owner = target.value
    if isinstance(owner, ast.Attribute) and owner.attr == "mark":
        return target.attr in _PYTEST_SKIP_MARKS
    return "skip" in target.attr.lower()


def _never_skips(call: ast.Call) -> bool:
    """A conditional skip whose condition is a literal false value, so it never skips."""
    condition = call.args[0] if call.args else _kwarg(call, "condition")
    falsy = isinstance(condition, ast.Constant) and not condition.value
    return falsy and _callee(call)[1] in _CONDITIONAL_SKIPS


def _has_skipif(decorators: Iterable[ast.expr], skip_marks: frozenset[str]) -> bool:
    """A decorator that is a skip mark, directly or through a module-level alias."""
    return any(_is_skip_mark(d, skip_marks) for d in decorators)


def _pytestmark_skips(body: list[ast.stmt], skip_marks: frozenset[str]) -> bool:
    """A ``pytestmark = ...`` assignment in this module or class body that skips."""
    return any(
        isinstance(stmt, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in stmt.targets)
        and _is_skip_mark(stmt.value, skip_marks)
        for stmt in body
    )


def _module_skip_marks(tree: ast.Module) -> frozenset[str]:
    """Module names bound to a skip mark, as in ``POSIX_ONLY = pytest.mark.skipif(...)``."""
    marks: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and _is_skip_mark(node.value, frozenset(marks)):
            marks.update(t.id for t in node.targets if isinstance(t, ast.Name))
    return frozenset(marks)


class _Visitor(ast.NodeVisitor):
    def __init__(self, path: str, tree: ast.Module) -> None:
        self._path = path
        self._test_file = is_test_path(path)
        self._modules, self._functions = _subprocess_names(tree)
        self._skip_marks = _module_skip_marks(tree)
        # Only a module mark that skips counts; `pytestmark = usefixtures(...)` does not guard.
        self._module_skip = _pytestmark_skips(tree.body, self._skip_marks)
        # Skip guards (marks, skip-named helpers) act only when a test body runs;
        # a try guards only code in its own execution scope, not a def it wraps.
        self._skips: list[bool] = []
        self._tries: list[bool] = []
        self._function_depth = 0
        self._found: list[Violation] = []

    @property
    def found(self) -> list[Violation]:
        """Violations in visit order."""
        return list(self._found)

    def _add(self, node: ast.AST, rule: str, message: str) -> None:
        line = getattr(node, "lineno", 0)
        end = getattr(node, "end_lineno", None) or line
        self._found.append(Violation(self._path, line, rule, message, end))

    def _scope(self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> None:
        # A helper such as symlink_or_skip guards its body; a test named test_skips_x does not.
        name = node.name.lower()
        named_guard = "skip" in name and not name.startswith("test")
        guarded = named_guard or _has_skipif(node.decorator_list, self._skip_marks)
        if isinstance(node, ast.ClassDef):  # a class pytestmark marks every method
            guarded = guarded or _pytestmark_skips(node.body, self._skip_marks)
        if isinstance(node, ast.ClassDef):
            self._skips.append(guarded)
            self.generic_visit(node)
            self._skips.pop()
            return
        # Decorators, defaults, and annotations run when the def runs, in the
        # enclosing scope; only the body runs later, outside any try around it.
        for part in (*node.decorator_list, node.args, node.returns):
            if part is not None:
                self.visit(part)
        self._skips.append(guarded)
        saved, self._tries = self._tries, []
        self._function_depth += 1
        for statement in node.body:
            self.visit(statement)
        self._function_depth -= 1
        self._tries = saved
        self._skips.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._scope(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._scope(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._scope(node)

    def _try(self, node: ast.Try | ast.TryStar) -> None:
        """Only the ``try`` body is guarded; handlers, ``else`` and ``finally`` are not."""
        self._tries.append(any(_catches_symlink_failure(h) for h in node.handlers))
        for statement in node.body:
            self.visit(statement)
        self._tries.pop()
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
        is_subprocess = (receiver in self._modules and name in _SUBPROCESS_CALLS) or (
            receiver is None and name in self._functions
        )
        if is_subprocess and _text_mode_without_encoding(node):
            self._add(
                node, "subprocess-text-encoding", f"subprocess.{name} text mode without encoding"
            )
        message = _file_io_without_encoding(node)
        if message:
            self._add(node, "file-text-encoding", message)
        if self._test_file and self._is_symlink_call(receiver, name, node):
            skipped = self._function_depth and (self._module_skip or any(self._skips))
            if not (skipped or any(self._tries)):
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
    suppressed = _suppressed_lines(source)
    return sorted(v for v in visitor.found if v.line not in suppressed)


def _suppressed_lines(source: str) -> set[int]:
    """Lines whose comment token, not a string, carries the reasoned suppression."""
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source, newline=None).readline))
    except (tokenize.TokenError, SyntaxError):
        return set()
    return {
        tok.start[0]
        for tok in tokens
        if tok.type == tokenize.COMMENT and _SUPPRESSION.search(tok.string)
    }
