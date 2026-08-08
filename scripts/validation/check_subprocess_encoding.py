#!/usr/bin/env python3
"""Require ``errors="replace"`` for UTF-8 subprocess text capture.

The scanner tracks subprocess imports and aliases through lexical scopes.
It flags literal UTF-8 calls that decode through text mode, capture flags,
PIPE streams, or unconditional decode entry points without replacement
error handling. Unknown ``**kwargs`` remain fail-closed. See issue #4261.

Canonical pattern:
``subprocess.run(argv, text=True, encoding="utf-8", errors="replace")``.
Exits follow ADR-035: 0 clean, 1 violations, 2 configuration error.
"""

from __future__ import annotations

import ast
import os
import stat
import subprocess
import sys
from pathlib import Path

_UTF8_ALIASES: frozenset[str] = frozenset({"utf-8", "utf8", "utf_8", "UTF-8", "UTF8", "UTF_8"})

# subprocess entry points that accept keyword arguments
_TEXT_CAPTURING_CALLS: frozenset[str] = frozenset({"run", "Popen", "check_call"})

# Entry points that unconditionally return decoded text (no text= needed)
_UNCONDITIONAL_DECODE_CALLS: frozenset[str] = frozenset({"check_output", "getoutput"})

_ALL_SUBPROCESS_CALLS: frozenset[str] = _TEXT_CAPTURING_CALLS | _UNCONDITIONAL_DECODE_CALLS


def _keyword_value(call: ast.Call, name: str) -> ast.expr | None:
    """Return the value node for the first keyword matching ``name``, or None."""
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return None


def _is_true_literal(node: ast.expr | None) -> bool:
    if node is None:
        return False
    return isinstance(node, ast.Constant) and node.value is True


def _is_utf8_literal(node: ast.expr | None) -> bool:
    if node is None:
        return False
    return isinstance(node, ast.Constant) and node.value in _UTF8_ALIASES


def _is_subprocess_pipe(
    node: ast.expr | None,
    module_aliases: set[str],
    pipe_aliases: set[str],
) -> bool:
    """Return whether *node* resolves to ``subprocess.PIPE``."""
    module_pipe = (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id in module_aliases
        and node.attr == "PIPE"
    )
    imported_pipe = isinstance(node, ast.Name) and node.id in pipe_aliases
    return module_pipe or imported_pipe


def _subprocess_call_name(
    node: ast.Call,
    module_aliases: set[str],
    callable_aliases: dict[str, str],
) -> str | None:
    """Return the bare function name for a ``subprocess.*`` call, or None."""
    func = node.func
    # subprocess.run(...) or an imported module alias such as sp.run(...)
    if (
        isinstance(func, ast.Attribute)
        and isinstance(func.value, ast.Name)
        and func.value.id in module_aliases
        and func.attr in _ALL_SUBPROCESS_CALLS
    ):
        return func.attr
    # from subprocess import run; run(...), imported aliases, or direct rebinding.
    if isinstance(func, ast.Name):
        return callable_aliases.get(func.id)
    return None


def _assignment_pairs(node: ast.AST) -> list[tuple[str, ast.expr]]:
    """Return simple target names paired with their assigned value nodes."""
    if isinstance(node, ast.Assign):
        targets = node.targets
        value = node.value
    elif isinstance(node, ast.AnnAssign) and node.value is not None:
        targets = [node.target]
        value = node.value
    else:
        return []

    def _pairs(target: ast.expr, assigned: ast.expr) -> list[tuple[str, ast.expr]]:
        if isinstance(target, ast.Name):
            return [(target.id, assigned)]
        if (
            isinstance(target, (ast.Tuple, ast.List))
            and isinstance(assigned, (ast.Tuple, ast.List))
            and len(target.elts) == len(assigned.elts)
        ):
            return [
                pair
                for target_item, value_item in zip(target.elts, assigned.elts, strict=True)
                for pair in _pairs(target_item, value_item)
            ]
        return []

    return [pair for target in targets for pair in _pairs(target, value)]


def _resolve_value_binding(
    value: ast.expr,
    module_aliases: set[str],
    callable_aliases: dict[str, str],
    pipe_aliases: set[str],
) -> tuple[str, str] | None:
    """Resolve a value to one subprocess binding kind and canonical name."""
    if (
        isinstance(value, ast.Attribute)
        and isinstance(value.value, ast.Name)
        and value.value.id in module_aliases
    ):
        if value.attr in _ALL_SUBPROCESS_CALLS:
            return "callable", value.attr
        if value.attr == "PIPE":
            return "pipe", "PIPE"
    if isinstance(value, ast.Name) and value.id in callable_aliases:
        return "callable", callable_aliases[value.id]
    if isinstance(value, ast.Name) and value.id in pipe_aliases:
        return "pipe", "PIPE"
    if isinstance(value, ast.Name) and value.id in module_aliases:
        return "module", "subprocess"
    return None


def _is_flagged(
    call: ast.Call,
    module_aliases: set[str],
    callable_aliases: dict[str, str],
    pipe_aliases: set[str],
) -> bool:
    """Return True when this call violates the errors="replace" convention.

    A call is flagged when it reaches a subprocess text entry point, pins
    UTF-8 as the codec, enables text mode, and omits ``errors=``.
    """
    name = _subprocess_call_name(call, module_aliases, callable_aliases)
    if name is None:
        return False

    encoding_node = _keyword_value(call, "encoding")
    if not _is_utf8_literal(encoding_node):
        # No explicit UTF-8 pin: not in scope for this checker.
        return False

    # Verify text mode is enabled (or the call decodes unconditionally).
    unconditional = name in _UNCONDITIONAL_DECODE_CALLS
    text_enabled = (
        _is_true_literal(_keyword_value(call, "text"))
        or _is_true_literal(_keyword_value(call, "capture_output"))
        or _is_subprocess_pipe(_keyword_value(call, "stdout"), module_aliases, pipe_aliases)
        or _is_subprocess_pipe(_keyword_value(call, "stderr"), module_aliases, pipe_aliases)
    )
    if not unconditional and not text_enabled:
        # Binary mode with an explicit encoding is unusual but not our concern.
        return False

    # Only replacement decoding satisfies the convention. Strict decoding must
    # use the line-scoped suppression marker when failure is intentional.
    errors_node = _keyword_value(call, "errors")
    if isinstance(errors_node, ast.Constant) and errors_node.value == "replace":
        return False

    # A **kwargs splat may carry errors= but we cannot verify; flag conservatively.
    # This is the deliberate over-approximation described in the module docstring.
    return True


class _SubprocessCallVisitor(ast.NodeVisitor):
    """Find violations while tracking bindings in statement and scope order."""

    def __init__(self) -> None:
        self.module_aliases: set[str] = set()
        self.callable_aliases: dict[str, str] = {}
        self.pipe_aliases: set[str] = set()
        self.flagged_lines: list[int] = []

    def _clear(self, name: str) -> None:
        self.module_aliases.discard(name)
        self.callable_aliases.pop(name, None)
        self.pipe_aliases.discard(name)

    def _bind(self, name: str, resolved: tuple[str, str] | None) -> None:
        self._clear(name)
        if resolved is None:
            return
        kind, canonical = resolved
        if kind == "module":
            self.module_aliases.add(name)
        elif kind == "callable":
            self.callable_aliases[name] = canonical
        else:
            self.pipe_aliases.add(name)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            bound = alias.asname or alias.name.split(".", maxsplit=1)[0]
            resolved = ("module", "subprocess") if alias.name == "subprocess" else None
            self._bind(bound, resolved)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            bound = alias.asname or alias.name
            resolved: tuple[str, str] | None = None
            if node.module == "subprocess":
                if alias.name in _ALL_SUBPROCESS_CALLS:
                    resolved = ("callable", alias.name)
                elif alias.name == "PIPE":
                    resolved = ("pipe", "PIPE")
            self._bind(bound, resolved)

    def _visit_assignment(self, node: ast.AST, value: ast.expr) -> None:
        self.visit(value)
        resolved = [
            (
                name,
                _resolve_value_binding(
                    assigned,
                    self.module_aliases,
                    self.callable_aliases,
                    self.pipe_aliases,
                ),
            )
            for name, assigned in _assignment_pairs(node)
        ]
        for name, binding in resolved:
            self._bind(name, binding)

    def visit_Assign(self, node: ast.Assign) -> None:
        self._visit_assignment(node, node.value)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            self._visit_assignment(node, node.value)
        elif isinstance(node.target, ast.Name):
            self._clear(node.target.id)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self.visit(node.value)
        if isinstance(node.target, ast.Name):
            self._clear(node.target.id)

    def _visit_scope(self, body: list[ast.stmt], shadowed: set[str]) -> None:
        saved = (
            self.module_aliases.copy(),
            self.callable_aliases.copy(),
            self.pipe_aliases.copy(),
        )
        for name in shadowed:
            self._clear(name)
        for statement in body:
            self.visit(statement)
        self.module_aliases, self.callable_aliases, self.pipe_aliases = saved

    @staticmethod
    def _argument_names(arguments: ast.arguments) -> set[str]:
        args = arguments.posonlyargs + arguments.args + arguments.kwonlyargs
        names = {arg.arg for arg in args}
        if arguments.vararg is not None:
            names.add(arguments.vararg.arg)
        if arguments.kwarg is not None:
            names.add(arguments.kwarg.arg)
        return names

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        positional = node.args.posonlyargs + node.args.args
        default_pairs = [
            *zip(
                positional[len(positional) - len(node.args.defaults) :],
                node.args.defaults,
                strict=True,
            ),
            *(
                (argument, value)
                for argument, value in zip(
                    node.args.kwonlyargs,
                    node.args.kw_defaults,
                    strict=True,
                )
                if value is not None
            ),
        ]
        defaults = [value for _, value in default_pairs]
        for expression in [*node.decorator_list, *defaults]:
            self.visit(expression)
        default_bindings = {
            argument.arg: _resolve_value_binding(
                value,
                self.module_aliases,
                self.callable_aliases,
                self.pipe_aliases,
            )
            for argument, value in default_pairs
        }
        saved = (
            self.module_aliases.copy(),
            self.callable_aliases.copy(),
            self.pipe_aliases.copy(),
        )
        for name in self._argument_names(node.args):
            self._clear(name)
        for name, binding in default_bindings.items():
            self._bind(name, binding)
        for statement in node.body:
            self.visit(statement)
        self.module_aliases, self.callable_aliases, self.pipe_aliases = saved
        self._clear(node.name)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for expression in [*node.decorator_list, *node.bases, *node.keywords]:
            self.visit(expression)
        self._visit_scope(node.body, set())
        self._clear(node.name)

    def visit_Call(self, node: ast.Call) -> None:
        if _is_flagged(
            node,
            self.module_aliases,
            self.callable_aliases,
            self.pipe_aliases,
        ):
            self.flagged_lines.append(node.lineno)
        self.generic_visit(node)


_SUPPRESSION_COMMENT = "# subprocess-encoding: strict-ok"


class ScanError(RuntimeError):
    """Raised when the gate cannot inspect its declared source corpus."""


def _clean_git_env() -> dict[str, str]:
    """Return the process environment without ambient Git repository pointers."""
    return {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}


def find_violations(source: str, filename: str = "<string>") -> list[int]:
    """Return line numbers of flagged calls in *source*.

    A call on a line that ends with ``# subprocess-encoding: strict-ok`` is
    suppressed. Use this only when strict decoding is intentional and
    documented (for example, when the stream is guaranteed valid UTF-8 and a
    decode failure should propagate as an error rather than silently produce
    replacement characters).
    """
    tree = ast.parse(source, filename=filename)
    visitor = _SubprocessCallVisitor()
    visitor.visit(tree)

    source_lines = source.splitlines()

    def _suppressed(lineno: int) -> bool:
        if lineno < 1 or lineno > len(source_lines):
            return False
        return _SUPPRESSION_COMMENT in source_lines[lineno - 1]

    return sorted(lineno for lineno in visitor.flagged_lines if not _suppressed(lineno))


def _collect_sources(repo_root: Path) -> list[Path]:
    """Return tracked Python files under ``scripts/`` that are not in cache dirs."""
    try:
        completed = subprocess.run(
            [
                "git",
                "-C",
                str(repo_root),
                "ls-files",
                "-z",
                "scripts/*.py",
                "scripts/**/*.py",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            env=_clean_git_env(),
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ScanError(f"git could not list tracked scripts: {exc}") from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or f"git exited {completed.returncode}"
        raise ScanError(f"git could not list tracked scripts: {detail}")

    rels = [entry for entry in completed.stdout.split("\0") if entry]
    sources = [repo_root / rel for rel in rels if rel.endswith(".py")]
    if not sources:
        raise ScanError("git reported zero tracked Python files under scripts/")
    return sources


def _scan_all(repo_root: Path) -> tuple[list[tuple[Path, int]], int]:
    """Return violations and the number of tracked source files examined."""
    sources = _collect_sources(repo_root)
    results: list[tuple[Path, int]] = []
    for path in sources:
        try:
            mode = path.stat(follow_symlinks=False).st_mode
        except OSError as exc:
            raise ScanError(f"tracked source is missing: {path}") from exc
        if not stat.S_ISREG(mode):
            raise ScanError(f"tracked source is not a regular file: {path}")
        try:
            source = path.read_text(encoding="utf-8")
            lines = find_violations(source, str(path))
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            raise ScanError(f"could not analyze tracked source {path}: {exc}") from exc
        for lineno in lines:
            results.append((path, lineno))
    return results, len(sources)


def find_all_violations(repo_root: Path) -> list[tuple[Path, int]]:
    """Return ``(path, lineno)`` pairs for every flagged call site."""
    return _scan_all(repo_root)[0]


def validate_subprocess_encoding(repo_root: Path) -> bool:
    """Return True when no violation is found.

    Entry point matching the ``validate_*(repo_root) -> bool`` contract used
    by ``pre_pr_sequence.py``.
    """
    violations, scanned_files = _scan_all(repo_root)
    if not violations:
        print(
            f"[OK] Scanned {scanned_files} tracked Python file(s) under scripts/; "
            "0 subprocess encoding violations."
        )
        return True
    count = len(violations)
    print(
        f"[FAIL] {count} subprocess call(s) in {scanned_files} tracked file(s) "
        'pin UTF-8 encoding without errors="replace":',
        file=sys.stderr,
    )
    for path, lineno in violations:
        rel = path.relative_to(repo_root) if path.is_relative_to(repo_root) else path
        print(f"  {rel}:{lineno}", file=sys.stderr)
    print(
        '\nFix: add errors="replace" to each flagged call.',
        file=sys.stderr,
    )
    print(
        "Reason: a child process on Windows can emit bytes invalid for UTF-8.",
        file=sys.stderr,
    )
    print(
        'Without errors="replace", the decode raises before the caller can report '
        "the real failure.",
        file=sys.stderr,
    )
    return False


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns an ADR-035 exit code."""
    args = argv if argv is not None else sys.argv[1:]
    repo_root = Path(args[0]).resolve() if args else Path(__file__).resolve().parents[2]
    if not repo_root.is_dir():
        print(f"[FAIL] Invalid repository root: {repo_root}", file=sys.stderr)
        return 2
    try:
        return 0 if validate_subprocess_encoding(repo_root) else 1
    except ScanError as exc:
        print(f"[FAIL] Subprocess encoding scan did not run: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
