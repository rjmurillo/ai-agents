#!/usr/bin/env python3
"""Gate: subprocess calls with text-mode UTF-8 must pair errors="replace".

A ``subprocess.run`` (or any ``subprocess.*`` call) that sets both
``encoding="utf-8"`` (case-insensitive, common aliases accepted) and
text-capturing mode (``text=True``, ``capture_output=True``, or decoded
``stdout=PIPE`` / ``stderr=PIPE`` captures) must also pass
``errors="replace"``.

Without ``errors="replace"``, a child process that emits bytes invalid for
UTF-8 raises ``UnicodeDecodeError`` on the calling side. On Windows CI
runners, ``git`` and ``gh`` can emit such bytes in branch names, commit
messages, or file-system paths. The decode fails before the caller can
report the real assertion, hiding the underlying failure. See issue #4261.

Canonical house pattern (in ``scripts/ci/verify_code_env.py``):

    subprocess.run(
        argv,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

What this scanner checks:
    A call is flagged when ALL of these hold:
    1. It reaches a subprocess text-capturing entry point (``subprocess.run``,
       ``subprocess.check_output``, ``subprocess.Popen``,
       ``subprocess.check_call``).
    2. It has a literal ``encoding=`` keyword whose value is a UTF-8 alias
       (``"utf-8"``, ``"utf8"``, ``"UTF-8"``, ``"UTF8"``, ``"utf_8"``).
    3. The call enables text mode: ``text=True`` or ``capture_output=True``
       are present as literal ``True``-valued keywords, or the call captures
       decoded ``stdout=PIPE`` / ``stderr=PIPE`` output, or the entry point
       decodes unconditionally (``check_output``).
    4. No ``errors=`` keyword is present.

Deliberate over-approximation:
    When a call site uses ``**kwargs``, we cannot know whether ``errors`` was
    supplied by the caller. Rather than silently wave it through, we flag the
    site. The author must either add ``errors="replace"`` or restructure to
    avoid the splat. One extra keyword in the rare-but-valid call is worth
    never missing a decode on the common violating call.

Exits (ADR-035):
    0 - No violations found.
    1 - One or more violations detected.
    2 - Configuration error (invalid repository root).
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

_UTF8_ALIASES: frozenset[str] = frozenset({"utf-8", "utf8", "utf_8", "UTF-8", "UTF8", "UTF_8"})

# subprocess entry points that accept keyword arguments
_TEXT_CAPTURING_CALLS: frozenset[str] = frozenset({"run", "Popen", "check_call"})

# Entry points that unconditionally return decoded text (no text= needed)
_UNCONDITIONAL_DECODE_CALLS: frozenset[str] = frozenset({"check_output", "getoutput"})

_ALL_SUBPROCESS_CALLS: frozenset[str] = _TEXT_CAPTURING_CALLS | _UNCONDITIONAL_DECODE_CALLS

_SKIP_DIRS: frozenset[str] = frozenset(
    {".venv", "venv", ".git", "__pycache__", "node_modules", ".mypy_cache", ".ruff_cache"}
)


def _keyword_value(call: ast.Call, name: str) -> ast.expr | None:
    """Return the value node for the first keyword matching ``name``, or None."""
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return None


def _has_keyword(call: ast.Call, name: str) -> bool:
    return any(kw.arg == name for kw in call.keywords)


def _has_splat(call: ast.Call) -> bool:
    """True when the call has a ``**kwargs`` expansion."""
    return any(kw.arg is None for kw in call.keywords)


def _is_true_literal(node: ast.expr | None) -> bool:
    if node is None:
        return False
    return isinstance(node, ast.Constant) and node.value is True


def _is_utf8_literal(node: ast.expr | None) -> bool:
    if node is None:
        return False
    return isinstance(node, ast.Constant) and node.value in _UTF8_ALIASES


def _subprocess_alias_sets(
    tree: ast.AST,
) -> tuple[frozenset[str], dict[str, str], frozenset[str]]:
    """Return ordered top-level aliases that resolve to subprocess."""
    module_aliases = {"subprocess"}
    callable_aliases: dict[str, str] = {}
    pipe_aliases: set[str] = set()

    if not isinstance(tree, ast.Module):
        return frozenset(module_aliases), callable_aliases, frozenset(pipe_aliases)

    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                bound_name = alias.asname or alias.name
                _clear_alias_binding(
                    bound_name,
                    module_aliases,
                    callable_aliases,
                    pipe_aliases,
                )
                if alias.name == "subprocess":
                    module_aliases.add(bound_name)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "*":
                    if node.module == "subprocess":
                        callable_aliases.update({name: name for name in _ALL_SUBPROCESS_CALLS})
                        pipe_aliases.add("PIPE")
                    continue
                bound_name = alias.asname or alias.name
                _clear_alias_binding(
                    bound_name,
                    module_aliases,
                    callable_aliases,
                    pipe_aliases,
                )
                if node.module != "subprocess":
                    continue
                if alias.name in _ALL_SUBPROCESS_CALLS:
                    callable_aliases[bound_name] = alias.name
                elif alias.name == "PIPE":
                    pipe_aliases.add(bound_name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            _clear_alias_binding(node.name, module_aliases, callable_aliases, pipe_aliases)
        elif isinstance(node, ast.Assign):
            resolved_module = _is_subprocess_module_alias(
                node.value,
                frozenset(module_aliases),
            )
            resolved_callable = _subprocess_callable_name(
                node.value,
                frozenset(module_aliases),
                dict(callable_aliases),
            )
            resolved_pipe = _is_pipe_capture_target(
                node.value,
                frozenset(module_aliases),
                frozenset(pipe_aliases),
            )
            for target in node.targets:
                if not isinstance(target, ast.Name):
                    continue
                _clear_alias_binding(
                    target.id,
                    module_aliases,
                    callable_aliases,
                    pipe_aliases,
                )
                if resolved_module:
                    module_aliases.add(target.id)
                elif resolved_callable is not None:
                    callable_aliases[target.id] = resolved_callable
                elif resolved_pipe:
                    pipe_aliases.add(target.id)
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            if not isinstance(node.target, ast.Name):
                continue
            resolved_module = _is_subprocess_module_alias(
                node.value,
                frozenset(module_aliases),
            )
            resolved_callable = _subprocess_callable_name(
                node.value,
                frozenset(module_aliases),
                dict(callable_aliases),
            )
            resolved_pipe = _is_pipe_capture_target(
                node.value,
                frozenset(module_aliases),
                frozenset(pipe_aliases),
            )
            _clear_alias_binding(
                node.target.id,
                module_aliases,
                callable_aliases,
                pipe_aliases,
            )
            if resolved_module:
                module_aliases.add(node.target.id)
            elif resolved_callable is not None:
                callable_aliases[node.target.id] = resolved_callable
            elif resolved_pipe:
                pipe_aliases.add(node.target.id)
        elif isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
            _clear_alias_binding(
                node.target.id,
                module_aliases,
                callable_aliases,
                pipe_aliases,
            )
        elif isinstance(node, ast.Delete):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    _clear_alias_binding(
                        target.id,
                        module_aliases,
                        callable_aliases,
                        pipe_aliases,
                    )

    return (
        frozenset(module_aliases),
        callable_aliases,
        frozenset(pipe_aliases),
    )


def _is_subprocess_module_alias(
    node: ast.expr | None,
    module_aliases: frozenset[str],
) -> bool:
    """Return True when *node* resolves to the subprocess module."""
    return isinstance(node, ast.Name) and node.id in module_aliases


def _clear_alias_binding(
    name: str,
    module_aliases: set[str],
    callable_aliases: dict[str, str],
    pipe_aliases: set[str],
) -> None:
    """Remove any alias binding currently attached to *name*."""
    module_aliases.discard(name)
    callable_aliases.pop(name, None)
    pipe_aliases.discard(name)


def _is_pipe_capture_target(
    node: ast.expr | None,
    module_aliases: frozenset[str],
    pipe_aliases: frozenset[str],
) -> bool:
    """Return True when *node* resolves to subprocess.PIPE."""
    if node is None:
        return False
    if isinstance(node, ast.Name):
        return node.id in pipe_aliases
    return (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id in module_aliases
        and node.attr == "PIPE"
    )


def _subprocess_call_name(
    node: ast.Call,
    module_aliases: frozenset[str],
    callable_aliases: dict[str, str],
) -> str | None:
    """Return the canonical subprocess function name, or None."""
    return _subprocess_callable_name(node.func, module_aliases, callable_aliases)


def _subprocess_callable_name(
    node: ast.expr,
    module_aliases: frozenset[str],
    callable_aliases: dict[str, str],
) -> str | None:
    """Return the canonical subprocess callable for *node*, or None."""
    func = node
    # subprocess.run(...)
    if (
        isinstance(func, ast.Attribute)
        and isinstance(func.value, ast.Name)
        and func.value.id in module_aliases
        and func.attr in _ALL_SUBPROCESS_CALLS
    ):
        return func.attr
    # from subprocess import run; run(...)
    if isinstance(func, ast.Name) and func.id in callable_aliases:
        return callable_aliases[func.id]
    return None


def _is_flagged(
    call: ast.Call,
    module_aliases: frozenset[str],
    callable_aliases: dict[str, str],
    pipe_aliases: frozenset[str],
) -> bool:
    """Return True when this call violates the errors="replace" convention.

    A call is flagged when it reaches a subprocess text entry point, pins
    UTF-8 as the codec, captures decoded text, and omits ``errors=``.
    """
    name = _subprocess_call_name(call, module_aliases, callable_aliases)
    if name is None:
        return False

    encoding_node = _keyword_value(call, "encoding")
    if not _is_utf8_literal(encoding_node):
        # No explicit UTF-8 pin: not in scope for this checker.
        return False

    # If errors= is already present, the call is compliant.
    if _has_keyword(call, "errors"):
        return False

    # A **kwargs splat may carry errors=, text=, capture_output=, or PIPE-based
    # captures. We cannot verify any of those statically, so fail closed.
    if _has_splat(call):
        return True

    # Verify text mode is enabled (or the call decodes unconditionally).
    unconditional = name in _UNCONDITIONAL_DECODE_CALLS
    pipe_capture = _is_pipe_capture_target(
        _keyword_value(call, "stdout"), module_aliases, pipe_aliases
    ) or _is_pipe_capture_target(
        _keyword_value(call, "stderr"), module_aliases, pipe_aliases
    )
    text_enabled = (
        _is_true_literal(_keyword_value(call, "text"))
        or _is_true_literal(_keyword_value(call, "capture_output"))
        or pipe_capture
    )
    if not unconditional and not text_enabled:
        # Binary mode with an explicit encoding is unusual but not our concern.
        return False

    return True


_SUPPRESSION_COMMENT = "# subprocess-encoding: strict-ok"


def find_violations(source: str, filename: str = "<string>") -> list[int]:
    """Return line numbers of flagged calls in *source*.

    A call on a line that ends with ``# subprocess-encoding: strict-ok`` is
    suppressed. Use this only when strict decoding is intentional and
    documented (for example, when the stream is guaranteed valid UTF-8 and a
    decode failure should propagate as an error rather than silently produce
    replacement characters).
    """
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError:
        return []

    source_lines = source.splitlines()
    module_aliases, callable_aliases, pipe_aliases = _subprocess_alias_sets(tree)

    def _suppressed(lineno: int) -> bool:
        if lineno < 1 or lineno > len(source_lines):
            return False
        return _SUPPRESSION_COMMENT in source_lines[lineno - 1]

    return sorted(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and _is_flagged(node, module_aliases, callable_aliases, pipe_aliases)
        and not _suppressed(node.lineno)
    )


def _is_scannable_source(repo_root: Path, path: Path) -> bool:
    """Return True when ``path`` is a safe Python file inside ``repo_root``."""
    try:
        relative = path.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return False
    return (
        path.is_file()
        and path.suffix == ".py"
        and not any(part in _SKIP_DIRS for part in relative.parts)
    )


def _collect_sources(repo_root: Path, explicit_paths: list[Path] | None = None) -> list[Path]:
    """Return Python sources to scan."""
    if explicit_paths is not None:
        return sorted(path for path in explicit_paths if _is_scannable_source(repo_root, path))

    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), "ls-files", "scripts/*.py", "scripts/**/*.py"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=15,
        )
        if completed.returncode == 0:
            rels = [line for line in completed.stdout.splitlines() if line.strip()]
            return [repo_root / r for r in rels if _is_scannable_source(repo_root, repo_root / r)]
    except (OSError, subprocess.SubprocessError):
        pass
    # Fallback: walk the tree
    found: list[Path] = []
    for path in (repo_root / "scripts").rglob("*.py"):
        if any(part in _SKIP_DIRS for part in path.relative_to(repo_root).parts):
            continue
        found.append(path)
    return sorted(found)


def find_all_violations(
    repo_root: Path, explicit_paths: list[Path] | None = None
) -> list[tuple[Path, int]]:
    """Return ``(path, lineno)`` pairs for every flagged call site."""
    results: list[tuple[Path, int]] = []
    for path in _collect_sources(repo_root, explicit_paths):
        if not path.is_file():
            continue
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno in find_violations(source, str(path)):
            results.append((path, lineno))
    return results


def validate_subprocess_encoding(
    repo_root: Path, explicit_paths: list[Path] | None = None
) -> bool:
    """Return True when no violation is found.

    Entry point matching the ``validate_*(repo_root) -> bool`` contract used
    by ``pre_pr_sequence.py``.
    """
    violations = find_all_violations(repo_root, explicit_paths)
    if not violations:
        return True
    count = len(violations)
    print(
        f"[FAIL] {count} subprocess call(s) pin UTF-8 encoding without errors=\"replace\":",
        file=sys.stderr,
    )
    for path, lineno in violations:
        rel = path.relative_to(repo_root) if path.is_relative_to(repo_root) else path
        print(f"  {rel}:{lineno}", file=sys.stderr)
    print(
        "\nFix: add errors=\"replace\" to each flagged call.",
        file=sys.stderr,
    )
    print(
        "Reason: a child process on Windows can emit bytes invalid for UTF-8.",
        file=sys.stderr,
    )
    print(
        "Without errors=\"replace\", the decode raises before the caller can report "
        "the real failure.",
        file=sys.stderr,
    )
    return False


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns an ADR-035 exit code."""
    args = argv if argv is not None else sys.argv[1:]
    repo_root = Path(__file__).resolve().parents[2]
    explicit_paths: list[Path] | None = None
    if len(args) == 1:
        single_arg = Path(args[0]).resolve()
        if single_arg.is_dir():
            repo_root = single_arg
        elif single_arg.suffix == ".py":
            explicit_paths = [single_arg]
        else:
            repo_root = single_arg
    elif args:
        explicit_paths = [Path(arg) if Path(arg).is_absolute() else repo_root / arg for arg in args]
    if not repo_root.is_dir():
        print(f"[FAIL] Invalid repository root: {repo_root}", file=sys.stderr)
        return 2
    return 0 if validate_subprocess_encoding(repo_root, explicit_paths) else 1


if __name__ == "__main__":
    raise SystemExit(main())
