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
    no module ``pytestmark`` that skips. Windows without Developer Mode raises ``OSError``,
    so the test errors instead of skipping.

These are the three mechanical rules behind 86 of the 166 Cursor Bugbot
"learned rule" findings on pull requests #6110 to #7380 (evals/third-party-review-gap).

Scope: with ``--base-ref``, only lines the branch's commits add over that
ref are reported (``base...HEAD``, read from HEAD), so existing code does not
block. A line moved unchanged within a file is not new and is not reported.
Generated mirror trees (``MIRROR_PREFIXES``) are skipped in that mode, because
``build_all.py`` copies them from ``src/claude/`` and ``scripts/``. Generated
copies outside that list, such as ``src/claude/lib/`` and the rendered hook
launchers, are still checked, so a violation in their source can be reported
more than once. With file arguments, every line in those files is reported. A
call carrying ``**kwargs`` is skipped: its encoding cannot be read statically.

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

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent
# checks_common imports ``scripts.cli_exec`` by absolute name, so the repository
# root must be importable when this runs as a plain script, as in the sibling
# added-lines gates (check_measurement_anchoring.py).
for _entry in (_REPO_ROOT, _SCRIPT_DIR):
    if str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))

import checks_common  # noqa: E402
import citation_head_state  # noqa: E402

SUPPRESS = "# io-portability: ignore"
# A suppression must say why: the marker followed by at least one word.
_SUPPRESSION = re.compile(re.escape(SUPPRESS) + r"\s+\S")
_SUBPROCESS_CALLS = frozenset({"run", "Popen", "check_output", "check_call", "call"})
_TEXT_FLAGS = ("text", "universal_newlines")
_SYMLINK_CATCHES = frozenset({"OSError", "NotImplementedError", "Exception", "BaseException"})
# Generated Python trees: every output prefix in
# scripts/validation/git_hook_policy.py:_GENERATED_MIRRORS that can hold a .py
# file, plus src/hermes/ (ADR-115 Decision 6 packs). src/claude/skills/ is
# deliberately absent although that map lists it: since ADR-119 it is the
# canonical, hand-maintained skill source, so its scripts are checked.
# test_mirror_prefixes_match_the_generated_mirror_map pins this.
MIRROR_PREFIXES: tuple[str, ...] = (
    "src/copilot-cli/skills/",
    "src/copilot-cli/lib/",
    "src/copilot-cli/hooks/",
    "src/codex/skills/",
    "src/codex/lib/",
    "src/cursor/skills/",
    "src/cursor/lib/",
    "src/muse/skills/",
    "src/muse/lib/",
    "src/hermes/",
)


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
    if not is_attr and name == "open" and (call.args or _kwarg(call, "file") is not None):
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


def _is_skip_mark(expr: ast.expr, skip_marks: frozenset[str]) -> bool:
    """A mark whose callable is a skip, or a module alias of one.

    Only the callable's own name counts (``pytest.mark.skipif``, ``unittest.skipIf``,
    ``skip_on_windows``). Arguments do not: ``usefixtures('skip_cache')`` does not
    skip. A list or tuple, as ``pytestmark`` allows, guards when any element does.
    """
    if isinstance(expr, ast.List | ast.Tuple):
        return any(_is_skip_mark(e, skip_marks) for e in expr.elts)
    target = expr.func if isinstance(expr, ast.Call) else expr
    if isinstance(target, ast.Name):
        return target.id in skip_marks or "skip" in target.id.lower()
    return isinstance(target, ast.Attribute) and "skip" in target.attr.lower()


def _has_skipif(decorators: Iterable[ast.expr], skip_marks: frozenset[str]) -> bool:
    """A decorator that is a skip mark, directly or through a module-level alias."""
    return any(_is_skip_mark(d, skip_marks) for d in decorators)


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
        self._module_skip = any(
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets)
            and _is_skip_mark(node.value, self._skip_marks)
            for node in tree.body
        )
        self._guards: list[bool] = []  # one entry per enclosing scope or try that guards
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
        guarded = "skip" in node.name.lower() or _has_skipif(node.decorator_list, self._skip_marks)
        self._guards.append(guarded)
        self.generic_visit(node)
        self._guards.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._scope(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._scope(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._scope(node)

    def _try(self, node: ast.Try | ast.TryStar) -> None:
        """Only the ``try`` body is guarded; handlers, ``else`` and ``finally`` are not."""
        self._guards.append(any(_catches_symlink_failure(h) for h in node.handlers))
        for statement in node.body:
            self.visit(statement)
        self._guards.pop()
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
            if not (self._module_skip or any(self._guards)):
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
    # Match the AST's line model: CRLF, a lone CR, and LF each end a line, while
    # form feed and U+2028 do not. splitlines() would split on those too and
    # shift every later line number. Known limit: git numbers diff lines by LF
    # only, so in a file with lone-CR line ends added-line matching can miss.
    lines = re.split(r"\r\n|\r|\n", source)
    return sorted(
        v
        for v in visitor.found
        if not (0 < v.line <= len(lines) and _SUPPRESSION.search(lines[v.line - 1]))
    )


def added_line_numbers(
    repo_root: Path, base_ref: str, head_ref: str = "HEAD"
) -> dict[str, set[int]]:
    """Line numbers each path adds between ``base_ref`` and ``head_ref``, as the gate reads them.

    The one parser the gate uses (``citation_head_state._added_lines_since_base``),
    so an eval that replays a past commit pair measures the shipped behavior.
    """
    added = citation_head_state._added_lines_since_base(repo_root, base_ref, head_ref)
    if added is None:
        raise ValueError(f"git diff {base_ref}...{head_ref} failed")
    return {path: {number for number, _text in lines} for path, lines in added.items()}


def _git(repo_root: Path, args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    """Run git; a timeout or a missing binary is a configuration error (exit 2), not a finding."""
    try:
        return subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=60,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        raise ValueError(f"git {args[0]} could not run: {exc}") from exc


def is_skipped_path(path: str) -> bool:
    """Generated mirrors and fixture trees are not authored code under review."""
    return path.startswith(MIRROR_PREFIXES) or "fixtures" in Path(path).parts


def scan_diff(base_ref: str, repo_root: Path = Path(".")) -> tuple[list[Violation], int]:
    """Violations on lines this branch adds over ``base_ref``, and Python files examined.

    Judges what a push sends: the committed ``base_ref...HEAD`` diff, with
    sources read from HEAD, so an uncommitted edit neither hides nor adds a
    finding. The added lines come from ``citation_head_state._added_lines_since_base``,
    the parser the other added-lines gates share, which pins prefixes, colour,
    rename detection and diff drivers so a contributor's git config cannot empty
    the diff, and keeps renamed, copied and type-changed files.
    """
    changed = {
        path: lines
        for path, lines in added_line_numbers(repo_root, base_ref).items()
        if path.endswith(".py") and not is_skipped_path(path)
    }
    found: list[Violation] = []
    for path, lines in sorted(changed.items()):
        shown = _git(repo_root, ["show", f"HEAD:{path}"])
        if shown.returncode != 0:
            raise ValueError(f"cannot read {path} at HEAD: {shown.stderr.strip()}")
        found.extend(
            v for v in scan_source(path, shown.stdout) if any(v.spans(line) for line in lines)
        )
    return found, len(changed)


def repository_root() -> Path:
    """The working tree's top level, so a run from a subdirectory sees the whole diff."""
    top = _git(Path("."), ["rev-parse", "--show-toplevel"])
    if top.returncode != 0:
        raise ValueError(f"not inside a git repository: {top.stderr.strip()}")
    return Path(top.stdout.strip())


def validate_io_portability(repo_root: Path) -> bool:
    """Pre-PR gate entry point: print findings, return True when added lines are clean.

    Resolving no base ref prints ``[SKIP]`` and passes, the same contract as the
    other added-lines gates: with no base there is no added range to judge.
    """
    base_ref = checks_common._resolve_default_base_ref(repo_root)
    if base_ref is None:
        print("[SKIP] io-portability: no base ref resolved; nothing to diff against")
        return True
    try:
        found, examined = scan_diff(base_ref, repo_root)
    except ValueError as exc:
        print(f"[io-portability] {exc}", file=sys.stderr)
        return False
    for violation in found:
        print(violation.render(), file=sys.stderr)
    status = "FAIL" if found else "OK"
    print(
        f"[{status}] io-portability: {len(found)} violation(s) on added lines "
        f"in {examined} changed Python file(s) vs {base_ref}"
    )
    if found:
        print(
            "  Fix: pass encoding='utf-8' (and errors='replace' for subprocess capture), "
            "or create test symlinks through a helper that skips on OSError.",
            file=sys.stderr,
        )
    return not found


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
        if args.base_ref:
            found, examined = scan_diff(args.base_ref, repository_root())
        else:
            found, examined = scan_files(args.files)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for violation in found:
        print(violation.render())
    print(f"{len(found)} io-portability violation(s) in {examined} file(s) examined")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
